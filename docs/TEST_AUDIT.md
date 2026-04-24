# Test Suite Audit (April 2026)

This document is a **standing checklist** of tests in this repo that do not earn their keep, organized by what to do with them. It is the output of a one-time audit conducted alongside the introduction of `.cursor/rules/testing_when_to_write.mdc` and `.cursor/rules/test_anti_patterns.mdc`.

The audit is read-only — no code has been changed yet. Use this document to drive the cleanup in small, reviewable batches. Re-evaluate any item before deletion against the rule files referenced above; if a test still passes the gate, keep it.

## Audit scope and headline numbers

- **Unit tests:** 188 files, ~1,086 test functions
- **Integration tests:** 33 files, ~90 test functions
- **Source code:** 219 Python files under `app/`, ~52,400 LOC
- **Test code:** ~25,650 LOC

Test functions per source file: ~6.4. The proximate cause of the bloat is two `alwaysApply: true` rules that pushed TDD on every change without a "when not to test" gate.

## Conventions

Each entry below names the file, the specific tests within it that match an anti-pattern, and the rule from `.cursor/rules/test_anti_patterns.mdc` that applies. Numeric ranges (e.g. "~17 tests") are conservative; consolidation via parametrization can recover more.

---

## 1. Delete outright

These tests have no behavioral signal and should be removed without replacement. Estimated: ~17 tests across 4 files.

### `[tests/unit/core/test_constants.py](../tests/unit/core/test_constants.py)` — entire file (3 tests)

- `test_global_state_constant_values`
- `test_project_structure_constant_values`
- `test_temp_namespace_constant_is_stable`

**Anti-pattern:** Constant pinning (rule §1). Each test asserts `constants.X == "literal"` for many constants; the assertions duplicate the source of truth. Type checking and call sites already protect renames.

**Action:** Delete the file. If a constant participates in an external contract (filesystem path read by another tool, persisted JSON key with migrations), assert that contract in the consumer's test instead.

### `[tests/unit/compat/test_python39_typing_compat.py](../tests/unit/compat/test_python39_typing_compat.py)` — entire file (1 test)

- `test_syntax_registry_avoids_runtime_pipe_union_aliases`

**Anti-pattern:** Lint-as-test (rule §3). The test parses `app/editors/syntax_registry.py` with `ast` and asserts no `|` characters appear in assignment values. This is a linter rule wearing a pytest costume.

**Action:** Delete the file. Replace with `pyright` configuration (the existing `pyrightconfig.json` already targets Python 3.9, which flags PEP 604 unions in runtime contexts) and/or a `ruff` rule (`UP007`).

### `[tests/unit/core/test_errors.py](../tests/unit/core/test_errors.py)` — partial (2 of 4 tests)

- `test_project_manifest_validation_error_is_validation_error`
- `test_project_enumeration_error_is_project_load_validation_error`

**Anti-pattern:** `isinstance` of a hierarchy declared in the same file (rule §5). The base classes sit a few lines above the assertions in `app/core/errors.py`.

**Action:** Delete these two tests. Keep `test_project_manifest_validation_error_keeps_field_and_manifest_path_context` and `test_project_structure_validation_error_keeps_project_root_context` — those test real `__str__` formatting and field preservation.

### `[tests/integration/examples/test_load_example_project_integration.py](../tests/integration/examples/test_load_example_project_integration.py)` — partial (1 test)

- `test_materialized_showcase_readme_references_key_features`

**Anti-pattern:** Constant pinning on marketing copy (rule §1). Asserting that the showcase README contains specific substrings is high-churn, low-protection — the moment someone improves the copy, the test breaks.

**Action:** Delete the test. Keep the rest of the file.

---

## 2. Trim or parametrize

These files contain real behavioral coverage mixed with copy-paste duplication, default-literal walls, or schema snapshots. Rewrite, do not delete the file. Estimated: ~50–70 test functions can be removed via consolidation.

### `[tests/unit/core/test_models.py](../tests/unit/core/test_models.py)` — schema snapshots

Tests `test_project_metadata_serializes_to_stable_schema`, `test_project_file_entry_serializes_to_stable_schema`, and `test_loaded_project_serializes_to_stable_schema` assert literal `to_dict()` output that mirrors the dataclass constructors.

**Anti-pattern:** Schema snapshot mirroring the dataclass (rule §2).

**Action:** Replace with one round-trip test per dataclass (`to_dict` → `json.dumps` → `json.loads` → `from_dict`) plus assertions on the two or three fields that have non-trivial defaults. Keep `test_capability_probe_report_preserves_check_order` and `test_capability_probe_report_exposes_aggregate_fields` — those test real aggregation behavior.

