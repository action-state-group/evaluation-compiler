# evaluation-compiler

A Claude Code skill that compiles a natural-language **scenario + value
proposition** into evaluation **axes** and an executable **evaluation-skill
bundle**. The output is instructions for an agent, not a program: the generated
bundle's host agent selects a range of cases (a sequence range or time window),
verifies each, extracts outcomes in three isolated contexts, judges against the
axes, and publishes one evaluation Capsule per case.

The evaluation source is always a **CLL** (Capsule Ledger Log) of recorded agent
interactions, read through the Capsule CLI. A plain dataset (e.g. a customer-service
task set) is first **backfilled** into a CLL as Capsules and then evaluated the same
way.

## Contents

- [`SKILL.md`](SKILL.md) — the compiler skill (intake, bundle generation, exercise).
- [`assets/execution.md`](assets/execution.md) — the per-case execution template
  adapted into each generated bundle.
- [`assets/aggregation.md`](assets/aggregation.md) — the cross-case aggregation
  template; adapted into a second **aggregation** bundle only when
  `cross_case_aggregation` is requested. It reduces `evaluation-report/v1` Capsules
  into one `evaluation-summary/v1` Capsule, never re-judging.
- [`references/capsule-cli.md`](references/capsule-cli.md) — the Capsule CLI contract
  copied verbatim into bundles.
- [`DEMO.md`](DEMO.md) — end-to-end reproductions: an Alchemy investigation over an
  existing CLL, and a tau2 customer-service evaluation over a local SQLite CLL
  (create → backfill → compile → evaluate), plus CLL checkpointing and witnessing.
- [`tools/tau2-backfill/`](tools/tau2-backfill/) — operator-side data-prep for Demo B:
  maps shipped tau2 benchmark runs into seal requests. A repo tool, not bundle
  material.

## Boundaries

The compiler is the only editable source of evaluation instructions. Generated
bundles are immutable outputs — fix the compiler and regenerate, never patch a
bundle. The host agent uses the Capsule CLI and ordinary tools; no helper programs,
runners, or scripts are generated. Operator-side data-prep (e.g. `tools/`) may live
in this repo but is never copied into a bundle: `assets/` and `references/` are the
only bundle-source material.
