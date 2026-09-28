#!/usr/bin/env python3
"""Exercise script for skills/daily-judge-and-close: run one day, end to end.

It performs the skill's steps in order and calls only the verbs the skill lists:
judge pin, cll list, get, verify, publish, close. The judge is an external command
(--judge-cmd) that reads one case on stdin and prints {"verdict", "rationale"};
this script never decides a verdict. Any consequential step that produces no
record stops the run with `evidence unavailable` before the next one.

    run_daily.py --profile tau2 --spec demo/tau2/compiled.json \\
        --judge-cmd "python3 tests/stub_judge.py" --judge-model-id stub-judge/0 \\
        --date 2026-09-16 --out RUN_DIR

Re-running a day seals nothing new: every report is published with a timestamp fixed
to the day, so the same judgment is the same capsule, and `close` returns the day's
existing Close.
"""

import argparse
import datetime
import json
import pathlib
import shlex
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from capsulectl_calls import (EvidenceUnavailable, committed_on, list_capsules, payload,  # noqa: E402
                              publish, run, seal_request, sha256_file, verify)

VERDICTS = {"met", "not_met", "not_evaluable"}


def judge(cmd, case_payload, clause, spec_root):
    request = {"clause": clause, "case": case_payload["case"],
               "agent_interaction": case_payload["agent_interaction"],
               "policy": str(spec_root / "airline-data" / "policy.md"),
               "booking_db": str(spec_root / "airline-data" / "db.json")}
    proc = subprocess.run(shlex.split(cmd), input=json.dumps(request), capture_output=True, text=True)
    if proc.returncode != 0:
        raise EvidenceUnavailable(f"judge exited {proc.returncode}: {proc.stderr.strip()}")
    answer = json.loads(proc.stdout)
    if answer.get("verdict") not in VERDICTS:
        raise EvidenceUnavailable(f"judge returned no valid verdict: {answer!r}")
    return answer


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--spec", required=True, type=pathlib.Path)
    ap.add_argument("--judge-cmd", required=True)
    ap.add_argument("--judge-model-id", required=True, help="the pinned judge's model id, as the judge command reports it")
    ap.add_argument("--date", required=True, help="the day to judge and close, YYYY-MM-DD (UTC)")
    ap.add_argument("--out", required=True, type=pathlib.Path)
    ap.add_argument("--capsulectl", default="capsulectl")
    args = ap.parse_args(argv)

    root = args.spec.resolve().parents[2]
    spec = json.loads(args.spec.read_text())
    day = datetime.date.fromisoformat(args.date)
    out = args.out / f"day-{day}"
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    ctl, profile = args.capsulectl, args.profile
    operator = run(ctl, "profile", "show", profile)["Operator"]
    log = {"skill": "daily-judge-and-close", "day": str(day), "profile": profile}

    try:
        # 1. Resolve the pinned judge before judging anything.
        pin_input = {"model_id": args.judge_model_id,
                     "prompt_digest": sha256_file(root / spec["judge"]["prompt"]),
                     "axes_digest": sha256_file(root / spec["judge"]["axes"]),
                     "sampling_params": spec["judge"].get("sampling_params") or {}}
        (work / "judge-pin.json").write_text(json.dumps(pin_input))
        pin = run(ctl, "judge", "pin", str(work / "judge-pin.json"))["judge_pin_digest"]
        log["judge_pin_digest"] = pin

        # 2. Read the day's range: the cases the book committed that day.
        cases = []
        for entry in list_capsules(ctl, profile):
            if not committed_on(entry, day):
                continue
            body = payload(ctl, profile, entry["capsule_id"])
            if isinstance(body, dict) and isinstance(body.get("case"), dict):
                cases.append((entry["capsule_id"], body))
        log["cases"] = len(cases)

        # 3-4. Authenticate each case, judge it per judged clause, seal the report.
        reports, verdicts = [], {}
        stamp = f"{day}T23:59:59Z"
        for capsule_id, body in cases:
            verify(ctl, profile, capsule_id, work)
            c = body["case"]
            case_id = f"{c['benchmark']}:{c['domain']}:task-{c['task_id']}:trial-{c['trial']}"
            for clause in spec["clauses"]:
                if clause["tier"] != "judged":
                    continue  # recomputed clauses go to the engine plugin, never a judge
                answer = judge(args.judge_cmd, body, clause, root)
                report = {"record_type": "evaluation-report/v1", "epistemic_type": "semantic_judgment",
                          "contract": spec["contract"], "clause_id": clause["id"], "case_id": case_id,
                          "source_capsule_id": capsule_id, "judge_pin_digest": pin,
                          "verdict": answer["verdict"], "rationale": answer.get("rationale", ""),
                          "period": f"day:{day}"}
                rid = publish(ctl, profile, seal_request(
                    f"urn:evidencebook-skills:evaluation-report:{case_id}:{clause['id']}", operator,
                    "evidencebook-skills/daily-judge-and-close", stamp, report), work, f"report-{capsule_id[:16]}")
                reports.append(rid)
                verdicts[answer["verdict"]] = verdicts.get(answer["verdict"], 0) + 1
        log["reports"] = reports
        log["verdicts"] = verdicts

        # 5. Seal the day's Close. No peer bundle is held: it is unilateral.
        close_args = ["close", "--profile", profile, "--period", "day", "--date", str(day),
                      "--counterparty", spec["counterparty"]]
        capsule_out, bundle_out = out / "close.json", out / "close-bundle.json"
        if not capsule_out.exists():
            close_args += ["--capsule-out", str(capsule_out), "--bundle-out", str(bundle_out)]
        closed = run(ctl, *close_args)
        log["close"] = {"record_id": closed["record_id"], "already_closed": closed["already_closed"],
                        "unilateral": not closed.get("peer_bundle"),
                        "window": [closed["reconciliation"]["from_seq"], closed["reconciliation"]["to_seq"]],
                        "capsule": str(capsule_out), "bundle": str(bundle_out)}
    except EvidenceUnavailable as e:
        log["evidence_unavailable"] = str(e)
        print(json.dumps(log, indent=2))
        return 2
    (out / "run.json").write_text(json.dumps(log, indent=2))
    print(json.dumps(log, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
