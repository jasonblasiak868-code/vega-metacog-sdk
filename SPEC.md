# vega-metacog-sdk — Specification

Spec v1.0 — 2026-10-19 — describes the published reference implementation as tested; where this document and the source disagree, the source wins.

## 1. Purpose and scope

This specification covers the three modules in `src/vega_metacog/`: `evidence.py`, `requirements.py`, and `recursive.py`. It defines the evidence-rung grading system, the requirements ledger with completion gate, and the recursive/dual-pass/weakest-link verification primitives.

Out of scope: persistence (the SDK records hashes to a caller-supplied custody DAG), source fetching, policy enforcement beyond the coded invariants, and any orchestration that wires the gate into build steps.

## 2. Vocabulary

| Term | Definition |
|------|------------|
| **Rung** | A grade of evidence, highest to lowest: FACT, SINGLE_SOURCE, UNVERIFIED, RECALL_ONLY, ABSENCE_UNPROBED, ABSENCE_RECEIPT. |
| **Independent origin** | A source whose `origin` field (casefolded, stripped) differs from all others; repeated origins count as one. |
| **Checkable source** | A source with `checkable: true`; only checkable origins count toward FACT or SINGLE_SOURCE. |
| **Commit source** | A source with `kind: "commit"`, `checkable: true`, and an `id` matching a git-style hash (7–64 hex chars). Sufficient for FACT on its own. |
| **Absence claim** | A claim matching phrases like "does not exist", "was never filed", "no such file", etc. Requires a probe receipt to avoid ABSENCE_UNPROBED. |
| **Probe receipt** | A dict `{"query": text, "result": text}` documenting a search that returned nothing; both fields must be non-empty strings. |
| **Requirement kind** | `programmatic` (a check function decides), `judged` (an independent verifier decides), `human` (only a human sign-off decides). |
| **Stalemate** | Three failed verifications on a requirement without change; state becomes NEEDS_HUMAN and cannot be reopened by code. |
| **Family** | A verifier group identifier; independence in `recursive_verify` requires ≥2 distinct families. |
| **Split** | At least one verifier returns True and at least one returns False; result is STALEMATE → NEEDS_HUMAN. |
| **Weakest-link confidence** | A parent node's confidence is the minimum of its own confidence and all descendants'; the conclusion is never more certain than the shakiest step. |

## 3. Components

### 3.1 evidence.py

**Role:** Grades a claim into an evidence rung based on supplied sources; never fetches or generates evidence.

**Public interface:**
- `RUNGS` — tuple of rung names in order.
- `MAX_SOURCES` — constant (200).
- `EvidenceRefused` — exception raised on invalid input.
- `is_absence_claim(text: str) -> bool` — detects absence phrasing.
- `grade(claim: str, sources: list[dict] = None, probe_receipt: dict = None) -> dict` — returns `{"rung", "why", "independent_origins"}`.

**Behavior:**
- On success: returns a rung with reasoning. FACT if ≥2 independent checkable origins OR a checkable commit. SINGLE_SOURCE if exactly 1 checkable origin. UNVERIFIED if sources exist but none checkable. RECALL_ONLY if no sources. ABSENCE_RECEIPT if absence claim with valid probe receipt. ABSENCE_UNPROBED if absence claim without receipt.
- On failure: raises `EvidenceRefused` for empty claim, malformed source dict (must have exactly `id`, `origin`, `checkable`, `kind`), non-boolean `checkable`, >200 sources, invalid probe receipt shape.

**Invariants:**
- Independence = distinct casefolded `origin` values; repeated origins never add.
- Only checkable sources count toward FACT/SINGLE_SOURCE.
- A commit source is FACT only if `checkable: true` and `id` matches hex hash pattern.
- Absence claims without probe receipt are refused as claims (ABSENCE_UNPROBED rung, not an exception).
- Nothing fetches; the function only grades what it is given.

### 3.2 requirements.py

**Role:** A requirements ledger that fixes the requirement list before judging, enforces independent verification, and provides a completion gate that never guesses.

