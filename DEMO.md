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
# Capsule CLI (MySQL + SQLite backends), commit b1cc1fe or later
git -C ~/GitHub/capsule-cli pull && (cd ~/GitHub/capsule-cli && go install ./cmd/capsule)
capsule --version    # capsule version 0.1.0-dev
```

- Demo A: the `alchemy` MySQL profile configured, and `gh` authenticated for
  `github.ibm.com` (independent business evidence).
- Demo B: no database server — SQLite is a single local file. tau2 dataset at
  `~/GitHub/tau2-bench/data/tau2/domains/…`.

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
   ./bin/capsule get    --profile alchemy --capsule-id <ID> --raw --output rec.json
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

tau2 supplies **only the dataset** (customer-service task scenarios). Axes are the
compiler's job. Value proposition used here: **customer experience** — *"give the
customer a clear, empathetic service experience that fully resolves their request
in one interaction with minimal effort."*

This whole demo was executed; concrete results are noted inline. Run
`run-20260909` used store `d9ce77fd…d02d0`, log `tau2-retail-20260909`.

### B1. Create a local SQLite CLL  (executed)

```sh
DEMO=~/.local/share/evaluation-runs/tau2-eval; mkdir -p "$DEMO/keys"
# generate an ed25519 signer (seed hex -> key file; public hex -> trusted key)
read SEED PUB < <(python3 -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization as s
k=Ed25519PrivateKey.generate()
print(k.private_bytes(s.Encoding.Raw,s.PrivateFormat.Raw,s.NoEncryption()).hex(),
      k.public_key().public_bytes(s.Encoding.Raw,s.PublicFormat.Raw).hex())")
printf '%s' "$SEED" > "$DEMO/keys/tau2.ed25519"; chmod 600 "$DEMO/keys/tau2.ed25519"

capsule profile create --name tau2demo --type sqlite \
  --sqlite-path "$DEMO/store.db" \
  --namespace tau2 --log-id tau2-retail-20260909 \
  --signing-key-file "$DEMO/keys/tau2.ed25519" --trusted-key "$PUB"
capsule store init --profile tau2demo      # generates + pins store_id into the profile
```

The SQLite store keeps the artifact tables and the CLL log in one file
(`store.db`), opened with `foreign_keys`, `busy_timeout`, and WAL.

### B2. Backfill tau2 interactions as Capsules

For each selected task (e.g. retail task `0` from
`~/GitHub/tau2-bench/data/tau2/domains/retail/tasks.json`), build ONE
`capsule-seal-request/v1` whose `payload` carries the interaction — the customer
scenario (from `user_scenario`) plus the agent's recorded transcript/actions —
and publish it. Each publish appends one CLL entry:

```sh
capsule publish --profile tau2demo --request "$DEMO/backfill/interaction-0.json"
capsule publish --profile tau2demo --request "$DEMO/backfill/interaction-1.json"
capsule cll list --profile tau2demo --after 0
```

Executed result: **seq 1** = `6b4d7f82…` (task 0), **seq 2** = `bc283397…` (task 1).
`payload` is bound (`agent_input_digest`) and therefore authenticated. The desired
outcome for judging is DECLARED and read independently from the tau2 dataset by
`payload.case.task_id`, so it never sees the transcript. Backfill is operator
data-prep — plain `capsule publish` calls, no runner or helper program — and uses
**only** the tau2 dataset. (To mirror Alchemy's split exactly one may instead set
`capsule.effect` with `effect_request`/`effect_response` artifacts; the payload
form above needs no manual digest computation.)

### B3. Compile and run the evaluation  (executed)

1. Invoked the `evaluation-compiler` skill with the customer-experience value
   proposition and access facts (profile `tau2demo`). It generated the bundle at
   `~/.local/share/evaluation-bundles/tau2-investigation/` — `axes.json`
   (request_resolution, effort_and_containment, communication_clarity; no aggregate),
   `references/source.md` (the dataset→Capsule payload mapping), `resolved-spec.json`,
   `references/{execution,capsule-cli}.md`, `bin/capsule`.
2. Ran the generated skill in a fresh agent with `profile=tau2demo`,
   `selection=(1,2]`, `dataset_path=…/retail/tasks.json`, `run_dir=…/tau2-eval/run`.
   It enumerated the SQLite CLL (seq 2, `bc283397…`, task-1), `get --raw` + `verify`
   (identity + signature + payload bound/verified), read the DECLARED desired outcome
   from the dataset task 1, ran the three isolated sub-agent stages, judged, and
   published a new evaluation Capsule back into the same SQLite CLL — identical
   commands to Demo A, only the profile differs.

**Executed result:** new evaluation Capsule `606c4a43…` at CLL **sequence 3**,
verified (identity + signature + payload bound), request payload == bound payload
(exact), CLL inclusion confirmed. Judgments: `request_resolution=pass`,
`effort_and_containment=pass`, `communication_clarity=pass`, `aggregate=null`.
Retrieve it the same way as any capsule:

```sh
capsule cll list --profile tau2demo --after 2 --through 3
capsule get --profile tau2demo --capsule-id 606c4a43e8e9be5f2800cc980a63e99fe469b5147df6fb62dcb22593cb0c66a1
```

Note: the backfilled transcripts here are synthesized demo interactions (the tau2
dataset ships task scenarios, not agent runs); each payload records that
provenance. Swap in real agent transcripts to evaluate a real system.

---

## Checkpointing and witnessing the CLL

`publish`/`cll append` only append entries — they do not witness or checkpoint.
Anchoring the log is a separate, explicit `cll checkpoint` step. This applies to
any CLL (SQLite `tau2demo` here, or the MySQL `alchemy` profile).

### C1. Local checkpoint (offline, no witness)  — executed

A checkpoint needs a *checkpoint* signing key (distinct from the producer signing
key), and that key must be trusted:

```sh
CKEY=~/.local/share/evaluation-runs/tau2-eval/keys/tau2-checkpoint.ed25519
mkdir -p "$(dirname "$CKEY")"
read CSEED CPUB < <(python3 -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization as s
k=Ed25519PrivateKey.generate()
print(k.private_bytes(s.Encoding.Raw,s.PrivateFormat.Raw,s.NoEncryption()).hex(),
      k.public_key().public_bytes(s.Encoding.Raw,s.PublicFormat.Raw).hex())")
printf '%s' "$CSEED" > "$CKEY"; chmod 600 "$CKEY"

capsule profile update --profile tau2demo \
  --checkpoint-signing-key-file "$CKEY" --checkpoint-trusted-key "$CPUB"

capsule cll checkpoint create --profile tau2demo
# -> {"checkpoint":4,"indexed_sequence":3,"statement":"<base64 COSE>", ...}
```

With no endpoint configured, `create` is fully local: it builds and COSE-signs the
checkpoint over the current MMR and stores it; no network, no witness. Verify it
offline (optionally with a Capsule inclusion proof):

```sh
STMT=$(capsule cll checkpoint create --profile tau2demo | python3 -c "import sys,json;print(json.load(sys.stdin)['statement'])")
python3 -c "import json;open('/tmp/proof.json','w').write(json.dumps({'checkpoint':'$STMT'}))"
capsule cll verify --profile tau2demo --proof /tmp/proof.json
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
capsule profile update --profile tau2demo \
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
SIZE=$(capsule cll checkpoint create --profile tau2demo | python3 -c "import sys,json;print(json.load(sys.stdin)['checkpoint'])")
capsule cll checkpoint publish --profile tau2demo --checkpoint "$SIZE"
# -> {"state":"verified","receipt":{...}}   (pending/failed otherwise)
capsule cll checkpoint status  --profile tau2demo --checkpoint "$SIZE"
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
