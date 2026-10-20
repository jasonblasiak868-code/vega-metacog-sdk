# vega-metacog-sdk

![vega-metacog-sdk](assets/tile.svg)

Metacognitive recursive verification: evidence rungs that are never rounded up, a requirements ledger with a completion gate, recursive and skeptic/advocate checking, and confidence capped by the weakest step. The kit owns the **verify** concern (layer 12): it grades how much a claim has earned, enforces that work is complete only when every requirement is verified by an independent party, and runs checkers that check each other — never letting confidence exceed the shakiest link.

> **Licensing.** Source-available, not open source. Free for personal use; free for registered small businesses (under US$1M revenue and valuation); everyone else needs a commercial license (see LICENSE; for a commercial license write to jasonblasiak.ai.mail@gmail.com). Patent pending (U.S. provisional application 64/178,949 and others). Draft licence text, not yet reviewed by an attorney.

## Specifications

| Item | Detail |
|------|--------|
| Version | 0.1.0 |
| Python | >=3.10 |
| Package | `vega_metacog` (src layout) |
| Dependencies | vega-custody-sdk |
| Tests | 46 tests in 3 files, all passing |
| Status | BUILT: evidence, requirements, recursive |

## End-to-end functions

1. **Grade evidence** — `evidence.grade(claim, sources, probe_receipt)` returns a rung (FACT, SINGLE_SOURCE, UNVERIFIED, RECALL_ONLY, ABSENCE_UNPROBED, ABSENCE_RECEIPT) with reasoning and independent-origin count.
2. **Run the requirements ledger** — `requirements.Ledger(dag, author).register(id, text, kind)` fixes the requirement list; `verify(id, verifier_id, verdict)` records judgments; `gate()` returns COMPLETE only when every item is VERIFIED.
3. **Recursive verification** — `recursive.recursive_verify(claim, verifiers)` runs checkers across families; each level sees prior verdicts; VERIFIED requires all answering levels True across ≥2 families; a split becomes STALEMATE → NEEDS_HUMAN.
4. **Skeptic/advocate pass** — `recursive.dual_pass(claim, skeptic, advocate)` returns SETTLED only when skeptic raises no objections AND advocate returns exactly True.
5. **Weakest-link confidence** — `recursive.weakest_link(tree)` computes confidence as the minimum along any path; returns the path to the weakest step.

## Controls

| Control | Location | What it does |
|---------|----------|--------------|
| `evidence.grade()` | `vega_metacog.evidence` | Grades a claim into a rung; refuses malformed sources, empty claims, excess sources (>200). |
| `evidence.is_absence_claim()` | `vega_metacog.evidence` | Detects absence phrasing; forces ABSENCE_UNPROBED unless a probe receipt is provided. |
| `requirements.Ledger.register()` | `vega_metacog.requirements` | Registers a requirement (programmatic/judged/human); freezes the list on first verify. |
| `requirements.Ledger.verify()` | `vega_metacog.requirements` | Records a verdict (exactly True/False); enforces author independence for judged/human kinds; 3 failures → NEEDS_HUMAN. |
| `requirements.Ledger.reopen()` | `vega_metacog.requirements` | Reopens only FAILED items; NEEDS_HUMAN items require human decision. |
| `requirements.Ledger.gate()` | `vega_metacog.requirements` | Returns COMPLETE only if zero PENDING/FAILED/NEEDS_HUMAN; otherwise INCOMPLETE with missing list. |
| `recursive.recursive_verify()` | `vega_metacog.recursive` | Runs 2–12 verifiers across families; each fn(claim, prior) returns {verdict, confidence}; crashes/wrong shapes abstain. |
| `recursive.dual_pass()` | `vega_metacog.recursive` | Skeptic returns objection list; advocate returns exactly True; any real objection blocks. |
| `recursive.weakest_link()` | `vega_metacog.recursive` | Walks a confidence tree (max depth 40, max nodes 5000); returns min confidence and path. |

## What it CANNOT do

- It grades the evidence it is given; it does not search, fetch, or generate sources.
- Independence is declared by the caller (families, origins); the repo cannot prove two verifiers are truly independent.
- It does not persist the ledger or evidence rungs itself; it records hashes to a custody DAG provided by the caller.
- Not production-hardened; reference implementation only.
- Not independently security-reviewed.
- Cryptography has not had expert review.
- The completion gate does not execute actions; it only reports whether requirements are met. Wiring the gate into every build step is the caller's job.
- No native mobile build is published. The SDK is pure Python and can run inside a Python runtime on Android (Termux) or Apple platforms (BeeWare/Kivy) where that runtime supports its dependencies.

