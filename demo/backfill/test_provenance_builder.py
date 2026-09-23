#!/usr/bin/env python3
"""Standalone stdlib-unittest tests for provenance_builder.py -- this repo
ships no test framework/dependency manifest (it is a Claude Code skill repo,
demo/ scripts only), so these use only the standard library, exactly like
every other script here.

Run with:  python3 demo/backfill/test_provenance_builder.py -v

Every negative case flips exactly one thing and confirms the mutant is
caught, per QUEUE_PROTOCOL §7.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from provenance_builder import (  # noqa: E402
    SourceRecord,
    compute_source_ref,
    default_mapper,
    load_contemporaneous_index,
    run_backfill,
)

SOURCE_TYPE = "oo-history-export"


def _synthetic_oo_export(n: int) -> list[SourceRecord]:
    records = []
    for i in range(1, n + 1):
        raw = {
            "external_id": f"oo-evt-{i:05d}",
            "asserted_at": f"2026-0{1 + (i % 9)}-01T00:00:00Z",
            "kind": "oo.action",
            "amount": i,
        }
        records.append(SourceRecord(raw=raw, position=i))
    return records


def _synthetic_contemporaneous(external_ids: list[str]) -> list[dict]:
    return [
        {"capsule_id": f"cap-{eid}", "payload": {"external_id": eid, "kind": "oo.action"}}
        for eid in external_ids
    ]


class ProvenanceBuilderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out_dir = pathlib.Path(self.tmp.name) / "out"
        self.checkpoint_path = self.out_dir / ".checkpoint-batch1.json"
        self.mapper = default_mapper(source_type=SOURCE_TYPE)

    def _run(self, records, contemporaneous_index):
        return run_backfill(
            records,
            mapper=self.mapper,
            out_dir=self.out_dir,
            import_batch="batch1",
            imported_at="2026-09-22T00:00:00Z",
            contemporaneous_index=contemporaneous_index,
            checkpoint_path=self.checkpoint_path,
        )

    def test_1k_synthetic_history_with_10pct_overlap_imports_and_collapses_duplicates(self):
        records = _synthetic_oo_export(1000)
        overlapping_ids = [r.raw["external_id"] for r in records[:100]]  # first 10%
        contemporaneous = _synthetic_contemporaneous(overlapping_ids)
        index = load_contemporaneous_index(
            contemporaneous, source_type=SOURCE_TYPE,
            external_id_of=lambda c: c["payload"]["external_id"],
        )

        summary = self._run(records, index)

        self.assertEqual(summary.total_source_records, 1000)
        self.assertEqual(summary.written, 1000)
        self.assertEqual(summary.duplicates_of_contemporaneous, 100)
        self.assertEqual(summary.contemporaneous_total, 100)
        self.assertEqual(summary.to_dict()["backfilled_new_coverage"], 900)

        written_files = sorted(self.out_dir.glob("batch1-*.json"))
        self.assertEqual(len(written_files), 1000)

        with_chain = [json.loads(p.read_text()) for p in written_files if "chain" in json.loads(p.read_text())]
        self.assertEqual(len(with_chain), 100)
        for req in with_chain:
            self.assertEqual(req["chain"]["relation"], "duplicates")
            self.assertTrue(req["chain"]["parent_capsule_id"].startswith("cap-oo-evt-"))
            self.assertEqual(req["provenance_mode"]["mode"], "backfilled")

    def test_import_twice_is_idempotent_appends_nothing_new(self):
        records = _synthetic_oo_export(1000)
        index = load_contemporaneous_index(
            _synthetic_contemporaneous([r.raw["external_id"] for r in records[:100]]),
            source_type=SOURCE_TYPE, external_id_of=lambda c: c["payload"]["external_id"],
        )
        first = self._run(records, index)
        self.assertEqual(first.written, 1000)

        second = self._run(_synthetic_oo_export(1000), index)  # same logical export, re-read fresh
        self.assertEqual(second.written, 0)
        self.assertEqual(second.skipped_already_imported, 1000)
        # no files renumbered or duplicated on disk
        self.assertEqual(len(list(self.out_dir.glob("batch1-*.json"))), 1000)

    def test_import_of_a_superset_export_appends_only_the_new_records(self):
        base = _synthetic_oo_export(1000)
        index: dict[str, str] = {}
        first = self._run(base, index)
        self.assertEqual(first.written, 1000)

        superset = _synthetic_oo_export(1010)  # same 1000 + 10 genuinely new
        second = self._run(superset, index)
        self.assertEqual(second.written, 10)
        self.assertEqual(second.skipped_already_imported, 1000)
        self.assertEqual(len(list(self.out_dir.glob("batch1-*.json"))), 1010)

    def test_mutant_no_contemporaneous_overlap_collapses_nothing(self):
        """Same 1k/100-overlap fixture, but the dedup index is built from a
        DIFFERENT set of external ids -- the digests can never match, so
        nothing collapses. Proves the collapse in the positive test is
        actually driven by matching source_ref digests, not incidental."""
        records = _synthetic_oo_export(1000)
        disjoint_contemporaneous = _synthetic_contemporaneous([f"unrelated-{i}" for i in range(100)])
        index = load_contemporaneous_index(
            disjoint_contemporaneous, source_type=SOURCE_TYPE,
            external_id_of=lambda c: c["payload"]["external_id"],
        )
        summary = self._run(records, index)
        self.assertEqual(summary.written, 1000)
        self.assertEqual(summary.duplicates_of_contemporaneous, 0)

    def test_mutant_mismatched_source_type_prevents_a_true_duplicate_from_collapsing(self):
        """The contemporaneous index built under a DIFFERENT source_type
        never matches a backfill run's digests, even for the identical
        external_id -- proves source_type is load-bearing in the digest,
        not decorative."""
        records = _synthetic_oo_export(10)
        same_ids = [r.raw["external_id"] for r in records]
        index = load_contemporaneous_index(
            _synthetic_contemporaneous(same_ids), source_type="a-different-source-type",
            external_id_of=lambda c: c["payload"]["external_id"],
        )
        summary = self._run(records, index)
        self.assertEqual(summary.duplicates_of_contemporaneous, 0)

    def test_compute_source_ref_is_deterministic_and_identity_sensitive(self):
        a = compute_source_ref(SOURCE_TYPE, "oo-evt-00001")
        b = compute_source_ref(SOURCE_TYPE, "oo-evt-00001")
        c = compute_source_ref(SOURCE_TYPE, "oo-evt-00002")
        self.assertEqual(a, b)
        self.assertNotEqual(a["digest"], c["digest"])
        self.assertEqual(a["digest_alg"], "sha256")
        self.assertEqual(len(a["digest"]), 64)


if __name__ == "__main__":
    unittest.main()
