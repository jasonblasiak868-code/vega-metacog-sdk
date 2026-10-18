"""evidence.py - how much a claim has earned, as a rung, never rounded up.

Rungs, highest first:
  FACT              two or more sources of independent origin, or a checkable commit (a commit hash, a filed application number, a dated append-only custody entry)
  SINGLE_SOURCE     one checkable source
  UNVERIFIED        one source that cannot be checked
  RECALL_ONLY       the claim rests on memory with no probe made
  ABSENCE_UNPROBED  the claim says something does not exist or was never done, and no probe receipt is attached: refused as a claim
  ABSENCE_RECEIPT   an absence claim WITH a receipt (the probe that was run and what it returned)
Independence means separate origin: two pages repeating one press release, two files copied from one parent, or a document and its own summary are ONE source.
A source is {"id": text, "origin": text, "checkable": bool, "kind": "commit"|"document"|"probe"|...}. Nothing here fetches anything: it only grades what it is given."""
import re

RUNGS = ("FACT", "SINGLE_SOURCE", "UNVERIFIED", "RECALL_ONLY", "ABSENCE_UNPROBED", "ABSENCE_RECEIPT")
_ID = re.compile(r"[^\x00-\x1f]{1,300}")
_COMMIT = re.compile(r"[0-9a-f]{7,64}")
MAX_SOURCES = 200


class EvidenceRefused(ValueError):
    pass


def _source(s):
    if not isinstance(s, dict) or set(s) - {"id", "origin", "checkable", "kind"}:
        raise EvidenceRefused("a source is {id, origin, checkable, kind}")
    for k in ("id", "origin"):
        if not isinstance(s.get(k), str) or not _ID.fullmatch(s[k].strip() or "\x00"):
            raise EvidenceRefused("source %s must be non-empty text" % k)
    if s.get("checkable") is not True and s.get("checkable") is not False:
        raise EvidenceRefused("checkable is true or false")
    kind = s.get("kind", "document")
    if not isinstance(kind, str):
        raise EvidenceRefused("kind is text")
    return {"id": s["id"].strip(), "origin": s["origin"].strip().casefold(), "checkable": s["checkable"], "kind": kind}


def is_absence_claim(text):
    return bool(re.search(r"(?i)\b(does not exist|doesn't exist|is not there|was never|has never|never filed|never existed|no such|nowhere|not found|is absent|isn't there|none exist)\b", text))


def grade(claim, sources=None, probe_receipt=None):
    """claim: text. sources: list of source dicts. probe_receipt: {"query": text, "result": text} for an absence claim. Returns {"rung", "why", "independent_origins"}."""
    if not isinstance(claim, str) or not claim.strip():
        raise EvidenceRefused("a claim is non-empty text")
    srcs = [_source(s) for s in (sources or [])]
    if len(srcs) > MAX_SOURCES:
        raise EvidenceRefused("too many sources")
    if is_absence_claim(claim):
        if (isinstance(probe_receipt, dict) and isinstance(probe_receipt.get("query"), str) and probe_receipt["query"].strip() and isinstance(probe_receipt.get("result"), str)
                and probe_receipt["result"].strip()):
            return {"rung": "ABSENCE_RECEIPT", "why": "absence claim with a probe receipt; an empty result is evidence of nothing found, not of nothing existing", "independent_origins": 0}
        return {"rung": "ABSENCE_UNPROBED", "why": "an absence claim needs a receipt (the probe and its result)", "independent_origins": 0}
    if not srcs:
        return {"rung": "RECALL_ONLY", "why": "no source attached", "independent_origins": 0}
    commits = [s for s in srcs if s["kind"] == "commit" and s["checkable"] and _COMMIT.fullmatch(s["id"])]
    origins = {s["origin"] for s in srcs if s["checkable"]}
    if commits:
        return {"rung": "FACT", "why": "a checkable commit is sufficient on its own", "independent_origins": len(origins)}
    if len(origins) >= 2:
        return {"rung": "FACT", "why": "%d independent checkable origins" % len(origins), "independent_origins": len(origins)}
    if len(origins) == 1:
        return {"rung": "SINGLE_SOURCE", "why": "one checkable origin (repeats of it do not add)", "independent_origins": 1}
    return {"rung": "UNVERIFIED", "why": "sources exist but none can be checked", "independent_origins": 0}
