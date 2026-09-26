#!/usr/bin/env python3
"""Generalise `backfill.py`'s per-run mechanics into a domain-agnostic
provenance-mode builder ([batch3-backfill-builder-provenance-mode]).

    provenance_builder.py --source <export.jsonl|export.csv> --out <dir>
        [--format jsonl|csv] [--source-type <label>] [--import-batch <id>]
        [--contemporaneous <dir of already-sealed capsule JSON files>]

Where `backfill.py` reads exactly one shipped shape (a tau2 results file,
per-act), this module reads an arbitrary source export -- one JSON object
per line (JSONL) or one row per line (CSV) -- and maps each row/object to a
`capsule-seal-request/v1` file carrying an AAC -05
(`draft-mih-scitt-agent-action-capsule-05` §provenancemode) top-level
`provenance_mode: {mode: "backfilled", source_ref, source_asserted_at,
import_batch, imported_at}` block. It reuses `backfill.py`'s established
conventions -- the seal-request envelope shape, whole-second-UTC RFC3339
timestamps, filesystem-safe naming -- rather than reinventing them; it does
NOT modify `backfill.py`, which remains Demo B's tau2-specific, already-
shipped path.

Digest binding (do not hash the capsule's own payload here)
-------------------------------------------------------------
Exactly like `backfill.py`: this module computes no digest of the capsule's
`payload` itself -- `capsulectl publish` (capsule-cli -> capsule-emit-go)
owns that path (SHA-256 over RFC 8785 JCS), and introducing a second one
would be a bug. `provenance_mode.source_ref`, by contrast, is a NEW,
spec-required field identifying the SOURCE ARTIFACT this record was
imported from (AAC -05 §provenancemode: "a typed digest reference ...
identifying the historical record or artifact this Capsule was imported
from") -- a genuinely different digest, over different bytes, computed for
a different purpose (cross-referencing and de-duplication against an
existing contemporaneous stream), so computing it here is not a second path
for the SAME data.

`source_ref.digest` is deliberately NOT a digest of the raw row's every
field: two captures of the same logical event -- one live (contemporaneous)
and one from a later batch export (backfilled) -- routinely differ in
transcription detail (field order, extra columns, formatting) even though
they describe the same real-world event. The digest is instead computed
over the event's minimal identity tuple, `{source_type, external_id}}` --
see `compute_source_ref`.

Known gap, same class as the one `[batch3-aac-05-backfill-provenance-mode]`
flagged (evaluation-compiler `backfill.py`, 2026-09-22): `capsule-emit-go`'s
`emit.Input` has no `ProvenanceMode`/`Chain`-at-seal-request-level field
today and `capsulectl`'s seal-request decoder rejects unknown fields
(`json.Decoder.DisallowUnknownFields()`), so a request this module writes
cannot yet be published for real via `capsulectl publish --request`. This
module emits the spec-correct TOP-LEVEL shape anyway (rather than folding
into the existing `payload.provenance` opaque dict, which the prior task
used for a narrower, tau2-only threading) because this task's own
acceptance criteria are about the BUILDER's and `capsule-engine`'s own
Python-side behaviour (dedup, checkpointing, coverage), not about
round-tripping through `capsulectl` -- and the top-level shape is what a
real capsule will actually carry once the Go-side gap (capsule-cli /
capsule-emit-go, both out of this task's repo scope) closes.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field

__all__ = [
    "SourceRecord",
    "MappedEvent",
    "RecordMapper",
    "BackfillSummary",
    "iter_jsonl",
    "iter_csv",
    "compute_source_ref",
    "build_backfill_request",
    "load_contemporaneous_index",
    "load_checkpoint",
    "save_checkpoint",
    "default_mapper",
    "run_backfill",
    "main",
]

DEFAULT_OPERATOR = "oo-backfill"
DEFAULT_DEVELOPER = "oo@provenance-builder-v1"

# Reserved source-row fields the default mapper consumes structurally;
# every other field on the row rides into `payload` verbatim.
_RESERVED_FIELDS = frozenset({"external_id", "source_type", "asserted_at", "action_id", "action_type"})


def normalize_timestamp(value: object, record_ref: object) -> str:
    """Whole-seconds UTC RFC3339 -- identical contract to `backfill.py`'s
    own `normalize_timestamp`: a missing/unparseable stamp is a hard error,
    since a fabricated timestamp would make the eventual content-addressed
    Capsule id non-reproducible."""
    if not isinstance(value, str) or not value:
        raise SystemExit(f"record {record_ref!r} has no usable asserted_at timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit(f"record {record_ref!r} has an unparseable timestamp {value!r}") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_name(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(value))


@dataclass(frozen=True)
class SourceRecord:
    """One row/object from a source export, in the export's own order --
    `position` (1-based) is that order, preserved through mapping so output
    is always appended at import position, never re-sorted."""

    raw: dict
    position: int


def iter_jsonl(path: pathlib.Path) -> Iterator[SourceRecord]:
    with path.open("r", encoding="utf-8") as fh:
        for position, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            yield SourceRecord(raw=json.loads(line), position=position)


def iter_csv(path: pathlib.Path) -> Iterator[SourceRecord]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for position, row in enumerate(reader, start=1):
            yield SourceRecord(raw=dict(row), position=position)


@dataclass(frozen=True)
class MappedEvent:
    """A source row resolved to the fields a backfilled Capsule needs."""

    external_id: str
    source_type: str
    source_asserted_at: str  # RFC3339, whole-seconds UTC
    action_id: str
    action_type: str
    operator: str
    developer: str
    payload: dict = field(default_factory=dict)


RecordMapper = Callable[[SourceRecord], MappedEvent]


def default_mapper(
    *, source_type: str, operator: str = DEFAULT_OPERATOR, developer: str = DEFAULT_DEVELOPER
) -> RecordMapper:
    """The generic mapper the CLI uses: a source row with `external_id` and
    `asserted_at` columns (any export whose rows carry those two natural
    names), everything else folded into `payload` verbatim. A caller
    embedding this module directly (rather than via the CLI) supplies its
    own `RecordMapper` instead -- this is a convenience default, not the
    only shape this module accepts."""

    def _map(record: SourceRecord) -> MappedEvent:
        raw = record.raw
        external_id = raw.get("external_id")
        if not isinstance(external_id, str) or not external_id:
            raise SystemExit(f"source record at position {record.position} has no external_id")
        asserted_at = normalize_timestamp(raw.get("asserted_at"), external_id)
        action_type = raw.get("action_type") or "fyi"
        payload = {k: v for k, v in raw.items() if k not in _RESERVED_FIELDS}
        return MappedEvent(
            external_id=external_id,
            source_type=source_type,
            source_asserted_at=asserted_at,
            action_id=raw.get("action_id") or f"urn:backfill:{source_type}:{safe_name(external_id)}",
            action_type=action_type,
            operator=operator,
            developer=developer,
            payload=payload,
        )

    return _map


def _canonical_digest(obj: Mapping[str, object]) -> str:
    """SHA-256 over sorted-key JSON -- an internal correlation digest, not a
    capsule-identity digest (see module docstring): determinism (same
    logical identity tuple -> same digest) is all this needs, not RFC 8785
    JCS rigor."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def compute_source_ref(source_type: str, external_id: str) -> dict:
    """AAC -05 §provenancemode's typed digest reference:
    `{type, digest_alg, digest}`, over the event's minimal identity tuple
    (see module docstring for why not the whole row)."""
    digest = _canonical_digest({"source_type": source_type, "external_id": external_id})
    return {"type": source_type, "digest_alg": "sha256", "digest": digest}


