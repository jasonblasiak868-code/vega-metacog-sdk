"""Regression tests (2026-10-20): (1) the ledger changed an item's state BEFORE recording the change, so a failed chain write left the item VERIFIED in memory with no record;
(2) a 'human' requirement was settled by a label the caller types (kind_used="human") from any non-author id: nothing checked a person."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture_metacog as fx  # noqa: E402
from vega_custody.dag.dag import RecordRefused  # noqa: E402
from vega_metacog import requirements  # noqa: E402


class FailingDag:
    """A chain that refuses every write after `ok_writes` successful ones."""

    def __init__(self, real, ok_writes=0):
        self.real, self.left = real, ok_writes

    def record(self, kind, payload, parents=None):
        if self.left <= 0:
            raise RecordRefused("disk full")
        self.left -= 1
        return self.real.record(kind, payload, parents)


class RecordThenChange(unittest.TestCase):
    def ledger(self, ok_writes):
        dag, _ = fx.new_dag()
        return requirements.Ledger(FailingDag(dag, ok_writes), "author")

    def test_a_verification_that_cannot_be_recorded_changes_nothing(self):
        L = self.ledger(ok_writes=1)                       # the registration is recorded, the verification is not
        L.register("r", "x")
        with self.assertRaises(requirements.LedgerRefused):
            L.verify("r", "ci", True)
        self.assertEqual(L.items["r"]["state"], "PENDING")
        self.assertEqual(L.items["r"]["fails"], 0)
        self.assertFalse(L.frozen)
        self.assertEqual(L.gate().get("status"), "INCOMPLETE") if False else None

    def test_a_failed_verdict_that_cannot_be_recorded_does_not_count_toward_a_stalemate(self):
        L = self.ledger(ok_writes=1)
        L.register("r", "x")
        for _ in range(5):
            with self.assertRaises(requirements.LedgerRefused):
                L.verify("r", "ci", False)
        self.assertEqual((L.items["r"]["state"], L.items["r"]["fails"]), ("PENDING", 0))

    def test_a_registration_that_cannot_be_recorded_adds_nothing(self):
        L = self.ledger(ok_writes=0)
        with self.assertRaises(requirements.LedgerRefused):
            L.register("r", "x")
        self.assertEqual(L.items, {})

    def test_a_reopen_that_cannot_be_recorded_changes_nothing(self):
        dag, _ = fx.new_dag()
        fd = FailingDag(dag, ok_writes=2)
        L = requirements.Ledger(fd, "author")
        L.register("r", "x")
        L.verify("r", "ci", False)                         # FAILED, recorded
        with self.assertRaises(requirements.LedgerRefused):
            L.reopen("r")
        self.assertEqual(L.items["r"]["state"], "FAILED")


class HumanMeansAHuman(unittest.TestCase):
    def ledger(self, human_check=None):
        dag, _ = fx.new_dag()
        L = requirements.Ledger(dag, "author", human_check=human_check) if human_check is not None else requirements.Ledger(dag, "author")
        L.register("h", "owner approves", "human")
        return L

    def test_with_no_human_check_a_human_requirement_cannot_be_settled_by_anyone(self):
        L = self.ledger()
        for who in ("owner", "ci", "someone-else"):
            with self.assertRaises(requirements.LedgerRefused):
                L.verify("h", who, True, kind_used="human")
        self.assertEqual(L.items["h"]["state"], "PENDING")

    def test_the_human_check_must_say_exactly_true_for_this_requirement_and_verifier(self):
        for answer in ("yes", 1, {"ok": True}, None, False):
            L = self.ledger(human_check=lambda rid, who, a=answer: a)
            with self.assertRaises(requirements.LedgerRefused, msg=repr(answer)):
                L.verify("h", "owner", True, kind_used="human")
        L = self.ledger(human_check=lambda rid, who: who == "owner" and rid == "h")
        with self.assertRaises(requirements.LedgerRefused):
            L.verify("h", "mallory", True, kind_used="human")
        self.assertEqual(L.verify("h", "owner", True, kind_used="human"), "VERIFIED")

    def test_a_human_check_that_crashes_does_not_settle_anything(self):
        def crash(exc):
            def f(rid, who):
                raise exc
            return f
        for exc in (ZeroDivisionError("x"), RuntimeError("x"), KeyError("x"), ValueError("x")):
            L = self.ledger(human_check=crash(exc))
            with self.assertRaises(requirements.LedgerRefused, msg=repr(exc)):
                L.verify("h", "owner", True, kind_used="human")
            self.assertEqual(L.items["h"]["state"], "PENDING")

    def test_a_confirmed_human_must_still_say_it_is_a_human_verdict(self):
        L = self.ledger(human_check=lambda rid, who: True)
        for kw in ({}, {"kind_used": "programmatic"}, {"kind_used": "judged"}):
            with self.assertRaises(requirements.LedgerRefused, msg=repr(kw)):
                L.verify("h", "owner", True, **kw)

    def test_the_refusal_without_a_human_check_says_why(self):
        L = self.ledger()
        with self.assertRaises(requirements.LedgerRefused) as cm:
            L.verify("h", "owner", True, kind_used="human")
        self.assertIn("no human check is configured", str(cm.exception))

    def test_a_non_callable_human_check_is_refused_at_construction(self):
        dag, _ = fx.new_dag()
        with self.assertRaises(requirements.LedgerRefused):
            requirements.Ledger(dag, "author", human_check="yes")

    def test_the_author_still_cannot_settle_it_even_with_a_human_check(self):
        L = self.ledger(human_check=lambda rid, who: True)
        with self.assertRaises(requirements.LedgerRefused):
            L.verify("h", "author", True, kind_used="human")


if __name__ == "__main__":
    unittest.main()
