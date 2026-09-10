# Evaluation-compiler demos

Two reproductions of the same compiler workflow. In both, the evaluation source
is a **CLL** (Capsule Ledger Log) read through the Capsule CLI; the compiler turns
a scenario + value proposition into an evaluation-skill bundle, and the bundle's
host agent selects, verifies, extracts (three isolated contexts), judges, and
publishes a new evaluation Capsule.

- **Demo A – Alchemy**: the CLL already exists (production investigations).
- **Demo B – tau2**: a plain dataset, so its interactions are first **backfilled**
  into a local **SQLite** CLL, then evaluated exactly like Alchemy.

## Prerequisites

```sh
# Capsule CLI (MySQL + SQLite backends). Installs the `capsulectl` binary; the
# older builds installed it as `capsule`, which collided with the Python
# capsule-emit CLI on PATH.
CAPSULE_CLI=~/GitHub/capsule-cli   # cloned capsule-cli repo
git -C "$CAPSULE_CLI" pull && (cd "$CAPSULE_CLI" && go install ./cmd/capsulectl)
# remove any stale `capsule` from a previous install so it no longer shadows capsulectl
BIN="$(go env GOBIN)"; GOPATH="$(go env GOPATH)"; rm -f "${BIN:-${GOPATH%%:*}/bin}/capsule"
capsulectl --version    # capsulectl version 0.1.0-dev
```

- Demo A: the `alchemy` MySQL profile configured, and `gh` authenticated for
  `github.ibm.com` (independent business evidence).
- Demo B: no database server — SQLite is a single local file. tau2 dataset at
  `~/GitHub/tau2-bench/data/tau2/domains/…` and the shipped benchmark runs at
  `~/GitHub/tau2-bench/data/tau2/results/final/…` (plain-tracked JSON; the retail
  file alone is ~24 MB, so a full clone is required, not a sparse `domains/` one).

---

## Demo A — Alchemy investigation (existing CLL)

Value proposition: *"Under limited evidence, reduce ticket uncertainty and guide
the handler to the correct next step faster and more safely."* Evaluation unit:
one investigation trigger/run. `target_mode=evidence_derived`, `aggregation=none`.

1. **Compile the bundle.** Invoke the `evaluation-compiler` skill with the scenario
   above and the access facts (profile `alchemy`). It writes the bundle to
   `~/.local/share/evaluation-bundles/alchemy-investigation/`
   (`SKILL.md`, `axes.json`, `resolved-spec.json`, `references/{source,execution,capsule-cli}.md`,
   `bin/capsule`).

2. **Run the generated skill** in a fresh agent, passing only runtime inputs:
   `profile=alchemy`, `selection=(164,165]`, `run_dir=<private dir outside the bundle>`.
   The skill performs, using `./bin/capsule` and `gh`:

   ```sh
   ./bin/capsule cll list --profile alchemy --after 164 --through 165 --limit 1000
   ID=$(./bin/capsule cll list --profile alchemy --after 164 --through 165 --limit 1000 | python3 -c 'import sys,json;print(json.load(sys.stdin)["entries"][-1]["capsule_id"])')
   ./bin/capsule get    --profile alchemy --capsule-id "$ID" --raw --output rec.json
   ./bin/capsule verify --profile alchemy --capsule rec.json      # identity/signature/bindings
   gh api --hostname github.ibm.com /repos/lakehouse/tracker/issues/82049
   gh api --hostname github.ibm.com /repos/lakehouse/tracker/issues/82049/comments
   # three isolated sub-agents: desired outcome, agent outcome, judge
   ./bin/capsule publish --profile alchemy --request seal-request.json
   ./bin/capsule get/verify + cll list        # read back the new evaluation Capsule
   ```

   Bindings: `effect_request → effect.request_digest`, `effect_response →
   effect.response_digest`; the `payload` artifact is **unbound** and is not
   authenticated evidence. Verification uses the `--raw` record (readable JSON
   re-encodes request bytes).

