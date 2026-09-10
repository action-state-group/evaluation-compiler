---
marp: true
title: Evaluation-compiler — provable agent evaluation
paginate: true
theme: default
---

<!--
Render:  npx @marp-team/marp-cli@latest slides/demo-deck.md -o demo-deck.html
         (--pdf, or --pptx for PowerPoint; --pptx-editable needs LibreOffice/soffice)
Live demo: run the fenced commands top-to-bottom in ONE terminal; shell variables
(TAU2, EC, DEMO, …) persist across the blocks. Every command here is copy-paste
from DEMO.md and has been run verbatim.
-->

# Provable agent evaluation
## evaluation-compiler + Agent Action Capsules

Turn a **scenario + value proposition** into evaluation **axes** and an
executable **evaluation skill**, run it over a **CLL** of recorded agent
interactions, and publish a **signed, verifiable evaluation report Capsule**.

Two demos:
- **A — Alchemy**: evaluate a production investigation (CLL already exists)
- **B — tau2**: evaluate a public benchmark (backfill a local CLL first) — *live*

---

## The pieces

- **Agent Action Capsule (AAC)** — a signed, JCS-canonical, content-addressed
  record of one agent action (IETF I-D `draft-mih-scitt-agent-action-capsule-04`).
- **CLL (Checkpointed Local Log)** — an append-only MMR log of Capsule IDs;
  anchorable to a public **witness**.
- **capsulectl** — the CLI: seal / store / publish / list / verify / checkpoint.
- **evaluation-compiler** — compiles *value proposition → axes → skill bundle*;
  the per-case skill selects a **range** of cases (a sequence range or time
  window), verifies each, extracts **desired** vs **agent** outcome in isolated
  contexts, judges, and publishes **one `evaluation-report/v1` Capsule per case**.
  When cross-case aggregation is asked for, it also generates a second
  **aggregation skill** that reduces those reports into one
  `evaluation-summary/v1` Capsule.

*Source of truth is the CLL; every input and output is signed and re-verifiable.*

---

## The workflow (both demos)

```
scenario + value proposition
        │  evaluation-compiler
        ▼
   axes.json + evaluation skill bundle
        │  run skill over the CLL
        ▼
 select a range → for each case: verify Capsule → extract desired outcome (source of truth)
                                 → extract agent outcome (from the Capsule)
                                 → judge against axes
        ▼
 publish one evaluation-report/v1 Capsule per case  → checkpoint / witness
```

The selection is a sequence range `(after, through]` or a time window; the pipeline
above repeats per case. Desired and agent outcomes are extracted in **separate
contexts**; the judge never conflates "what should happen" with "what the agent did."

---

## Setup 1/3 — toolchain (start from nothing)

Need **git**, **Go 1.27+** (the CLI's `go.mod` floor; Go 1.21+ also works — it
auto-fetches the pinned toolchain), **python3** (stdlib only — to read JSON output).
Run in one terminal.

```sh
# macOS (Homebrew). Linux: apt/dnf install git golang python3; or https://go.dev/dl
brew install go git python3

# make `go install` binaries findable on PATH (add this line to your shell profile)
BIN="$(go env GOBIN)"; export PATH="$PATH:${BIN:-$(go env GOPATH)/bin}"
```

No API key, no `pip install`: `capsulectl` generates the signing keys itself.

---

## Setup 2/3 — clone the repos

```sh
mkdir -p ~/GitHub && cd ~/GitHub
git clone https://github.com/action-state-group/capsule-cli.git
git clone https://github.com/action-state-group/evaluation-compiler.git

# tau2-bench is 1.8 GB fully; sparse-clone only what the demo reads (~30 MB)
git clone --filter=blob:none --sparse --depth 1 \
  https://github.com/sierra-research/tau2-bench.git
git -C tau2-bench sparse-checkout set --no-cone \
  /data/tau2/results/final/claude-3-7-sonnet-20250219_retail_default_gpt-4.1-2025-04-14_4trials.json \
  /data/tau2/domains/retail
```

The two `action-state-group` repos must be **public** (or the audience needs
access). `tau2-bench` is public.

---

## Setup 3/3 — build & install the CLI

```sh
GOWORK=off go -C ~/GitHub/capsule-cli install ./cmd/capsulectl

capsulectl --version    # capsulectl version 0.1.0-dev  ← if "command not found", re-run the PATH export
```

Nothing else is global: profiles live under `~/.config/capsule/`, the demo's CLL
and keys under `~/.local/share/evaluation-runs/`. No database server, no cloud,
no API key for the live path.

