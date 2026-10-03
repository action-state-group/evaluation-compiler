"""Tests for the judgment names on judged records: rubric_digest and
judge_parameters_digest on a judged evaluation report, and the judged_from
reference (scripts/capsulectl_calls.py: seal_request). When CAPSULECTL names a
real capsulectl binary, one more test seals a judged_from reference through it
and verifies the record.

    python3 -m unittest discover -s tests -p 'test_*.py'
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from capsulectl_calls import EvidenceUnavailable, publish, seal_request  # noqa: E402
from run_daily import build_report  # noqa: E402

D1, D2, D3 = "a1" * 32, "b2" * 32, "c3" * 32
CASE_ID = "d4" * 32
REFERENCE = {"Type": "agent-action-capsule", "DigestAlg": "SHA-256", "Digest": CASE_ID,
             "CitationPurpose": "judged_from"}


class JudgedFrom(unittest.TestCase):
    def test_judged_from_is_an_agent_action_capsule_reference(self):
        request = seal_request("urn:x", "op", "dev", "t", {}, judged_from=CASE_ID)
        self.assertEqual(request["capsule"]["References"], [REFERENCE])

    def test_judged_from_must_be_a_capsule_id(self):
        for bad in ("task-14", CASE_ID.upper(), CASE_ID[:-1]):
            with self.assertRaises(EvidenceUnavailable, msg=bad):
                seal_request("urn:x", "op", "dev", "t", {}, judged_from=bad)

    def test_without_judged_from_the_request_is_unchanged(self):
        self.assertEqual(seal_request("urn:x", "op", "dev", "t", {"a": 1}), {
            "spec_version": "capsule-seal-request/v1",
            "capsule": {"ActionID": "urn:x", "ActionType": "fyi", "Operator": "op", "Developer": "dev",
                        "Timestamp": "t"},
            "payload": {"a": 1}})


class JudgedReport(unittest.TestCase):
    CLAUSE = {"id": "policy_compliance.confirmed_before_acting", "tier": "judged", "claim": "Explicit yes."}
    RECOMPUTED = {"id": "policy_compliance.within_fare_rules", "tier": "judged", "claim": "No forbidden change.",
                  "tier_switch": {"flag": "within_fare_rules_recomputed", "tier_when_on": "recomputed"}}
    PIN_INPUT = {"model_id": "m", "prompt_digest": D1, "axes_digest": D2, "sampling_params": {}}

    def test_judged_report_carries_rubric_and_judge_parameters_digests(self):
        report = build_report(self.CLAUSE, {}, {"verdict": "met"}, "c/v1", "case-1", CASE_ID, D3, "2026-09-23",
                              judge_pin=self.PIN_INPUT)
        self.assertEqual(report["judge_parameters_digest"], D3)
        self.assertEqual(report["rubric_digest"], self.PIN_INPUT["axes_digest"])
        self.assertEqual(report["judge_pin_digest"], D3)

    def test_recomputed_report_carries_no_judgment_names(self):
        report = build_report(self.RECOMPUTED, {"within_fare_rules_recomputed": True}, {"verdict": "met"},
                              "c/v1", "case-1", CASE_ID, D3, "2026-09-23", judge_pin=self.PIN_INPUT)
        self.assertNotIn("rubric_digest", report)
        self.assertNotIn("judge_parameters_digest", report)


@unittest.skipUnless(os.environ.get("CAPSULECTL"), "set CAPSULECTL to a capsulectl binary to run")
class AgainstCapsulectl(unittest.TestCase):
    """A judged_from reference sealed by `capsulectl publish` is committed and verifies."""

    def test_judged_from_publishes_and_verifies(self):
        ctl = os.environ["CAPSULECTL"]
        tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        env = dict(os.environ, HOME=str(tmp / "home"), XDG_CONFIG_HOME=str(tmp / "home" / ".config"))
        (tmp / "home" / ".config").mkdir(parents=True)

        def ctl_run(*args):
            proc = subprocess.run([ctl, *args], capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout) if proc.stdout.strip() else None

        keys = {n: ctl_run("key", "generate", "--output", str(tmp / f"{n}.seed")) for n in ("p", "c")}
        ctl_run("profile", "create", "--name", "t", "--type", "jsonl", "--jsonl-path", str(tmp / "store"),
                "--namespace", "t", "--log-id", "t", "--operator", "example-operator",
                "--signing-key-file", str(tmp / "p.seed"), "--trusted-key", keys["p"]["public_key"],
                "--checkpoint-signing-key-file", str(tmp / "c.seed"),
                "--checkpoint-trusted-key", keys["c"]["public_key"])
        ctl_run("store", "init", "--profile", "t")
        old_env = dict(os.environ)
        os.environ.update(env)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(old_env)))
        capsule_id = publish(ctl, "t", seal_request("urn:x", "example-operator", "dev", "2026-09-23T23:59:59Z",
                                                     {"verdict": "met"}, judged_from=CASE_ID), tmp, "judged")
        record = ctl_run("get", "--profile", "t", "--capsule-id", capsule_id)
        self.assertEqual(record["capsule"]["references"], [
            {"type": "agent-action-capsule", "digest_alg": "SHA-256", "digest": CASE_ID,
             "citation_purpose": "judged_from"}])
        ctl_run("get", "--profile", "t", "--capsule-id", capsule_id, "--raw", "--output", str(tmp / "r.json"))
        verified = ctl_run("verify", "--profile", "t", "--capsule", str(tmp / "r.json"))
        self.assertEqual(verified["capsule_identity"], "passed")


if __name__ == "__main__":
    unittest.main()