### `[tests/unit/shell/test_settings_models.py](../tests/unit/shell/test_settings_models.py)` — default-literal walls

The first ~120 lines re-state every default field after `parse_editor_settings_snapshot({})`. There are ~35 tests in the file; many are similar default-equality blocks for related parsers.

**Anti-pattern:** Tautological / duplicate coverage (rules §8, §10).

**Action:** Collapse the default-assertion blocks into one parametrized test per parser using `(payload, field, expected)` tuples. Keep merge/scope/override tests as-is — those test real branching.

### `[tests/unit/shell/test_status_bar.py](../tests/unit/shell/test_status_bar.py)` — `format_diagnostics_counts_`*

Five tests differ only by inputs: `..._errors_and_warnings`, `..._singular`, `..._only_errors`, `..._only_warnings`, `..._zero`.

**Anti-pattern:** Duplicate coverage / parametrize candidate (rule §8).

**Action:** Replace with a single `@pytest.mark.parametrize` block. Keep the other `map_*_status_`* tests.

### `[tests/unit/shell/test_theme_tokens.py](../tests/unit/shell/test_theme_tokens.py)` — color matrix

`test_dark_tokens_have_expected_fields`, `test_light_tokens_have_expected_fields`, `test_light_and_dark_produce_different_tokens` mostly pin hex strings or assert non-empty fields.

**Anti-pattern:** Constant pinning + duplicate coverage (rules §1, §8).

**Action:** Replace the per-color assertions with a golden-file or single "all keys present and non-empty" test plus one "light differs from dark" smoke. Keep mode/branch tests.

### `[tests/unit/intelligence/test_semantic_tokens.py](../tests/unit/intelligence/test_semantic_tokens.py)` — repeated registry setup

Five tests repeat nearly identical `monkeypatch` skeletons over `TreeSitterLanguageRegistry`. The file is also misleadingly named — it tests the registry, not semantic tokens.

**Anti-pattern:** Duplicate coverage (rule §8) plus naming debt.

**Action:** Parametrize the cases over a shared fixture, and rename the file to `test_treesitter_language_registry.py` (or move to `tests/unit/treesitter/`).

### `[tests/unit/intelligence/test_cache_controls.py](../tests/unit/intelligence/test_cache_controls.py)` — defaults vs explicit

Same "defaults dict vs explicit dict" pattern as `test_settings_models.py`.

**Action:** Parametrize. Keep clamp logic and `rebuild_symbol_cache` tests.

### `[tests/unit/plugins/test_workflow_broker.py](../tests/unit/plugins/test_workflow_broker.py)` — metrics snapshot

`test_workflow_broker_records_success_metrics_for_builtin_query_provider` asserts a large literal `metrics == [{...}]` plus `isinstance` on floats.

**Anti-pattern:** Schema snapshot (rule §2).

**Action:** Trim to assert the keys and the relationships that matter (e.g. `metric["status"] == "ok"`, `metric["duration_ms"] >= 0`). Keep the failure/timeout tests.

### `[tests/unit/shell/test_main_window_settings_scope.py](../tests/unit/shell/test_main_window_settings_scope.py)` — private API

`test_load_effective_exclude_patterns_`* tests reach `MainWindow._load_effective_exclude_patterns` via `__new__`.

**Anti-pattern:** Private-attribute / private-method probing (rule §6).

**Action:** Extract the pattern-resolution logic into a free function under `app/shell/` (or wherever owns the policy), test that directly, and have `MainWindow` call into it. Then either delete these tests or rewrite them to exercise the public seam.

---

## 3. Relocate

These integration tests are heavily mocked and exercise no real cross-process boundary — they belong under `tests/unit/`. Estimated: ~11 tests across 5 files.

### `[tests/integration/bootstrap/test_editor_startup_probe.py](../tests/integration/bootstrap/test_editor_startup_probe.py)`

`run_minimal_startup_capability_probe`, `configure_app_logging`, `_load_qt_runtime`, `_start_editor` are all stubbed. There is no real subprocess, filesystem, or protocol behavior under test.

**Action:** Move to `tests/unit/bootstrap/` and rename if needed. Anything that wants to exercise a real probe goes in `tests/runtime_parity/`.

### `[tests/integration/persistence/test_local_history_checkpoints.py](../tests/integration/persistence/test_local_history_checkpoints.py)`

Constructs `MainWindow.__new__` and hand-attaches services. Tests `_save_tab` and `_record_local_history_transaction` as static-ish units.

