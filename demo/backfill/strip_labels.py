#!/usr/bin/env python3
"""Strip gold labels from a tau2-bench results file, keeping the raw tau2 format.

    strip_labels.py --results <tau2 results/final/*.json> --out <cleaned .json>

The output is the SAME tau2 results structure ({timestamp, info, tasks, simulations})
with only the desired-outcome / gold fields removed, so it reads exactly like a raw
tau2-bench run that simply has no answer key. This is the customer's pre-capsule
interaction history for the backfill demo: an evaluator must derive the desired
outcome from evidence (booking DB + policy + transcript), not read it from a label.

Removed (the only things removed):
  - simulations[].reward_info        tau2's native graded score for the run
  - tasks[].evaluation_criteria      the gold actions / nl_assertions / communicate_info

Everything else is kept verbatim, including the full raw `messages` (content, tool
calls and results, and tau2's per-message cost/usage/raw_data/turn_idx bookkeeping)
and each task's description / user_scenario / ticket / initial_state context.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

# Keys removed wherever they appear at their expected level.
SIMULATION_GOLD = "reward_info"
TASK_GOLD = "evaluation_criteria"


def strip(data: dict) -> tuple[dict, int, int]:
    n_reward = n_criteria = 0
    for sim in data.get("simulations", []) or []:
        if SIMULATION_GOLD in sim:
            del sim[SIMULATION_GOLD]
            n_reward += 1
    for task in data.get("tasks", []) or []:
        if TASK_GOLD in task:
            del task[TASK_GOLD]
            n_criteria += 1
    return data, n_reward, n_criteria


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--results", required=True, type=pathlib.Path,
                    help="a tau2 results file (data/tau2/results/final/*.json)")
    ap.add_argument("--out", required=True, type=pathlib.Path,
                    help="output path for the cleaned tau2-format results file")
    args = ap.parse_args(argv)

    data = json.loads(args.results.read_text())
    if "simulations" not in data or "tasks" not in data:
        raise SystemExit(f"{args.results} is not a tau2 results file (no simulations/tasks)")

    data, n_reward, n_criteria = strip(data)

    # Fail loudly if any gold survived — the whole point is that none does.
    leaked = [s["id"] for s in data["simulations"] if SIMULATION_GOLD in s]
    if leaked:
        raise SystemExit(f"reward_info still present on simulations: {leaked[:3]}")
    if any(TASK_GOLD in t for t in data["tasks"]):
        raise SystemExit("evaluation_criteria still present on tasks")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1) + "\n")
    print(f"stripped reward_info from {n_reward} simulations, "
          f"evaluation_criteria from {n_criteria} tasks -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