def build_backfill_request(
    event: MappedEvent, *, import_batch: str, imported_at: str, duplicate_of: str | None
) -> dict:
    provenance_mode = {
        "mode": "backfilled",
        "source_ref": compute_source_ref(event.source_type, event.external_id),
        "source_asserted_at": event.source_asserted_at,
        "import_batch": import_batch,
        "imported_at": imported_at,
    }
    request: dict = {
        "spec_version": "capsule-seal-request/v1",
        "capsule": {
            "ActionID": event.action_id,
            "ActionType": event.action_type,
            "Operator": event.operator,
            "Developer": event.developer,
            "Timestamp": event.source_asserted_at,
        },
        "payload": dict(event.payload),
        "provenance_mode": provenance_mode,
    }
    if duplicate_of is not None:
        # AAC -05 §provenancemode "Duplicates": chain the backfilled Capsule
        # to its contemporaneous twin; the parent's own state and status
        # govern, this record exists only to preserve the import.
        request["chain"] = {"relation": "duplicates", "parent_capsule_id": duplicate_of}
    return request


def load_contemporaneous_index(
    capsules: Iterable[Mapping[str, object]],
    *,
    source_type: str,
    external_id_of: Callable[[Mapping[str, object]], str | None],
) -> dict[str, str]:
    """Build `{source_ref_digest: capsule_id}` over an already-sealed,
    contemporaneous capsule stream, for dedup matching against backfilled
    imports of the SAME logical events. `external_id_of` is REQUIRED, no
    default -- same explicit-injection convention `backfill.py`'s own
    per-domain fields use: this module has no built-in notion of a
    contemporaneous capsule's natural external id.
    """
    index: dict[str, str] = {}
    for capsule in capsules:
        capsule_id = capsule.get("capsule_id")
        if not isinstance(capsule_id, str) or not capsule_id:
            continue
        external_id = external_id_of(capsule)
        if not external_id:
            continue
        digest = compute_source_ref(source_type, external_id)["digest"]
        index[digest] = capsule_id
    return index


