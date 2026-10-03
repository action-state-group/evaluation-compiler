# Skill-action capsules

Every action a skill takes seals one capsule through `capsulectl publish`, so the book
holds a record of what the skill did as well as what it judged. Nothing new is added
to the emission path: the record goes through the same `seal_request` / `publish`
helpers in `scripts/capsulectl_calls.py` that seal evaluation reports.

## The record: `skill-action/v1`

```json
{
  "record_type": "skill-action/v1",
  "skill": "evidence-contract-compile",
  "action": "contract-validate",
  "inputs": [{"role": "contract", "digest": "<sha256 of the file>"}],
  "output_digest": "<sha256 of the action's stdout>",
  "argv_digest": "<sha256 of the JSON argv>",
  "outcome": "ok",
  "exit_code": 0
}
```

- **Digests only.** No file contents, paths, profile details or environment. Every
  digest field must be 64 lowercase hex characters. `skill`, `action` and input roles
  are plain names, and a name that refers to secret material (key, seed, token,
  password, credential, dsn, private) is refused. `scripts/skill_action.py` also
  refuses an `--input` that looks like key material (`.seed`, `.key`, `.pem`, `.env`,
  and similar).
- **Capsule fields.** ActionType is `fyi`, Developer is `evidencebook-skills/<skill>`,
  and ActionID is `urn:evidencebook-skills:skill-action:<skill>:<action>:<digest>`,
  where the digest covers the record and its `judged_from`.
- **Re-runs.** A re-run with the same inputs and outcome is the same capsule, so
  nothing new is sealed. A different outcome is a different capsule, never a
  publish conflict.
- **Failures.** A failed action is sealed too, with `outcome: failed` and the exit
  status. An action whose record cannot be sealed is `evidence unavailable`, and the
  run stops there.

## Judgments

An action that is a judgment uses these names:

| name | where | value |
|---|---|---|
| `rubric_digest` | payload | digest of what the case was judged against (the pinned axes file) |
| `judge_parameters_digest` | payload | digest of the parameters the judge ran under (the judge pin's digest) |
| `judged_from` | Capsule `references[]` | `{type: capsule, digest_alg: SHA-256, digest: <capsule_id judged>, citation_purpose: judged_from}` |

`judged_from` is committed into `capsule_id` by `capsulectl publish` on capsule-cli's
current main branch, and the record verifies. `capsule` (as a reference type) and
`judged_from` are open tokens there: both are accepted and verified, but neither is
registered yet.

`rubric_digest` and `judge_parameters_digest` ride in the payload for now. They move
into the judgment extension member of the compute attestation once `capsulectl
publish` accepts it. The names stay the same.

## Where each skill seals

| skill | action | sealed as |
|---|---|---|
| daily-judge-and-close | judge pin | `skill-action/v1` (input: the pin input's digest; output: the pin digest) |
| | read the day's range | `skill-action/v1` (output: digest of the sorted case capsule_ids) |
| | judge a case on a clause | the `evaluation-report/v1` itself, carrying `rubric_digest` and `judge_parameters_digest`, citing the case as `judged_from` |
| | recompute a clause | the `evaluation-report/v1` (not a judgment, so no judgment names) |
| | verify the day's cases | `skill-action/v1` (output: digest of the verified capsule_ids) |
| | close | the Close capsule |
| weekly-blind-expert | read the week's frame | `skill-action/v1` (output: digest of the frame's report capsule_ids) |
| | draw the sample | the `sample-manifest/v1` |
| | hand out blind packets | `skill-action/v1` (input: the manifest; output: digest of the packets) |
| | a human rating | the `human-rating/v1`, carrying `rubric_digest` and citing the case as `judged_from` (a human has no judge parameters) |
| | calibration summary, close | their own capsules |
| any skill, by hand | install, discover, map, contract validate, roll-up, result build, … | `scripts/skill_action.py --skill S --action A [--input ROLE=PATH]… -- COMMAND` |

Records the skills already sealed are not duplicated: a report, a manifest, a rating
or a Close *is* the record of the action that produced it.

## Readers

`rollup_day.py`, `run_weekly.py` and `run_daily.py` select records by `record_type`
or by a `case` payload, so `skill-action/v1` records never enter a roll-up, a frame or
a day's cases. A verifier that walks the whole book (as `tests/fresh_env*.sh` do)
counts them as ordinary capsules. They verify like any other.

## Tested

- `tests/test_skill_action.py` covers the record and request shape, refusals,
  determinism, failure sealing, the wrapper against a stand-in capsulectl, and, with
  `CAPSULECTL` set, a judgment sealed and verified by a real `capsulectl` with
  `judged_from` in its references.
- `tests/fresh_env.sh` and `tests/fresh_env_outcomes.sh` now count the skill-action
  records among the capsules that must verify. A second daily run still seals nothing.
