"""recursive.py - verification that checks its own checkers, a skeptic-and-advocate pass, and confidence that cannot exceed its weakest part.

  recursive_verify(claim, verifiers)   verifiers: list of {"id", "family", "fn"}; fn(claim, prior) -> {"verdict": True|False, "confidence": 0..1}. Level 0 judges the claim; each later level
      judges the claim AGAIN with the earlier verdicts in view. VERIFIED only if every level that answered says exactly True AND at least two different families answered. Any False with
      any True is a split: it goes to the next level; if the levels run out still split, the result is STALEMATE and the answer is NEEDS_HUMAN, never a majority vote. A verifier that crashes
      or answers in the wrong shape abstains and cannot help a claim pass.
  dual_pass(claim, skeptic, advocate)  skeptic(claim) -> list of objections; advocate(claim) -> True|False. SETTLED only when the skeptic raised nothing and the advocate said exactly True.
  weakest_link(tree)                   tree: {"claim", "confidence", "children": [...]}. A parent's confidence is the lowest of its own and its children's, so a conclusion is never more
                                       certain than the shakiest step under it. Returns the path to that step."""
import re

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")
MAX_LEVELS = 12
MAX_DEPTH = 40
MAX_NODES = 5000


class RecursiveRefused(ValueError):
    pass


def _conf(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not 0 <= x <= 1 or x != x:
        return None
    return float(x)


def recursive_verify(claim, verifiers):
    if not isinstance(claim, str) or not claim.strip():
        raise RecursiveRefused("a claim is non-empty text")
    if not isinstance(verifiers, (list, tuple)) or not 2 <= len(verifiers) <= MAX_LEVELS:
        raise RecursiveRefused("recursive verification needs 2..%d verifiers" % MAX_LEVELS)
    ids = set()
    for v in verifiers:
        if not isinstance(v, dict) or set(v) != {"id", "family", "fn"} or not callable(v["fn"]):
            raise RecursiveRefused("a verifier is {id, family, fn}")
        for k in ("id", "family"):
            if not isinstance(v[k], str) or not _ID.fullmatch(v[k]):
                raise RecursiveRefused("verifier %s must be a plain id" % k)
        if v["id"] in ids:
            raise RecursiveRefused("two verifiers share the id %s" % v["id"])
        ids.add(v["id"])
    prior, abstained, levels = [], [], []
    for v in verifiers:
        try:
            out = v["fn"](claim, [dict(p) for p in prior])
        except Exception as exc:
            abstained.append({"id": v["id"], "why": "crashed: %s" % type(exc).__name__})
            continue
        ok = isinstance(out, dict) and (out.get("verdict") is True or out.get("verdict") is False) and _conf(out.get("confidence")) is not None
        if not ok:
            abstained.append({"id": v["id"], "why": "answered in the wrong shape"})
            continue
        row = {"id": v["id"], "family": v["family"], "verdict": out["verdict"], "confidence": _conf(out["confidence"])}
        prior.append(row)
        levels.append(row)
    trues = [r for r in levels if r["verdict"]]
    falses = [r for r in levels if not r["verdict"]]
    families = {r["family"] for r in levels}
    if falses and trues:
        status, why = "STALEMATE", "the checkers split and no further level was left: NEEDS_HUMAN"
    elif falses:
        status, why = "REFUTED", "every answering level said False"
    elif len(families) >= 2 and trues:
        status, why = "VERIFIED", "every answering level said True across %d families" % len(families)
    elif trues:
        status, why = "UNVERIFIED", "all answering levels agree but they are one family: not independent"
    else:
        status, why = "UNVERIFIED", "no verifier answered"
    return {"status": status, "why": why, "levels": levels, "abstained": abstained, "needs_human": status in ("STALEMATE", "UNVERIFIED")}


def dual_pass(claim, skeptic, advocate):
    if not isinstance(claim, str) or not claim.strip() or not callable(skeptic) or not callable(advocate):
        raise RecursiveRefused("dual_pass takes a claim and two functions")
    try:
        objections = skeptic(claim)
    except Exception:
        return {"status": "UNSETTLED", "why": "the skeptic crashed", "objections": []}
    if not isinstance(objections, (list, tuple)) or any(not isinstance(o, str) for o in objections):
        return {"status": "UNSETTLED", "why": "the skeptic answered in the wrong shape", "objections": []}
    if [o for o in objections if o.strip()]:
        return {"status": "CONTESTED", "why": "the skeptic raised objections", "objections": [o for o in objections if o.strip()][:50]}
    try:
        support = advocate(claim)
    except Exception:
        return {"status": "UNSETTLED", "why": "the advocate crashed", "objections": []}
    if support is True:
        return {"status": "SETTLED", "why": "no objection and the advocate supports it", "objections": []}
    return {"status": "UNSETTLED", "why": "the advocate did not say exactly True", "objections": []}


def weakest_link(tree):
    count = [0]

    def walk(n, depth, path):
        if depth > MAX_DEPTH:
            raise RecursiveRefused("tree deeper than %d" % MAX_DEPTH)
        count[0] += 1
        if count[0] > MAX_NODES:
            raise RecursiveRefused("tree larger than %d nodes" % MAX_NODES)
        if not isinstance(n, dict) or set(n) - {"claim", "confidence", "children"} or not isinstance(n.get("claim"), str):
            raise RecursiveRefused("a node is {claim, confidence, children}")
        c = _conf(n.get("confidence"))
        if c is None:
            raise RecursiveRefused("confidence is a number in 0..1")
        kids = n.get("children", [])
        if not isinstance(kids, (list, tuple)):
            raise RecursiveRefused("children is a list")
        here = path + [n["claim"]]
        best = (c, here)
        for k in kids:
            kc, kp = walk(k, depth + 1, here)
            if kc < best[0]:
                best = (kc, kp)
        return best
    c, p = walk(tree, 0, [])
    return {"confidence": c, "path": p}