**Public interface:**
- `KINDS` — tuple `("programmatic", "judged", "human")`.
- `STALEMATE_AFTER` — constant (3).
- `MAX_ITEMS` — constant (500).
- `LedgerRefused` — exception raised on invalid input.
- `Ledger(dag, author)` — constructor; `dag` must have a `record(kind, payload)` method; `author` is a plain id.
- `Ledger.register(rid: str, text: str, kind: str = "programmatic")` — adds a requirement; freezes list on first `verify`.
- `Ledger.verify(rid: str, verifier_id: str, verdict: bool, kind_used: str = "programmatic") -> str` — records verdict; returns new state.
- `Ledger.reopen(rid: str)` — reopens only FAILED items.
- `Ledger.gate() -> dict` — returns `{"status": "COMPLETE"|"INCOMPLETE"|"REFUSED", "missing": {...}}`.

**Behavior:**
- On success: `register` records `REQ_REGISTER` to DAG with text hash. `verify` records `REQ_VERIFY`; on True → VERIFIED; on False → FAILED (or NEEDS_HUMAN after 3 failures). `gate` returns COMPLETE only if zero non-VERIFIED items; REFUSED if zero items registered.
- On failure: raises `LedgerRefused` for frozen list, duplicate/bad id, empty text, bad kind, non-boolean verdict, author verifying own judged/human item, unknown requirement, bad verifier id, flipping VERIFIED, reopening non-FAILED item.

**Invariants:**
- Requirements are fixed once judging starts (`frozen` flag set on first `verify`).
- Author cannot verify own judged/human requirements (independence).
- Human requirements settle only when `kind_used="human"`, the verifier is not the author, AND the Ledger's `human_check(requirement id, verifier id)` returns exactly True. With no `human_check` configured no human requirement can be settled (fail closed). Every state change is recorded BEFORE it takes effect, so a failed chain write leaves the item as it was.
- Three failures without change → NEEDS_HUMAN (stalemate); NEEDS_HUMAN cannot be reopened by code.
- Every state change appends to the custody DAG (hashes only, never requirement text).
- `gate()` never guesses; missing items listed explicitly.

### 3.3 recursive.py

**Role:** Recursive verification across independent families, a skeptic/advocate dual pass, and a weakest-link confidence tree.

**Public interface:**
- `MAX_LEVELS` — constant (12).
- `MAX_DEPTH` — constant (40).
- `MAX_NODES` — constant (5000).
- `RecursiveRefused` — exception raised on invalid input.
- `recursive_verify(claim: str, verifiers: list[dict]) -> dict` — verifiers = `[{"id", "family", "fn"}]`; `fn(claim, prior) -> {"verdict": bool, "confidence": float}`.
- `dual_pass(claim: str, skeptic: callable, advocate: callable) -> dict` — `skeptic(claim) -> list[str]`; `advocate(claim) -> bool`.
- `weakest_link(tree: dict) -> dict` — tree = `{"claim", "confidence", "children": [...]}`; returns `{"confidence": float, "path": list[str]}`.

**Behavior:**
- `recursive_verify`: Runs each verifier sequentially; each `fn` receives the claim and a **copy** of prior verdicts. Crashing or wrong-shaped answers abstain (cannot help a claim pass). VERIFIED only if all answering levels returned True AND ≥2 distinct families answered. Split (True + False) → STALEMATE → NEEDS_HUMAN. All False → REFUTED. Single family with all True → UNVERIFIED (not independent). No verifiers answered → UNVERIFIED → NEEDS_HUMAN.
- `dual_pass`: Runs skeptic; if it crashes/wrong shape → UNSETTLED. If any non-blank objection → CONTESTED. If skeptic clean, runs advocate; if advocate returns exactly True → SETTLED; else → UNSETTLED. Advocate crash → UNSETTLED.
- `weakest_link`: Recursively walks tree; parent confidence = min(self, children). Returns minimum confidence and path to that node. Bounds: depth ≤40, nodes ≤5000.

