# Calibration execution

The agent executing a generated **calibration** skill owns this workflow. Its
inputs are the period's `evaluation-report/v1` Capsules (the judged population) and
the `human-rating/v1` Capsules that audit a sample of them; it produces one
`calibration-summary/v1` Capsule. Use Capsule CLI commands from `capsule-cli.md`
and ordinary file operations. Do not create runners, helper programs, scripts or
Makefiles. Do not edit the generated bundle; corrections belong in the compiler and
require regeneration.

Calibration estimates how well the judge agrees with independent human ratings and
turns that into a bias-corrected population rate with confidence intervals. It never
re-judges, never re-opens source interactions, and never creates or edits ratings —
the sampling-and-rating skill produced those. It certifies the **judge**, not the
unsampled cases, which remain judge-derived.

## Select and verify reports and ratings

Resolve the runtime profile and the period window. Enumerate the CLL and separate:
- `evaluation-report/v1` Capsules of this bundle's cohort (matching `axes` digest,
  evaluated subject and dataset revision), deduplicated by case/trial key — the
  population, size `N`, split into judge-`pass` `N_p` and judge-`fail` `N_f` on the
  audited quantity;
- `human-rating/v1` Capsules whose audited quantity matches and whose window falls in
  the period — the audit sample.

Verify every consumed Capsule's identity, producer signature and bound payload. For
each rating, verify the **complete binding** to the report it audits, and drop it as a
verification error (with an explicit reason) if any check fails — never enter a
loosely-bound rating into a confusion cell:
- `chain.relation` equals `io.evaluation.human_rates`;
- `chain.parent_capsule_id` resolves to a report in this cohort and in the same CLL;
- the payload `audited_report_capsule_id` equals that chain parent;
- the payload `subject` matches that report's subject (case/trial);
- the rating's recorded stratum matches the report's judge verdict on the audited
  quantity, recomputed here from the report — a `judge_pass` rating whose report is
  actually judge-`fail` is misfiled and dropped;
- its audited report is a member of the period's **`sample-manifest/v1`** Capsule:
  resolve that manifest Capsule (its id is carried by every rating) and verify it —
  confirm its `period_window`, `cohort`, `audited_quantity`, strata sizes, `seed` and
  `selection_rule` match this run, not just its envelope — then require the report to be
  in its `selected` set. A rating for a report outside the sample is dropped; only the
  pre-registered sample feeds the estimate, so no otherwise-valid off-sample rating can
  bias it. All ratings in the period must reference the same manifest Capsule; a divergent
  reference is a verification error.

Join each rating to its report through the verified chain parent, never by re-deriving
identity. A report is audited once: if more than one rating chains to the same report,
resolve it by a verdict-blind rule fixed before rating (e.g. earliest by append
sequence) or exclude all of them and report the unresolved slot — never choose among
conflicting human verdicts by their value.

## Reduce

Count only **usable** ratings: drop `unsure` and verification-dropped ratings from both
numerator and denominator, and report the excluded count as nonresponse. Let `m_p` and
`m_f` be the usable rating counts in the judge-`pass` (P) and judge-`fail` (F) strata.
Use `m_p`/`m_f`, never the drawn sample sizes `n_p`/`n_f`, in every estimate and
interval — dividing by the drawn size biases the error rates toward zero.

Blind human verdict versus judge verdict, per stratum:
- from F: `â = (# usable human "pass" in F) / m_f` — false-fail rate `P(truth pass | judge fail)`;
- from P: `b̂ = (# usable human "fail" in P) / m_p` — false-pass rate `P(truth fail | judge pass)`.

Build the 2×2 confusion counts (judge × human) per stratum. Because the strata are
sampled disproportionately, **raw sample agreement is not judge accuracy** — report it
only as a labelled descriptive statistic. The population quantities are the
population-weighted **judge accuracy** and the **bias-corrected pass rate** (a judge-`fail`
is *correct* when the human also says fail, rate `1-â`; it is *truly pass* at rate `â`):

```
Â = [ N_p·(1 - b̂) + N_f·(1 - â) ] / (N_p + N_f)   # judge accuracy
p̂ = [ N_p·(1 - b̂) + N_f·â       ] / (N_p + N_f)   # corrected pass rate
```