**Actual result of the validated run** (`run-20260909T070002Z`): source capsule
`9c4a2524…` at CLL **sequence 165** (tracker #82049); new evaluation Capsule
`cbcb24e9…` at CLL **sequence 169**, payload verified identical; judgments
`uncertainty_reduction=pass`, `next_step_correctness=fail`, `safety_calibration=pass`,
`aggregate=null`.

---

## Demo B — tau2 (backfill a local SQLite CLL, then evaluate)

tau2 supplies the dataset (customer-service task scenarios and gold criteria) and
its own recorded benchmark runs under `data/tau2/results/final/`. Axes are the
compiler's job. Value proposition used here: **customer experience** — *"give the
customer a clear, empathetic service experience that fully resolves their request
in one interaction with minimal effort."*

B1 and B2 below are verified and reproducible against the shipped tau2 results;
B3 is the compiler run over that CLL (log `tau2-retail-20260909`).

### B1. Create a local SQLite CLL

```sh
umask 077   # new key/config files are created owner-only, no world-readable window
DEMO=~/.local/share/evaluation-runs/tau2-eval
# re-runnable clean slate (store init / profile create are not idempotent):
# delete the old tau2 SQLite CLL and the tau2demo profile first
rm -f "$DEMO"/store.db*                                             # the old SQLite CLL (+ WAL/SHM)
rm -rf "$DEMO"                                                      # keys/, backfill/, any prior run
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/capsule/profiles/tau2demo.yaml"
mkdir -p "$DEMO/keys"
# generate the producer signing key (CLI writes the seed file 0600; prints the public key)
PUB=$(capsulectl key generate --output "$DEMO/keys/tau2.ed25519" \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["public_key"])')

capsulectl profile create --name tau2demo --type sqlite \
  --sqlite-path "$DEMO/store.db" \
  --namespace tau2 --log-id tau2-retail-20260909 \
  --signing-key-file "$DEMO/keys/tau2.ed25519" --trusted-key "$PUB"
capsulectl store init --profile tau2demo      # generates + pins store_id into the profile
```

The SQLite store keeps the artifact tables and the CLL log in one file
(`store.db`), opened with `foreign_keys`, `busy_timeout`, and WAL.

### B2. Backfill tau2 interactions as Capsules

Backfill reads **only shipped tau2 results**: no agent run, no user simulator,
**no model/LLM API key**, and nothing synthesized. tau2-bench is a runnable
benchmark and ships its recorded runs under `data/tau2/results/final/*.json`;
each file holds `simulations[]` for every `(task_id, trial)`, with the real agent
+ user-simulator transcript. `tools/tau2-backfill/backfill.py` takes just the
results file and an output dir, and writes one `capsule-seal-request/v1` per task
(its trial-0 run) as `task-<id>.json`. The bound `payload` carries the real
`agent_interaction` (transcript + tool calls, with each call's `requestor`
attribution), a `case` block, and `provenance`. Domain is read from the results
file; the Capsule's operator/developer are fixed backfill-provenance labels.

```sh
TAU2=~/GitHub/tau2-bench            # cloned tau2-bench repo
EC=~/GitHub/evaluation-compiler     # this repo
RES="$TAU2/data/tau2/results/final/claude-3-7-sonnet-20250219_retail_default_gpt-4.1-2025-04-14_4trials.json"
python3 "$EC/tools/tau2-backfill/backfill.py" --results "$RES" --out "$DEMO/backfill"
# publish every backfilled interaction (one per task) as one CLL entry
for f in "$DEMO"/backfill/*.json; do capsulectl publish --profile tau2demo --request "$f" >/dev/null; done
capsulectl cll list --profile tau2demo --after 0 --limit 1000 \
  | python3 -c 'import sys,json;print("CLL entries:",len(json.load(sys.stdin)["entries"]))'
```

The retail file backfills **114 tasks** → 114 CLL entries. Capsule IDs are
content-addressed (JCS over the metadata and payload digest), so they do **not**
depend on the signing key: **seq 1** = `e9fa572d…` (task 0), **seq 2** =
`2daa93d9…` (task 1). `payload` is bound (`agent_input_digest`) and
therefore authenticated. The desired outcome for judging is the task's
`evaluation_criteria`, which the judge reads independently from the dataset by
`payload.case.task_id`. Neither it nor tau2's own `reward_info` (the benchmark's
score, which the compiler does not consume) is placed in the bound payload. (To
mirror Alchemy's split exactly one may instead set
`capsule.effect` with `effect_request`/`effect_response` artifacts; the payload
form above needs no manual digest computation.)

### B3. Compile and run the evaluation

