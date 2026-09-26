# The four skills — draft text

This directory holds draft `SKILL.md`/`AGENTS.md` text for the skills this repo is growing
into: the evolution of the existing compiler, and the two cron-run skills it compiles. It is
additive — the repo's root `SKILL.md` (the `evaluation-compiler` skill, still live and still
the thing generated bundles are exercised against) is untouched. These drafts are for review as
text; the cutover (retiring the root file, moving assets, renaming the repo to
`evidencebook-skills`) is a separate, later step.

## The four skills, and where each one lives

| # | Skill | Here | Status |
|---|---|---|---|
| 1 | `evidence-contract-compile` | [`evidence-contract-compile/SKILL.md`](evidence-contract-compile/SKILL.md) | drafted, unwired |
| 2 | `daily-judge-and-close` | [`daily-judge-and-close/SKILL.md`](daily-judge-and-close/SKILL.md) | drafted, not runnable yet (see verb table) |
| 3 | `weekly-blind-expert` | [`weekly-blind-expert/SKILL.md`](weekly-blind-expert/SKILL.md) | drafted, not runnable yet (see verb table) |
| 4 | `capsulectl` (thin verb skill) | **not here** | ships with `capsule-cli` at `skills/capsulectl/`, generated from `spec.yaml` |

Skill 4 is consumed, not vendored. Nothing in this repo copies its `SKILL.md`/`AGENTS.md` or
`spec.yaml` — a customer installs `capsulectl` and gets that skill with it. Duplicating the
files here would create a second copy that drifts from the binary it describes.

## Why skills 1–3 are not `spec.yaml`-rendered

`capsule-cli` renders skills from a `skill-spec/v0` document (`skills/SKILL-SPEC.md` there), so
that `SKILL.md` and `AGENTS.md` come out byte-identical from one source. That format is scoped,
by its own text, to thin tool-calling skills:

> "A **thin, tool-calling skill** — the shape this format is for — may call verbs, validate a
> contract, request evidence, verify a bundle, or inspect a result. It never reasons about
> business meaning... Contrast a **reasoning-heavy** skill (a compiler that decomposes a value
> proposition into axes and writes new instructions) — that shape does not fit this
> schema... See `evaluation-compiler`'s `SKILL.md`."

`evidence-contract-compile` *is* that reasoning-heavy compiler (it is `evaluation-compiler`,
evolved). `daily-judge-and-close` and `weekly-blind-expert` judge, sample, and blind a human —
also reasoning, not a closed verb list. Forcing any of the three into `skill-spec/v0` would mean
either misstating their verb surface or stripping the reasoning out.

So all three are hand-authored `SKILL.md` prose, in the same voice and rigor as the existing
`evaluation-compiler` skill, with `AGENTS.md` a literal byte-identical copy — Claude Code and
Codex read the same text. Only skill 4 goes through `skillgen`, because only skill 4 is thin.
**Open question for review:** whether the spec format should grow a shape for reasoning-heavy
skills, or whether hand-authored-plus-copy is the intended pattern for them.

## Verb dependency status (checked against `capsule-cli` `skills/capsulectl/spec.yaml`)

Ships today: `verify`, `contract validate`, `discover`, `plugin ls`, `cll list`, `cll append`,
`get`, `publish`, `seal`. **Not yet shipped:** `close --period day|week [--peer] --since-last`,
`reconcile --peer --period`, `judge pin`, `judge drift`, `calibration summarize`, `request`,
`respond` — these come with the book-verbs work in `capsule-cli` and the Go EvidenceBook
reference module. `evidence-contract-compile` is runnable today (it only needs `contract
validate` + `publish`). `daily-judge-and-close` and `weekly-blind-expert` are **not** runnable
today — every consequential step they take (`close`, `judge pin`, `calibration summarize`) calls
a verb that does not exist yet. The drafts are written against the verb names that work has
already committed to, so no rewrite is expected when the verbs land — only the "not yet
available" caveats come out.

The `capsulectl-engine` plugin (`fold run --clause ID --profile X`, wrapping `capsule-engine`
folds for the `recomputed` tier) is also not built yet. `daily-judge-and-close` documents calling
it through `plugin ls` discovery once it exists.

## Record family — named here, not defined here

`contract-compile/v1`, `evaluation-report/v1`, `close/v1`, `sample-manifest/v1`,
`human-rating/v1`, `calibration-summary/v1` are referenced below by name and shape only. Their
JSON schemas belong to the judge record family spec; this repo does not define or fork a second
copy, and record names are kept in step with the monthly aggregation stage that consumes them.

## Open tension with `docs/calibration-sampling-spec.md`

This repo's own `docs/calibration-sampling-spec.md` computes a population-weighted judge
accuracy `Â` and a bias-corrected pass rate `p̂` — i.e. it scores the judge. The design for
`weekly-blind-expert` is explicit that `calibration-summary/v1` is a `derived_metric`:
"agreement as k of n, never a score." The two documents disagree about what calibration is
allowed to output. `weekly-blind-expert/SKILL.md` follows the k-of-n rule; the estimator math in
`docs/calibration-sampling-spec.md` is left in place, unedited. Reconciling the two belongs with
the judge record family spec, not with either skill.

## Not in these drafts

An end-to-end fresh-environment run, retiring the older compiler and judge programs, the repo
rename, and turning `demo/week-eval` (and a blind-expert demo) into exercise scripts for the two
cron skills all depend on the verbs above landing. None of that is attempted here.
