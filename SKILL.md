---
name: evaluation-compiler
description: Turn a user scenario and value proposition into evaluation axes and an executable evaluation skill bundle. Use when creating or adapting an outcome evaluator, including CLL-backed investigations and native benchmark data.
---
# Evaluation compiler

Compile an evaluation workflow into instructions for an agent, not into a program. The output is axes plus a scenario skill. The generated skill directs its host agent and uses the Capsule CLI for Capsule, artifact and CLL operations. Never generate helper programs, runners, scripts, a Go module or a Makefile.

The evaluation source is always a CLL of recorded interactions. A native benchmark or dataset (e.g. a customer-service task set) is not evaluated directly: its interactions are first backfilled into a CLL as Capsules, and the generated skill then evaluates that CLL exactly like any other source. Axes and judging remain the compiler's job even when the dataset ships its own scoring contract.

## Resolve the user's intent

Accept natural language. Derive the internal contract yourself; do not ask the user to write a spec. Use supplied examples and accessible sources before asking questions. Ask a small, focused question only when a material choice remains unresolved.

Resolve:
- The scenario, value proposition and evaluation unit: what should improve, for whom, and which individual outcome is evaluated?
- Desired-outcome authority: declared task criteria or independent evidence; what establishes success, and what was knowable at execution time?
- Agent-outcome source: where the actual answer or action is recorded and how it is authenticated.
- Access: for CLL, the named Capsule CLI profile. Do not ask for database credentials or a caller-written adapter. Discover existing access to external evidence separately; a storage profile does not grant GitHub access.
- Judgment policy: observable axes, applicability, insufficient-evidence behavior and aggregation.

If access is missing from the request, explicitly resolve it during intake. Obtain CLI command/output semantics from [capsule-cli.md](references/capsule-cli.md). Inspect a representative source through the CLI when available, but do not mistake stored context or an agent-authored answer for independent truth.

Selection belongs to execution, not compilation. A CLL-backed skill accepts a profile name and either an exclusive/inclusive sequence range `(after, through]` or an append-time window such as the last seven days. Never hardcode the experiment's profile, IDs, range, dates, secrets or machine paths into a reusable bundle.

`target_mode` is `evidence_derived` or `declared`. `aggregation` is `none`, `all_required` or `native`. Default to `none` unless aggregation is requested and justified. `native` requires the benchmark's existing scoring contract; preserve its task/trial/reward semantics rather than inventing a replacement score. A benchmark's trials originate outside CLL and are backfilled into it before evaluation.

## Generate the bundle

Create only these resources:
- `SKILL.md`: scenario purpose, accepted runtime inputs and actionable execution steps. The host agent performs selection, verification, independent extraction, judging and publication; do not delegate that workflow to a custom program.
- `axes.json`: each axis's ID, link to the value proposition, applicability, required evidence, pass/fail boundaries, missing-evidence behavior and role.
- `resolved-spec.json`: the resolved scenario, evaluation unit, target and aggregation policies, source/reference locations, required and optional runtime inputs, and honest limitations. This is compiler output, not user homework.
- `references/source.md`: observed source semantics, case/run identity, exact original-content bindings and independent evidence access. Do not invent mappings. For a dataset backfilled into the CLL, document the mapping from dataset record to Capsule artifacts/bindings so the same get/verify path applies.
- `references/execution.md`: adapt [execution.md](assets/execution.md) to the scenario without weakening independence or verification.
- `references/capsule-cli.md`: the CLI contract, copied from this compiler's reference.
- `bin/capsule`: the compatible CLI executable when distributing a self-contained bundle. This is the only program in the bundle; configuration and credentials stay on the execution host.

Use outcome-linked axes, not an output-feature checklist. Separate desired and agent outcome records, with evidence IDs per claim. Do not claim that a proxy measures actual time saved or risk reduced.

## Exercise the generated skill

Run the generated SKILL.md using the host agent and CLI directly. Do not replace missing instructions with a bespoke runner. For Alchemy, exercise CLL selection, get/verify, separate outcome records, judging, report publication and readback. Keep private run results outside the compiler and bundle.

Validate the compiler with a fresh evaluation under the newly generated bundle: acquire evidence, extract desired and agent outcomes independently, judge the current axes, create a new report and publish a new evaluation Capsule. Never substitute a previous evaluation report or its judgments for this execution. Record the actual bundle content digests in the report and distinguish missing evidence from execution errors.

The compiler is the only editable source of evaluation instructions. Generated bundles are immutable outputs: fix this compiler or its references and assets, then regenerate the whole bundle. Never patch a generated skill or add historical-evaluation replay as a shortcut.
