#!/usr/bin/env python3
"""Publish daily airline reports and a month-selected evaluation summary.

Bundle assembly and HTML rendering belong to ``capsulectl view``, not this script.
"""
from __future__ import annotations
import argparse, calendar, json, os, pathlib, subprocess, tempfile

HERE = pathlib.Path(__file__).resolve().parent
CAPSULECTL = os.environ.get("CAPSULECTL", "capsulectl")
PROFILE = os.environ.get("AAC_PROFILE", "airlinedemo")
LOG_ID = os.environ.get("AAC_LOG_ID", "tau2-airline-20260914")
AXES = ("policy_compliance", "task_resolution", "grounded_communication")

def cli(*args):
    result = subprocess.run([CAPSULECTL, *args], text=True, capture_output=True)
    if result.returncode: raise SystemExit(f"capsulectl {' '.join(args)}: {result.stderr.strip()}")
    return json.loads(result.stdout)
def publish(request):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f: json.dump(request, f); name = f.name
    try:
        response = cli("publish", "--profile", PROFILE, "--request", name)
        return response.get("capsule_id") or response["capsuleId"]
    finally: os.unlink(name)
def payload(record):
    for artifact in record.get("artifacts", []):
        if artifact.get("name") in ("agent_input", "payload") and isinstance(artifact.get("content"), dict): return artifact["content"]
    return None
def records():
    after = 0
    while True:
        page = cli("cll", "list", "--profile", PROFILE, "--after", str(after), "--limit", "1000")
        for entry in page.get("entries", []):
            cid = entry.get("capsule_id") or entry["capsuleId"]
            body = payload(cli("get", "--profile", PROFILE, "--capsule-id", cid))
            if body: yield cid, body
        if not page.get("entries") or page.get("next_after") in (None, after): return
        after = page["next_after"]
def month_bounds(month):
    year, number = map(int, month.split("-")); return f"{year:04d}-{number:02d}-01", f"{year:04d}-{number:02d}-{calendar.monthrange(year, number)[1]:02d}"
def aggregate(task):
    statuses = [task[a]["status"] for a in AXES if task[a]["status"] != "not_applicable"]
    return "pass" if statuses and all(s == "pass" for s in statuses) else "fail"

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--month", default="2026-09"); parser.add_argument("--days", type=int); parser.add_argument("--verdicts", type=pathlib.Path, default=HERE / "verdicts.json"); args = parser.parse_args()
    days = json.loads(args.verdicts.read_text())["days"][:args.days]
    # Act attribution comes from committed case.conversation_id + turn_idx, never
    # from CLL sequence or the lexical order of backfill filenames.
    acts = {}
    for cid, body in records():
        case = body.get("case", {})
        if case.get("conversation_id") is not None and case.get("turn_idx") is not None: acts.setdefault(str(case.get("task_id")), []).append(cid)
    for day in days:
        cases, act_ids = [], []
        for task_id, judgment in day["tasks"].items():
            selected = acts.get(str(task_id), [])
            if not selected: raise SystemExit(f"no acts selected by case.conversation_id/turn_idx for task {task_id}")
            act_ids.extend(selected)
            cases.append({"task_id": task_id, "trial": 0, "axis_judgments": [{"axis_id": axis, "outcome_id": "policy_compliant_resolution", **judgment[axis]} for axis in AXES], "case_aggregate": aggregate(judgment)})
        passed = sum(c["case_aggregate"] == "pass" for c in cases)
        report = {"spec_version":"evaluation-report/v1", "date":day["date"], "evaluation_identity":{"evaluator":"tau2-airline-eval","run":f"day-{day['day']}","judged_at":day["date"]}, "scenario":"tau2-airline policy-compliant resolution (daily)", "cases":cases, "source_selection":{"log_id":LOG_ID,"conversations":list(day["tasks"]),"interaction_capsule_ids":act_ids}, "daily_aggregate":{"policy":"all_required","cases_total":len(cases),"cases_pass":passed,"verdict":"pass" if passed == len(cases) else "fail"}, "limitations":["Demo fixture judgments; acts selected from committed case conversation_id and turn_idx."]}
        req = {"spec_version":"capsule-seal-request/v1", "capsule":{"ActionID":f"tau2-airline-eval-{day['date']}","ActionType":"fyi","Operator":"ACME-AIR","Developer":"tau2-airline-eval@v1","Timestamp":f"{day['date']}T18:00:00Z","References":[{"Type":"agent-action-capsule","DigestAlg":"SHA-256","Digest":cid,"CitationPurpose":"acted_on"} for cid in act_ids]}, "payload":report}
        print("DAILY_REPORT_CAPSULE_ID=" + publish(req))
    start, end = month_bounds(args.month)
    selected = sorted((cid, body) for cid, body in records() if body.get("spec_version") == "evaluation-report/v1" and start <= body.get("date", "") <= end)
    if not selected: raise SystemExit(f"no evaluation-report/v1 capsules declare dates in {args.month}")
    counts = {a:{s:0 for s in ("pass","fail","unjudgeable","not_applicable")} for a in AXES}
    for _, report in selected:
        for case in report.get("cases", []):
            for judgment in case.get("axis_judgments", []): counts[judgment["axis_id"]][judgment["status"]] += 1
    per_axis = {a:{**v,"pass_rate":f"{v['pass']}/{v['pass']+v['fail']+v['unjudgeable']}"} for a,v in counts.items()}
    ids = [cid for cid,_ in selected]
    summary = {"spec_version":"evaluation-summary/v1","period":args.month,"aggregation_identity":{"reducer":"tau2-airline-monthly","reduced_at":end},"source_selection":{"log_id":LOG_ID,"selection":"declared evaluation-report/v1 payload.date within month","contributing_report_capsule_ids":ids},"cross_case_aggregation":"rate","per_axis":per_axis,"counts":{"reports":len(ids),"unique_cases":sum(len(x.get("cases",[])) for _,x in selected)},"limitations":["Monthly roll-up selects frozen IDs by declared report.date, not sequence range."]}
    req = {"spec_version":"capsule-seal-request/v1","capsule":{"ActionID":f"tau2-airline-eval-{args.month}-summary","ActionType":"fyi","Operator":"ACME-AIR","Developer":"tau2-airline-monthly@v1","Timestamp":f"{end}T20:00:00Z","References":[{"Type":"agent-action-capsule","DigestAlg":"SHA-256","Digest":cid,"CitationPurpose":"acted_on"} for cid in ids]},"payload":summary}
    print("MONTHLY_SUMMARY_CAPSULE_ID=" + publish(req))
if __name__ == "__main__": main()