Give confidence intervals targeting **95% simultaneous** coverage, not point estimates
alone. Compute a **Wilson score interval** for each stratum proportion `â`, `b̂` from its
usable count `m_f`, `m_p`; Wilson stays non-degenerate at `0` and `1`, so a clean stratum
still carries honest uncertainty (a Wald plug-in variance `p(1-p)/m` collapses to zero
there — do not use it). Because the combined estimate uses **both** stratum intervals at
once, split the error budget with Bonferroni: take each stratum interval at level
`1 - 0.05/2 = 97.5%` so the joint interval holds at ≥95%. Apply the finite-population
correction to each stratum interval as `[mid - fpc·h, mid + fpc·h]`, where `mid` and `h`
are the Wilson midpoint and half-width and `fpc = sqrt((N_s - m_s)/(N_s - 1))`. Then
combine by monotonicity, noting `p̂` and `Â` differ:
- `p̂` increases in `â`, decreases in `b̂`: `p̂_L` from `b̂_U, â_L`; `p̂_U` from `b̂_L, â_U`.
- `Â` decreases in **both** `â` and `b̂`: `Â_L` from `b̂_U, â_U`; `Â_U` from `b̂_L, â_L`.

Handle degenerate strata explicitly, applied **before** the fpc formula:
- `N_s = 0` — the stratum is absent; the population reduces to the other stratum.
- `m_s = 0` — that stratum's error rate is unestimated; do **not** treat it as `0`. Report
  `p̂`/`Â` only as partial bounds over the estimable stratum and flag the missing one, or
  withhold the population estimate.
- `m_s = N_s` (a census, including `N_s = 1`) — the stratum rate is the exact observed
  `x_s/N_s` with the point interval `[x_s/N_s, x_s/N_s]`; use that, not a scaled Wilson
  midpoint.

A single period is coarse (e.g. `m=10`, 10/10 agreement still has a wide Wilson lower
bound); treat each period as one point on a **control chart** and compute drift versus
prior `calibration-summary/v1` Capsules for this cohort — deltas in `â`, `b̂`, `Â` and
`p̂` — flagging movement beyond a stated threshold. Pooling periods into a tighter
estimate is valid only under an explicit multi-period estimator with stable strata
weights and judge behaviour; do not assert a specific pooled precision from a period
count alone, and keep drift detection separate from any pooling. Do not infer the judge
is good from one clean period, and do not overwrite the coarse-n caveat.

## Publish and verify the summary

Create a new calibration identity for this run. Record the calibration bundle's
instructional-file digests, the shared `axes` digest, the CLI digest, the source
store/namespace/log, the audited quantity, the frozen population and sample
(report and rating Capsule IDs/sequences, `N_p`/`N_f`, drawn `n_p`/`n_f`, usable
`m_p`/`m_f`, sampling method `stratified_by_verdict`, the sample manifest digest/reference,
blinding attested), and the prior summaries used for drift. Never manufacture historical
provenance.

Write one `calibration-summary/v1` JSON payload holding: calibration identity, period
window, cohort identity, audited quantity, sampling design (including drawn and usable
counts), the per-stratum confusion counts, `â`/`b̂`/judge-accuracy `Â`/corrected-rate `p̂`
each with its confidence interval and level, raw sample agreement labelled as descriptive,
the drift comparison, excluded (`unsure`/dropped) ratings as nonresponse, degenerate/
zero-denominator strata, verification references,
and limitations (small-n caveats first).

Prepare a `capsule-seal-request/v1` request as specified in `capsule-cli.md`; AAC digest
inputs reject floating-point numbers, so encode every rate, interval bound and decimal
metadatum as a decimal string. Call `capsulectl publish`, then get the returned summary
Capsule, verify its identity/signature/trust and bound payload, and read back its
sequence. A calibration summary reduces many reports and ratings, so it binds them
through the enumerated Capsule IDs/sequences in its source selection, not through a
single-parent `chain`. Keep run data outside the distributed bundle. Report the summary
Capsule ID/sequence, the population and sample sizes, and any dropped ratings or
zero-denominator strata.
