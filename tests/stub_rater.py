#!/usr/bin/env python3
"""A stand-in for the human expert in tests: it rates the blind packets.

It sees only what a human would (the packets written by scripts/run_weekly.py, which
carry no verdict) and rates each from a hash of its case id, independent of the stub
judge's, so agreement is partial. A real run pauses for a person instead; nothing in
the weekly skill ever fills in a rating.

    stub_rater.py PACKETS_DIR > ratings.json
"""
import hashlib
import json
import pathlib
import sys

ratings = []
for packet in sorted(pathlib.Path(sys.argv[1]).glob("*.json")):
    case_id = json.loads(packet.read_text())["case_id"]
    h = int(hashlib.sha256(f"rater:{case_id}".encode()).hexdigest(), 16)
    ratings.append({"case_id": case_id, "rating": "met" if h % 2 == 0 else "not_met"})
json.dump(ratings, sys.stdout, indent=2)