---

## Demo B — tau2 (public benchmark)

**Why tau2 needs a step Demo A doesn't:** tau2 is a *dataset*, not a CLL. But
tau2-bench ships **real recorded runs** (`data/tau2/results/final/*.json`) — an
agent (claude-3-7-sonnet) against a user simulator (gpt-4.1). We **backfill**
those real interactions into a local SQLite CLL, then evaluate exactly like A.

**Compiler input**
- Value proposition: *"Give the customer a clear, empathetic service experience
  that fully resolves their request in a single interaction with minimal effort."*
- `target_mode: declared` — desired outcome = the tau2 task scenario, read by
  `task_id`, never seeing the transcript. tau2's own reward is **not** used.

**Generated axes (`aggregation: none`)**
1. `request_resolution` · 2. `effort_and_containment` · 3. `communication_clarity`

---

## Demo B · B1 — create a local SQLite CLL  *(live)*

```sh
umask 077
DEMO=~/.local/share/evaluation-runs/tau2-eval
# re-runnable: delete the old tau2 SQLite CLL and profile first
rm -f "$DEMO"/store.db* ; rm -rf "$DEMO"
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/capsule/profiles/tau2demo.yaml"
mkdir -p "$DEMO/keys"

# the CLI generates the signing key (writes the seed 0600; prints the public key)
PUB=$(capsulectl key generate --output "$DEMO/keys/tau2.ed25519" \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["public_key"])')

capsulectl profile create --name tau2demo --type sqlite \
  --sqlite-path "$DEMO/store.db" \
  --namespace tau2 --log-id tau2-retail-20260909 \
  --signing-key-file "$DEMO/keys/tau2.ed25519" --trusted-key "$PUB"
capsulectl store init --profile tau2demo
```

---

## Demo B · B2 — backfill every task, publish to the CLL  *(live)*

```sh
TAU2=~/GitHub/tau2-bench
EC=~/GitHub/evaluation-compiler
RES="$TAU2/data/tau2/results/final/claude-3-7-sonnet-20250219_retail_default_gpt-4.1-2025-04-14_4trials.json"

# one seal request per task (its trial-0 run) — 114 for retail
python3 "$EC/tools/tau2-backfill/backfill.py" --results "$RES" --out "$DEMO/backfill"

# publish each as one CLL entry
for f in "$DEMO"/backfill/*.json; do capsulectl publish --profile tau2demo --request "$f" >/dev/null; done

capsulectl cll list --profile tau2demo --after 0 --limit 1000 \
  | python3 -c 'import sys,json;print("CLL entries:",len(json.load(sys.stdin)["entries"]))'
```

Expected: `wrote 114 seal requests …` → `CLL entries: 114`.
Capsule IDs are content-addressed: **seq 1 = `e9fa572d…`** (task 0),
**seq 2 = `2daa93d9…`** (task 1) — same with any signing key.

---

## Demo B · read one back — signed & verifiable  *(live)*

```sh
# the seq-1 Capsule id (task 0)
ID=$(capsulectl cll list --profile tau2demo --after 0 --through 1 \
     | python3 -c 'import sys,json;print(json.load(sys.stdin)["entries"][0]["capsule_id"])')

capsulectl get    --profile tau2demo --capsule-id "$ID" --raw --output rec.json
capsulectl verify --profile tau2demo --capsule rec.json
# identity + producer signature + payload binding all verify;
# rec.json shows case / provenance / the real agent_interaction transcript
```

`verify` re-checks the content-address, the Ed25519 producer signature, and that
the bound `payload` matches its `agent_input_digest` — offline, no trust in us.

---

## Demo B · B3 — compile axes & evaluate  *(presenter-driven, not copy-paste)*

B3 is an **agent** step, not a shell command: it runs inside **Claude Code** with
the `evaluation-compiler` skill (from that repo), which needs its own agent host
and model access — so it is driven by the presenter, not pasted by the audience.

1. Invoke the **evaluation-compiler** skill (value proposition + profile
   `tau2demo`) → generates `axes.json`, `references/source.md`, the skill bundle.
2. Run the generated skill: `selection=(1,2]` → it verifies the seq-2 Capsule
   (`2daa93d9…`, task 1), reads the **declared** desired outcome from the dataset
   by `task_id`, extracts the **agent** outcome from the real transcript, judges
   the three axes, and **publishes an `evaluation-report/v1` Capsule at seq 115**.

