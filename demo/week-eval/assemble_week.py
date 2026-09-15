"""Demo B (temporal): publish 3 daily evaluation reports + 1 weekly aggregate over
the airline CLL, then assemble two Evidence Bundle v2 outputs:
  v1: ALL capsules (acts + reports + aggregate), both members disclosed  -> offline HTML
  v2: reports + aggregate only (acts declared missing)                   -> URL permalink
The judge verdicts were produced by isolated evidence-derived sub-agents; see verdicts.json."""
import json, os, subprocess, sys, tempfile, datetime
# Point these at your local checkouts of the two reference libraries (or install
# them and drop these inserts). Override via env for a non-default layout.
sys.path.insert(0, os.environ.get("AAC_PY", os.path.expanduser("~/GitHub/agent-action-capsule/python")))
sys.path.insert(0, os.environ.get("CLL_PY", os.path.expanduser("~/GitHub/checkpointed-local-log")))
from agent_action_capsule.bundle import encode_fragment, decode_fragment, verify_bundle
from agent_action_capsule.canonical import json_digest
from cll.checkpoint import core
from cll.checkpoint.store import MemoryNodeStore
import sqlite3

CAPSULECTL = os.environ.get("CAPSULECTL", "capsulectl")
PROFILE = os.environ.get("AAC_PROFILE", "airlinedemo")
LOG_ID = "tau2-airline-20260914"
DEMO = os.path.expanduser("~/.local/share/evaluation-runs/tau2-airline-eval")
STORE = f"{DEMO}/store.db"
BACKFILL = f"{DEMO}/backfill"
OUT = os.environ.get("AAC_DEMO_OUT", os.path.expanduser("~/Downloads"))
AXES = ["policy_compliance", "task_resolution", "grounded_communication"]
HERE = os.path.dirname(os.path.abspath(__file__))
verdicts = json.load(open(os.path.join(HERE, "verdicts.json")))

def cll_entries():
    db = sqlite3.connect(STORE)
    rows = [(seq, bytes(v).hex()) for seq, v in db.execute("select seq,value from cll_entries where log_id=? order by seq", (LOG_ID,))]
    db.close()
    return rows

# map seq -> task via sorted backfill filenames (publish order)
files = sorted(f for f in os.listdir(BACKFILL) if f.endswith(".json"))
seq_task = {}
for i, fn in enumerate(files, start=1):
    # task-<id>-act-<NNNN>.json
    seq_task[i] = fn.split("-act-")[0].replace("task-", "")
# The seq<->task mapping assumes the i-th sorted backfill file is CLL seq i (the
# publish order). Validate it: the CLL must currently hold exactly the acts, so a
# failed/duplicate publish or a pre-existing entry cannot silently shift attribution.
_initial = cll_entries()
if len(_initial) != len(files):  # not assert: must survive python -O
    raise SystemExit(f"CLL has {len(_initial)} entries but {len(files)} backfill files; "
                     "seq<->task attribution would be wrong — re-run B1/B2 from a clean store")

