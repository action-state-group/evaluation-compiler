# evaluation-compiler

A Claude Code skill that compiles a natural-language **scenario + value
proposition** into evaluation **axes** and an executable **evaluation-skill
bundle**. The output is instructions for an agent, not a program: the generated
bundle's host agent selects a case, verifies it, extracts outcomes in three
isolated contexts, judges against the axes, and publishes a new evaluation Capsule.

The evaluation source is always a **CLL** (Capsule Ledger Log) of recorded agent
interactions, read through the Capsule CLI. A plain dataset (e.g. a customer-service
task set) is first **backfilled** into a CLL as Capsules and then evaluated the same
way.

## Contents

- [`SKILL.md`](SKILL.md) — the compiler skill (intake, bundle generation, exercise).
- [`assets/execution.md`](assets/execution.md) — the execution template adapted into
  each generated bundle.
- [`references/capsule-cli.md`](references/capsule-cli.md) — the Capsule CLI contract
  copied verbatim into bundles.
- [`DEMO.md`](DEMO.md) — end-to-end reproductions: an Alchemy investigation over an
  existing CLL, and a tau2 customer-service evaluation over a local SQLite CLL
  (create → backfill → compile → evaluate), plus CLL checkpointing and witnessing.

## Boundaries

The compiler is the only editable source of evaluation instructions. Generated
bundles are immutable outputs — fix the compiler and regenerate, never patch a
bundle. The host agent uses the Capsule CLI and ordinary tools; no helper programs,
runners, or scripts are generated.
