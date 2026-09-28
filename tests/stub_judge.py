#!/usr/bin/env python3
"""A stand-in judge for tests: no model, deterministic, and labelled as such.

Reads one judge request on stdin (see scripts/run_daily.py) and answers from a hash
of the case id alone, so a test run is reproducible and runs anywhere with no model,
key or network. Its verdicts say nothing about the conversation; a real deployment
points --judge-cmd at the pinned judge instead.
"""
import hashlib
import json
import sys

request = json.load(sys.stdin)
case = request["case"]
h = int(hashlib.sha256(f"judge:{case['task_id']}".encode()).hexdigest(), 16)
verdict = "not_evaluable" if h % 7 == 0 else ("met" if h % 2 == 0 else "not_met")
json.dump({"verdict": verdict, "rationale": "stub judge: verdict derived from the case id; no model read the conversation"}, sys.stdout)
