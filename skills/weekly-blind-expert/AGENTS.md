---
name: weekly-blind-expert
description: Cron-run, once per week. Draw a stratified sample of the week's judged cases, present them to a human blind to the judge's verdict, and seal the calibration summary and the week's Close. The human's ratings are the approval point.
---
# Weekly blind-expert audit

Compiled per contract by `evidence-contract-compile`; this file is the template the
compiler specialises, not something a customer edits by hand. Runs weekly, and
**pauses for a human** — it is the one point in the whole cron contract with a human in
the loop, and the human's ratings are the approval; this skill never fills one in on
their behalf, never infers a rating from a timeout, and never proceeds past the sample
with fewer ratings than were drawn without reporting the shortfall.

**Not runnable today.** Sealing `calibration-summary/v1` needs `calibration summarize`
and reading the week's Closes needs `close`/`reconcile`, neither shipped yet. See
[`../README.md`](../README.md)'s verb table and its flagged tension with this repo's
own `docs/calibration-sampling-spec.md`.

## Verbs this skill may call, and nothing else

- `cll list` / `get` / `verify` (today) — resolve and authenticate the week's
  `evaluation-report/v1` and `close/v1` records before sampling from them.
- Draw the sample per the contract's `sample_policy` (`weekly: N`, `stratify_by`),
  reusing the deterministic rule this repo already specifies in
  `docs/calibration-sampling-spec.md` (order each stratum by the hex of
  `SHA-256(u32be(len(seed)) || seed || report_capsule_id)`, break ties by capsule id,
  take the first `n` per stratum) — do not invent a second sampling rule for this
  skill. Seal the draw as `sample-manifest/v1` (frame, strata sizes, seed, exact rule,
  selected report ids) via `publish` (today) **before** any human sees a case — the
  manifest is what makes the sample unable to be cherry-picked or redrawn after the
  fact.
- For each sampled report, resolve the source interaction and the same
  independently-sourced desired-outcome materials the judge used (the audited axis
  rubric, the declared criteria or evidence procedure) — transcript-blind, as the
  judge itself required. Assemble a packet that **excludes** the report's verdict,
  rationale, axis judgments and stratum label, and withholds any field the contract's
  `disclosure.suppress` list names (with digest, never silently dropped).
- Present the packet to a human expert; record their pass/fail as `human-rating/v1`
  (epistemic type `human_report`, `blind: true`), chained to the `evaluation-report/v1`
  Capsule it audits, via `publish` (today).
- `calibration summarize` (pending) — reduce the week's
  ratings against the reports they audit into one `calibration-summary/v1`: **agreement
  as k of n, and nothing else.** See the flag below — this is a deliberate, narrower
  output than this repo's own pre-existing calibration estimators.
- `close --period week [--peer NAME]` (pending) — seal the week's Close, same
  UNILATERAL-by-construction rule as the daily skill when no counterparty is
  configured.

## Flag: `calibration-summary/v1` is k-of-n only, and that is narrower than this repo already ships

`docs/calibration-sampling-spec.md` (pre-existing in this repo) computes two error
rates, a population-weighted judge accuracy `Â`, and a bias-corrected pass rate `p̂` —
i.e. it scores the judge. The design for this skill is explicit that
`calibration-summary/v1` is a `derived_metric` reporting agreement as k of n, and that
nobody computes an accuracy score. This skill follows that rule. The estimator math in
`docs/calibration-sampling-spec.md` is not wrong, and is not touched here — it is an
open tension between this repo's existing design and the new record family, to be
reconciled in the judge record family spec rather than decided by this skill.

## Evidence policy

Every consequential action (the sample manifest, each human rating, the calibration
summary, the week's Close) must produce a record. A seal failure stops the run before
the next consequential step and reports `evidence unavailable`; it never infers that a
rating was given, or that the week closed, from the absence of its record. If fewer
ratings come back than were drawn (a rater unavailable, a case dropped on
verification), the summary reports the shortfall against the drawn `n`, not a silently
smaller stated sample.

## What this skill never does

Show a rater the judge's verdict, rationale, or the case's stratum. Fabricate a rating
for an unsampled case, or for a sampled case nobody rated. Redraw or re-stratify a
sample after the manifest is sealed. Compute or publish an accuracy score, false-pass,
or false-fail rate under `calibration-summary/v1` — see the flag above. Decide the
disclosure or sample policy; both are read from the compiled resolved-spec and applied,
never chosen here.
