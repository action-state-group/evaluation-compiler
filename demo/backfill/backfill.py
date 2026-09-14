#!/usr/bin/env python3
"""Backfill a tau2-bench results file into PER-ACT capsule-seal-request/v1 files.

    backfill.py --results <tau2 results/final/*.json> --out <dir>

Input is one shipped tau2 results file. Output is one seal request per AGENT ACT:
each assistant turn the agent produced in a task's trial-0 simulation (its
natural-language reply and/or the tool calls it issued that step). It is NOT one
capsule per whole task, and NOT one per raw message: the user-simulator turns and
the tool results are never their own capsules — they are inputs/outputs of the
surrounding act capsules. It reads only the results file: no agent run, no user
simulator, no model API key, and nothing synthesized. Then
`capsulectl publish --request <file>` seals each act into a Capsule and appends it
to the CLL.

Per-act mapping
---------------
An act = one `role="assistant"` message (the system under evaluation). tau2's user
simulator appears as `role="user"` and tool results as `role="tool"` (all with
`requestor="assistant"` in the airline runs); neither is an act.

For the i-th assistant message (ordered by `turn_idx`):

- `payload.agent_input` reconstructs the model-invocation context the agent saw
  before it spoke: the domain `policy` (system/policy), the observed `tools`
  surface, and `messages` — every prior turn (greeting, user turns, earlier
  assistant turns, tool results) up to and including the latest user turn.
- `agent_output` is the assistant message that step produced: its `content`
  and/or `tool_calls`.

There are NO effect blocks, NO gate/decision, NO gate_executed. A write tool call
is simply part of `agent_output`; its result becomes context in the next act's
`agent_input`.

Digest binding (do not hash here)
---------------------------------
The seal request carries `payload` and `agent_output` as raw JSON. `capsulectl
publish` (capsule-cli → capsule-emit-go) commits them as DIGESTS under
`model_attestation.compute_attestation`: `payload` → `agent_input_digest`,
`agent_output` → `agent_output_digest`, using the single AAC JSON-DIGEST path
(emit.DigestJSON = SHA-256 over RFC 8785 JCS). The original bytes are written to
the capsule-emit-go artifact store as bound `present` artifacts (for the SQLite
`airlinedemo` profile, the same `store.db`). This script therefore computes no
digest of its own — introducing a second hashing path would be a bug.

Grouping and ordering
---------------------
Every act of one conversation shares a `case` block: the existing `task_id`/`trial`
plus a `conversation_id` (the tau2 simulation id) and this act's `turn_idx`; acts
are ordered by `turn_idx`.

Honesty properties (unchanged)
------------------------------
Gold labels are stripped upstream (`reward_info` / `evaluation_criteria`) and are
never placed in the bound payload; the judge reads the desired outcome
independently from the dataset by `payload.case.task_id`. Nothing is synthesized.
Each act's `Timestamp` is that assistant message's own tau2 timestamp; a missing
or unparseable stamp is a hard error, because a fabricated timestamp would make
the content-addressed Capsule id non-reproducible.

The domain is read from the results file. Operator/Developer are the fixed
provenance identities of this backfill tool, not per-run inputs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

OPERATOR = "tau2-demo"
DEVELOPER = "tau2@backfill-v1"


def normalize_timestamp(value: object, simulation_id: object) -> str:
    """Whole-seconds UTC RFC3339 from the source's own timestamp.

    A fabricated (wall-clock) timestamp would make the content-addressed Capsule
    ID non-reproducible, so a missing or unparseable stamp is a hard error.
    """
    if not isinstance(value, str) or not value:
        raise SystemExit(f"simulation {simulation_id!r} has an act with no usable timestamp")
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
    agent tool call is never confused with a user-simulator one. Used both for the
    prior-turn context in `agent_input.messages` and for the act's `agent_output`.
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


def agent_tool_surface(messages: list[dict]) -> list[str]:
    """Distinct tool names the agent invoked anywhere in this conversation.

    Derived from the transcript (not synthesized): the results file ships no tool
    schemas, so this is the observable agent tool surface, held constant across the
    conversation's acts as an available-tools set. Only `requestor="assistant"`
    calls count, so a user-simulator tool call would never leak in.
    """
    names = {
        c.get("name")
        for m in messages
        for c in (m.get("tool_calls") or [])
        if c.get("requestor") == "assistant" and c.get("name")
    }
    return sorted(names)


def build_act_request(sim: dict, info: dict, results_name: str, domain: str,
                      policy: object, tools: list[str], conversation_id: object,
                      act_index: int, act_msg: dict, prefix: list[dict]) -> dict:
    task_id = sim["task_id"]
    trial = sim["trial"]
    turn_idx = act_msg.get("turn_idx")
    return {
        "spec_version": "capsule-seal-request/v1",
        "capsule": {
            "ActionID": f"urn:tau2:{domain}:task-{task_id}:trial-{trial}:turn-{turn_idx}",
            "ActionType": "fyi",
            "Operator": OPERATOR,
            "Developer": DEVELOPER,
            "Timestamp": normalize_timestamp(act_msg.get("timestamp"), sim.get("id")),
        },
        # payload is committed as model_attestation.compute_attestation.agent_input_digest.
        "payload": {
            "case": {
                "benchmark": "tau2", "domain": domain, "task_id": task_id, "trial": trial,
                "conversation_id": conversation_id, "turn_idx": turn_idx, "act_index": act_index,
            },
            "provenance": {
                "results_file": results_name,
                "agent_llm": (info.get("agent_info") or {}).get("llm"),
                "user_simulator_llm": (info.get("user_info") or {}).get("llm"),
                "simulation_id": sim.get("id"),
                "seed": sim.get("seed"),
                "termination_reason": sim.get("termination_reason"),
            },
            "agent_input": {
                "policy": policy,
                "tools": tools,
                "messages": [trim_message(m) for m in prefix],
            },
        },
        # agent_output is committed as model_attestation.compute_attestation.agent_output_digest.
        "agent_output": trim_message(act_msg),
    }


def safe_name(task_id: object) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(task_id))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True, type=pathlib.Path,
                    help="a tau2 results file (data/tau2/results/final/*.json)")
    ap.add_argument("--out", required=True, type=pathlib.Path,
                    help="output directory; one seal request per agent act (trial-0 runs)")
    ap.add_argument("--conversations", type=int, default=None, metavar="N",
                    help="keep only the first N trial-0 conversations (by task_id order); default all")
    args = ap.parse_args(argv)

    data = json.loads(args.results.read_text())
    sims = data.get("simulations")
    if not isinstance(sims, list) or not sims:
        raise SystemExit(f"{args.results} has no simulations[]")
    info = data.get("info", {})
    env = info.get("environment_info") or {}
    domain = env.get("domain_name")
    if not domain:
        raise SystemExit("results file has no environment_info.domain_name")
    policy = env.get("policy")

    # one conversation per task: its trial-0 simulation
    trial0 = [s for s in sims if s.get("trial") == 0]
    if not trial0:
        raise SystemExit(f"{args.results} has no trial-0 simulations")
    trial0 = sorted(trial0, key=lambda s: str(s["task_id"]))
    if args.conversations is not None:
        trial0 = trial0[: args.conversations]

    args.out.mkdir(parents=True, exist_ok=True)
    # clear our own prior outputs so a reused dir can't leak a different/smaller run
    for stale in args.out.glob("task-*.json"):
        stale.unlink()
    # NOTE: CLL sequence is set by the publish order, which is the shell glob over these
    # filenames (lexical). Act files are zero-padded so a conversation's acts publish in
    # turn order; but across tasks the lexical task order is not task_id order, and one task
    # now yields many entries. Select a specific case/act by capsule/case fields (task_id +
    # conversation_id + turn_idx), never by assuming sequence == task.
    used: dict[str, int] = {}
    n_acts = 0
    for sim in trial0:
        messages = sorted(sim.get("messages", []), key=lambda m: m.get("turn_idx"))
        conversation_id = sim.get("id")
        tools = agent_tool_surface(messages)
        base = f"task-{safe_name(sim['task_id'])}"
        c = used.get(base, 0)
        used[base] = c + 1
        stem = base if c == 0 else f"{base}-c{c}"
        act_index = 0
        for i, msg in enumerate(messages):
            if msg.get("role") != "assistant":
                continue  # user-simulator turns and tool results are inputs, not acts
            request = build_act_request(
                sim, info, args.results.name, domain, policy, tools,
                conversation_id, act_index, msg, messages[:i],
            )
            name = f"{stem}-act-{act_index:04d}.json"
            (args.out / name).write_text(json.dumps(request, indent=2) + "\n")
            act_index += 1
            n_acts += 1
    print(f"wrote {n_acts} act seal requests across {len(trial0)} conversations "
          f"(domain={domain}, trial 0) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
