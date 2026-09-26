# Airline customer-service interaction dataset

Recorded airline customer-service interactions, together with the domain evidence
needed to reason about them: the authoritative booking database and the
customer-service policy. Interactions are provided as raw conversation logs with no
graded scores or answer keys — the correct outcome of each interaction is meant to be
determined from the evidence (booking state + policy + the conversation itself).

## Contents

Interaction files — each is one run of the same 50 scenarios repeated over 4 trials
(200 interactions per file):

- `claude-3-7-sonnet-20250219_airline_default_gpt-4.1-2025-04-14_4trials.json`
- `gpt-4.1-2025-04-14_airline_default_gpt-4.1-2025-04-14_4trials.json`
- `o4-mini-2025-04-16_airline_default_gpt-4.1-2025-04-14_4trials.json`
- `gpt-4.1-mini-2025-04-14_airline_base_gpt-4.1-2025-04-14_4trials.json`

Domain evidence:

- `db.json` — authoritative booking state: 300 flights, 500 users, 2000 reservations.
- `policy.md` — the airline customer-service policy (cancellation windows, change rules, refunds, baggage, escalation).

## Interaction file structure

Each interaction file is a JSON object:

- `timestamp` — when the run was recorded.
- `info` — run configuration (models used, limits, environment).
- `tasks` — the scenario definitions: each has an `id`, a `description`, the
  `user_scenario` (what the customer wants and how they behave), an optional
  `ticket`, and an optional `initial_state`.
- `simulations` — the interactions. Each has an `id`, its `task_id`, `trial` and
  `seed`, start/end timestamps and duration, a `termination_reason`, per-turn cost,
  and `messages`: the ordered conversation, where assistant turns may carry
  `tool_calls` and each following tool turn carries that call's result.

No ground-truth outcome, reward, or evaluation criteria is included in any file.
