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
# generate an ed25519 signer (seed hex -> key file; public hex -> trusted key)
read SEED PUB < <(python3 -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization as s
k=Ed25519PrivateKey.generate()
print(k.private_bytes(s.Encoding.Raw,s.PrivateFormat.Raw,s.NoEncryption()).hex(),
      k.public_key().public_bytes(s.Encoding.Raw,s.PublicFormat.Raw).hex())")
printf '%s' "$SEED" > "$DEMO/keys/tau2.ed25519"; chmod 600 "$DEMO/keys/tau2.ed25519"

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

B3 describes the compiler run; unlike B1/B2 it has not yet been executed against
these real trajectories, so no evaluation Capsule id or judgments are pinned.
Retrieve the evaluation Capsule the same way as any capsule:

```sh
capsulectl cll list --profile tau2demo --after 114 --through 115
ID=$(capsulectl cll list --profile tau2demo --after 114 --through 115 | python3 -c 'import sys,json;e=json.load(sys.stdin)["entries"];print(e[-1]["capsule_id"] if e else "")')
capsulectl get --profile tau2demo --capsule-id "$ID"
```

The judged system here is the shipped `claude-3-7-sonnet` retail run (user
simulator `gpt-4.1`); point `--results` at another tau2 results file to evaluate
a different system.

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
read CSEED CPUB < <(python3 -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization as s
k=Ed25519PrivateKey.generate()
print(k.private_bytes(s.Encoding.Raw,s.PrivateFormat.Raw,s.NoEncryption()).hex(),
      k.public_key().public_bytes(s.Encoding.Raw,s.PublicFormat.Raw).hex())")
printf '%s' "$CSEED" > "$CKEY"; chmod 600 "$CKEY"

capsulectl profile update --profile tau2demo \
  --checkpoint-signing-key-file "$CKEY" --checkpoint-trusted-key "$CPUB"

capsulectl cll checkpoint create --profile tau2demo
# after B1+B2 (114 entries): {"checkpoint":224,"indexed_sequence":114,"statement":"<base64 COSE>", ...}
# checkpoint is the MMR size, not the entry count; running B3 appends sequence 115 and makes it 225 / 115.
```

With no endpoint configured, `create` is fully local: it builds and COSE-signs the
checkpoint over the current MMR and stores it; no network, no witness. Verify it
offline (optionally with a Capsule inclusion proof):

```sh
STMT=$(capsulectl cll checkpoint create --profile tau2demo | python3 -c "import sys,json;print(json.load(sys.stdin)['statement'])")
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
# authority key is published at /.well-known/did.json (publicKeyJwk.x, base64url -> hex)
capsulectl profile update --profile tau2demo \
  --checkpoint-endpoint https://witness.agentactioncapsule.org \
  --checkpoint-public-key 39bb654c9dc0afe1c0edef0deffaa69099b8518836c9ba26e0491535840f96b5
```

(As of this writing the witness `key_id` is `19a9ab3e02fad55c`; re-resolve from
`/.well-known/did.json` if it rotates. For an *enrolled* production log, e.g.
`alchemy`, set the same three `checkpoint.*` fields with your enrolled key.)

### C3. Publish the checkpoint to the witness and check status

Configure the endpoint (C2) **before** `create`, so `create` enqueues a witness
delivery; then deliver by MMR size:

```sh
SIZE=$(capsulectl cll checkpoint create --profile tau2demo | python3 -c "import sys,json;print(json.load(sys.stdin)['checkpoint'])")
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

### C4. Query the witness endpoint directly

```sh
curl -s https://witness.agentactioncapsule.org/health        # {"ok":true,"key_id":...,"tree_size":...,"latest_root_hash":...}
curl -s https://witness.agentactioncapsule.org/.well-known/did.json   # authority Ed25519 key (JWK)
# interactive API docs: https://witness.agentactioncapsule.org/docs
```

Network vs local: `create` (C1) and `status` (C3) are local — only `publish` (C3)
and the curls (C4) contact the witness. `status`/`publish` both require the endpoint
configured (they derive the service id from it) and error with "checkpoint service
not configured" if it is unset, but only `publish` sends bytes over the network.

Executed vs documented: C1 (local checkpoint + offline `cll verify`) and C4 (the
`/health` and `/.well-known/did.json` queries) were run here; C2/C3 (adding the
endpoint and delivering to the live witness) are the documented procedure and were
not submitted to the production log in this demo. If a checkpoint at the current
MMR size already exists locally (from C1), append/observe a new entry before the
C3 `create` so a witness delivery is enqueued for the just-configured service.
