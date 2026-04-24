# Test Suite Audit (April 2026, executed)

This document is the **executed** output of a one-time test-suite audit conducted alongside the introduction of `.cursor/rules/testing_when_to_write.mdc` and `.cursor/rules/test_anti_patterns.mdc`. The cleanup was completed in six small commits driven by `.cursor/plans/test_audit_cleanup_*.plan.md`. Each section below shows the original finding and the action taken, so the file can stay linked from the rules as a worked example of the catalog in action.

## Audit scope (post-cleanup)

- **Unit tests:** 192 files, ~1,104 test functions (baseline: 188 files / ~1,086 — moves and parametrize bookkeeping changes net out to a small increase in *files* and a small decrease in *functions* once parametrized cases are counted by their `def`)
- **Integration tests:** 25 files, ~66 test functions (baseline: 33 files / ~90 — five files relocated to unit, three perf files deleted)
- **Source code:** 221 Python files under `app/`, ~52,700 LOC (baseline: 219 / ~52,400 — Batch 6 added `app/persistence/local_history_writer.py` and surfaced `load_effective_exclude_patterns` in `app/project/file_excludes.py`)
- **Test code:** ~30,100 LOC

The proximate cause of the original bloat was two `alwaysApply: true` rules that pushed TDD on every change without a "when not to test" gate. The new gate plus the anti-pattern catalog should keep growth proportional going forward.

## Conventions

Each entry below names the file, the specific tests within it that match an anti-pattern, and the rule from `.cursor/rules/test_anti_patterns.mdc` that applies. Numeric ranges (e.g. "~17 tests") are conservative; consolidation via parametrization can recover more.

---

## 1. Delete outright — DONE

Executed: ~17 tests removed across 4 files (`tests/unit/core/test_constants.py`, `tests/unit/compat/test_python39_typing_compat.py`, two tests from `tests/unit/core/test_errors.py`, one test from `tests/integration/examples/test_load_example_project_integration.py`). The empty `tests/unit/compat/` directory was also removed.

---

## 2. Trim or parametrize — PARTIALLY DONE

Parametrization complete (Batch 3): collapsed `tests/unit/shell/test_status_bar.py` (`format_diagnostics_counts_*`), `tests/unit/shell/test_settings_models.py` (default + explicit walls), `tests/unit/shell/test_theme_tokens.py` (color matrix), `tests/unit/intelligence/test_cache_controls.py` (defaults vs explicit), and renamed/relocated `tests/unit/intelligence/test_semantic_tokens.py` → `tests/unit/treesitter/test_language_registry.py` with shared fixture and parametrized cases.

Schema-snapshot trims (Batch 4) and private-API refactor (Batch 6) are tracked below in §6.

### Schema snapshots — DONE (Batch 4)

Trimmed `tests/unit/core/test_models.py` to assert canonical key sets and nested-payload contracts (no `from_dict` exists on these dataclasses, so a literal-payload schema check on the persisted `project.json` boundary keys is the meaningful coverage). Trimmed `tests/unit/plugins/test_workflow_broker.py::test_workflow_broker_records_success_metrics_for_builtin_query_provider` from a literal `metrics == [{...}]` snapshot to a focused field-and-relationship check.

### Private API coupling — DONE (Batch 6)

Extracted `MainWindow._load_effective_exclude_patterns` into `app.project.file_excludes.load_effective_exclude_patterns` (taking a `SettingsServiceLike` protocol) and deleted the redundant `_load_global_exclude_patterns` / `_load_project_exclude_patterns` private helpers; rewrote the corresponding tests in `tests/unit/project/test_file_excludes.py` against the public seam with a `_StubSettingsService`. Extracted the multi-file checkpoint pipeline used by `MainWindow._record_local_history_transaction` into `app.persistence.local_history_writer` (`resolve_local_history_context`, `record_local_history_checkpoint`, `record_local_history_transaction`); rewrote `tests/unit/persistence/test_local_history_checkpoints.py` to exercise those free functions and dropped the legacy `MainWindow.__new__` hand-attach pattern.

---

## 3. Relocate — DONE

Executed: 5 files moved from `tests/integration/{bootstrap,persistence,intelligence}/` to `tests/unit/{bootstrap,persistence,intelligence}/` and their `pytestmark` switched from `pytest.mark.integration` to `pytest.mark.unit`. The now-empty `tests/integration/bootstrap/`, `tests/integration/persistence/`, and `tests/integration/intelligence/` directories were also removed. The private-attribute coupling in `test_local_history_checkpoints.py` is addressed in §6 below.

---

## 4. Performance subsuite decision — DONE (demoted)

Decision: demote.

Executed:

- Added `performance` marker to `pyproject.toml` and updated `run_tests.py` to auto-inject `-m "not performance"` unless the caller supplies `-m` or selects a path under `tests/integration/performance/`.
- Updated `AGENTS.md` with the explicit invocation for the demoted suite (`python3 run_tests.py -m performance tests/integration/performance/`).
- Deleted `test_runtime_onboarding_performance.py`, `test_local_history_performance.py`, and `test_semantic_intelligence_performance.py` outright (per-widget micro-timings, private-method probes, duplicated semantic coverage).
- Trimmed `test_responsiveness_thresholds.py` to the three real user-journey smokes (`open_project`, `open_2000_loc_file`, `find_in_files`); deleted the `ConsoleModel` and `RunLogPanel` burst-timing tests.
- Trimmed `test_editor_highlighting_performance.py` by deleting the two private-method probes (`_build_bracket_match_selections`, `_effective_highlighting_mode`); kept the four warm-path real-Qt rehighlight + theme-apply smokes.
- Tagged the surviving two files with `pytest.mark.performance`.

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