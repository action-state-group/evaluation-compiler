# tau2 backfill

`backfill.py` turns real [tau2-bench](https://github.com/sierra-research/tau2-bench)
runs into `capsule-seal-request/v1` files for Demo B. tau2-bench is a runnable
benchmark and ships its recorded runs under `data/tau2/results/final/*.json`;
each file holds `simulations[]` for every `(task_id, trial)`, with the real agent
and user-simulator transcript. This script reads those shipped results only — no
agent run, no user simulator, no model/LLM API key, and nothing is synthesized.
It has exactly two arguments:

```sh
RES=~/GitHub/tau2-bench/data/tau2/results/final/claude-3-7-sonnet-20250219_retail_default_gpt-4.1-2025-04-14_4trials.json
python3 backfill.py --results "$RES" --out "$DEMO/backfill"
```

It writes **one request per task — that task's trial-0 run** — named
`task-<id>.json` (task ids are sanitized for the filesystem; the retail file
yields 114). Publish them all with a loop:

```sh
for f in "$DEMO"/backfill/*.json; do capsulectl publish --profile tau2demo --request "$f"; done
```

The domain is read from the results file (`environment_info.domain_name`). The
Capsule's Operator/Developer are fixed backfill-provenance labels (`tau2-demo`,
`tau2@backfill-v1`), and the Timestamp is the simulation's own timestamp; a
simulation without a usable one is rejected rather than stamped with `now()`.

## Payload layout

The bound `payload` carries the authenticated interaction:

- `case`: `{benchmark, domain, task_id, trial}`
- `provenance`: results file, agent LLM, user-simulator LLM, simulation id, seed,
  termination reason
- `agent_interaction`: `{messages: [...]}` — the real transcript (role, content,
  tool calls and tool results, each with its `requestor` attribution), trimmed of
  cost/usage/raw-data bookkeeping

The gold outcome is deliberately excluded: neither the task's
`evaluation_criteria` nor the simulation's `reward_info` goes in the payload. The
judge reads the desired outcome independently from the dataset by
`payload.case.task_id`, so it must never travel inside the bound payload.

Capsule IDs are content-addressed (JCS over the metadata and payload digest), so
publishing the same simulation reproduces the same Capsule ID regardless of the
signing key.
