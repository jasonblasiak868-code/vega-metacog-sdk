# vega-metacog-sdk — Capabilities

## Capability inventory

Each capability below is a concrete behavior the published code provides. For each: the capability, why a policy-or-prompt-level approach structurally cannot provide it, where it is enforced in this repo's code, which test demonstrates it, and the honest limit.

---

### 1. Evidence rungs that are never rounded up

**Capability:** `evidence.grade()` returns one of six rungs (FACT, SINGLE_SOURCE, UNVERIFIED, RECALL_ONLY, ABSENCE_UNPROBED, ABSENCE_RECEIPT). A claim never receives a higher rung than its evidence earns; two sources with the same origin count as one; uncheckable sources never contribute to FACT or SINGLE_SOURCE; absence claims without a probe receipt are capped at ABSENCE_UNPROBED.

**Why policy/prompt cannot provide it:** A prompt can ask a model to "be careful" or "cite sources," but the model grades its own evidence. There is no independent check that two citations actually come from independent origins, that a commit hash is valid and checkable, or that an absence claim was actually probed. The model can hallucinate citations, conflate repeated sources, or claim absence without searching.

**Where enforced:** `evidence.py:42–63` — `grade()` normalizes origins (casefold, strip), counts only checkable origins, validates commit format, and forces ABSENCE_UNPROBED for unprobed absence claims.

**Test:** `tests/test_metacog.py::Evidence::test_rungs`, `tests/test_metacog.py::Evidence::test_repeats_of_one_origin_are_one_source`, `tests/test_metacog.py::Evidence::test_absence_needs_a_receipt`, `tests/redteam_1_evidence_and_ledger.py::A_Evidence` (all 7 tests).

**Honest limit:** Independence is declared by the caller via the `origin` field; the code cannot verify two origins are truly independent in the real world. A commit is only FACT if it matches a hex pattern and is marked checkable; the code does not verify the commit exists in a real git repo.

---

### 2. Requirements ledger with a completion gate that never guesses

**Capability:** `requirements.Ledger` fixes the requirement list before any verification (`register` freezes on first `verify`), enforces independent verification (author cannot verify own judged/human items), escalates three failures to NEEDS_HUMAN (stalemate, not a vote), and `gate()` returns COMPLETE only when every item is VERIFIED — REFUSED if zero items, INCOMPLETE otherwise, with an explicit missing list.

**Why policy/prompt cannot provide it:** A prompt can say "don't ship until tests pass," but the model can mark its own work done, add new requirements after seeing failures, or declare completion while items are still pending. There is no structural barrier to the model moving the goalposts or self-approving.

**Where enforced:** `requirements.py:24–84` — `frozen` flag set on first `verify` (line 60); author independence check (line 58); `STALEMATE_AFTER = 3` with NEEDS_HUMAN state (line 67); `gate()` logic (lines 79–84) with explicit missing dict.

**Test:** `tests/test_metacog.py::Ledger::test_gate_needs_everything_verified`, `::test_author_cannot_verify_their_own_judged_item`, `::test_three_failures_become_a_stalemate_for_a_human`, `::test_list_is_fixed_once_judging_starts`; `tests/redteam_1_evidence_and_ledger.py::B_Ledger` (all 10 tests).

**Honest limit:** The ledger records to a caller-supplied custody DAG; the SDK does not persist anything itself. Wiring the gate into every build/deploy step is the caller's responsibility — the gate only reports status.

---

### 3. Recursive verification across independent families (no majority vote)

**Capability:** `recursive.recursive_verify()` runs 2–12 verifiers across declared families. Each level sees prior verdicts (as copies). VERIFIED requires **all** answering levels True across **≥2 distinct families**. A split (any True + any False) becomes STALEMATE → NEEDS_HUMAN — never a majority vote. Crashing or wrong-shaped verifiers abstain and cannot help a claim pass.

**Why policy/prompt cannot provide it:** A prompt can ask "have multiple models check this," but the models can collude, share context, or be the same model with different prompts. A voting scheme lets a majority override a minority; a split is resolved by counting. The model doing the checking is the same architecture doing the work — no structural independence.

**Where enforced:** `recursive.py:28–70` — family set collected (line 59); VERIFIED condition requires `len(families) >= 2 and trues` (line 64); split detected by `falses and trues` (line 60) → STALEMATE; abstention on exception/wrong shape (lines 47–53); prior passed as copy (line 46).

**Test:** `tests/test_metacog.py::Recursive::test_agreement_across_families_verifies`, `::test_one_family_is_not_independent`, `::test_a_split_is_a_stalemate_not_a_vote`, `::test_later_levels_see_earlier_verdicts`; `tests/redteam_2_recursive.py::A_Verifiers` (all 8 tests).

**Honest limit:** Family independence is declared by the caller; the code cannot prove verifiers run on separate infrastructure, have different weights, or are otherwise uncorrelated. A verifier that crashes is silently dropped — the caller must check `abstained` in the result.

---

### 4. Skeptic/advocate dual pass (objection blocks, advocate must say exactly True)

**Capability:** `recursive.dual_pass(claim, skeptic, advocate)` runs a skeptic function that returns a list of objections, then an advocate that must return exactly `True`. SETTLED only if skeptic returns no non-blank objections **and** advocate returns exactly `True`. Any real objection → CONTESTED (blocks regardless of advocate). Skeptic crash/wrong shape → UNSETTLED. Advocate crash or non-True → UNSETTLED.

