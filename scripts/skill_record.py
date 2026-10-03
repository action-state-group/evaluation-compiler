"""skill-action/v1: one capsule per skill action.

Every action a skill takes (install, discover, map, contract validate, a week's
frame read, handing out blind packets, ...) seals one skill-action/v1 record
through the same `seal_request` / `publish` helpers that seal evaluation reports
(scripts/capsulectl_calls.py). The record carries digests only: of the inputs the
action read, of what it printed, and of its argv. Never file contents, paths,
profile details or environment. Records the skills already seal (evaluation
reports, sample manifests, ratings, calibration summaries, Closes) are the
records of their own actions and are not duplicated.

Digests of JSON values are JSON-DIGESTs: SHA-256 over the RFC 8785 (JCS)
canonical form, so a reader recomputes them with any JCS implementation.
"""
import hashlib
import re

import rfc8785

from capsulectl_calls import EvidenceUnavailable, publish, seal_request

SKILL_ACTION = "skill-action/v1"
SECRET_WORDS = frozenset({"secret", "secrets", "token", "tokens", "password", "passwd", "credential",
                          "credentials", "dsn", "seed", "private", "key", "keys", "apikey", "pat"})
_HEX64 = re.compile(r"[0-9a-f]{64}")
_PLAIN = re.compile(r"[A-Za-z0-9._-]+")


def json_digest(value):
    """JSON-DIGEST: SHA-256 over the JCS (RFC 8785) form of `value`. A value JCS
    cannot represent (a non-finite float, an integer beyond I-JSON's range) has no
    digest, and the action has no record."""
    try:
        return hashlib.sha256(rfc8785.dumps(value)).hexdigest()
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as e:
        raise EvidenceUnavailable(f"value has no JSON-DIGEST: {e}") from e


def _hex64(name, value):
    if not (isinstance(value, str) and _HEX64.fullmatch(value)):
        raise EvidenceUnavailable(f"{name} must be a SHA-256 hex digest, got {value!r}")
    return value


def _plain_name(name, value):
    if not (isinstance(value, str) and _PLAIN.fullmatch(value)):
        raise EvidenceUnavailable(f"{name} must be a plain name ([A-Za-z0-9._-]+), got {value!r}")
    if SECRET_WORDS & set(re.split(r"[._-]", value.lower())):
        raise EvidenceUnavailable(f"{name} {value!r} names secret material; skill-action records never carry it")
    return value


def skill_action_record(skill, action, inputs=(), output_digest=None, outcome="ok", exit_code=0,
                        argv_digest=None):
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
    return record


def skill_action_request(record, operator, timestamp):
    """The seal request for one skill-action/v1 record. The ActionID names the
    record's own digest, so a different outcome is a different capsule, never a
    publish conflict. With the timestamp fixed too, the same action over the same
    inputs is the same capsule: a re-run seals nothing new."""
    action_id = (f"urn:evidencebook-skills:skill-action:{record['skill']}:{record['action']}:"
                 f"{json_digest(record)[:16]}")
    return seal_request(action_id, operator, f"evidencebook-skills/{record['skill']}", timestamp, record)


def emit_skill_action(capsulectl, profile, workdir, operator, timestamp, record):
    """Seal one skill action. Fails closed: no record, no next step."""
    request = skill_action_request(record, operator, timestamp)
    name = f"skill-action-{record['action']}-{request['capsule']['ActionID'][-16:]}"
    return publish(capsulectl, profile, request, workdir, name)
