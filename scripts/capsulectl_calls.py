"""Thin helpers the two exercise scripts share: call capsulectl, read its JSON."""

import datetime
import hashlib
import json
import pathlib
import re
import subprocess

_FRACTIONAL_SECONDS = re.compile(r"\.(\d+)")


def parse_rfc3339(timestamp):
    """capsulectl stamps appended_at with Go's RFC3339Nano, which trims trailing
    zeros from the fractional seconds -- so the digit count varies record to
    record (".39222" as readily as ".781403"). Python's fromisoformat before 3.11
    only accepts exactly 0, 3 or 6 fractional digits and raises on anything else
    (seen in practice: a Close capsule's real wall-clock append time, 5 digits,
    crashed a second daily-judge-and-close run that lists every published capsule
    including it). Pad or truncate to 6 digits so any valid RFC3339 timestamp
    parses, whatever the producer trimmed."""
    ts = timestamp.replace("Z", "+00:00")
    m = _FRACTIONAL_SECONDS.search(ts)
    if m:
        frac = (m.group(1) + "000000")[:6]
        ts = ts[:m.start()] + "." + frac + ts[m.end():]
    return datetime.datetime.fromisoformat(ts)


class EvidenceUnavailable(Exception):
    """A consequential step produced no record. The run stops at this step."""


