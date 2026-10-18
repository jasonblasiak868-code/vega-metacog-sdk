"""requirements.py - the requirements ledger and the completion gate.

Before work starts the requirements are written down. Work is 'done' only when the gate says every required item is VERIFIED, and the gate is the only thing that can say so.
  Ledger(dag).register(id, text, kind)     kind: 'programmatic' (a check function decides), 'judged' (an independent verifier decides), 'human' (only a human sign-off decides)
  Ledger.verify(id, verifier_id, verdict)  verdict must be exactly True or False; the verifier must not be the author of the work (independence)
  Ledger.gate()                            COMPLETE only if nothing is PENDING, FAILED or NEEDS_HUMAN. Otherwise lists what is missing. A stalemate (the same item failed STALEMATE_AFTER times
                                           with no change) becomes NEEDS_HUMAN: the ledger will not guess its way out.
Every state change is appended to a custody chain (hashes and ids, never the work itself)."""
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
    def __init__(self, dag, author):
        if not isinstance(author, str) or not _ID.fullmatch(author):
            raise LedgerRefused("author is a plain id")
        self.dag, self.author = dag, author
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
        self.items[rid] = {"text": text, "kind": kind, "state": "PENDING", "fails": 0}
        self._rec("REQ_REGISTER", {"id": rid, "kind": kind, "text_sha256": hashlib.sha256(text.encode()).hexdigest()})

    def verify(self, rid, verifier_id, verdict, kind_used="programmatic"):
        it = self.items.get(rid)
        if it is None:
            raise LedgerRefused("unknown requirement")
        if not isinstance(verifier_id, str) or not _ID.fullmatch(verifier_id):
            raise LedgerRefused("verifier_id is a plain id")
        if verdict is not True and verdict is not False:
            raise LedgerRefused("a verdict is exactly True or False")
        if it["kind"] == "human" and kind_used != "human":
            raise LedgerRefused("a human requirement is settled only by a human sign-off")
        if verifier_id == self.author and it["kind"] != "programmatic":
            raise LedgerRefused("the author cannot verify their own judged or human requirement")
        self.frozen = True
        if it["state"] == "VERIFIED":
            raise LedgerRefused("already verified")
        if verdict:
            it["state"] = "VERIFIED"
        else:
            it["fails"] += 1
            it["state"] = "NEEDS_HUMAN" if it["fails"] >= STALEMATE_AFTER else "FAILED"
        self._rec("REQ_VERIFY", {"id": rid, "verifier": verifier_id, "verdict": verdict, "state": it["state"], "fails": it["fails"]})
        return it["state"]

    def reopen(self, rid):
        """A failed requirement goes back to PENDING after the work changed. A stalemated one (NEEDS_HUMAN) does not: only a human decision moves it."""
        it = self.items.get(rid)
        if it is None or it["state"] != "FAILED":
            raise LedgerRefused("only a FAILED requirement can be reopened")
        it["state"] = "PENDING"
        self._rec("REQ_REOPEN", {"id": rid})

    def gate(self):
        missing = {rid: it["state"] for rid, it in self.items.items() if it["state"] != "VERIFIED"}
        if not self.items:
            return {"status": "REFUSED", "why": "no requirements were registered, so nothing can be called complete", "missing": {}}
        status = "COMPLETE" if not missing else "INCOMPLETE"
        self._rec("REQ_GATE", {"status": status, "missing": sorted(missing)})
        return {"status": status, "missing": missing}
