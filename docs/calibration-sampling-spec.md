# Statistical calibration of the judge via human-rated sampling

## Problem

Nobody labels the desired outcome for every interaction, so an evaluator that
requires per-case declared ground truth (`target_mode: declared`) is unrealistic
at volume (e.g. ~1000 interactions/week). We still want a defensible answer to
"how often does the agent fully resolve the request, and can we trust the
automated judge?"

Approach: the per-case evaluator judges **all** interactions (judge-only, no
ground truth). Humans independently rate a **sample** each period. Comparing the
human ratings to the judge's verdicts yields a *statistical* estimate of judge
quality and a bias-corrected population rate. Ground truth exists only for the
sample; the certified object is the **judge**, not each capsule.

This does not change the per-case evaluator contract. It adds one Capsule type
and one aggregation, both reusing existing mechanisms (Capsules, the `chain`
link, the aggregation-bundle pattern). No new store, table, or service.

## What is measured

The audited quantity is a single judged pass/fail per interaction. Pin it to a
named quantity up front — either the `full_resolution` axis or a defined overall
roll-up — and record that name in every rating and in the summary. Auditing an
ambiguous target corrupts the agreement number.

Two error rates, not one (they have different costs):

- **false-fail** `a = P(truth = pass | judge = fail)`
- **false-pass** `b = P(truth = fail | judge = pass)`

## Sampling design: stratify by the judge's verdict

Plain random sampling is the trap. At a ~90% pass rate a random 10 contains ~1
failure, so it barely measures `b` (the usually-costlier error). Instead
stratify by the judge verdict over the period:

- Stratum P = interactions the judge marked pass (population size `N_p`).
- Stratum F = interactions the judge marked fail (population size `N_f`).
- Draw `n_p` from P and `n_f` from F (e.g. 5 + 5) by seeded random selection.

Record the sampling frame, strata sizes, seed, and selected interaction ids in a
**sample manifest** (optionally its own Capsule) before humans rate, so the
sample cannot be cherry-picked after the fact.

## Blinding

The human rater sees the interaction transcript and any permitted evidence, but
**not** the judge's verdict or rationale — otherwise anchoring inflates
agreement. Each rating attests `blind: true`. This is the audit analog of the
evaluator's extraction isolation.

## Estimators

Within each stratum the human ratings give binomial proportions:

- from F: `â = (#human-pass in F sample) / n_f`  → false-fail rate
- from P: `b̂ = (#human-fail in P sample) / n_p`  → false-pass rate

Bias-corrected population pass rate (stratified):

```
p̂ = [ N_p·(1 - b̂) + N_f·â ] / (N_p + N_f)
```

Variance (add finite-population correction per stratum; use Wilson intervals for
the per-stratum proportions when n is small, then propagate):

```
Var(p̂) = [ N_p²·Var(b̂) + N_f²·Var(â) ] / (N_p + N_f)²
Var(b̂) = b̂(1-b̂)/n_p · (N_p - n_p)/(N_p - 1)     (fpc)
Var(â) = â(1-â)/n_f · (N_f - n_f)/(N_f - 1)
```

Precision reality: a single period of 10 is coarse (10/10 agreement → 95% Wilson
CI ≈ [72%, 100%]). Treat each period as a point on a **control chart**; the
running estimate over many periods (10/week × 52 ≈ 520) tightens agreement to
~±2–3pp. The weekly value catches a badly broken judge; the trend certifies a
good one and flags drift.

## Capsule: `human-rating/v1`

One Capsule per human rating, appended to the same CLL, chained to the
`evaluation-report/v1` Capsule it audits (reuse of the `chain` mechanism — see
`references/capsule-cli.md`), forming the provenance chain interaction ← report ←
rating. The sampling skill sets the chain parent to the report; the **rater sees
only the interaction** (transcript + evidence), never the report payload, so the
rating audits exactly one verdict while staying blind to it. The chain link is
also the calibration join — no identity re-derivation needed.

Request `capsule` (PascalCase `emit.Input`; `assurance`/`ledger_mode` are derived,
not caller-set):