**Invariants:**
- Verifier ids must be unique; families declared by caller.
- Prior verdicts passed to each `fn` are copies (verifier cannot mutate history).
- Verdict must be exactly `True` or `False`; confidence must be a finite float in [0,1].
- A split is never resolved by majority; it escalates to human.
- Independence requires ≥2 families, not ≥2 verifiers.
- Confidence never exceeds the weakest descendant.

## 4. Guarantees and non-guarantees

| Guarantee | Module | Test demonstrating |
|-----------|--------|---------------------|
| FACT rung requires ≥2 independent checkable origins or a checkable commit | evidence | `test_rungs`, `test_repeats_of_one_origin_are_one_source` |
| Absence claim without probe receipt → ABSENCE_UNPROBED | evidence | `test_absence_needs_a_receipt`, `test_every_absence_phrasing_demands_a_receipt` |
| Requirements list frozen after first verify | requirements | `test_list_is_fixed_once_judging_starts` |
| Author cannot verify own judged/human work | requirements | `test_author_cannot_verify_their_own_judged_item`, `test_author_cannot_verify_own_human_or_judged_work_but_may_run_a_programmatic_check` |
| Three failures → NEEDS_HUMAN (stalemate); NEEDS_HUMAN cannot reopen | requirements | `test_three_failures_become_a_stalemate_for_a_human` |
| Gate returns COMPLETE only when all VERIFIED; REFUSED if zero items | requirements | `test_gate_needs_everything_verified`, `test_no_requirements_means_no_completion` |
| Recursive VERIFIED requires ≥2 families all True | recursive | `test_agreement_across_families_verifies`, `test_one_family_is_not_independent` |
| Split → STALEMATE → NEEDS_HUMAN (no majority vote) | recursive | `test_a_split_is_a_stalemate_not_a_vote`, `test_two_of_three_is_not_a_majority_win` |
| Crashing/wrong-shaped verifiers abstain, cannot help pass | recursive | `test_wrong_shaped_answers_abstain_and_cannot_help_a_claim_pass`, `test_a_crashing_verifier_abstains` |
| Dual-pass SETTLED only if skeptic clean AND advocate exactly True | recursive | `test_an_empty_or_blank_objection_list_is_no_objection_but_the_advocate_must_say_exactly_true`, `test_any_real_objection_blocks_whatever_the_advocate_says` |
| Weakest-link confidence = minimum along any path | recursive | `test_confidence_is_capped_by_the_weakest_step`, `test_a_confident_parent_cannot_outrank_a_shaky_grandchild` |
| All state changes recorded to custody DAG (hashes only) | requirements | `test_the_chain_records_hashes_not_requirement_text` |

| Non-guarantee | Explanation |
|---------------|-------------|
| The SDK proves two verifiers are truly independent | Independence is declared by caller via `family` field; code cannot verify real-world independence. |
| The SDK fetches or generates evidence | `evidence.grade` only grades supplied sources. |
| The gate executes actions | `gate()` only reports status; wiring it into build steps is the caller's job. |
| Confidence values are calibrated probabilities | Confidence is a 0–1 number supplied by verifiers; no calibration is performed. |
| The SDK persists anything | It records to a caller-supplied DAG; no internal persistence. |
| Mobile/native builds | Pure Python only; no native packaging. |

## 5. Failure modes

