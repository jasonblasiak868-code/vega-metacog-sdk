# Changelog

## 2026-10-20: fixes found by a source read

These were found by reading the source against its own documentation after release, not by the earlier test and review passes. Each fix has a regression test in
`tests/test_findings_20261020.py` that failed before the fix, and each fix was checked by undoing it and confirming a test fails. Behaviour that changed is listed under "Changed".

### Fixed
- **A "human" requirement was settled by a label, not a person.** Any non-author id passing `kind_used="human"` settled it. The Ledger now takes a `human_check(requirement id, verifier id)` and settles a human item only when it returns exactly True; with none configured, no one can settle it.
- **State changed before it was recorded.** `verify`, `register` and `reopen` changed the item and then wrote the record, so a failed chain write left an item VERIFIED in memory with no record. They now record first.

### Changed (read before upgrading)
- `Ledger(dag, author, human_check=None)`: human requirements need a `human_check`. The umbrella's `metacog_ledger(author, human_check=None)` passes it through.
