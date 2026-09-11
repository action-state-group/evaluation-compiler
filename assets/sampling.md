# Sampling and expert-rating execution

The agent executing a generated **sampling-and-rating** skill owns this workflow.
It runs only after per-case evaluation reports exist: its input is
`evaluation-report/v1` Capsules, and its output is one `human-rating/v1` Capsule
per expert rating. Use Capsule CLI commands from `capsule-cli.md` and ordinary
file operations. Do not create runners, helper programs, scripts or Makefiles. Do
not edit the generated bundle; corrections belong in the compiler and require
regeneration.

This skill does not judge and does not compute the calibration. It draws a sample
of already-judged cases, obtains an **independent human pass/fail** for each, and
records those ratings as Capsules for the calibration skill to reduce. The human
is the ground truth for the sample; the judge is what the sample audits.

## Fix the audited quantity

Every rating audits one named pass/fail quantity — the axis or roll-up recorded in
`resolved-spec.json` as the calibration target (e.g. `full_resolution`). Use the
same quantity for the whole sample and record it on every rating. Do not mix
quantities in one period.

## Select the population and stratify

Resolve the runtime profile and the period window. Enumerate the CLL, accept only
`evaluation-report/v1` Capsules from this bundle's cohort (matching `axes` digest,
evaluated subject and dataset revision), verify each Capsule's identity, producer
signature and bound payload, and deduplicate by the case/trial key. This frozen,
verified set is the population.

Partition the population by the judge's verdict on the audited quantity:
- stratum **P** = reports the judge marked `pass` (size `N_p`);
- stratum **F** = reports the judge marked `fail` (size `N_f`).

Random sampling wastes effort: at a high pass rate a random draw is almost all
passes and barely measures the false-pass rate, usually the costlier error.
Stratifying by verdict measures both error directions for the same human effort.
Reports whose audited quantity is `unjudgeable`/`not_applicable` form their own
excluded stratum — record them; do not force them into P or F.

## Draw the sample

Draw `n_p` from P and `n_f` from F by **seeded** random selection (sizes are runtime
inputs). Before any rating, record a sample manifest — the period window, cohort
identity, `N_p`/`N_f`, `n_p`/`n_f`, the seed, and the selected report Capsule IDs —
so the sample is reproducible and cannot be re-drawn to taste. Persist the manifest
(optionally as its own Capsule) as the frozen selection for this period.

## Present blind and capture ratings

For each sampled report, present the underlying **interaction** to a human expert —
the transcript and permitted evidence only. The expert must not see the judge's
verdict, rationale, or any axis result: reveal none of the report payload. Capture
the expert's pass/fail (allow an explicit `unsure`) and optional rationale. A rating
produced while the rater could see the judge output is not independent; discard it
and re-rate blind, or record the exposure as a limitation rather than count it.

Never synthesize a rating, infer it from the judge, or fill an unrated sample slot
with a model verdict. A missing rater means the sample is incomplete, reported as
such — not completed by the agent.

## Publish and verify each rating

Create a new rating identity per expert rating. Write a `human-rating/v1` payload
holding: the audited quantity, the `pass`/`fail`/`unsure` verdict, rater identity
and role, a blind attestation, the audited `evaluation-report/v1` Capsule id, the
subject case/trial identity (matching that report), the sample manifest reference,
and any rationale.

Prepare a `capsule-seal-request/v1` request as specified in `capsule-cli.md`. Chain
the rating to the report it audits: add a `Chain` block whose `ParentCapsuleID` is
that `evaluation-report/v1` Capsule id and whose `Relation` is
`io.evaluation.human_rates` (`ledger_mode: chained` is derived, not caller-set). This
makes each rating audit exactly one verdict, so the calibration join is the chain
link itself. Call `capsulectl publish`, then get the returned Capsule, verify its
identity/signature/trust and bound payload, confirm the `chain` parent resolves to
the intended report in the same CLL, and read back its sequence. Publication runs a
store-level check that the parent report exists, so rate only reports already
appended.

Keep run data outside the distributed bundle. Report the sample manifest, the rated
and unrated slots per stratum, and the published rating Capsule IDs/sequences.
