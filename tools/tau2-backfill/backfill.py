#!/usr/bin/env python3
"""Backfill real tau2-bench trajectories into capsule-seal-request/v1 files.

Demo B evaluates a *dataset*, not an existing CLL, so its interactions are first
backfilled into a local SQLite CLL. tau2-bench is a runnable benchmark and ships
its recorded runs under `data/tau2/results/final/*.json`; each such file holds
`simulations[]`, one per (task_id, trial), with the real agent/user-simulator
`messages` transcript and tool calls. This script maps selected simulations to
seal requests — one per simulation — that `capsulectl publish` appends to the
CLL. It reads only shipped results: no agent run, no user simulator, no model
API key, and nothing is synthesized.

This is an operator-side data-prep tool in the compiler repo. It is NOT bundle
material: generated evaluation bundles still contain no programs.

Payload layout (the bound, authenticated interaction input):
  - case:              {benchmark, domain, task_id, trial}
  - provenance:        which results file / agent LLM / user-simulator LLM /
                       simulation id / seed / termination reason produced it
  - agent_interaction: the real transcript (role, content, tool calls with their
                       `requestor` attribution, and tool results), trimmed of
                       cost/usage/raw-data bookkeeping

Deliberately excluded from the payload: the simulation's `reward_info` (tau2's
own score). The compiler judges on its own axes and reads the desired outcome
independently from the dataset by `payload.case.task_id`, so tau2's score must
not travel inside the bound payload.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", required=True, type=pathlib.Path,
                   help="a tau2 results file, e.g. data/tau2/results/final/"
                        "claude-3-7-sonnet-20250219_retail_default_gpt-4.1-2025-04-14_4trials.json")
    p.add_argument("--out", required=True, type=pathlib.Path,
                   help="output directory for interaction-<n>.json seal requests")
    p.add_argument("--domain", default=None,
                   help="override the domain label; must match the results file's "
                        "environment_info.domain_name (default: use that value)")
    p.add_argument("--trial", type=int, default=0, help="which trial's simulation to use (default 0)")
    p.add_argument("--select", nargs="*", default=None,
                   help="task ids to emit, in order (default: the first --limit task ids)")
    p.add_argument("--limit", type=int, default=2,
                   help="number of task ids to emit when --select is omitted (default 2)")
    p.add_argument("--operator", default="tau2-demo",
                   help="operator identity recorded in the capsule (a real deployment sets its own)")
    p.add_argument("--developer", default="tau2@backfill-v1",
                   help="developer identity recorded in the capsule (a real deployment sets its own)")
    return p.parse_args(argv)


def resolve_domain(info: dict, override: str | None) -> str:
    """Domain comes from the results file; --domain may only confirm it.

    Mislabelling the domain would route the judge to another domain's gold for a
    task id that exists in several domains, so a disagreement is a hard error.
    """
    recorded = (info.get("environment_info") or {}).get("domain_name")
    if not recorded:
        raise SystemExit("results file has no environment_info.domain_name")
    if override is not None and override != recorded:
        raise SystemExit(f"--domain {override!r} disagrees with results domain {recorded!r}")
    return recorded


def normalize_timestamp(value: object, simulation_id: object) -> str:
    """Whole-seconds UTC RFC3339 from the simulation's own timestamp.

    A fabricated (wall-clock) timestamp would make the content-addressed Capsule
    ID non-reproducible, so a missing or unparseable stamp is a hard error rather
    than a silent `now()`.
    """
    if not isinstance(value, str) or not value:
        raise SystemExit(f"simulation {simulation_id!r} has no usable timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit(f"simulation {simulation_id!r} has an unparseable timestamp {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def trim_message(message: dict) -> dict:
    """Keep the interaction-bearing fields and tool-call attribution.

    Drops cost/usage/raw_data/turn bookkeeping but preserves `requestor` so an
    agent tool call is never confused with a user-simulator one.
    """
    kept: dict = {"role": message.get("role"), "content": message.get("content")}
    if message.get("tool_calls"):
        kept["tool_calls"] = [
            {"id": c.get("id"), "name": c.get("name"),
             "arguments": c.get("arguments"), "requestor": c.get("requestor")}
            for c in message["tool_calls"]
        ]
    if message.get("role") == "tool":
        kept["tool_call_id"] = message.get("id")
        kept["requestor"] = message.get("requestor")
        if message.get("error"):
            kept["error"] = message["error"]
    return kept


def build_request(sim: dict, info: dict, results_name: str, domain: str,
                  operator: str, developer: str) -> dict:
    task_id = sim["task_id"]
    trial = sim["trial"]
    return {
        "spec_version": "capsule-seal-request/v1",
        "capsule": {
            "ActionID": f"urn:tau2:{domain}:task-{task_id}:trial-{trial}",
            "ActionType": "fyi",
            "Operator": operator,
            "Developer": developer,
            "Timestamp": normalize_timestamp(sim.get("timestamp") or sim.get("start_time"), sim.get("id")),
        },
        "payload": {
            "case": {"benchmark": "tau2", "domain": domain, "task_id": task_id, "trial": trial},
            "provenance": {
                "results_file": results_name,
                "agent_llm": (info.get("agent_info") or {}).get("llm"),
                "user_simulator_llm": (info.get("user_info") or {}).get("llm"),
                "simulation_id": sim.get("id"),
                "seed": sim.get("seed"),
                "termination_reason": sim.get("termination_reason"),
            },
            "agent_interaction": {"messages": [trim_message(m) for m in sim.get("messages", [])]},
        },
    }


def pick_simulations(data: dict, select: list[str] | None, trial: int, limit: int) -> list[dict]:
    sims = data["simulations"]
    at_trial = {s["task_id"]: s for s in sims if s["trial"] == trial}
    if not at_trial:
        raise SystemExit(f"no simulations at trial {trial}")
    if select is None:
        # first `limit` task ids in the results file's declared task order
        task_order = [t.get("id") for t in data.get("tasks", [])]
        ordered = [tid for tid in task_order if tid in at_trial]
        # fall back to simulation order for any task not listed under `tasks`
        for tid in at_trial:
            if tid not in ordered:
                ordered.append(tid)
        select = ordered[:limit]
    chosen = []
    for task_id in select:
        if task_id not in at_trial:
            raise SystemExit(f"no simulation for task {task_id!r} at trial {trial}")
        chosen.append(at_trial[task_id])
    return chosen


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.select is not None and not args.select:
        raise SystemExit("--select requires at least one task id")
    data = json.loads(args.results.read_text())
    sims = data.get("simulations")
    if not isinstance(sims, list) or not sims:
        raise SystemExit(f"{args.results} has no simulations[]")
    info = data.get("info", {})
    domain = resolve_domain(info, args.domain)
    chosen = pick_simulations(data, args.select, args.trial, args.limit)
    args.out.mkdir(parents=True, exist_ok=True)
    for n, sim in enumerate(chosen):
        request = build_request(sim, info, args.results.name, domain, args.operator, args.developer)
        path = args.out / f"interaction-{n}.json"
        path.write_text(json.dumps(request, indent=2) + "\n")
        print(f"wrote {path}  (domain={domain} task_id={sim['task_id']} trial={sim['trial']} "
              f"reward={sim.get('reward_info', {}).get('reward')})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