Only *after* B3 has run does seq 115 exist; then read the report back like any
Capsule:

```sh
capsulectl cll list --profile tau2demo --after 114 --through 115
ID=$(capsulectl cll list --profile tau2demo --after 114 --through 115 \
     | python3 -c 'import sys,json;e=json.load(sys.stdin)["entries"];print(e[-1]["capsule_id"] if e else "")')
capsulectl get --profile tau2demo --capsule-id "$ID"
```

---

## The evaluation report Capsule (`evaluation-report/v1`)

Bound payload of the published report:

- `evaluation_identity`, `case_run_identity`, `source_selection` (store/log/entries)
- `bundle_provenance` — SHA-256 of every bundle file (which axes/skill produced it)
- **`desired_outcome`** + **`agent_outcome`** — each claim cites evidence ids
- **`axis_judgments`** — pass / fail / unjudgeable + rationale per axis
- `aggregate` (null here), `verification_references`, `limitations`

The report is itself a signed Capsule in the CLL — shareable as a permalink the
buyer can **verify offline**, no access to the vendor's systems.

---

## A real report — task 1, validated run

Source `2daa93d9…` (seq 2). Customer wants keyboard→clicky/RGB/full-size **and**
thermostat→Google-Home, with a declared fallback: *only the thermostat if no such
keyboard exists.* No matching keyboard was in stock → agent took the fallback,
confirmed before mutating, exchanged only the thermostat.

```text
axis_judgments (excerpt — full report is the bound payload of the Capsule):
  request_resolution     = pass   honored the fallback branch
                                   (no clicky/RGB/full-size keyboard → exchanged only the thermostat)
  effort_and_containment = pass   single session; no email → adapted auth to name+zip
  communication_clarity  = pass   restated the exchange, confirmed $13.46 refund, required "yes"
  aggregate              = null   (within-case aggregation: none)
```

→ `evaluation-report/v1` Capsule **`c308ebed…` at seq 115**, payload verified
identical on readback. Desired/agent/judge each ran in an **isolated context**.

---

## Aggregate across cases → `evaluation-summary/v1`

One report per case answers *"was this run good?"* A benchmark also asks *"how good
across all tasks?"* — the **cross-case** roll-up.

- A **second compiler output** (generated when `cross_case_aggregation ≠ none`): an
  **aggregation skill** whose input is the `evaluation-report/v1` Capsules, **not**
  the source interactions.
- It verifies each report, reduces `axis_judgments` across cases (per-axis pass rate;
  `all_required` / `native` overall), and publishes one **`evaluation-summary/v1`**
  Capsule back into the CLL — itself signed, checkpointable, witnessable.
- Re-aggregate any subset without re-judging; the contributing report ids are recorded.

*114 report Capsules → 1 summary Capsule.* (Judging all 114 is 114 runs; the validated
run here judged one, seq 115.)

---

## Checkpoint the CLL  *(live, offline — no witness)*

```sh
CKEY="$DEMO/keys/tau2-checkpoint.ed25519"
CPUB=$(capsulectl key generate --output "$CKEY" \
       | python3 -c 'import sys,json;print(json.load(sys.stdin)["public_key"])')

capsulectl profile update --profile tau2demo \
  --checkpoint-signing-key-file "$CKEY" --checkpoint-trusted-key "$CPUB"

# NO-WITNESS path: create is LOCAL only (no endpoint configured). To WITNESS the same
# MMR size instead, SKIP this create — the next slide sets the endpoint FIRST, because a
# delivery is enqueued only by the first create at a size after the endpoint is set.
capsulectl cll checkpoint create --profile tau2demo
# with the 114 backfilled entries (B3 not run in the copy-paste path):
#   {"checkpoint":224,"indexed_sequence":114, "statement":"<COSE>"}
# `checkpoint` is the MMR size, not the entry count; if B3 has appended seq 115 it is 225/115.
```

*Offline vs witnessed are alternative paths for a given MMR size — don't create the same size twice.*

---

## Anchor to Steven's public witness  *(live — real append)*