def run(capsulectl, *args, check=True):
    """Run one capsulectl verb and return its JSON result (or None)."""
    proc = subprocess.run([capsulectl, *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise EvidenceUnavailable(f"capsulectl {args[0]} exited {proc.returncode}: {proc.stderr.strip()}")
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def list_capsules(capsulectl, profile):
    """Every log entry that records a capsule, in log order, paging through."""
    entries, after = [], 0
    while True:
        page = run(capsulectl, "cll", "list", "--profile", profile, "--after", str(after), "--limit", "1000")
        batch = page.get("entries") or []
        if not batch:
            return entries
        entries.extend(batch)
        after = page["next_after"]


def payload(capsulectl, profile, capsule_id):
    """The decoded payload of one stored capsule (readable `get`)."""
    record = run(capsulectl, "get", "--profile", profile, "--capsule-id", capsule_id)
    for artifact in record.get("artifacts") or []:
        if artifact.get("name") == "payload":
            return artifact.get("content")
    return None


def verify(capsulectl, profile, capsule_id, workdir):
    """Authenticate one stored capsule before acting on it: get --raw, then verify."""
    path = pathlib.Path(workdir) / f"{capsule_id}.json"
    if not path.exists():
        run(capsulectl, "get", "--profile", profile, "--capsule-id", capsule_id, "--raw", "--output", str(path))
    result = subprocess.run([capsulectl, "verify", "--profile", profile, "--capsule", str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise EvidenceUnavailable(f"capsule {capsule_id} does not verify: {result.stderr.strip()}")


def committed_on(entry, day):
    return parse_rfc3339(entry["appended_at"]).date() == day


def publish(capsulectl, profile, request, workdir, name):
    """Seal one record into the book. The request's Timestamp is fixed by the
    caller, so publishing the same record again returns the same capsule."""
    path = pathlib.Path(workdir) / f"{name}.request.json"
    path.write_text(json.dumps(request, sort_keys=True))
    return run(capsulectl, "publish", "--profile", profile, "--request", str(path))["capsule_id"]


def seal_request(action_id, operator, developer, timestamp, body, judged_from=None):
    """`judged_from`, when given, is the capsule_id the sealed record is a judgment
    of. It rides in the Capsule's own references (citation purpose `judged_from`),
    so it is committed into capsule_id rather than left to the payload."""
    capsule = {"ActionID": action_id, "ActionType": "fyi", "Operator": operator,
               "Developer": developer, "Timestamp": timestamp}
    if judged_from is not None:
        capsule["References"] = [judged_from_reference(judged_from)]
    return {
        "spec_version": "capsule-seal-request/v1",
        "capsule": capsule,
        "payload": body,
    }


def judged_from_reference(capsule_id):
    """The typed reference a judgment carries to the record it judged. `capsule`
    is the reference type for a capsule_id; it and `judged_from` are open tokens
    today (accepted and verified by `capsulectl publish`, not yet registered)."""
    if not (isinstance(capsule_id, str) and len(capsule_id) == 64
            and all(c in "0123456789abcdef" for c in capsule_id)):
        raise EvidenceUnavailable(f"judged_from must be a capsule_id (64 lowercase hex), got {capsule_id!r}")
    return {"Type": "capsule", "DigestAlg": "SHA-256", "Digest": capsule_id, "CitationPurpose": "judged_from"}


# -- skill-action/v1: one capsule per skill action -------------------------------
#
# Every action a skill takes (install, discover, map, contract validate, judge pin,
# a day's range read, verify, result build, ...) seals one skill-action/v1 record.
# The record carries digests only: of the inputs the action read, of what it
# printed, and of its argv. Never file contents, paths, profile details or
# environment. An action that is itself a judgment adds rubric_digest and
# judge_parameters_digest, and cites what it judged as judged_from (see
# seal_request). Records the skills already seal (evaluation reports, sample
# manifests, ratings, calibration summaries, Closes) are not duplicated here.

SKILL_ACTION = "skill-action/v1"
_SECRET_WORDS = ("secret", "token", "password", "passwd", "credential", "dsn", "seed", "private", "key")


def json_digest(value):
    """SHA-256 over sorted-key, separator-free JSON: the digest a reader recomputes."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def _hex64(name, value):
    if not (isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)):
        raise EvidenceUnavailable(f"{name} must be a SHA-256 hex digest, got {value!r}")
    return value


def _plain_name(name, value):
    if not (isinstance(value, str) and value and all(c.isalnum() or c in "-_." for c in value)):
        raise EvidenceUnavailable(f"{name} must be a plain name ([A-Za-z0-9._-]+), got {value!r}")
    lowered = value.lower()
    if any(word in lowered for word in _SECRET_WORDS):
        raise EvidenceUnavailable(f"{name} {value!r} names secret material; skill-action records never carry it")
    return value


def skill_action_record(skill, action, inputs=(), output_digest=None, outcome="ok", exit_code=0,
                        argv_digest=None, rubric_digest=None, judge_parameters_digest=None):
    """The skill-action/v1 body -- pure, no I/O. `inputs` is [(role, sha256)]."""
    if outcome not in ("ok", "failed"):
        raise EvidenceUnavailable(f"outcome must be ok or failed, got {outcome!r}")
    record = {"record_type": SKILL_ACTION, "skill": _plain_name("skill", skill),
              "action": _plain_name("action", action),
              "inputs": [{"role": _plain_name("input role", role), "digest": _hex64(f"input {role}", digest)}
                         for role, digest in sorted(inputs)],
              "outcome": outcome, "exit_code": int(exit_code)}
    if output_digest is not None:
        record["output_digest"] = _hex64("output_digest", output_digest)
    if argv_digest is not None:
        record["argv_digest"] = _hex64("argv_digest", argv_digest)
    if judge_parameters_digest is not None and rubric_digest is None:
        raise EvidenceUnavailable("a judgment's judge_parameters_digest needs its rubric_digest")
    if rubric_digest is not None:
        record["epistemic_type"] = "semantic_judgment"
        record["rubric_digest"] = _hex64("rubric_digest", rubric_digest)
        if judge_parameters_digest is not None:
            record["judge_parameters_digest"] = _hex64("judge_parameters_digest", judge_parameters_digest)
    return record


def skill_action_request(record, operator, timestamp, judged_from=None):
    """The seal request for one skill-action/v1 record. The ActionID names the
    record's own digest, so the same action over the same inputs is the same
    capsule (a re-run seals nothing new) and a different outcome is a different
    capsule, never a conflict. A judgment must cite what it judged."""
    if "rubric_digest" in record and judged_from is None:
        raise EvidenceUnavailable("a judgment skill action must cite what it judged (judged_from)")
    action_id = (f"urn:evidencebook-skills:skill-action:{record['skill']}:{record['action']}:"
                 f"{json_digest([record, judged_from])[:16]}")
    return seal_request(action_id, operator, f"evidencebook-skills/{record['skill']}", timestamp, record,
                        judged_from=judged_from)


def emit_skill_action(capsulectl, profile, workdir, operator, timestamp, record, judged_from=None):
    """Seal one skill action. Fails closed: no record, no next step."""
    request = skill_action_request(record, operator, timestamp, judged_from)
    name = f"skill-action-{record['action']}-{request['capsule']['ActionID'][-16:]}"
    return publish(capsulectl, profile, request, workdir, name)
