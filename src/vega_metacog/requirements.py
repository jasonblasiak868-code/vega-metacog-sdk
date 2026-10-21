"""requirements.py - the requirements ledger and the completion gate.

Before work starts the requirements are written down. Work is 'done' only when the gate says every required item is VERIFIED, and the gate is the only thing that can say so.
  Ledger(dag, author, human_check=None).register(id, text, kind)
                                           kind: 'programmatic' (a check function decides), 'judged' (an independent verifier decides), 'human' (only a human sign-off decides)
  Ledger.verify(id, verifier_id, verdict)  verdict must be exactly True or False; the verifier must not be the author of the work (independence). A 'human' item is settled only
                                           when human_check(id, verifier_id) returns exactly True (for example a check of a signature from the human key). With no human_check
                                           configured, a human item cannot be settled by anyone: the ledger will not take a typed label for a person.
  Ledger.gate()                            COMPLETE only if nothing is PENDING, FAILED or NEEDS_HUMAN. Otherwise lists what is missing. A stalemate (the same item failed STALEMATE_AFTER times
                                           with no change) becomes NEEDS_HUMAN: the ledger will not guess its way out.
Every state change is appended to a custody chain (hashes and ids, never the work itself). RECORD FIRST: the chain write happens before the state changes, so a write that fails
leaves the item exactly as it was."""
import hashlib
import re

from vega_custody.dag.dag import RecordRefused

KINDS = ("programmatic", "judged", "human")
STALEMATE_AFTER = 3
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
MAX_ITEMS = 500


class LedgerRefused(ValueError):
    pass


class Ledger:
    def __init__(self, dag, author, human_check=None):
        if not isinstance(author, str) or not _ID.fullmatch(author):
            raise LedgerRefused("author is a plain id")
        if human_check is not None and not callable(human_check):
            raise LedgerRefused("human_check is a function (requirement id, verifier id) -> exactly True, or absent")
        self.dag, self.author, self._human_check = dag, author, human_check
        self.items = {}
        self.frozen = False

    def _rec(self, kind, payload):
        try:
            self.dag.record(kind, payload)
        except RecordRefused as exc:
            raise LedgerRefused("could not record: %s" % exc)

    def register(self, rid, text, kind="programmatic"):
        if self.frozen:
            raise LedgerRefused("requirements cannot be added after the first verification: the list is fixed before the work is judged")
        if not isinstance(rid, str) or not _ID.fullmatch(rid) or rid in self.items or len(self.items) >= MAX_ITEMS:
            raise LedgerRefused("requirement id must be a new plain id")
        if not isinstance(text, str) or not text.strip() or kind not in KINDS:
            raise LedgerRefused("a requirement has text and a kind in %s" % (KINDS,))
        self._rec("REQ_REGISTER", {"id": rid, "kind": kind, "text_sha256": hashlib.sha256(text.encode()).hexdigest()})
        self.items[rid] = {"text": text, "kind": kind, "state": "PENDING", "fails": 0}

    def verify(self, rid, verifier_id, verdict, kind_used="programmatic"):
        it = self.items.get(rid)
        if it is None:
            raise LedgerRefused("unknown requirement")
        if not isinstance(verifier_id, str) or not _ID.fullmatch(verifier_id):
            raise LedgerRefused("verifier_id is a plain id")
        if verdict is not True and verdict is not False:
            raise LedgerRefused("a verdict is exactly True or False")
        if it["kind"] == "human":
            if kind_used != "human":
                raise LedgerRefused("a human requirement is settled only by a human sign-off")
            if self._human_check is None:
                raise LedgerRefused("no human check is configured, so no one can settle a human requirement: give the Ledger a human_check")
            try:
                is_human = self._human_check(rid, verifier_id) is True
            except Exception:  # noqa: BLE001 - a human check that fails has not found a human
                is_human = False
            if not is_human:
                raise LedgerRefused("the human check did not confirm this verifier for this requirement")
        if verifier_id == self.author and it["kind"] != "programmatic":
            raise LedgerRefused("the author cannot verify their own judged or human requirement")
        if it["state"] == "VERIFIED":
            self.frozen = True
            raise LedgerRefused("already verified")
        if verdict:
            state, fails = "VERIFIED", it["fails"]
        else:
            fails = it["fails"] + 1
            state = "NEEDS_HUMAN" if fails >= STALEMATE_AFTER else "FAILED"
        self._rec("REQ_VERIFY", {"id": rid, "verifier": verifier_id, "verdict": verdict, "state": state, "fails": fails})
        it["state"], it["fails"] = state, fails                      # only after the record exists
        self.frozen = True
        return state

    def reopen(self, rid):
        """A failed requirement goes back to PENDING after the work changed. A stalemated one (NEEDS_HUMAN) does not: only a human decision moves it."""
        it = self.items.get(rid)
        if it is None or it["state"] != "FAILED":
            raise LedgerRefused("only a FAILED requirement can be reopened")
        self._rec("REQ_REOPEN", {"id": rid})
        it["state"] = "PENDING"

    def gate(self):
        missing = {rid: it["state"] for rid, it in self.items.items() if it["state"] != "VERIFIED"}
        if not self.items:
            return {"status": "REFUSED", "why": "no requirements were registered, so nothing can be called complete", "missing": {}}
        status = "COMPLETE" if not missing else "INCOMPLETE"
        self._rec("REQ_GATE", {"status": status, "missing": sorted(missing)})
        return {"status": status, "missing": missing}
