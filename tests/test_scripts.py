"""Unit tests for the exercise scripts' pure logic (no capsulectl, no book).

    python3 -m unittest discover -s tests -p 'test_*.py'
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from capsulectl_calls import EvidenceUnavailable  # noqa: E402
from run_daily import checked_answer  # noqa: E402
from run_weekly import PACKET_FIELDS, blind_packet, checked_ratings  # noqa: E402

REPORT = {"record_type": "evaluation-report/v1", "case_id": "tau2:airline:task-1:trial-0",
          "clause_id": "policy-followed", "verdict": "met", "rationale": "the agent refunded correctly",
          "judge_pin_digest": "ab" * 32, "stratum": "met", "source_capsule_id": "cd" * 32}
CASE = {"case": {"task_id": "1"}, "agent_interaction": {"messages": [{"role": "user", "content": "cancel"}]}}


class BlindPacket(unittest.TestCase):
    def test_carries_only_the_whitelisted_fields(self):
        packet = blind_packet(REPORT, CASE)
        self.assertEqual(tuple(packet), PACKET_FIELDS)
        for leaked in ("verdict", "rationale", "judge_pin_digest", "stratum", "source_capsule_id", "record_type"):
            self.assertNotIn(leaked, packet)

    def test_no_value_of_the_report_but_its_case_and_clause_reaches_the_packet(self):
        packet = blind_packet(REPORT, CASE)
        leaked = {REPORT["verdict"], REPORT["rationale"], REPORT["judge_pin_digest"], REPORT["source_capsule_id"]}
        self.assertFalse(leaked & {v for v in packet.values() if isinstance(v, str)})


class CheckedRatings(unittest.TestCase):
    SAMPLE = {"a", "b"}

    def test_one_rating_per_sampled_case_passes(self):
        ratings = [{"case_id": "a", "rating": "met"}, {"case_id": "b", "rating": "not_met"}]
        self.assertEqual(checked_ratings(ratings, self.SAMPLE), ratings)

    def test_fewer_ratings_than_drawn_pass_and_leave_a_shortfall(self):
        self.assertEqual(len(checked_ratings([{"case_id": "a", "rating": "met"}], self.SAMPLE)), 1)

    def test_a_second_rating_for_one_case_is_refused(self):
        with self.assertRaisesRegex(ValueError, "more than one rating"):
            checked_ratings([{"case_id": "a", "rating": "met"}, {"case_id": "a", "rating": "not_met"}], self.SAMPLE)

    def test_a_rating_outside_the_sample_is_refused(self):
        with self.assertRaisesRegex(ValueError, "outside the sample"):
            checked_ratings([{"case_id": "z", "rating": "met"}], self.SAMPLE)

    def test_a_rating_that_is_not_a_verdict_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not met, not_met or not_evaluable"):
            checked_ratings([{"case_id": "a", "rating": "yes"}], self.SAMPLE)


class CheckedAnswer(unittest.TestCase):
    def test_each_verdict_passes(self):
        for verdict in ("met", "not_met", "not_evaluable"):
            self.assertEqual(checked_answer({"verdict": verdict})["verdict"], verdict)

    def test_anything_else_is_refused(self):
        for answer in ({"verdict": "pass"}, {}, None, "met"):
            with self.assertRaises(EvidenceUnavailable):
                checked_answer(answer)


if __name__ == "__main__":
    unittest.main()