1. Invoke the `evaluation-compiler` skill with the customer-experience value
   proposition and access facts (profile `tau2demo`). It generates the bundle at
   `~/.local/share/evaluation-bundles/tau2-investigation/` — `axes.json`
   (request_resolution, effort_and_containment, communication_clarity; no aggregate),
   `references/source.md` (the dataset→Capsule payload mapping), `resolved-spec.json`,
   `references/{execution,capsule-cli}.md`, `bin/capsule`.
2. Run the generated skill in a fresh agent with `profile=tau2demo`,
   `selection=(1,2]`, `dataset_path=…/retail/tasks.json`, `run_dir=…/tau2-eval/run`.
   It enumerates the SQLite CLL, `get --raw` + `verify`s the seq-2 Capsule
   (`2daa93d9…`, task 1), reads the desired outcome from the dataset by
   `payload.case.task_id`, extracts the agent outcome from the real
   `agent_interaction` transcript, judges the three axes, and publishes a new
   `evaluation-report/v1` Capsule at **sequence 115** (one past the 114 backfilled
   entries) — identical commands to Demo A, only the profile differs.

**Actual result of the validated run** (`run-20260910T170818Z`, task 1 / trial 0,
the seq-2 source `2daa93d9…`): the desired outcome, agent outcome and judge ran in
three isolated contexts. The customer wanted the keyboard exchanged to a
clicky/RGB/full-size variant and the thermostat to a Google-Home model, with a
declared fallback to exchange only the thermostat if no such keyboard exists. No
matching keyboard was available, so the agent correctly took the fallback branch,
confirmed before mutating, and exchanged only the thermostat. Judgments
`request_resolution=pass`, `effort_and_containment=pass`, `communication_clarity=pass`,
`aggregate=null`; new `evaluation-report/v1` Capsule `c308ebed…` at CLL **sequence
115**, payload verified identical on readback. Retrieve it the same way as any
capsule:

```sh
capsulectl cll list --profile tau2demo --after 114 --through 115
ID=$(capsulectl cll list --profile tau2demo --after 114 --through 115 | python3 -c 'import sys,json;e=json.load(sys.stdin)["entries"];print(e[-1]["capsule_id"] if e else "")')
capsulectl get --profile tau2demo --capsule-id "$ID"
```

The judged system here is the shipped `claude-3-7-sonnet` retail run (user
simulator `gpt-4.1`); point `--results` at another tau2 results file to evaluate
a different system.

### B4. Aggregate across cases (cross-case roll-up)

B3 publishes one report per case (`aggregate:null` — the *within-case* roll-up).
A benchmark story also wants the *cross-case* roll-up: how the system did across
many tasks. That is a separate compiler output, generated only when
`cross_case_aggregation` is not `none`: a second **aggregation skill** whose input is
the `evaluation-report/v1` Capsules (never the source interactions). It selects the
report range, verifies each report, reduces their `axis_judgments` across cases
(per-axis pass/fail/unjudgeable counts and pass rate; the `all_required` or `native`
overall), and publishes one `evaluation-summary/v1` Capsule back into the same CLL —
itself signed, checkpointable and witnessable.

```sh
# presenter-driven: compile with cross_case_aggregation=rate, then run the generated
# aggregation skill over the report range (reports follow the 114 case entries,
# so a full 114-case run lands at seqs 115-228)
capsulectl cll list --profile tau2demo --after 114 --through 228   # the evaluation reports
# the aggregation skill: verify each report, reduce axis judgments, publish one
#   evaluation-summary/v1 Capsule; read it back like any capsule
```

Aggregating all 114 retail tasks means 114 per-case judge runs first; the validated
run here judged one case (seq 115). The aggregation skill reduces whatever reports
exist, so a subset is a valid summary as long as its contributing set is recorded.

---

## Checkpointing and witnessing the CLL

`publish`/`cll append` only append entries — they do not witness or checkpoint.
Anchoring the log is a separate, explicit `cll checkpoint` step. This applies to
any CLL (SQLite `tau2demo` here, or the MySQL `alchemy` profile).

### C1. Local checkpoint (offline, no witness)

A checkpoint needs a *checkpoint* signing key (distinct from the producer signing
key), and that key must be trusted:

