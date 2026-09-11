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

Verify every consumed Capsule's identity, producer signature and bound payload, and
verify each rating's `chain`: its `parent_capsule_id` must resolve to a report in this
cohort and in the same CLL. A rating whose parent does not resolve, whose audited
quantity differs, or which fails verification is an execution error that drops it with
an explicit reason — not a silent skip. Join each rating to its report through the
chain parent, not by re-deriving identity. If two ratings audit the same report, keep
one deterministically or record the conflict; do not double-count.

## Reduce

Blind human verdict versus judge verdict, per stratum:
- from stratum F (judge `fail`): `â = (# human "pass") / n_f` — the false-fail rate,
  `P(truth pass | judge fail)`;
- from stratum P (judge `pass`): `b̂ = (# human "fail") / n_p` — the false-pass rate,
  `P(truth fail | judge pass)`;
- `unsure` ratings are excluded from the numerator and denominator and reported
  separately.

Build the 2×2 confusion counts (judge × human) within each stratum. Report raw
agreement and, because the population is stratified, the **bias-corrected population
pass rate**:

```
p̂ = [ N_p·(1 - b̂) + N_f·â ] / (N_p + N_f)
```

Give confidence intervals, not point estimates alone. Use Wilson intervals for the
per-stratum proportions (n is small), apply the finite-population correction, and
propagate to `p̂`:

```
Var(b̂) = b̂(1-b̂)/n_p · (N_p - n_p)/(N_p - 1)
Var(â) = â(1-â)/n_f · (N_f - n_f)/(N_f - 1)
Var(p̂) = [ N_p²·Var(b̂) + N_f²·Var(â) ] / (N_p + N_f)²
```

A single period is coarse (e.g. 10/10 agreement gives a wide lower bound); treat each
period as one point on a control chart. Compute drift versus prior `calibration-summary/v1`
Capsules for this cohort — deltas in `â`, `b̂`, agreement and `p̂` — and flag movement
beyond a stated threshold. Do not infer the judge is good from one clean period, and do
not overwrite the coarse-n caveat.

## Publish and verify the summary

Create a new calibration identity for this run. Record the calibration bundle's
instructional-file digests, the shared `axes` digest, the CLI digest, the source
store/namespace/log, the audited quantity, the frozen population and sample
(report and rating Capsule IDs/sequences, `N_p`/`N_f`, `n_p`/`n_f`, sampling method
`stratified_by_verdict`, the sample manifest reference, blinding attested), and the
prior summaries used for drift. Never manufacture historical provenance.

Write one `calibration-summary/v1` JSON payload holding: calibration identity, period
window, cohort identity, audited quantity, sampling design, the per-stratum confusion
counts, `â`/`b̂`/agreement/`p̂` each with its confidence interval, the drift comparison,
excluded (`unsure`/dropped) ratings, zero-denominator strata, verification references,
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
