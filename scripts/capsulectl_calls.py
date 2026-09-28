"""Thin helpers the two exercise scripts share: call capsulectl, read its JSON."""

import datetime
import hashlib
import json
import pathlib
import subprocess


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
    at = datetime.datetime.fromisoformat(entry["appended_at"].replace("Z", "+00:00"))
    return at.date() == day


def publish(capsulectl, profile, request, workdir, name):
    """Seal one record into the book. The request's Timestamp is fixed by the
    caller, so publishing the same record again returns the same capsule."""
    path = pathlib.Path(workdir) / f"{name}.request.json"
    path.write_text(json.dumps(request, sort_keys=True))
    return run(capsulectl, "publish", "--profile", profile, "--request", str(path))["capsule_id"]


def seal_request(action_id, operator, developer, timestamp, body):
    return {
        "spec_version": "capsule-seal-request/v1",
        "capsule": {"ActionID": action_id, "ActionType": "fyi", "Operator": operator,
                    "Developer": developer, "Timestamp": timestamp},
        "payload": body,
    }