## Platform support

| Platform | Support |
|----------|---------|
| Windows, macOS, Linux (CPython 3.10+) | Runs anywhere CPython 3.10+ runs |
| Mobile (Android/iOS) | No native build; runs inside Termux (Android) or BeeWare/Kivy (Apple) where dependencies are available |
| GPU/TPM/hardware keys | Not required; pure Python |

## Standalone & unified install

**Standalone:** `pip install -e .` installs with one declared dependency: `vega-custody-sdk`. It imports nothing else from the family. Installs and runs alone with zero family dependencies beyond custody.

**Unified:** Registered in `vega-umbrella-sdk` registry as layer 12 (verify), depends on `custody`. Registry entry verbatim:

```
vega-metacog-sdk | 12 verify | custody
```

The umbrella resolves inter-SDK wiring; this SDK does not import any family SDK above custody.

## Diagnostic control

- **No console scripts** — no CLI entry points published.
- **Introspection:** `evidence.grade()` returns `{"rung", "why", "independent_origins"}`; `Ledger.gate()` returns `{"status", "missing"}`; `recursive_verify()` returns `{"status", "why", "levels", "abstained", "needs_human"}`; `dual_pass()` returns `{"status", "why", "objections"}`; `weakest_link()` returns `{"confidence", "path"}`.
- **Fail-closed indicators:** Every function raises a typed `*Refused` exception (EvidenceRefused, LedgerRefused, RecursiveRefused) on invalid input; `gate()` returns REFUSED when no requirements registered; `recursive_verify()` returns NEEDS_HUMAN on split or single-family; `dual_pass()` returns UNSETTLED on skeptic/advocate crash or wrong shape.
- **Environment variables:** None honored.
- **Exit codes:** Not applicable (library-only).

## Fail-closed constraints & custom constraints

**Fail-closed points (see ARCHITECTURE.md for diagram):**
1. `evidence.grade()` — refuses empty claim, malformed source, >200 sources, absence claim without receipt (raises `EvidenceRefused`).
2. `Ledger.register()` — refuses after first verify (frozen), duplicate id, bad id/text/kind (raises `LedgerRefused`).
3. `Ledger.verify()` — refuses non-boolean verdict, author verifying own judged/human item, unknown requirement, bad verifier id, flipping VERIFIED (raises `LedgerRefused`).
4. `Ledger.gate()` — returns REFUSED if zero requirements; INCOMPLETE if any not VERIFIED; never guesses.
5. `recursive.recursive_verify()` — refuses <2 or >12 verifiers, duplicate ids, bad verifier shape; crashing/wrong-shaped verifiers abstain; split → STALEMATE → NEEDS_HUMAN; single family → UNVERIFIED.
6. `recursive.dual_pass()` — refuses non-callable skeptic/advocate; skeptic crash/wrong shape → UNSETTLED; any real objection → CONTESTED; advocate not exactly True → UNSETTLED.
7. `recursive.weakest_link()` — refuses bad node shape, confidence outside [0,1], depth >40, nodes >5000 (raises `RecursiveRefused`).

**Custom constraints:** This version publishes no user-defined constraint hooks; constraints are fixed by the module and the jurisdiction floor (vega-jurisdiction-sdk). The governing rule: *User-defined constraints may be STRICTER than the legal minimum for the applicable jurisdiction, never looser. Jurisdictional legal minimums are defined by the jurisdiction registry; a custom constraint that would drop below a registered minimum is rejected at the gate.*

## Tests

46 tests in 3 files (`tests/test_metacog.py`, `tests/redteam_1_evidence_and_ledger.py`, `tests/redteam_2_recursive.py`), all passing.

Run:
```bash
PYTHONPATH="src:../vega-custody-sdk/src" python -m pytest tests/ -v
```

## Status & honesty

Reference implementation, work in progress, not independently security-reviewed, crypto not expert-reviewed. This kit details one branch of a broader filed architecture. The remaining branches are the subject of filed disclosures and are outside the scope of this repository.