| Failure mode | Behavior | Test file |
|--------------|----------|-----------|
| Tampered source list (duplicate origins disguised by case/spacing) | Normalized to casefolded stripped origin; counted as one | `redteam_1_evidence_and_ledger.py::A_Evidence::test_case_and_spacing_do_not_make_one_origin_two` |
| Uncheckable sources presented as checkable | Rejected at source validation; `checkable` must be boolean True | `redteam_1_evidence_and_ledger.py::A_Evidence::test_unchecked_sources_never_make_a_fact` |
| Commit source that isn't a valid hash or not checkable | Not counted as FACT; falls through to origin counting | `redteam_1_evidence_and_ledger.py::A_Evidence::test_a_commit_must_look_like_a_commit_and_be_checkable` |
| Absence claim without probe receipt | Returns ABSENCE_UNPROBED rung (not an exception) | `redteam_1_evidence_and_ledger.py::A_Evidence::test_every_absence_phrasing_demands_a_receipt` |
| Malformed probe receipt (missing query/result, empty, wrong types) | Returns ABSENCE_UNPROBED | `redteam_1_evidence_and_ledger.py::A_Evidence::test_a_receipt_must_have_a_query_and_a_result` |
| Attempt to register requirements after judging started | `LedgerRefused` raised | `redteam_1_evidence_and_ledger.py::B_Ledger::test_bad_registrations` (via frozen check) |
| Non-boolean verdict (1, "yes", None) | `LedgerRefused` raised | `redteam_1_evidence_and_ledger.py::B_Ledger::test_verdicts_must_be_exactly_booleans` |
| Author tries to verify own judged/human item | `LedgerRefused` raised | `redteam_1_evidence_and_ledger.py::B_Ledger::test_author_cannot_verify_own_human_or_judged_work_but_may_run_a_programmatic_check` |
| Flipping a VERIFIED item | `LedgerRefused` raised | `redteam_1_evidence_and_ledger.py::B_Ledger::test_a_verified_item_cannot_be_flipped_or_verified_twice` |
| Reopening non-FAILED item | `LedgerRefused` raised | `redteam_1_evidence_and_ledger.py::B_Ledger::test_only_failed_items_reopen` |
| Verifier returns wrong shape (missing verdict, bad confidence) | Verifier abstains; cannot help claim pass | `redteam_2_recursive.py::A_Verifiers::test_wrong_shaped_answers_abstain_and_cannot_help_a_claim_pass` |
| Verifier crashes | Verifier abstains; logged in `abstained` list | `redteam_2_recursive.py::A_Verifiers::test_a_crashing_verifier_abstains` |
| All verifiers crash/down | UNVERIFIED + NEEDS_HUMAN | `redteam_2_recursive.py::A_Verifiers::test_all_verifiers_down_is_unverified_and_needs_a_human` |
| Copycat family (same family id) | Counts as one family; UNVERIFIED if only family | `redteam_2_recursive.py::A_Verifiers::test_a_copycat_family_cannot_manufacture_independence` |
| Verifier tries to mutate prior verdicts seen by next level | Prior is a copy; mutation has no effect on later verifiers | `redteam_2_recursive.py::A_Verifiers::test_a_verifier_cannot_alter_the_prior_record_seen_by_the_next` |
| Skeptic returns non-list or non-string objections | UNSETTLED | `redteam_2_recursive.py::B_DualPass::test_a_skeptic_that_crashes_or_misbehaves_does_not_settle_a_claim` |
| Advocate returns non-True (1, "yes", None) | UNSETTLED | `redteam_2_recursive.py::B_DualPass::test_an_empty_or_blank_objection_list_is_no_objection_but_the_advocate_must_say_exactly_true` |
| Confidence tree exceeds depth/nodes | `RecursiveRefused` raised | `redteam_2_recursive.py::C_WeakestLink::test_deep_and_wide_trees_are_bounded` |

## 6. Dependencies and layer rules

Registry entry (verbatim from `vega-umbrella-sdk`):
```
vega-metacog-sdk | 12 verify | custody
```

Dependencies point down layers only, never up or sideways. This SDK imports only `vega_custody.dag.dag` (layer 0). It does not import any family SDK above layer 0.

## 7. Conformance

A third party can verify conformance by running the test suite:

```bash
PYTHONPATH="src:../vega-custody-sdk/src" python -m pytest tests/ -v
```

**What passing means:** All 57 tests in 4 files pass; the reference implementation behaves as specified.

**What passing does NOT mean:** Production readiness; independent security review; cryptographic expert review; that the SDK fetches evidence or executes actions; that verifier independence is proven in the real world; that the completion gate is wired into any build step.
