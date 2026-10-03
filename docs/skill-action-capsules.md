# Skill-action capsules

Every action a skill takes seals one capsule through `capsulectl publish`, so the book
holds a record of what the skill did as well as what it judged. The record goes
through the same `seal_request` / `publish` helpers in `scripts/capsulectl_calls.py`
that seal evaluation reports. `scripts/skill_record.py` builds it.

## The record: `skill-action/v1`

```json
{
  "record_type": "skill-action/v1",
  "skill": "evidence-contract-compile",
  "action": "contract-validate",
  "inputs": [{"role": "contract", "digest": "<sha256 of the file>"}],
  "output_digest": "<sha256 of the action's stdout>",
  "argv_digest": "<JSON-DIGEST of the argv array>",
  "outcome": "ok",
  "exit_code": 0
}
```

- **Digests only.** No file contents, paths, profile details or environment. Every
  digest field must be 64 lowercase hex characters. File digests are SHA-256 over the
  file's bytes. Digests of JSON values are JSON-DIGESTs: SHA-256 over the RFC 8785
  (JCS) form, so any JCS implementation recomputes them.
- **Refused names.** `skill`, `action` and input roles are plain names. A name with a
  part that refers to secret material (key, seed, token, password, credential, dsn,
  private, ...) is refused. `keyword` is fine, `signing-key` is not.
  `scripts/skill_action.py` also refuses an `--input` that looks like key material
  (`.seed`, `.key`, `.pem`, `.env`, and similar).
- **Capsule fields.** ActionType is `fyi`, Developer is `evidencebook-skills/<skill>`,
  and ActionID is `urn:evidencebook-skills:skill-action:<skill>:<action>:<digest>`,
  where the digest is the record's own JSON-DIGEST.
- **Re-runs.** The timestamp is committed into the capsule, so it is always fixed:
  `run_weekly.py` uses the week's stamp, and `skill_action.py` requires `--at`. The same
  action over the same inputs with the same timestamp is the same capsule, so nothing
  new is sealed. A different outcome is a different capsule, never a publish conflict.
- **Failures.** A failed action is sealed too, with `outcome: failed` and the exit
  status. An action whose record cannot be sealed, including a JSON value JCS cannot
  represent, is `evidence unavailable`, and the run stops there.

## Where each skill seals

| skill | action | sealed as |
|---|---|---|
| weekly-blind-expert | read the week's frame | `skill-action/v1` (output: JSON-DIGEST of the sorted report capsule_ids) |
| | draw the sample | the `sample-manifest/v1` |
| | hand out blind packets | `skill-action/v1` (input: the manifest; output: JSON-DIGEST of the packets) |
| | a human rating, calibration summary, close | their own capsules |
| daily-judge-and-close | judge pin | `skill-action/v1` (input: JSON-DIGEST of the pin input; output: the pin digest) |
| | read the day's range | `skill-action/v1` (output: JSON-DIGEST of the sorted case capsule_ids) |
| | judge or recompute a clause | the `evaluation-report/v1` |
| | verify the day's cases | `skill-action/v1` (output: JSON-DIGEST of the verified capsule_ids) |
| | close | the Close capsule |
| any skill, by hand | install, discover, map, contract validate, judge pin, roll-up, … | `scripts/skill_action.py --skill S --action A --at T [--input ROLE=PATH]… -- COMMAND` |

Records the skills already sealed are not duplicated: a report, a manifest, a rating
or a Close *is* the record of the action that produced it.

## Judgment names

A record that is a judgment uses these names:

| name | where | value today |
|---|---|---|
| `judged_from` | Capsule `references[]` | `{type: agent-action-capsule, digest_alg: SHA-256, digest: <capsule_id judged>, citation_purpose: judged_from}` |
| `rubric_digest` | payload | a judged report: the pinned axes digest; a human rating: copied from the report it audits |
| `judge_parameters_digest` | payload | a judged report: the judge pin digest |

- **Which records.** A judged `evaluation-report/v1` carries all three. A
  `human-rating/v1` carries `judged_from` (the case it rated) and the audited report's
  `rubric_digest`. A recomputed report is not a judgment and carries none of them.
- **Status.** These are provisional names. `judged_from` is committed into
  `capsule_id` and verifies with `capsulectl publish` on capsule-cli main.
- **Interim construction.** The `rubric_digest` and `judge_parameters_digest` values
  above are not yet built the way the judgment extension proposes. That proposal
  builds them as JSON-DIGESTs of the rubric document and of the judge's parameters
  (identity excluded), in the compute attestation's judgment member, with a human's
  parameters being its protocol and packet digest. They follow that construction and
  placement once it is ratified and `capsulectl publish` accepts the member.

## Readers

`run_daily.py` selects cases by a `case` payload, and `run_weekly.py` selects reports
by `record_type`, so `skill-action/v1` records never enter a day's cases or a week's
frame. A verifier that walks the whole book (as `tests/fresh_env.sh` does) counts
them as ordinary capsules. They verify like any other.

## Tested

- `tests/test_skill_action.py` covers:
  - the record and request shape, the refusals and JCS vectors;
  - determinism and failure sealing;
  - the wrapper against a stand-in capsulectl;
  - with `CAPSULECTL` set, a real `capsulectl`: an action sealed twice with the same
    `--at` appends one capsule, and that capsule verifies.
- `tests/fresh_env.sh` installs `requirements.txt` into a venv and counts the
  skill-action records among the capsules that must verify.