```sh
# resolve the witness authority public key (verify receipts against this)
curl -s https://witness.agentactioncapsule.org/anchor/authority-pubkey
# -> {"pubkey_hex":"39bb654c9dc0afe1c0edef0deffaa69099b8518836c9ba26e0491535840f96b5",
#     "key_id":"19a9ab3e02fad55c"}

capsulectl profile update --profile tau2demo \
  --checkpoint-endpoint https://witness.agentactioncapsule.org \
  --checkpoint-public-key 39bb654c9dc0afe1c0edef0deffaa69099b8518836c9ba26e0491535840f96b5

# endpoint is now set; this must be the FIRST create at this MMR size (don't run the
# offline create on the previous slide for the same size, or append an entry first)
CP=$(capsulectl cll checkpoint create --profile tau2demo)          # the ONLY create at this size
SIZE=$(echo "$CP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["checkpoint"])')
STMT=$(echo "$CP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["statement"])')   # reused next slide
capsulectl cll checkpoint publish --profile tau2demo --checkpoint "$SIZE"   # -> {"state":"verified","receipt":{…}}
capsulectl cll checkpoint status  --profile tau2demo --checkpoint "$SIZE"   # re-verifies stored receipt, offline
```

**Ran it live:** checkpoint **225/115** → `state=verified`, countersigned at witness
`tree_size 1062→1063`. Size 225 was *fresh* — the seq-115 report advanced it past the
offline 224 checkpoint. A delivery is enqueued only by the **first `create` at a size
after the endpoint is set**; if you already checkpointed this size offline, append an
entry first. `publish` appends to a public, append-only log — run it only when you mean it.

---

## Fetch the witness record; re-verify locally

The witness *receipt* was already verified against the authority key at `publish`
(prev slide). Here: fetch the witness's public record, and independently re-verify
the **local** checkpoint offline.

```sh
# 1. fetch the witness's countersigned checkpoint for this log (prints only)
curl -s https://witness.agentactioncapsule.org/checkpoints/tau2-retail-20260909
#   -> {"mmr_size":225,"prev_size":224,"tree_size":1063,"equivocations":[],
#       "root":"45476a60b940a88d1595c7a440b79374e9a7a32ccc8fb280ff5e4325ed75c693",
#       "receipt_b64":"0oRHogEnGQGLAaEZAYyhIIFYkIMZBCcZBCaE…",   # real COSE receipt
#       "key_id":"02698f0b010cfe504df82c375c0a226f92cd8128fb5d3d72ea3aed4282129cc5"}
#   key_id above = this log's checkpoint key; the receipt verifies against the
#   witness authority key 39bb654c…f96b5 resolved on the previous slide.

# 2. re-verify the LOCAL checkpoint offline (reuse $STMT from the single create — no re-create)
python3 -c 'import json,sys;open("/tmp/proof.json","w").write(json.dumps({"checkpoint":sys.argv[1]}))' "$STMT"
capsulectl cll verify --profile tau2demo --proof /tmp/proof.json
#   -> checkpoint_signature_and_trust=passed, embedded_consistency=passed, log_id=passed
```

The witness anchors the **MMR root**, not each Capsule. A single Capsule's inclusion
would need a local per-Capsule audit path; this CLI build ships none, so inclusion is
**not proven** (`inclusion=not_performed`) — only the checkpoint, hence the whole MMR,
is. `GET /v1/inclusion/{capsule_id}` is the direct-register surface and 404s a CLL Capsule.

---

## Demo A — Alchemy (production CLL)  *(concept; internal, not copy-paste)*

Same workflow, source is an **existing production CLL** of real investigations.
- Value proposition: *"Under limited evidence, reduce ticket uncertainty and
  guide the handler to the correct next step faster and more safely."*
- `target_mode: evidence_derived` — truth comes from the live tracker issue
  (independent evidence), not a declared spec.
- Axes: `uncertainty_reduction`, `next_step_correctness`, `safety_calibration`.

**Real validated run:** source `9c4a2524…` (seq 165, tracker #82049) → evaluation
Capsule `cbcb24e9…` (seq 169); judgments `uncertainty_reduction=pass`,
`next_step_correctness=fail`, `safety_calibration=pass`, `aggregate=null`.

---

## Recap

- **One workflow**, two sources: an existing CLL (A) or a public dataset
  backfilled into a CLL (B).
- Axes are **compiled from the value proposition**, not a hand-checklist and not
  the benchmark's native score.
- Every artifact — source interaction, desired/agent outcome, judgment — is a
  **signed, content-addressed Capsule** in a checkpointable CLL.
- The evaluation report **verifies offline** and can be **witnessed** on a public
  transparency log.

Repos: `action-state-group/capsule-cli`, `action-state-group/evaluation-compiler`,
`sierra-research/tau2-bench`. Full runnable script: `evaluation-compiler/DEMO.md`.