```sh
umask 077
CKEY=~/.local/share/evaluation-runs/tau2-eval/keys/tau2-checkpoint.ed25519
mkdir -p "$(dirname "$CKEY")"
CPUB=$(capsulectl key generate --output "$CKEY" \
       | python3 -c 'import sys,json;print(json.load(sys.stdin)["public_key"])')

capsulectl profile update --profile tau2demo \
  --checkpoint-signing-key-file "$CKEY" --checkpoint-trusted-key "$CPUB"

CP=$(capsulectl cll checkpoint create --profile tau2demo); echo "$CP"
# after B1+B2 (114 entries): {"checkpoint":224,"indexed_sequence":114,"statement":"<base64 COSE>", ...}
# checkpoint is the MMR size, not the entry count; running B3 appends sequence 115 and makes it 225 / 115.
```

With no endpoint configured, `create` is fully local: it builds and COSE-signs the
checkpoint over the current MMR and stores it; no network, no witness. Verify it
offline (optionally with a Capsule inclusion proof):

```sh
STMT=$(echo "$CP" | python3 -c "import sys,json;print(json.load(sys.stdin)['statement'])")   # reuse the create above
python3 -c "import json;open('/tmp/proof.json','w').write(json.dumps({'checkpoint':'$STMT'}))"
capsulectl cll verify --profile tau2demo --proof /tmp/proof.json
# -> checkpoint_signature_and_trust=passed, log_id=passed, embedded_consistency=passed
#    inclusion=not_performed (exit 3, partial) unless the proof includes capsule_id + path
```

### C2. Configure the Action State Group witness endpoint

