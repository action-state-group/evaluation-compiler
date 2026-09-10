---
name: evaluation-compiler
description: Turn a user scenario and value proposition into evaluation axes and an executable evaluation skill bundle. Use when creating or adapting an outcome evaluator, including CLL-backed investigations and native benchmark data.
---
# Evaluation compiler

Compile an evaluation workflow into instructions for an agent, not into a program. The output is axes plus a scenario skill. The generated skill directs its host agent and uses the Capsule CLI for Capsule, artifact and CLL operations. Never generate helper programs, runners, scripts, a Go module or a Makefile.

The evaluation source is always a CLL of recorded interactions. A native benchmark or dataset (e.g. a customer-service task set) is not evaluated directly: its interactions are first backfilled into a CLL as Capsules, and the generated skill then evaluates that CLL exactly like any other source. Axes and judging remain the compiler's job even when the dataset ships its own scoring contract.

## Resolve the user's intent

Start from the **value proposition**. The user leads with what should improve and for whom; take that as the entry point and derive the rest of the contract yourself from it and any accessible context. The items below are your internal checklist, not a questionnaire — never open by asking the user to answer all of them. Resolve what you can, adopt a sensible default where one clearly exists, and then ask **one focused question at a time** for anything that remains genuinely unresolved and material, in a short back-and-forth. Do not ask the user to write a spec.

Resolve (derive first; ask only for what is missing and material):
- The scenario and evaluation unit: which individual outcome is evaluated (usually implied by the value proposition and the source)?
- Desired-outcome authority: declared task criteria or independent evidence; what establishes success, and what was knowable at execution time?
- Agent-outcome source: where the actual answer or action is recorded and how it is authenticated.
- Access: for CLL, the named Capsule CLI profile. Do not ask for database credentials or a caller-written adapter. Discover existing access to external evidence separately; a storage profile does not grant GitHub access.
- Judgment policy: observable axes, applicability, insufficient-evidence behavior and aggregation.

Access is the one input you usually cannot infer, so it is the most likely single question. Everything else — evaluation unit, target mode, axes, aggregation defaults — you normally derive from the value proposition and a quick look at the source.

If access is missing from the request, explicitly resolve it during intake. Obtain CLI command/output semantics from [capsule-cli.md](references/capsule-cli.md). Inspect a representative source to learn its shape, but do not mistake stored context or an agent-authored answer for independent truth. When the source is already a CLL, read one entry through the CLI; when it is not yet in a CLL (a native benchmark or dataset), read the original data files directly. Do not create a profile, stand up a CLL, or run any backfill in order to inspect it.

Ignore the `demo/` folder entirely when compiling. Everything under `demo/` is a self-contained demonstration, and any previously generated bundle is a prior output — none of it is an input. Do not read the demo walkthrough as a spec, and do not read or copy a prior bundle's axes, source mapping, or run results. "Accessible sources" means only the evaluation source the user named: the CLL read through the CLI, and the dataset. Derive the axes fresh from the value proposition; inspect a representative Capsule via the CLI only to learn the source's shape. The compiler's own machinery — this `SKILL.md`, `assets/`, and `references/capsule-cli.md` — is what you use to build the bundle.

Never infer the evaluation's domain, dataset, or source from the current working directory or the files that happen to sit in it. The value proposition's wording never implies a particular dataset, domain, or benchmark; do not reach for a script or dataset the user did not name. The interactions source, and whether any backfill is relevant, are part of access and come from the user — when the user gives only a value proposition and no source, ask where the interactions are recorded.

Selection belongs to execution, not compilation. A CLL-backed skill accepts a profile name and either an exclusive/inclusive sequence range `(after, through]` or an append-time window such as the last seven days. Never hardcode the experiment's profile, IDs, range, dates, secrets or machine paths into a reusable bundle.

`target_mode` is `evidence_derived` or `declared`. `aggregation` is `none`, `all_required` or `native`; it is the **within-case** roll-up across a single run's axes and sets each report's `aggregate`. Default to `none` unless aggregation is requested and justified. `native` requires the benchmark's existing scoring contract; preserve its task/trial/reward semantics rather than inventing a replacement score. A benchmark's trials originate outside CLL and are backfilled into it before evaluation.

