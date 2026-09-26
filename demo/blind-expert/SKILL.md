---
name: demo-blind-expert
description: Demo scaffold for collecting blind human ratings chained to airline evaluation reports.
---

# Blind human-rating workflow

This directory demonstrates the human step of calibration. Invoke the compiler's
sampling-and-rating instructions in [`../../assets/sampling.md`](../../assets/sampling.md)
to enumerate verified `evaluation-report/v1` Capsules, stratify and freeze the sample
in a `sample-manifest/v1` Capsule before requesting ratings.

For each selected report, resolve the source interaction and prepare a rater packet
with the transcript, permitted evidence, audited rubric, and independently sourced
desired-outcome materials. Exclude every judge-derived field: verdict, rationale,
axis judgments, and stratum. Capture the expert's `pass`, `fail`, or `unsure` and a
blind attestation. Publish one `human-rating/v1` Capsule with
`Chain.ParentCapsuleID` set to that report and
`Relation: io.evaluation.human_rates`.

This is demo scaffolding, not compiler output or a runner. The adjacent synthetic
generator is only an illustrative stand-in; a real run requires a human rater and
must never present its synthetic values as human evidence.
