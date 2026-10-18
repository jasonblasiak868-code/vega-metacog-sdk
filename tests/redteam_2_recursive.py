"""RED TEAM 2 - metacog SDK: lying, crashing and copycat verifiers; a fake-agreeing skeptic; confidence trees built to overflow."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import fixture_metacog as fx  # noqa: E402
from vega_metacog import recursive  # noqa: E402


def fn(out):
    return lambda claim, prior: out


class A_Verifiers(unittest.TestCase):
    def test_wrong_shaped_answers_abstain_and_cannot_help_a_claim_pass(self):
        for bad in (None, True, "yes", {"verdict": "True", "confidence": 0.9}, {"verdict": 1, "confidence": 0.9}, {"verdict": True}, {"verdict": True, "confidence": 2},
                    {"verdict": True, "confidence": True}, {"verdict": True, "confidence": float("nan")}, [True], {}):
            r = recursive.recursive_verify("c", [fx.v("a", "f1"), {"id": "b", "family": "f2", "fn": fn(bad)}])
            self.assertNotEqual(r["status"], "VERIFIED", repr(bad))
            self.assertEqual(len(r["abstained"]), 1, repr(bad))

    def test_a_crashing_verifier_abstains(self):
        def boom(c, p):
            raise RuntimeError("down")
        r = recursive.recursive_verify("c", [fx.v("a", "f1"), {"id": "b", "family": "f2", "fn": boom}])
        self.assertNotEqual(r["status"], "VERIFIED")
        self.assertIn("crashed", r["abstained"][0]["why"])

    def test_all_verifiers_down_is_unverified_and_needs_a_human(self):
        def boom(c, p):
            raise RuntimeError("down")
        r = recursive.recursive_verify("c", [{"id": "a", "family": "f1", "fn": boom}, {"id": "b", "family": "f2", "fn": boom}])
        self.assertEqual((r["status"], r["needs_human"]), ("UNVERIFIED", True))

    def test_a_copycat_family_cannot_manufacture_independence(self):
        r = recursive.recursive_verify("c", [fx.v("a", "same"), fx.v("b", "same"), fx.v("c", "same")])
        self.assertEqual(r["status"], "UNVERIFIED")

    def test_two_of_three_is_not_a_majority_win(self):
        r = recursive.recursive_verify("c", [fx.v("a", "f1"), fx.v("b", "f2"), fx.v("c", "f3", False)])
        self.assertEqual(r["status"], "STALEMATE")

    def test_all_false_is_refuted(self):
        self.assertEqual(recursive.recursive_verify("c", [fx.v("a", "f1", False), fx.v("b", "f2", False)])["status"], "REFUTED")

    def test_a_verifier_cannot_alter_the_prior_record_seen_by_the_next(self):
        def tamper(claim, prior):
            for row in prior:
                row["verdict"] = True                                   # rewrite an earlier verifier's answer
            prior.clear()
            return {"verdict": True, "confidence": 0.9}
        seen = []

        def spy(claim, prior):
            seen.append([(r["id"], r["verdict"]) for r in prior])
            return {"verdict": True, "confidence": 0.9}
        recursive.recursive_verify("c", [fx.v("a", "f1", False), {"id": "b", "family": "f2", "fn": tamper}, {"id": "c", "family": "f3", "fn": spy}])
        self.assertEqual(seen, [[("a", False), ("b", True)]])

    def test_bad_arguments(self):
        good = [fx.v("a", "f1"), fx.v("b", "f2")]
        for claim, vs in (("", good), (None, good), ("c", good[:1]), ("c", []), ("c", None), ("c", [fx.v("a", "f1"), fx.v("a", "f2")]), ("c", [fx.v("a", "f1"), {"id": "b", "family": "f2"}]),
                          ("c", [fx.v("a", "f1"), {"id": "b b", "family": "f2", "fn": len}]), ("c", [fx.v("a", "f1"), {"id": "b", "family": "", "fn": len}]),
                          ("c", [fx.v("a", "f1"), {"id": "b", "family": "f2", "fn": "notcallable"}]), ("c", [fx.v("v%d" % i, "f%d" % i) for i in range(recursive.MAX_LEVELS + 1)])):
            with self.assertRaises(recursive.RecursiveRefused, msg=repr(claim)):
                recursive.recursive_verify(claim, vs)


class B_DualPass(unittest.TestCase):
    def test_an_empty_or_blank_objection_list_is_no_objection_but_the_advocate_must_say_exactly_true(self):
        self.assertEqual(recursive.dual_pass("c", lambda c: ["", "  "], lambda c: True)["status"], "SETTLED")
        for adv in ("yes", 1, None, [True]):
            self.assertEqual(recursive.dual_pass("c", lambda c: [], lambda c, a=adv: a)["status"], "UNSETTLED", repr(adv))

    def test_any_real_objection_blocks_whatever_the_advocate_says(self):
        self.assertEqual(recursive.dual_pass("c", lambda c: ["a flaw"], lambda c: True)["status"], "CONTESTED")

    def test_a_skeptic_that_crashes_or_misbehaves_does_not_settle_a_claim(self):
        def boom(c):
            raise RuntimeError("x")
        for sk in (boom, lambda c: None, lambda c: "no objections", lambda c: [1, 2], lambda c: {"a": 1}):
            self.assertEqual(recursive.dual_pass("c", sk, lambda c: True)["status"], "UNSETTLED")

    def test_an_advocate_crash_is_unsettled(self):
        def boom(c):
            raise RuntimeError("x")
        self.assertEqual(recursive.dual_pass("c", lambda c: [], boom)["status"], "UNSETTLED")

    def test_bad_arguments(self):
        for args in (("", len, len), ("c", None, len), ("c", len, None), (None, len, len)):
            with self.assertRaises(recursive.RecursiveRefused):
                recursive.dual_pass(*args)


class C_WeakestLink(unittest.TestCase):
    def test_a_confident_parent_cannot_outrank_a_shaky_grandchild(self):
        t = {"claim": "top", "confidence": 0.99, "children": [{"claim": "mid", "confidence": 0.95, "children": [{"claim": "leaf", "confidence": 0.2}]}]}
        w = recursive.weakest_link(t)
        self.assertEqual((w["confidence"], w["path"]), (0.2, ["top", "mid", "leaf"]))

    def test_bad_nodes_are_refused(self):
        for bad in (None, [], {"claim": 5, "confidence": 0.5}, {"claim": "x"}, {"claim": "x", "confidence": 2}, {"claim": "x", "confidence": True}, {"claim": "x", "confidence": 0.5, "extra": 1},
                    {"claim": "x", "confidence": 0.5, "children": "kids"}, {"claim": "x", "confidence": 0.5, "children": [None]}, {"claim": "x", "confidence": float("nan")}):
            with self.assertRaises(recursive.RecursiveRefused, msg=repr(bad)):
                recursive.weakest_link(bad)

    def test_deep_and_wide_trees_are_bounded(self):
        deep = {"claim": "n", "confidence": 0.5}
        for _ in range(recursive.MAX_DEPTH + 5):
            deep = {"claim": "n", "confidence": 0.5, "children": [deep]}
        with self.assertRaises(recursive.RecursiveRefused):
            recursive.weakest_link(deep)
        wide = {"claim": "r", "confidence": 0.5, "children": [{"claim": "c", "confidence": 0.5} for _ in range(recursive.MAX_NODES + 1)]}
        with self.assertRaises(recursive.RecursiveRefused):
            recursive.weakest_link(wide)


if __name__ == "__main__":
    unittest.main()