`cross_case_aggregation` is a separate, **cross-case** policy — `none` (default), `rate`, `all_required` or `native` — for rolling up many evaluated cases (e.g. a benchmark's pass rate across tasks). Set it only when a roll-up across cases is requested and justified. When it is not `none`, the compiler additionally generates an aggregation skill bundle (see below); the per-case skill is unchanged. Cross-case aggregation consumes the `evaluation-report/v1` Capsules the per-case skill produces, never the source interactions, so it presumes those reports already exist. It is independent of the within-case `aggregation`: `all_required` and `native` reduce from each report's `axis_judgments` (and recorded native result) directly, not from the report's within-case `aggregate`, so they work even when the per-case policy was `none`. `native` requires the per-case reports to record the benchmark's native result; if they do not, reject the `native` configuration rather than emit an undefined score.

## Generate the bundle

Create only these resources:
- `SKILL.md`: scenario purpose, accepted runtime inputs and actionable execution steps. The host agent performs selection, verification, independent extraction, judging and publication; do not delegate that workflow to a custom program.
- `axes.json`: each axis's ID, link to the value proposition, applicability, required evidence, pass/fail boundaries, missing-evidence behavior and role.
- `resolved-spec.json`: the resolved scenario, evaluation unit, target and aggregation policies, source/reference locations, required and optional runtime inputs, and honest limitations. This is compiler output, not user homework.
- `references/source.md`: observed source semantics, case/run identity, exact original-content bindings and independent evidence access. Do not invent mappings. For a dataset backfilled into the CLL, document the mapping from dataset record to Capsule artifacts/bindings so the same get/verify path applies.
- `references/execution.md`: adapt [execution.md](assets/execution.md) to the scenario without weakening independence or verification.
- `references/capsule-cli.md`: the CLI contract, copied from this compiler's reference.
- `bin/capsule`: the compatible CLI executable when distributing a self-contained bundle. This is the only program in the bundle; configuration and credentials stay on the execution host.

Compilation produces the bundle and nothing else. The compiler does not create Capsule CLI profiles, stand up or initialize a CLL, backfill a dataset, or publish — and it does not investigate how to do those things (no `profile create`/`profile show`, no store init, no backfill run). It records the named profile as a runtime input in `resolved-spec.json` and the generated evaluator and aggregator skills, so they know which profile to read; it neither creates nor validates that profile. Creating the profile and backfilling a native benchmark into a CLL are separate operator prep steps performed outside the compiler; the bundle's `source.md` documents the dataset→Capsule mapping so those steps and the generated skill agree.

Use outcome-linked axes, not an output-feature checklist. Separate desired and agent outcome records, with evidence IDs per claim. Do not claim that a proxy measures actual time saved or risk reduced.

When `cross_case_aggregation` is not `none`, also generate a separate aggregation bundle (e.g. `<scenario>-aggregate/`) whose host agent reduces completed reports rather than judging. It reuses the same `axes.json` and `resolved-spec.json` by reference — do not regenerate or fork the axes — and its resources are:
- `SKILL.md`: the aggregation purpose, the runtime inputs (profile and a report range or append-time window), and the reduce-then-publish steps.
- `references/aggregation.md`: adapt [aggregation.md](assets/aggregation.md) to the scenario and the resolved `cross_case_aggregation` policy, without weakening report verification or the reports-only input rule.
- `references/capsule-cli.md` and `bin/capsule`: copied as for the per-case bundle.
The aggregation skill selects `evaluation-report/v1` Capsules over the range, verifies each, reduces their axis judgments across cases, and publishes one `evaluation-summary/v1` Capsule back into the same CLL. It never re-judges, re-opens source interactions, or imports raw source outcomes.

## Exercise the generated skill (only against a CLL that already exists)

Exercising validates the bundle; it is not setup. Run the generated SKILL.md against a CLL that already exists — for Alchemy, the production CLL; for a backfilled benchmark, only after the operator has separately created the profile and backfilled it. Never create a profile, stand up a CLL, backfill, or otherwise prepare data in order to exercise: if the source is not yet in a CLL, stop after generating the bundle and hand the backfill off as an operator step. Do not replace missing instructions with a bespoke runner. When a CLL is available, exercise selection, get/verify, separate outcome records, judging, report publication and readback; keep private run results outside the compiler and bundle.

Validate the compiler with a fresh evaluation under the newly generated bundle: acquire evidence, extract desired and agent outcomes independently, judge the current axes, create a new report and publish a new evaluation Capsule. Never substitute a previous evaluation report or its judgments for this execution. Record the actual bundle content digests in the report and distinguish missing evidence from execution errors.

When an aggregation bundle was generated, exercise it too, after enough per-case reports exist: select the report range, verify each report, reduce the axis judgments across cases per `cross_case_aggregation`, and publish a new `evaluation-summary/v1` Capsule; read it back. Do not let aggregation re-run judging or substitute for a per-case validation.

The compiler is the only editable source of evaluation instructions. Generated bundles are immutable outputs: fix this compiler or its references and assets, then regenerate the whole bundle. Never patch a generated skill or add historical-evaluation replay as a shortcut.
