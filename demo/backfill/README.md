# tau2 backfill

`backfill.py` turns real [tau2-bench](https://github.com/sierra-research/tau2-bench)
runs into `capsule-seal-request/v1` files for Demo B. tau2-bench is a runnable
benchmark and ships its recorded runs under `data/tau2/results/final/*.json`;
each file holds `simulations[]` for every `(task_id, trial)`, with the real agent
and user-simulator transcript. This script reads those shipped results only — no
agent run, no user simulator, no model/LLM API key, and nothing is synthesized.
It has exactly two arguments:

```sh
DEMO=~/.local/share/evaluation-runs/tau2-airline-eval
RES=~/GitHub/tau2-bench/data/tau2/results/final/claude-3-7-sonnet-20250219_airline_default_gpt-4.1-2025-04-14_4trials.json
python3 backfill.py --results "$RES" --out "$DEMO/backfill"
```

It writes **one request per agent act** — one per `role="assistant"` turn (the system
under evaluation) in each task's trial-0 run — named `task-<id>-act-<NNNN>.json`
(`NNNN` is the zero-padded act index in the conversation; task ids are sanitized for
the filesystem). It is **not** one capsule per task and **not** one per raw message:
the user-simulator (`role="user"`) turns and the tool results (`role="tool"`) are
never their own capsules — they are inputs/outputs of the surrounding acts. The
airline file yields **762 acts across 50 conversations**. Publish them all into a
profile you have already created (see [demo/DEMO.md](../DEMO.md) for creating the
`airlinedemo` profile):

```sh
for f in "$DEMO"/backfill/*.json; do capsulectl publish --profile airlinedemo --request "$f"; done
```

The domain is read from the results file (`environment_info.domain_name`). The
Capsule's Operator/Developer are fixed backfill-provenance labels (`tau2-demo`,
`tau2@backfill-v1`), and the Timestamp is the simulation's own timestamp; a
simulation without a usable one is rejected rather than stamped with `now()`.

## Payload layout

Each act request carries two payloads that `capsulectl publish` (capsule-cli →
capsule-emit-go) commits as digests under `model_attestation.compute_attestation`
(SHA-256 over RFC 8785 JCS), writing the original bytes to the artifact store as bound
`present` artifacts:

- `payload` → `agent_input_digest`. `payload` holds:
  - `case`: `{benchmark, domain, task_id, trial, conversation_id, turn_idx, act_index}`
    — `conversation_id` is the tau2 simulation UUID; a conversation's acts share it and
    order by `turn_idx`.
  - `provenance`: results file, agent LLM, user-simulator LLM, simulation id, seed,
    termination reason.
  - `agent_input`: `{policy, tools, messages}` — the model-invocation context the agent
    saw before this act: the domain policy, the observed tool surface (distinct tools
    the agent invoked in the conversation, derived from the transcript), and every prior
    turn (greeting, user turns, earlier assistant turns, tool results, each trimmed of
    cost/usage/raw-data bookkeeping and keeping `requestor` attribution) up to and
    including the latest user turn.
- `agent_output` → `agent_output_digest`: the assistant message this act produced — its
  `content` and/or `tool_calls`.

There are **no** effect blocks and **no** gate/decision layer. A write tool call is
simply part of `agent_output`; its result becomes context in the next act's
`agent_input`. The script computes no digest of its own — a second hashing path would
be a bug.

The gold outcome is deliberately excluded: neither the task's `evaluation_criteria`
nor the simulation's `reward_info` goes in the payload. The judge reads the desired
outcome independently from the dataset by `payload.case.task_id`, so it must never
travel inside the bound payload.

Capsule IDs are content-addressed (JCS over the metadata and the payload digests), so
publishing the same act reproduces the same Capsule ID regardless of the signing key.
`capsulectl verify` on a published act reports `Bound:true`, `Verified:true`, exit 0.
