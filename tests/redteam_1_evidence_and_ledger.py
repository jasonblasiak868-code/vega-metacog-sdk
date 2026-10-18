"""RED TEAM 1 - metacog SDK: inflate evidence, dodge the completion gate, verify your own work."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import fixture_metacog as fx  # noqa: E402
from vega_metacog import evidence, requirements  # noqa: E402


class A_Evidence(unittest.TestCase):
    def test_case_and_spacing_do_not_make_one_origin_two(self):
        r = evidence.grade("x", [fx.src(1, origin="The Daily"), fx.src(2, origin="  the daily "), fx.src(3, origin="THE DAILY")])
        self.assertEqual((r["rung"], r["independent_origins"]), ("SINGLE_SOURCE", 1))

    def test_unchecked_sources_never_make_a_fact(self):
        self.assertEqual(evidence.grade("x", [fx.src(1, checkable=False), fx.src(2, checkable=False)])["rung"], "UNVERIFIED")

    def test_one_checkable_plus_one_uncheckable_is_still_single(self):
        self.assertEqual(evidence.grade("x", [fx.src(1), fx.src(2, checkable=False)])["rung"], "SINGLE_SOURCE")

    def test_a_commit_must_look_like_a_commit_and_be_checkable(self):
        for bad in ({"id": "not a hash", "origin": "g", "checkable": True, "kind": "commit"}, {"id": "a1b2c3d", "origin": "g", "checkable": False, "kind": "commit"},
                    {"id": "A1B2C3D", "origin": "g", "checkable": True, "kind": "commit"}, {"id": "abc", "origin": "g", "checkable": True, "kind": "commit"}):
            self.assertNotEqual(evidence.grade("x", [bad])["rung"], "FACT", bad)

    def test_every_absence_phrasing_demands_a_receipt(self):
        for claim in ("it does not exist", "That was never filed", "there is no such file", "it is not found anywhere", "the feature doesn't exist", "none exist"):
            self.assertEqual(evidence.grade(claim, [fx.src(1), fx.src(2)])["rung"], "ABSENCE_UNPROBED", claim)

    def test_a_receipt_must_have_a_query_and_a_result(self):
        for bad in (None, {}, {"query": "ls"}, {"result": "none"}, {"query": " ", "result": "none"}, {"query": "ls", "result": ""}, {"query": 1, "result": 2}, "receipt", []):
            self.assertEqual(evidence.grade("it does not exist", probe_receipt=bad)["rung"], "ABSENCE_UNPROBED", repr(bad))

    def test_malformed_sources_are_refused(self):
        for bad in ([{"id": "a"}], [{"id": "", "origin": "o", "checkable": True}], [{"id": "a", "origin": "o", "checkable": "yes"}], [{"id": "a", "origin": "o", "checkable": True, "extra": 1}], ["x"], [None],
                    [{"id": 1, "origin": "o", "checkable": True}]):
            with self.assertRaises(evidence.EvidenceRefused, msg=repr(bad)):
                evidence.grade("x", bad)
        with self.assertRaises(evidence.EvidenceRefused):
            evidence.grade("", [])
        with self.assertRaises(evidence.EvidenceRefused):
            evidence.grade("x", [fx.src(i) for i in range(evidence.MAX_SOURCES + 1)])


class B_Ledger(unittest.TestCase):
    def setUp(self):
        self.dag, self.t = fx.new_dag()
        self.L = requirements.Ledger(self.dag, "author")

    def test_no_requirements_means_no_completion(self):
        self.assertEqual(self.L.gate()["status"], "REFUSED")

    def test_verdicts_must_be_exactly_booleans(self):
        self.L.register("r", "x")
        for bad in (1, 0, "True", "yes", None, [True]):
            with self.assertRaises(requirements.LedgerRefused, msg=repr(bad)):
                self.L.verify("r", "ci", bad)

    def test_a_human_requirement_cannot_be_settled_by_a_program(self):
        self.L.register("h", "owner approves", "human")
        with self.assertRaises(requirements.LedgerRefused):
            self.L.verify("h", "ci", True)
        with self.assertRaises(requirements.LedgerRefused):
            self.L.verify("h", "author", True, kind_used="human")                  # not even the author
        self.assertEqual(self.L.verify("h", "owner", True, kind_used="human"), "VERIFIED")

    def test_author_cannot_verify_own_human_or_judged_work_but_may_run_a_programmatic_check(self):
        self.L.register("p", "unit tests", "programmatic")
        self.assertEqual(self.L.verify("p", "author", True), "VERIFIED")

    def test_a_verified_item_cannot_be_flipped_or_verified_twice(self):
        self.L.register("r", "x")
        self.L.verify("r", "ci", True)
        with self.assertRaises(requirements.LedgerRefused):
            self.L.verify("r", "ci", False)

    def test_only_failed_items_reopen(self):
        self.L.register("r", "x")
        with self.assertRaises(requirements.LedgerRefused):
            self.L.reopen("r")
        with self.assertRaises(requirements.LedgerRefused):
            self.L.reopen("missing")

    def test_bad_registrations(self):
        self.L.register("ok", "text")
        for rid, text, kind in (("ok", "dup", "judged"), ("", "t", "judged"), ("a b", "t", "judged"), ("x", "", "judged"), ("x", "  ", "judged"), ("x", "t", "unknown"), ("x", 5, "judged"), (None, "t", "judged")):
            with self.assertRaises(requirements.LedgerRefused, msg=repr((rid, text, kind))):
                self.L.register(rid, text, kind)
        with self.assertRaises(requirements.LedgerRefused):
            requirements.Ledger(self.dag, "")

    def test_the_chain_records_hashes_not_requirement_text(self):
        self.L.register("r", "TOP SECRET REQUIREMENT TEXT")
        self.assertNotIn("TOP SECRET", open(self.t / "c.jsonl", encoding="utf-8").read())

    def test_unknown_requirement_and_bad_verifier_ids(self):
        self.L.register("r", "x")
        with self.assertRaises(requirements.LedgerRefused):
            self.L.verify("nope", "ci", True)
        for bad in ("", "a b", None, 5):
            with self.assertRaises(requirements.LedgerRefused):
                self.L.verify("r", bad, True)

    def test_gate_lists_exactly_what_is_missing(self):
        self.L.register("a", "x")
        self.L.register("b", "y")
        self.L.verify("a", "ci", True)
        self.assertEqual(self.L.gate()["missing"], {"b": "PENDING"})


if __name__ == "__main__":
    unittest.main()
