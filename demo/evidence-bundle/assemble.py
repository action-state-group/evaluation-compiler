"""Demo: assemble a spec-conformant Evidence Bundle v2 from the real airline store,
using the verified agent-action-capsule Python reference + CLL, and mint a local permalink."""
import sqlite3, json, sys
sys.path.insert(0, "/Users/ezhang/GitHub/agent-action-capsule/python")
sys.path.insert(0, "/Users/ezhang/GitHub/checkpointed-local-log")
from agent_action_capsule.bundle import encode_fragment, decode_fragment, verify_bundle
from agent_action_capsule.canonical import json_digest
from cll.checkpoint import RangeProof, core
from cll.checkpoint.store import MemoryNodeStore

DB = "/Users/ezhang/.local/share/evaluation-runs/tau2-airline/store.db"
LOG_ID = "tau2-airline-20260911"
db = sqlite3.connect(DB)

caps = {cid: json.loads(bytes(b)) for cid, b in db.execute("select capsule_id, capsule_bytes from capsule_store_capsules")}
# artifact originals (agent_output kept)
arts = {}
for cid, name, content in db.execute("select capsule_id, name, content_bytes from capsule_store_artifacts where content_bytes is not null"):
    arts.setdefault(cid, {})[name] = bytes(content)
# ordered leaves
entries = [(seq, bytes(v).hex()) for seq, v in db.execute("select seq, value from cll_entries where log_id=? order by seq", (LOG_ID,))]
seq_of = {cid: seq for seq, cid in entries}

# build full MMR over all leaves in seq order
nodes = MemoryNodeStore()
for _, cid in entries:
    core.add_leaf(nodes, core.leaf_hash(bytes.fromhex(cid)))
size = nodes.size()
root_hash = core.root_from_peaks([nodes.node(pos) for pos in core.peaks(size)])

def proof_dict(p):
    return {"v": p.v, "kind": p.kind, "size": p.size, "leaf_index": p.leaf_index,
            "witness": list(p.witness), "peaks_left": list(p.peaks_left), "peaks_right": list(p.peaks_right)}

# transitive closure from root over references[].digest + chain, depth 2 (aggregate->reports->acts)
ROOT = "388b87cae7a5"
root_id = next(c for c in caps if c.startswith(ROOT))
def closure(start, depth=2):
    seen, frontier = set(), [(start, 0)]
    while frontier:
        cid, d = frontier.pop()
        if cid in seen or cid not in caps: continue
        seen.add(cid)
        if d >= depth: continue
        c = caps[cid]
        for r in c.get("references", []):
            tgt = r.get("digest")
            if tgt: frontier.append((tgt, d+1))
        ch = c.get("chain", {})
        if ch.get("parent_capsule_id"): frontier.append((ch["parent_capsule_id"], d+1))
    return seen
ids = closure(root_id)
# order records by seq
records = [caps[cid] for cid in sorted(ids, key=lambda x: seq_of.get(x, 1<<30))]
first_seq = min(seq_of[c["capsule_id"]] for c in records)
last_seq  = max(seq_of[c["capsule_id"]] for c in records)

memberships = {}
for c in records:
    seq = seq_of[c["capsule_id"]]; idx = seq - 1
    memberships[c["capsule_id"]] = {"log_coordinates": {"log_id": LOG_ID, "seq": seq, "leaf_index": idx},
                                    "inclusion_proof": proof_dict(core.inclusion_proof(nodes, idx, size))}
lo_idx, hi_idx = first_seq-1, last_seq-1
certificate = {"log_id": LOG_ID, "range_root": root_hash.hex(), "first_seq": first_seq, "last_seq": last_seq,
    "first_digest": next(c["capsule_id"] for c in records if seq_of[c["capsule_id"]]==first_seq),
    "last_digest":  next(c["capsule_id"] for c in records if seq_of[c["capsule_id"]]==last_seq),
    "range_proof": {"from_seq": first_seq, "to_seq": last_seq, "size": size,
                    "inclusion_from": proof_dict(core.inclusion_proof(nodes, lo_idx, size)),
                    "inclusion_to":   proof_dict(core.inclusion_proof(nodes, hi_idx, size))},
    "memberships": memberships}

# disclosures overlay: disclose-all agent_output originals (nested payloads), suppress agent_input
disclosures = {}
for c in records:
    cid = c["capsule_id"]
    ca = c.get("model_attestation", {}).get("compute_attestation", {})
    if "agent_output_digest" in ca and cid in arts and "agent_output" in arts[cid]:
        val = json.loads(arts[cid]["agent_output"])
        # only include if it actually matches the committed digest (DE-3)
        if json_digest(val) == ca["agent_output_digest"]:
            disclosures.setdefault(cid, {})["agent_output"] = val

bundle = {"bundle_version": "2", "bundle_kind": "evidence-bundle/v2", "root": root_id,
    "records": records,
    "completeness": {"closure_depth": 2, "records_mode": "complete", "payloads_mode": "all",
                     "suppressed_fields": ["agent_input"], "missing": []},
    "disclosures": disclosures,
    "completeness_certificate": certificate,
    "checkpoint": {"root": root_hash.hex(), "mmr_size": size}}

res = verify_bundle(bundle)
print("records in bundle:", len(records))
print("graph_closure      :", res.graph_closure.status)
print("interval_coverage  :", res.interval_coverage.status)
print("per_record_membership:", res.per_record_membership.status)
print("disclosures (match/withheld):", [(d.member, d.status) for d in res.disclosures][:8], "...total", len(res.disclosures))
frag = encode_fragment(bundle)
assert decode_fragment(frag) == bundle, "round-trip failed"
url = "http://127.0.0.1:8080/bundle#" + frag
open("/tmp/aac-demo6/PERMALINK.txt","w").write(url)
open("/tmp/aac-demo6/bundle.json","w").write(json.dumps(bundle))
print("permalink bytes:", len(url), "-> /tmp/aac-demo6/PERMALINK.txt")
