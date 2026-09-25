---
name: daily-judge-and-close
description: Cron-run, once per day. Judge the day's cases against a compiled contract's clauses and seal the day's Close. No human in this loop; a failed seal stops the run and reports evidence unavailable.
---
# Daily judge-and-close

Compiled per contract by `evidence-contract-compile`; this file is the template the
compiler specialises, not something a customer edits by hand. Runs unattended, nightly.
There is no approval point in this loop by design — every judgment is pinned and every
seal either succeeds or the run stops and says so; nothing here waits on a human.

**Not runnable today.** Every consequential step below calls a verb that does not exist
yet (`close`, `judge pin`) or a plugin that is not built yet (`capsulectl-engine`). See
[`../README.md`](../README.md)'s verb table. This file documents the shape the compiled
skill takes once the book verbs land in `capsulectl`; nothing here should need rewriting
when it does, only the caveats removed.

## Verbs this skill may call, and nothing else

- `cll list --profile NAME --after N --through N` (today) / a book-level `--since-last`
  convenience once the Evidence Book ships (pending) — read the day's range. Idempotent
  on the day key: re-running a day that already sealed a Close must not double-seal: a
  compiled instance persists the last sealed day and refuses to re-run it, distinct
  from `--since-last` itself resuming from the last *read* position.
- `get` / `verify` (today) — resolve and authenticate each candidate record before
  acting on it. Never act on an unverified record.
- `plugin ls` (today) then `capsulectl-engine fold run --clause ID --profile NAME`
  (plugin, pending) — for every clause this
  contract marked `tier: recomputed`, run the registered fold. No model runs for these
  clauses; the fold's own verdict (`established`/`failed`/`not present`) is final.
- `judge pin` (pending) — resolve the pinned judge (model id, prompt digest, axes
  digest, sampling) before judging anything. A day's judgments must all cite the same
  pin; a pin that changed mid-day is a compile-time error, not something this skill
  silently absorbs.
- the pinned judge itself, over each cancellation/conversation/case citing acts and
  method by digest — for every clause this contract marked `tier: judged`. The judge
  proposes a verdict (`met`/`not met`/`not evaluable`); this skill never overrides it
  and never infers a verdict for a case the judge could not reach.
- `publish` (today) — seal one `evaluation-report/v1` per case per judged clause
  (epistemic type `semantic_judgment`), citing the source interaction and the judge pin.
- `close --period day [--peer NAME]` (pending) — seal the day's Close: counts by kind,
  head, and reconcile tallies when a counterparty book is configured. A Close with no
  `--peer` is `UNILATERAL` by construction and the sealed record says so; it is not a
  lesser Close, it is an honest one for a single-party contract.
- `reconcile --peer NAME --period day` (pending) — when the contract names a
  counterparty, resolve the six states (MATCHED, A_ONLY, B_ONLY, CONFLICTING,
  INSUFFICIENT, UNRESOLVED) from the two books' held bundles. **Never a live query
  against the counterparty** — reconcile reads only what each side has already sealed
  and held. A day with an INSUFFICIENT count is reported as exactly that, never rounded
  up to MATCHED or silently dropped from the day's tally.

## Evidence policy

Every consequential action here (a fold result committed, a judgment sealed, a Close
sealed) must produce a record. If a seal fails at any step, this skill reports
`evidence unavailable` for that step, stops before the next consequential action for
the same case or clause, and does not infer that the underlying action — the fold
result, the judgment, the day itself — failed to occur just because its record could
not be made. A partial day (some clauses sealed, one seal failed) is reported as
exactly that: which clauses closed, which did not, and why.

## What this skill never does

Invent a fold for a `recomputed` clause that names no registered fold — that is a
compile-time rejection in `evidence-contract-compile`, not something this skill papers
over at run time. Judge a `recomputed` clause, or fold-check a `judged` one — the tier
is fixed at compile time. Reconcile against a live counterparty query. Re-open or
re-judge a case a prior day already sealed a report for. Decide the disclosure policy —
it reads `payloads`/`suppress` from its compiled resolved-spec and passes it through to
whatever later builds a bundle; it never chooses what to withhold.