The ASG (Steven's) witness is `capsule-anchor` at
`https://witness.agentactioncapsule.org`; its `/checkpoints` route is public and
unauthenticated for a non-enrolled `log_id` (no token). Resolve its authority key
and add the endpoint + key to the profile:

```sh
# resolve the witness authority public key (do not trust a hardcoded copy blindly)
curl -s https://witness.agentactioncapsule.org/anchor/authority-pubkey
# -> {"pubkey_hex":"39bb654c9dc0afe1c0edef0deffaa69099b8518836c9ba26e0491535840f96b5","key_id":"19a9ab3e02fad55c"}
# same key at /.well-known/did.json as publicKeyJwk.x (base64url) = ObtlTJ3Ar-HA7e8N7_qmkJm4UYg2ybom4EkVNYQPlrU

capsulectl profile update --profile tau2demo \
  --checkpoint-endpoint https://witness.agentactioncapsule.org \
  --checkpoint-public-key 39bb654c9dc0afe1c0edef0deffaa69099b8518836c9ba26e0491535840f96b5
```

The pinned authority public key is
`39bb654c9dc0afe1c0edef0deffaa69099b8518836c9ba26e0491535840f96b5` (`key_id`
`19a9ab3e02fad55c`); re-resolve from `/anchor/authority-pubkey` or
`/.well-known/did.json` if it rotates. For an *enrolled* production log, e.g.
`alchemy`, set the same checkpoint endpoint and public-key fields here with your
enrolled witness key (alongside the checkpoint signing/trusted keys from C1).

### C3. Publish the checkpoint to the witness and check status

A witness delivery is enqueued only by the **first `create` at a given MMR size
after the endpoint is configured**. C1 already created a checkpoint offline at the
114-entry size (224); so to witness, either target a *fresh* size — in this demo B3
appended seq 115, making size 225 new — or, if the size you want was already created
offline, append one more entry (`cll append`, or run B3) before this `create`.
With the endpoint configured (C2) and a fresh size, deliver by MMR size:

```sh
CP=$(capsulectl cll checkpoint create --profile tau2demo)   # the only create at this size
SIZE=$(echo "$CP" | python3 -c "import sys,json;print(json.load(sys.stdin)['checkpoint'])")
STMT=$(echo "$CP" | python3 -c "import sys,json;print(json.load(sys.stdin)['statement'])")   # reused in C4
capsulectl cll checkpoint publish --profile tau2demo --checkpoint "$SIZE"
# -> {"state":"verified","receipt":{...}}   (pending/failed otherwise)
capsulectl cll checkpoint status  --profile tau2demo --checkpoint "$SIZE"
```

`--checkpoint` is the MMR size (not the entry count). On `publish` the witness
verifies the checkpoint's COSE signature against its embedded `key_id`, grades it
`mmr-verified` (it understands the CLL MMR scheme), timestamps + countersigns, and
returns a receipt; the CLI verifies that receipt against the witness authority key
from C2 and stores it. `status` re-verifies the STORED receipt locally and makes no
network call. Note: `publish` appends to the live, append-only public transparency
log.

**Actual result of the executed publish** (this demo's 115-entry CLL): checkpoint
**225 / indexed 115** was delivered to the live witness and returned
`state=verified`. The witness countersigned it at global tree position
`leaf_index=1062`, `tree_size=1063` (its authority `key_id=19a9ab3e02fad55c`), and
the CLI verified that receipt against the authority key from C2 before storing it.

### C4. Fetch the witness record; re-verify the local checkpoint offline

The witness anchors the **checkpoint (the log's MMR root)**, not individual
Capsules. The witness *receipt* was already cryptographically verified against the
authority key during `publish`/`status` (C3). Here you fetch the witness's public
record of the checkpoint and independently re-verify the **local** checkpoint
statement offline (this step checks the local checkpoint's signature/trust/
consistency, not the fetched receipt):

```sh
LOG=tau2-retail-20260909
# the witness's countersigned checkpoint(s) for this log (this curl only prints it)
curl -s "https://witness.agentactioncapsule.org/checkpoints/$LOG"
# -> {"log_id":"tau2-retail-20260909","mmr_size":225,"prev_size":224,
#     "root":"45476a60b940a88d1595c7a440b79374e9a7a32ccc8fb280ff5e4325ed75c693",
#     "prev_root":"e9698ea2144dded92742502d39c06ba0de24dbf98abdbd00199c2291cbbb1ea3",
#     "key_id":"02698f0b010cfe504df82c375c0a226f92cd8128fb5d3d72ea3aed4282129cc5",
#     "receipt_b64":"0oRHogEnGQGLAaEZAYyhIIFYkIMZBCcZBCaE…",  # COSE receipt (truncated: ~180 B)
#     "leaf_index":1062,"tree_size":1063,"equivocations":[]}
#   mmr_size/prev_size match the local checkpoint; key_id is THIS log's checkpoint
#   signing key (02698f0b…), distinct from the witness authority key (39bb654c…).

# verify the checkpoint offline against the trusted checkpoint key (no network).
# Reuse $STMT captured from the single C3 create above — do not re-create at this size.
python3 -c "import json,sys;open('/tmp/proof.json','w').write(json.dumps({'checkpoint':sys.argv[1]}))" "$STMT"
capsulectl cll verify --profile tau2demo --proof /tmp/proof.json
# -> checkpoint_signature_and_trust=passed, embedded_consistency=passed, log_id=passed
#    inclusion=not_performed (exit 3, partial): this CLI build has no per-Capsule
#    audit-path emitter, so a single Capsule's inclusion against the checkpointed
#    root is not proven here — the checkpoint (hence the whole MMR) is.
```

The witness `root` is the bagged MMR root; the local checkpoint `statement` carries
the raw peaks and the 224→225 consistency proof (which `embedded_consistency`
checks). The `GET /v1/inclusion/{capsule_id}` route is for statements registered
directly to the transparency log, not for CLL-checkpoint capsules, so it returns
`not found` for a `tau2demo` Capsule id.

### C5. Query the witness endpoint directly

```sh
curl -s https://witness.agentactioncapsule.org/health        # {"ok":true,"key_id":...,"tree_size":...,"latest_root_hash":...}
curl -s https://witness.agentactioncapsule.org/.well-known/did.json   # authority Ed25519 key (JWK)
# interactive API docs: https://witness.agentactioncapsule.org/docs
```

Network vs local: `create` (C1) and `status` (C3) are local — only `publish` (C3)
and the curls (C4/C5) contact the witness. `status`/`publish` both require the
endpoint configured (they derive the service id from it) and error with "checkpoint
service not configured" if it is unset, but only `publish` sends bytes over the
network.

Executed here: C1–C5 were all run against this demo's CLL, including delivering
checkpoint 225/115 to the **live** production witness (C3, `state=verified`, the
receipt verified against the authority key) and fetching the witness record plus
offline-re-verifying the local checkpoint (C4). Because `publish`
appends to a public, append-only log, only run it when you intend a permanent
public record. If a checkpoint at the current MMR size already exists locally,
append/observe a new entry before `create` so a fresh witness delivery is enqueued.