**Why policy/prompt cannot provide it:** A prompt can ask "critique this then defend it," but the same model plays both roles. There is no structural separation; the model can choose to raise no objections and then say "yes." A voting or threshold approach would let a strong advocate override weak objections.

**Where enforced:** `recursive.py:73–90` — skeptic called first (line 77); non-list or non-string objections → UNSETTLED (line 80); any non-blank objection → CONTESTED (line 82); advocate called only if skeptic clean (line 84); `support is True` required (line 88).

**Test:** `tests/test_metacog.py::Recursive::test_dual_pass`; `tests/redteam_2_recursive.py::B_DualPass` (all 5 tests).

**Honest limit:** The skeptic and advocate are caller-supplied functions; the SDK cannot enforce they are different models, different prompts, or truly adversarial. A malicious caller could pass a no-op skeptic.

---

### 5. Weakest-link confidence (confidence never exceeds the shakiest step)

**Capability:** `recursive.weakest_link(tree)` computes confidence as the minimum along any root-to-leaf path. A parent node's confidence is capped by its lowest descendant. Returns the minimum confidence and the path to that step. Bounds: max depth 40, max nodes 5000.

**Why policy/prompt cannot provide it:** A prompt can ask "rate your confidence," but the model assigns a single number to the conclusion. There is no structural mechanism that forces the conclusion's confidence to be the minimum of its supporting steps. A model can claim high confidence in a conclusion built on a shaky premise.

**Where enforced:** `recursive.py:93–118` — recursive `walk` computes `best = (c, here)` then updates if `kc < best[0]` (line 114); depth and node bounds checked (lines 97–101, 108–110).

**Test:** `tests/test_metacog.py::Recursive::test_confidence_is_capped_by_the_weakest_step`; `tests/redteam_2_recursive.py::C_WeakestLink` (all 3 tests).

**Honest limit:** Confidence values are supplied by the verifiers; the SDK does not calibrate them. A verifier can return 1.0 for a guess. The tree structure is caller-supplied; the SDK cannot verify it reflects the actual reasoning chain.

---

## DKG + lattice integration

This SDK does **not** import `vega-dkg-lattice-sdk` or `vega-reasoning-sdk`. It operates at layer 12 (verify), depending only on layer 0 (custody). The integration points are:

- **Evidence rungs → reasoning lattice:** The rung (FACT, SINGLE_SOURCE, etc.) and `independent_origins` count can be used by `vega-reasoning-sdk` to weight lattice nodes. The SDK does not call reasoning; the caller passes rung data upward.
- **Requirements gate → harness predicted paths:** `vega-harness-sdk` (layer 6) can pre-register predicted paths that include metacog gate checks. The harness calls `gate()` as a step; the gate's COMPLETE/INCOMPLETE/REFUSED becomes a harness checkpoint.
- **Recursive outcomes → librarian lessons:** `recursive_verify` and `dual_pass` results (status, levels, abstained, objections) can be recorded to custody and later distilled by `vega-librarian-sdk` (layer 5) into lessons for the knowledge graph.
- **Custody DAG as the single anchor:** All three modules record hashes to the same caller-supplied DAG. The DAG is the chain-of-custody backbone that `vega-governance-feed-sdk` (layer 13) watches and `vega-galaxy-sdk` (layer 14) visualizes.

**No direct imports:** The published code in `src/vega_metacog/` imports only `vega_custody.dag.dag`. Any cross-layer wiring is done by the caller (typically `vega-umbrella-sdk` at assemble time).

---

## A category of its own

**Governance-first (authority outside the model):** The requirements ledger fixes the list before judgment; the gate refuses to guess; the author cannot verify their own judged work. Authority to declare "done" is held by independent verifiers and ultimately a human (NEEDS_HUMAN), not the model.

**Deterministic conductor (no model in the loop):** The ledger, gate, evidence grader, and recursive verifier are pure functions with typed exceptions. No LLM call is inside the SDK. The model may supply verifier functions, but the SDK's control flow — freeze, escalate, gate, abstain — is deterministic code.

**Pre-registered predicted paths:** The requirements list is registered upfront. The gate checks exactly that list. A caller (harness) can register the predicted path's requirements before execution; the gate then enforces the pre-declared path.

**Single-use human commitments:** Human-kind requirements settle only via `kind_used="human"` by a non-author verifier. This maps to the governance-jacket single-use commitment: one human decision per requirement, recorded to the DAG.

**Chain-of-custody by default:** Every state change (register, verify, reopen, gate, evidence grade, recursive outcome) records a hash to the custody DAG. The DAG is append-only, hash-chained, and tamper-evident. The SDK records hashes, never content.

**Lattice-informed foresight (via the family):** The rung grades, gate status, and recursive outcomes feed upward into the reasoning lattice (layer 11) and galaxy (layer 14). The human sees the full chain — evidence → requirements → recursive check → gate → record — before deciding the next action.

**Honest differentiation:** Every claim above is phrased as what *this design does*. The architecture (authority held outside the model, deterministic gates, append-only chain) structurally prevents the model from self-approving, moving goalposts, or inflating confidence. A policy-based approach cannot replicate this because the policy enforcer is the model itself.