**Action:** Move to `tests/unit/persistence/` (or `tests/unit/shell/`). Either expose a public seam first (preferred) or leave the private-attr coupling temporarily and flag it for follow-up cleanup.

### `[tests/integration/persistence/test_autosave_recovery.py](../tests/integration/persistence/test_autosave_recovery.py)`

Exercises `EditorManager` + `AutosaveStore` with no shell, project lifecycle, or subprocess involvement.

**Action:** Move to `tests/unit/persistence/`.

### `[tests/integration/intelligence/test_semantic_rename_integration.py](../tests/integration/intelligence/test_semantic_rename_integration.py)`

Calls `plan_rename_symbol` / `apply_rename` on fixture files. No app shell, no IPC.

**Action:** Move to `tests/unit/intelligence/`.

### `[tests/integration/intelligence/test_semantic_navigation_integration.py](../tests/integration/intelligence/test_semantic_navigation_integration.py)`

Calls navigation services + sqlite directly. No app shell.

**Action:** Move to `tests/unit/intelligence/`. (sqlite alone does not make a test "integration" — sqlite is in-process.)

---

## 4. Performance subsuite decision

The five files under `[tests/integration/performance/](../tests/integration/performance/)` account for ~18 of the ~90 integration tests and assert hard wall-clock thresholds (p95 ms, ratio limits, absolute seconds). They are the largest source of integration-suite flake risk and contribute disproportionately to runtime.

- `[test_runtime_onboarding_performance.py](../tests/integration/performance/test_runtime_onboarding_performance.py)` — times `RuntimeCenterDialog.set_report`, `WelcomeWidget._apply_filter`, `map_startup_report_to_status` against absolute second budgets. Also reaches `WelcomeWidget._apply_filter` (private).
- `[test_local_history_performance.py](../tests/integration/performance/test_local_history_performance.py)` — microbenchmarks `HistoryRestorePickerDialog._refresh_results` (private).
- `[test_responsiveness_thresholds.py](../tests/integration/performance/test_responsiveness_thresholds.py)` — mixes meaningful workflow timing (`open_project`, `find_in_files`) with module-level burst timing (`ConsoleModel`, `RunLogPanel`).
- `[test_editor_highlighting_performance.py](../tests/integration/performance/test_editor_highlighting_performance.py)` — exercises real Qt + tree-sitter; uses private editor methods (`_build_bracket_match_selections`, `_effective_highlighting_mode`).
- `[test_semantic_intelligence_performance.py](../tests/integration/performance/test_semantic_intelligence_performance.py)` — warm-path bounds on `SemanticFacade`, duplicating coverage already present in `tests/integration/intelligence/`.

**Recommended decision:** demote the whole subtree to a non-default suite and run it on a dedicated, machine-pinned job. Concretely:

1. Add a `performance` marker (already implied by the shard runner) and stop including this directory in default `python3 run_tests.py` invocations.
2. Keep at most 2–3 user-journey timing smokes (e.g. `open_project` of a known project must finish under N seconds on the reference machine), and delete the per-widget micro-timings.
3. Files that probe private methods (`WelcomeWidget._apply_filter`, `HistoryRestorePickerDialog._refresh_results`, `_build_bracket_match_selections`) should be deleted regardless — fix the seam or drop the assertion.

If you do not want a separate perf job, delete the whole subtree and rely on manual profiling driven by user complaints.

---

## Estimated cleanup totals


| Bucket                        | Files touched | Tests removed/relocated | Notes                                                   |
| ----------------------------- | ------------- | ----------------------- | ------------------------------------------------------- |
| Delete outright               | 4             | ~17                     | Constants, lint-as-test, README copy, isinstance-only   |
| Trim or parametrize           | 8             | ~50–70                  | Recovered via parametrization, schema-snapshot trimming |
| Relocate to `tests/unit/`     | 5             | ~11                     | Same coverage, correct layer                            |
| Performance subsuite (demote) | 5             | ~12–15                  | Or delete entirely, ~18                                 |
| **Total**                     | **~22**       | **~90–115**             | ~8–10% of the suite                                     |


These are floor numbers. The real win is preventing the next 100 low-value tests from being written.

## Suggested execution order

1. Delete outright (smallest blast radius, no behavior change).
2. Move the misclassified integration files into `tests/unit/`.
3. Parametrize the duplicate-coverage clusters.
4. Trim schema snapshots to round-trips.
5. Make the performance-subsuite decision and act on it.
6. Tackle the private-attr coupling by exposing public seams (longer-running cleanup).

Each step should be its own commit so the diff stays reviewable.