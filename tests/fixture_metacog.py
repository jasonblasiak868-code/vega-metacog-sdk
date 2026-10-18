"""Shared helpers for the metacog tests (not a test file)."""
import pathlib
import tempfile

from vega_custody.dag.dag import Dag


def new_dag():
    t = pathlib.Path(tempfile.mkdtemp())
    return Dag([t / "c.jsonl"], [t / "l.jsonl"]), t


def src(i, origin=None, checkable=True, kind="document"):
    return {"id": "doc-%s" % i, "origin": origin or "origin-%s" % i, "checkable": checkable, "kind": kind}


def v(vid, family, verdict=True, conf=0.9):
    return {"id": vid, "family": family, "fn": lambda claim, prior, vv=verdict, cc=conf: {"verdict": vv, "confidence": cc}}