def load_checkpoint(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"import_batch": None, "next_position": 1, "processed": {}}
    return json.loads(path.read_text())


def save_checkpoint(path: pathlib.Path, checkpoint: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n")


@dataclass
class BackfillSummary:
    total_source_records: int = 0
    written: int = 0
    skipped_already_imported: int = 0
    duplicates_of_contemporaneous: int = 0
    contemporaneous_total: int = 0

    def to_dict(self) -> dict:
        return {
            "total_source_records": self.total_source_records,
            "written": self.written,
            "skipped_already_imported": self.skipped_already_imported,
            "duplicates_of_contemporaneous": self.duplicates_of_contemporaneous,
            "backfilled_new_coverage": self.written - self.duplicates_of_contemporaneous,
            "contemporaneous_total": self.contemporaneous_total,
        }


def run_backfill(
    source_records: Iterable[SourceRecord],
    *,
    mapper: RecordMapper,
    out_dir: pathlib.Path,
    import_batch: str,
    imported_at: str,
    contemporaneous_index: Mapping[str, str],
    checkpoint_path: pathlib.Path,
) -> BackfillSummary:
    """Map, dedup, write, and checkpoint one import run.

    Idempotent by `source_ref` digest: a digest already present in the
    checkpoint's `processed` map is skipped -- re-running over the same (or
    an updated, superset) source export appends only genuinely new records,
    never re-writes or renumbers an already-written file (import position is
    preserved: `next_position` only ever increases). The checkpoint is
    persisted after every write, not just at the end, so an interrupted run
    resumes cleanly rather than re-processing what it already wrote.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = load_checkpoint(checkpoint_path)
    if checkpoint.get("import_batch") not in (None, import_batch):
        raise SystemExit(
            f"{checkpoint_path} was checkpointed under import_batch "
            f"{checkpoint['import_batch']!r}, not {import_batch!r} -- use a fresh checkpoint file per batch"
        )
    checkpoint["import_batch"] = import_batch
    processed: dict = checkpoint.setdefault("processed", {})
    next_position: int = checkpoint.get("next_position", 1)

    summary = BackfillSummary(contemporaneous_total=len(set(contemporaneous_index.values())))
    for record in source_records:
        summary.total_source_records += 1
        event = mapper(record)
        source_ref = compute_source_ref(event.source_type, event.external_id)
        digest = source_ref["digest"]

        if digest in processed:
            summary.skipped_already_imported += 1
            continue

        duplicate_of = contemporaneous_index.get(digest)
        request = build_backfill_request(
            event, import_batch=import_batch, imported_at=imported_at, duplicate_of=duplicate_of
        )
        filename = f"{safe_name(import_batch)}-{next_position:06d}.json"
        (out_dir / filename).write_text(json.dumps(request, indent=2) + "\n")

        processed[digest] = filename
        next_position += 1
        summary.written += 1
        if duplicate_of is not None:
            summary.duplicates_of_contemporaneous += 1

        checkpoint["next_position"] = next_position
        save_checkpoint(checkpoint_path, checkpoint)

    return summary


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, type=pathlib.Path, help="a JSONL or CSV source export")
    ap.add_argument("--format", choices=("jsonl", "csv"), default=None,
                     help="default: inferred from --source's extension")
    ap.add_argument("--out", required=True, type=pathlib.Path, help="output directory for seal-request files")
    ap.add_argument("--source-type", required=True, help="provenance_mode.source_ref.type label for this export")
    ap.add_argument("--import-batch", default=None,
                     help="opaque batch id; default the source filename stem")
    ap.add_argument("--contemporaneous", type=pathlib.Path, default=None,
                     help="a directory of already-sealed capsule JSON files to dedup against by "
                          "their own payload.external_id field")
    args = ap.parse_args(argv)

    fmt = args.format or ("csv" if args.source.suffix.lower() == ".csv" else "jsonl")
    reader = iter_csv if fmt == "csv" else iter_jsonl
    import_batch = args.import_batch or args.source.stem
    imported_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

    contemporaneous_index: dict[str, str] = {}
    if args.contemporaneous is not None:
        capsules = [json.loads(p.read_text()) for p in sorted(args.contemporaneous.glob("*.json"))]
        contemporaneous_index = load_contemporaneous_index(
            capsules, source_type=args.source_type,
            external_id_of=lambda c: (c.get("payload") or {}).get("external_id"),
        )

    mapper = default_mapper(source_type=args.source_type)
    checkpoint_path = args.out / f".checkpoint-{safe_name(import_batch)}.json"
    summary = run_backfill(
        reader(args.source), mapper=mapper, out_dir=args.out, import_batch=import_batch,
        imported_at=imported_at, contemporaneous_index=contemporaneous_index, checkpoint_path=checkpoint_path,
    )
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
