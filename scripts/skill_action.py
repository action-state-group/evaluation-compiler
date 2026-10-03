#!/usr/bin/env python3
"""Run one skill action and seal a skill-action/v1 capsule for it.

The exercise scripts (run_daily.py, run_weekly.py) seal their own steps. This is
for the actions a skill runs by hand from its SKILL.md: install, discover, map,
`contract validate`, `result build`, and any other step. It runs the command,
passes its stdout and stderr through unchanged, and seals one record of it with
`capsulectl publish` (scripts/capsulectl_calls.py: skill_action_record).

    skill_action.py --profile NAME --skill evidence-contract-compile --action contract-validate \\
        --input contract=CONTRACT.yaml --input schema=SCHEMA.json \\
        -- capsulectl contract validate CONTRACT.yaml --schema SCHEMA.json --json

The record carries digests only: of each --input file, of the command's stdout,
and of its argv. It never carries file contents, paths, the profile or the
environment. Role names that name secret material (key, seed, token, ...) are
refused, and so are input files that look like key material.

A judgment action adds --judged-from CAPSULE_ID and --rubric FILE (and
--judge-parameters FILE when a judge ran under parameters): the record then
carries rubric_digest and judge_parameters_digest, and the capsule cites the
judged record as judged_from.

A failed command is sealed too (`outcome: failed`), and this script exits with
the command's own exit status. If the record cannot be sealed, it prints
`evidence unavailable` and exits 2 whatever the command did: an action with no
record stops the run.
"""

import argparse
import datetime
import hashlib
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from capsulectl_calls import (EvidenceUnavailable, emit_skill_action, json_digest, run,  # noqa: E402
                              sha256_file, skill_action_record)

KEY_MATERIAL_SUFFIXES = (".seed", ".key", ".pem", ".p12", ".pfx", ".env")


def parse_input(spec):
    role, sep, path = spec.partition("=")
    if not sep or not role or not path:
        raise EvidenceUnavailable(f"--input must be ROLE=PATH, got {spec!r}")
    p = pathlib.Path(path)
    if p.name.startswith(".env") or p.suffix.lower() in KEY_MATERIAL_SUFFIXES:
        raise EvidenceUnavailable(f"--input {role}: refusing a key-material file ({p.name})")
    if not p.is_file():
        raise EvidenceUnavailable(f"--input {role}: not a file: {path}")
    return role, sha256_file(p)


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv):
    if "--" not in argv:
        print("usage: skill_action.py [options] -- COMMAND [ARGS...]", file=sys.stderr)
        return 2
    split = argv.index("--")
    own, command = argv[:split], argv[split + 1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--skill", required=True)
    ap.add_argument("--action", required=True)
    ap.add_argument("--input", action="append", default=[], metavar="ROLE=PATH")
    ap.add_argument("--at", help="RFC3339 UTC timestamp for the capsule (default: now). "
                                 "Fix it to make a re-run seal the same capsule.")
    ap.add_argument("--judged-from", help="capsule_id of the record this action judges")
    ap.add_argument("--rubric", type=pathlib.Path, help="the rubric the judgment is made against")
    ap.add_argument("--judge-parameters", type=pathlib.Path, help="the parameters the judge ran under")
    ap.add_argument("--work", type=pathlib.Path, default=pathlib.Path(".skill-actions"),
                    help="where the exact seal request is kept before publishing")
    ap.add_argument("--capsulectl", default="capsulectl")
    args = ap.parse_args(own)
    if not command:
        ap.error("no command after --")
    judgment = (args.judged_from, args.rubric, args.judge_parameters)
    if any(x is not None for x in judgment) and (args.judged_from is None or args.rubric is None):
        ap.error("a judgment action needs both --judged-from and --rubric")

    try:
        inputs = [parse_input(spec) for spec in args.input]
        operator = run(args.capsulectl, "profile", "show", args.profile)["Operator"]
    except EvidenceUnavailable as e:
        print(f"evidence unavailable: {e}", file=sys.stderr)
        return 2

    try:
        proc = subprocess.run(command, capture_output=True)
        code, stdout = proc.returncode, proc.stdout
        sys.stderr.buffer.write(proc.stderr)
    except OSError as e:
        code, stdout = 127, b""
        print(f"skill_action.py: {command[0]}: {e}", file=sys.stderr)
    sys.stdout.buffer.write(stdout)
    sys.stdout.flush()

    try:
        record = skill_action_record(
            args.skill, args.action, inputs=inputs,
            output_digest=hashlib.sha256(stdout).hexdigest(),
            outcome="ok" if code == 0 else "failed", exit_code=code,
            argv_digest=json_digest(command),
            rubric_digest=sha256_file(args.rubric) if args.rubric else None,
            judge_parameters_digest=sha256_file(args.judge_parameters) if args.judge_parameters else None)
        args.work.mkdir(parents=True, exist_ok=True)
        capsule_id = emit_skill_action(args.capsulectl, args.profile, args.work, operator,
                                       args.at or utc_now(), record, judged_from=args.judged_from)
    except (EvidenceUnavailable, OSError) as e:
        print(f"evidence unavailable: {args.skill} {args.action}: {e}", file=sys.stderr)
        return 2
    print(f"skill-action {args.skill} {args.action}: {capsule_id}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