def publish(request):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(request, f); path = f.name
    out = subprocess.run([CAPSULECTL, "publish", "--profile", PROFILE, "--request", path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print("PUBLISH FAILED:", out.stderr.strip()[:400]); sys.exit(1)
    return json.loads(out.stdout)

def all_required_case(task_j):
    # all_required: drop not_applicable axes, then the case passes iff its remaining
    # applicable required axes are a NONEMPTY set that all pass (any fail/unjudgeable
    # fails the case; no applicable required axis is a fail, not a vacuous pass). This
    # matches the cross-case rate math, which also excludes not_applicable.
    applicable = [task_j[a]["status"] for a in AXES if task_j[a]["status"] != "not_applicable"]
    if not applicable:
        return "fail"
    return "pass" if all(s == "pass" for s in applicable) else "fail"

# ---- publish 3 daily reports ----
report_ids = []
for day in verdicts["days"]:
    ents = cll_entries()
    seq_of = {cid: seq for seq, cid in ents}
    day_tasks = list(day["tasks"].keys())
    # act capsule_ids of this day's conversations, by seq order
    act_refs = [(seq, cid) for seq, cid in ents if seq_task.get(seq) in day_tasks]
    cases = []
    for tid, tj in day["tasks"].items():
        cases.append({"task_id": tid, "trial": 0,
                      "axis_judgments": [{"axis_id": a, "outcome_id": "policy_compliant_resolution",
                                          "status": tj[a]["status"], "rationale": tj[a]["rationale"],
                                          "evidence_ids": tj[a]["evidence_ids"]} for a in AXES],
                      "case_aggregate": all_required_case(tj)})
    daily_pass = sum(1 for c in cases if c["case_aggregate"] == "pass")
    report = {
        "spec_version": "evaluation-report/v1",
        "evaluation_identity": {"evaluator": "tau2-airline-eval", "run": f"day-{day['day']}", "judged_at": day["date"]},
        "scenario": "tau2-airline policy-compliant resolution (daily)",
        "day": day["day"], "date": day["date"],
        "source_selection": {"log_id": LOG_ID, "conversations": day_tasks,
                             "interaction_capsule_ids": [cid for _, cid in act_refs]},
        "outcomes": [{"outcome_id": "policy_compliant_resolution", "role": "required",
                      "aggregate": "pass" if daily_pass == len(cases) else "fail"}],
        "cases": cases,
        "daily_aggregate": {"policy": "all_required", "cases_total": len(cases), "cases_pass": daily_pass,
                            "verdict": "pass" if daily_pass == len(cases) else "fail"},
        "limitations": ["Isolation of desired/agent/judge contexts approximated; declared criteria read transcript-blind from tau2 tasks.json."],
    }
    req = {"spec_version": "capsule-seal-request/v1",
           "capsule": {"ActionID": f"tau2-airline-eval-day{day['day']}", "ActionType": "fyi",
                       "Operator": "ACME-AIR", "Developer": "tau2-airline-eval@v1",
                       "Timestamp": f"{day['date']}T18:00:00Z",
                       "References": [{"Type": "agent-action-capsule", "DigestAlg": "SHA-256", "Digest": cid,
                                       "CitationPurpose": "acted_on"} for seq, cid in act_refs]},
           "payload": report}
    res = publish(req)
    rid = res.get("capsule_id") or res.get("capsuleId")
    report_ids.append(rid)
    print(f"day {day['day']}: published report {rid[:12]} (refs {len(act_refs)} acts, daily {daily_pass}/{len(cases)} pass)")

# ---- publish weekly aggregate over the 3 daily reports ----
ents = cll_entries()
seq_of = {cid: seq for seq, cid in ents}
# per-axis weekly counts across all 9 cases
counts = {a: {"pass": 0, "fail": 0, "unjudgeable": 0, "not_applicable": 0} for a in AXES}
for day in verdicts["days"]:
    for tid, tj in day["tasks"].items():
        for a in AXES:
            counts[a][tj[a]["status"]] += 1
def rate(c):
    denom = c["pass"] + c["fail"] + c["unjudgeable"]
    return f"{c['pass']}/{denom}" if denom else "0/0"
summary = {
    "spec_version": "evaluation-summary/v1",
    "aggregation_identity": {"reducer": "tau2-airline-eval-aggregate", "run": "week-1", "reduced_at": "2026-09-16"},
    "cross_case_aggregation": "rate", "cohort": "claude-3-7-sonnet airline_default trial0",
    "source_selection": {"log_id": LOG_ID, "contributing_report_capsule_ids": report_ids},
    "per_axis": {a: {**counts[a], "pass_rate": rate(counts[a])} for a in AXES},
    "counts": {"reports": len(report_ids),
               "unique_cases": len({t for day in verdicts["days"] for t in day["tasks"]})},
    "limitations": ["Weekly roll-up of 3 daily reports; per-axis rate over 9 conversations."],
}
req = {"spec_version": "capsule-seal-request/v1",
       "capsule": {"ActionID": "tau2-airline-eval-week1", "ActionType": "fyi",
                   "Operator": "ACME-AIR", "Developer": "tau2-airline-eval-aggregate@v1",
                   "Timestamp": "2026-09-16T20:00:00Z",
                   "References": [{"Type": "agent-action-capsule", "DigestAlg": "SHA-256", "Digest": rid,
                                   "CitationPurpose": "acted_on"} for rid in report_ids]},
       "payload": summary}
res = publish(req)
agg_id = res.get("capsule_id") or res.get("capsuleId")
print(f"week: published aggregate {agg_id[:12]} (per-axis rates: "
      + ", ".join(f"{a}={rate(counts[a])}" for a in AXES) + ")")

# ---- assemble bundles ----
db = sqlite3.connect(STORE)
caps = {cid: json.loads(bytes(b)) for cid, b in db.execute("select capsule_id, capsule_bytes from capsule_store_capsules")}
arts = {}
for cid, name, content in db.execute("select capsule_id, name, content_bytes from capsule_store_artifacts where content_bytes is not null"):
    arts.setdefault(cid, {})[name] = bytes(content)
db.close()
ents = cll_entries()
seq_of = {cid: seq for seq, cid in ents}
nodes = MemoryNodeStore()
for _, cid in ents:
    core.add_leaf(nodes, core.leaf_hash(bytes.fromhex(cid)))
size = nodes.size()
root_hash = core.root_from_peaks([nodes.node(p) for p in core.peaks(size)])

def proof_dict(p):
    return {"v": p.v, "kind": p.kind, "size": p.size, "leaf_index": p.leaf_index,
            "witness": list(p.witness), "peaks_left": list(p.peaks_left), "peaks_right": list(p.peaks_right)}

MEMBER_ART = {"agent_output": "agent_output", "agent_input": "payload"}
def disclosures_for(record_ids):
    d = {}
    for cid in record_ids:
        ca = caps[cid].get("model_attestation", {}).get("compute_attestation", {})
        for member, art in MEMBER_ART.items():
            df = f"{member}_digest"
            if df in ca and cid in arts and art in arts[cid]:
                val = json.loads(arts[cid][art])
                if json_digest(val) != ca[df]:
                    raise SystemExit(f"data-integrity error: stored {member} original for {cid} "
                                     f"does not match its committed {df}")
                d.setdefault(cid, {})[member] = val
    return d

id_by_seq = {seq: cid for seq, cid in ents}

def assemble(record_ids, declared_missing):
    record_ids = sorted(record_ids, key=lambda c: seq_of[c])
    first_seq, last_seq = seq_of[record_ids[0]], seq_of[record_ids[-1]]
    memberships = {cid: {"log_coordinates": {"log_id": LOG_ID, "seq": seq_of[cid], "leaf_index": seq_of[cid] - 1},
                         "inclusion_proof": proof_dict(core.inclusion_proof(nodes, seq_of[cid] - 1, size))}
                   for cid in record_ids}
    # CLL #13 range membership: every leaf in [first_seq, last_seq] participates
    # via the ordered body_digests + flat witness, matching the realigned verifiers.
    rp = core.range_proof(nodes, first_seq - 1, last_seq - 1, size)
    cert = {"log_id": LOG_ID, "range_root": root_hash.hex(), "first_seq": first_seq, "last_seq": last_seq,
            "body_digests": [id_by_seq[s] for s in range(first_seq, last_seq + 1)],
            "range_proof": {"from_seq": first_seq, "to_seq": last_seq, "size": size,
                            "from_index": rp.from_index, "to_index": rp.to_index, "witness": list(rp.witness)},
            "memberships": memberships}
    return {"bundle_version": "2", "bundle_kind": "evidence-bundle/v2", "root": agg_id,
            "records": [caps[c] for c in record_ids],
            "completeness": {"closure_depth": 2,
                             "records_mode": "declared_incomplete" if declared_missing else "complete",
                             "payloads_mode": "all", "suppressed_fields": [], "missing": sorted(declared_missing)},
            "disclosures": disclosures_for(record_ids),
            "completeness_certificate": cert,
            "checkpoint": {"root": root_hash.hex(), "mmr_size": size}}

all_ids = [cid for _, cid in ents]
report_agg = report_ids + [agg_id]
# v2 excludes interaction (act) capsules: the acts the reports/aggregate cite are declared missing
cited = set()
for cid in report_agg:
    for r in caps[cid].get("references", []):
        if r.get("digest"): cited.add(r["digest"])
missing_v2 = sorted(cited - set(report_agg))
# v2's interval claim [first_seq,last_seq] requires a membership entry for every seq
# in the range; the reports+aggregate must therefore be a contiguous seq range, or
# an intervening/other append would leave a gap the verifier fails at. Assert it here
# so a shifted publish order fails loudly at build time, not at verify time.
report_seqs = sorted(seq_of[c] for c in report_agg)
if report_seqs != list(range(report_seqs[0], report_seqs[-1] + 1)):  # not assert: survive python -O
    raise SystemExit(f"reports+aggregate are not a contiguous seq range ({report_seqs}); "
                     "v2 interval coverage would fail")

v1 = assemble(all_ids, [])
v2 = assemble(report_agg, missing_v2)

# Gate: only write outputs if each bundle verifies to its EXPECTED shape. v1 is a
# complete graph; v2 is declared-incomplete (acts missing) so its graph closure is
# 'withheld'. Both must pass interval + membership, and every disclosure must match.
def gate(name, b, expect_graph):
    r = verify_bundle(b)
    disc = {}
    for x in r.disclosures: disc[x.status] = disc.get(x.status, 0) + 1
    print(f"{name}: records={len(b['records'])} graph={r.graph_closure.status} "
          f"interval={r.interval_coverage.status} membership={r.per_record_membership.status} "
          f"disclosures={disc} missing={len(b['completeness']['missing'])}")
    problems = []
    if r.graph_closure.status != expect_graph: problems.append(f"graph_closure={r.graph_closure.status} (want {expect_graph})")
    if r.interval_coverage.status != "pass": problems.append(f"interval_coverage={r.interval_coverage.status}")
    if r.per_record_membership.status != "pass": problems.append(f"per_record_membership={r.per_record_membership.status}")
    bad = [x.status for x in r.disclosures if x.status != "disclosure_match"]
    if bad: problems.append(f"non-matching disclosures: {sorted(set(bad))}")
    if problems:
        raise SystemExit(f"refusing to emit {name}: " + "; ".join(problems))

gate("v1 (all capsules)", v1, "pass")
gate("v2 (reports+aggregate only)", v2, "withheld")

frag1 = encode_fragment(v1); assert decode_fragment(frag1) == v1
frag2 = encode_fragment(v2); assert decode_fragment(frag2) == v2
url2 = "http://127.0.0.1:8080/bundle#" + frag2
json.dump(v1, open(os.path.join(HERE, "bundle_v1.json"), "w"))
json.dump(v2, open(os.path.join(HERE, "bundle_v2.json"), "w"))
open(os.path.join(HERE, "frag_v1.txt"), "w").write(frag1)
open(os.path.join(OUT, "tau2-airline-week1-permalink.txt"), "w").write(url2 + "\n")
print(f"\nv1 fragment bytes: {len(frag1)}  (offline HTML)")
print(f"v2 URL bytes: {len(url2)}  -> {os.path.join(OUT, 'tau2-airline-week1-permalink.txt')}")
print(f"report ids: {[r[:12] for r in report_ids]}  aggregate: {agg_id[:12]}")
