"""Functional tests for the metacognitive SDK."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import fixture_metacog as fx  # noqa: E402
from vega_metacog import evidence, recursive, requirements  # noqa: E402


class Evidence(unittest.TestCase):
    def test_rungs(self):
        self.assertEqual(evidence.grade("x holds", [fx.src(1), fx.src(2)])["rung"], "FACT")
        self.assertEqual(evidence.grade("x holds", [fx.src(1)])["rung"], "SINGLE_SOURCE")
        self.assertEqual(evidence.grade("x holds", [fx.src(1, checkable=False)])["rung"], "UNVERIFIED")
        self.assertEqual(evidence.grade("x holds", [])["rung"], "RECALL_ONLY")
        self.assertEqual(evidence.grade("x holds", [{"id": "a1b2c3d", "origin": "git", "checkable": True, "kind": "commit"}])["rung"], "FACT")

    def test_repeats_of_one_origin_are_one_source(self):
        self.assertEqual(evidence.grade("x holds", [fx.src(1, origin="press release"), fx.src(2, origin="Press Release")])["rung"], "SINGLE_SOURCE")

    def test_absence_needs_a_receipt(self):
        self.assertEqual(evidence.grade("the file does not exist", [fx.src(1), fx.src(2)])["rung"], "ABSENCE_UNPROBED")
        self.assertEqual(evidence.grade("the file does not exist", probe_receipt={"query": "ls /x", "result": "no such file"})["rung"], "ABSENCE_RECEIPT")


class Ledger(unittest.TestCase):
    def setUp(self):
        self.dag, _ = fx.new_dag()
        self.L = requirements.Ledger(self.dag, "author")
        self.L.register("r1", "tests pass")
        self.L.register("r2", "reviewed", "judged")

    def test_gate_needs_everything_verified(self):
        self.L.verify("r1", "ci", True)
        self.assertEqual(self.L.gate()["status"], "INCOMPLETE")
        self.L.verify("r2", "reviewer", True)
        self.assertEqual(self.L.gate()["status"], "COMPLETE")

    def test_author_cannot_verify_their_own_judged_item(self):
        with self.assertRaises(requirements.LedgerRefused):
            self.L.verify("r2", "author", True)

    def test_three_failures_become_a_stalemate_for_a_human(self):
        for _ in range(2):
            self.assertEqual(self.L.verify("r1", "ci", False), "FAILED")
            self.L.reopen("r1")
        self.assertEqual(self.L.verify("r1", "ci", False), "NEEDS_HUMAN")
        with self.assertRaises(requirements.LedgerRefused):
            self.L.reopen("r1")

    def test_list_is_fixed_once_judging_starts(self):
        self.L.verify("r1", "ci", True)
        with self.assertRaises(requirements.LedgerRefused):
            self.L.register("r3", "convenient new requirement")


class Recursive(unittest.TestCase):
    def test_agreement_across_families_verifies(self):
        r = recursive.recursive_verify("claim", [fx.v("a", "f1"), fx.v("b", "f2")])
        self.assertEqual(r["status"], "VERIFIED")

    def test_one_family_is_not_independent(self):
        self.assertEqual(recursive.recursive_verify("claim", [fx.v("a", "f1"), fx.v("b", "f1")])["status"], "UNVERIFIED")

    def test_a_split_is_a_stalemate_not_a_vote(self):
        r = recursive.recursive_verify("claim", [fx.v("a", "f1"), fx.v("b", "f2", False), fx.v("c", "f3")])
        self.assertEqual(r["status"], "STALEMATE")
        self.assertTrue(r["needs_human"])

    def test_later_levels_see_earlier_verdicts(self):
        seen = []

        def second(claim, prior):
            seen.append(prior)
            return {"verdict": True, "confidence": 0.8}
        recursive.recursive_verify("claim", [fx.v("a", "f1"), {"id": "b", "family": "f2", "fn": second}])
        self.assertEqual(seen[0][0]["id"], "a")

    def test_dual_pass(self):
        self.assertEqual(recursive.dual_pass("c", lambda c: [], lambda c: True)["status"], "SETTLED")
        self.assertEqual(recursive.dual_pass("c", lambda c: ["edge case"], lambda c: True)["status"], "CONTESTED")

    def test_confidence_is_capped_by_the_weakest_step(self):
        t = {"claim": "top", "confidence": 0.95, "children": [{"claim": "a", "confidence": 0.9, "children": []}, {"claim": "b", "confidence": 0.4, "children": [{"claim": "b1", "confidence": 0.7}]}]}
        w = recursive.weakest_link(t)
        self.assertEqual(w["confidence"], 0.4)
        self.assertEqual(w["path"], ["top", "b"])


if __name__ == "__main__":
    unittest.main()