```jsonc
{
  "spec_version": "capsule-seal-request/v1",
  "capsule": {
    "ActionID": "urn:human-rating:<scenario>:<simulation_id>:<rater>:<run>",
    "ActionType": "fyi",
    "Operator": "<audit-program identity>",
    "Developer": "<rating-tool identity>",
    "Timestamp": "<UTC>",
    "Chain": {
      "ParentCapsuleID": "<evaluation-report capsule_id being audited>",
      "Relation": "io.evaluation.human_rates"
    }
  },
  "payload": {
    "spec_version": "human-rating/v1",
    "subject": { "case_id": "...", "simulation_id": "..." },
    "rated_quantity": "full_resolution",
    "verdict": "pass",            // pass | fail | unsure
    "blind": true,
    "rater": { "role": "...", "id": "..." },
    "sampling": {
      "frame_window": "2026-09-01T00:00Z/2026-09-08T00:00Z",
      "stratum": "judge_pass",    // judge_pass | judge_fail
      "audited_report_capsule_id": "<evaluation-report capsule_id>",
      "sample_manifest_capsule_id": "<optional>"
    },
    "rationale": "optional",
    "cutoff": "<UTC>"
  }
}
```

Notes:
- The chain `parent_capsule_id` is the audited report; the calibration join is the
  chain link itself, so the confusion cell is unambiguous even if the judge is re-run.
  `subject` still records the case/trial for cohort checks and must match the report.
- `unsure` ratings are excluded from the numerators and reported separately.

## Calibration aggregation bundle

A sibling of the existing aggregation bundle. It reduces `evaluation-report/v1`
(the judged population) together with `human-rating/v1` (the audit sample) over a
period; it never re-judges and never creates ratings.

Resources (mirrors the aggregate bundle):
- `SKILL.md` — purpose, runtime inputs (`profile`, period window, `rated_quantity`,
  and either the strata sample sizes for a fresh draw or a `sample_manifest`),
  and the reduce-then-publish steps.
- `references/calibration.md` — adapted from a new `assets/calibration.md`.
- `references/capsule-cli.md` — copied as usual (`capsulectl` stays a host prereq).

Steps:
1. Select over the window: all `evaluation-report/v1` (population, with judge
   verdict on `rated_quantity`) and all `human-rating/v1` (sample).
2. `verify` each consumed Capsule including its `chain` link; a rating whose
   parent interaction or `audited_report_capsule_id` does not resolve in the CLL
   is a verification failure, not a silent drop.
3. Join by interaction identity within the window; build the confusion matrix per
   stratum from blind human `verdict` vs judge verdict.
4. Compute `â`, `b̂`, agreement, and the bias-corrected `p̂` with CIs; compare to
   prior window(s) for drift.
5. Publish one `calibration-summary/v1` Capsule back into the same CLL.

### `calibration-summary/v1` payload

- calibration identity; period window; scenario; shared `axes` digest;
  `rated_quantity`.
- sampling design: `N_p`, `N_f`, `n_p`, `n_f`, method (`stratified_by_verdict`),
  seed / `sample_manifest_capsule_id`, blinding attested.
- confusion matrix: counts of (judge, human) ∈ {pass, fail} per stratum;
  `unsure`/excluded counts.
- estimates: `false_pass_rate` `b̂`±CI, `false_fail_rate` `â`±CI, `agreement`±CI,
  `corrected_pass_rate` `p̂`±CI (decimal strings — AAC digests reject floats).
- drift: deltas vs prior window(s) and a threshold flag.
- verification references for every consumed report and rating; limitations
  (small-n caveats, excluded ratings, zero-denominator strata).

## Compiler surface

- Per-case evaluator: **unchanged** (judge-only; no ground truth per case).
- New `cross_case_aggregation` value `calibration` (alongside `none`/`rate`/
  `all_required`/`native`). When selected, the compiler generates **two** extra
  bundles beyond the per-case evaluator:
  1. a **sampling-and-rating** bundle (`<scenario>-sample/`) — reads the period's
     reports, stratifies by judge verdict, draws a seeded sample, presents each
     sampled interaction to a human expert blind to the judge verdict, and
     publishes a `human-rating/v1` Capsule chained to the audited report;
  2. a **calibration** bundle (`<scenario>-calibrate/`) — reduces the reports and
     ratings into `calibration-summary/v1`.
- New `assets/sampling.md` and `assets/calibration.md`, referenced the way
  `assets/aggregation.md` is. `resolved-spec.json` records the audited quantity and
  sampling design so both skills agree.
- `human-rating/v1` is created only by the sampling-and-rating skill's
  human-in-the-loop step — never by the compiler, the evaluator, or a model
  standing in for the expert. The ratings must exist before calibration can reduce
  them, so the two skills run in that order.

## What this does not solve

- It certifies the judge and yields an aggregate rate ± CI; it does **not**
  produce trustworthy per-case ground truth for the unsampled interactions. Their
  per-case reports remain judge-derived and are labeled as such.
- It reduces the *cost* of ground truth (fewer cases rated), not the isolation
  question: how the desired outcome is defined for those human ratings is still a
  separate decision (human judgment here, vs derived state+policy).
