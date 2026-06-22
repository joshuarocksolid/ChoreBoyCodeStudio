# Test and Tooling Audit — R6 Closeout (2026-06-22)

**Status:** complete (documentation pass; no test rewrites in this PR)  
**Related:** [AUDIT_app_remaining_handoff.md](AUDIT_app_remaining_handoff.md) §R6, [AUDIT_out_of_scope.md](AUDIT_out_of_scope.md) §OS-T* briefs

## 1. Purpose

Record concrete brittleness findings in the shell test tree, document the **no new static tools** decision, and give future agents small rewrite briefs without mixing `app/` slop into this file.

## 2. Scope audited

| Path | Role |
| --- | --- |
| `tests/unit/shell/` | Primary brittleness surface (48 files) |
| `tests/unit/editors/` | Secondary widget-coupling surface (7 files with private access) |
| `tests/integration/shell/` | Full `MainWindow` integration harness (12 files) |
| `tests/support/shell_host_stubs.py` | Preferred stub seam (341 lines) |
| `testing/main_window_test_helpers.py` | Integration lifecycle helpers |
| `requirements-dev.txt`, `pyproject.toml` | Tooling/config (no changes) |
| [AGENTS.md](../../AGENTS.md), [docs/TESTS.md](../TESTS.md) | Canonical run commands |

## 3. Metric sweep (2026-06-22, repo at HEAD)

```bash
# Shell private-attribute probes (pattern: \._[a-zA-Z])
rg '\._[a-zA-Z]' tests/unit/shell --count-matches
# => 723 matches across 48 files

rg '\._[a-zA-Z]' tests/integration/shell --count-matches
# => 166 matches across 12 files

rg '\._[a-zA-Z]' tests/unit/editors --count-matches
# => 112 matches across 7 files

# Layout / objectName brittleness (shell unit + integration)
rg 'objectName\(\)|\.layout\(\)|findChild\(' tests/unit/shell tests/integration/shell --count-matches
# => 25 matches

# MainWindow construction in shell tests
rg 'MainWindow\(' tests --glob '**/shell/**' -l | wc -l
# => 23 files

# Legacy __new__ harness (prefer shell_host_stubs)
rg 'MainWindow\.__new__|__new__\(cls' tests --glob '*.py' -l
# tests/support/shell_host_stubs.py (docstring only)
# tests/unit/shell/test_main_window_background_teardown.py
# tests/unit/persistence/test_local_history_checkpoints.py (comment only)

# Test harness adoption
rg 'shell_host_stubs' tests --glob '*.py' -l | wc -l   # => 3
rg 'prepare_main_window_for_test|shutdown_main_window_for_test' tests -l | wc -l  # => 15

# Suite shape
find tests -name '*.py' | wc -l   # => 359 files, ~48,216 LOC
find tests/unit/shell -name '*.py' | wc -l  # => 282 unit total; shell subtree is largest UI cluster
```

**Checkpoint reference:** fast shard **2064 selected / 0 failures** and `npx pyright` **0 errors** per [AGENTS.md](../../AGENTS.md). This audit does not change those gates.

## 4. Top brittle files (shell unit)

Prioritize rewrites by private-access density and R3/R6 overlap from shell wave reviews:

| File | Private `._` hits | Slop signature |
| --- | ---: | --- |
| [`tests/unit/shell/test_search_sidebar_widget.py`](../../tests/unit/shell/test_search_sidebar_widget.py) | 92 | Direct `_search_input`, `_summary_label`, `_replace_toggle_btn` text/layout assertions |
| [`tests/unit/shell/test_main_window_format_actions.py`](../../tests/unit/shell/test_main_window_format_actions.py) | 90 | Hand-attached `_`-prefixed host fields on partial MainWindow stand-ins |
| [`tests/unit/shell/test_settings_dialog.py`](../../tests/unit/shell/test_settings_dialog.py) | 69 | Banner/button label text via `_validation_banner_label`, `_ok_button` |
| [`tests/unit/shell/test_debug_panel_widget.py`](../../tests/unit/shell/test_debug_panel_widget.py) | 41 | Widget tree + `objectName()` contract tests |
| [`tests/unit/shell/test_run_debug_presenter.py`](../../tests/unit/shell/test_run_debug_presenter.py) | 37 | Presenter/state via private coordinator fields |
| [`tests/unit/shell/test_welcome_widget.py`](../../tests/unit/shell/test_welcome_widget.py) | 34 | Internal label/button probes |
| [`tests/unit/shell/test_test_explorer_panel.py`](../../tests/unit/shell/test_test_explorer_panel.py) | 33 | `_tree`, `_empty_label`, outcome toggle text |
| [`tests/unit/shell/test_project_tree_refresh_state.py`](../../tests/unit/shell/test_project_tree_refresh_state.py) | 31 | Partial MainWindow with `_project_tree` internals |
| [`tests/unit/shell/test_python_console_widget.py`](../../tests/unit/shell/test_python_console_widget.py) | 30 | Console widget private layout |
| [`tests/unit/shell/test_main_window_reference_rename_actions.py`](../../tests/unit/shell/test_main_window_reference_rename_actions.py) | 30 | Semantic action wiring through private host attrs |

**Integration cluster:** [`tests/integration/shell/test_main_window_quick_open_integration.py`](../../tests/integration/shell/test_main_window_quick_open_integration.py) (33), [`test_main_window_shutdown_integration.py`](../../tests/integration/shell/test_main_window_shutdown_integration.py) (33), [`test_main_window_session_persistence_integration.py`](../../tests/integration/shell/test_main_window_session_persistence_integration.py) (27) — all reach into live `MainWindow` private fields instead of observable UI outcomes.

**Editors follow-ups (lower volume, same pattern):** [`tests/unit/editors/test_find_replace_bar.py`](../../tests/unit/editors/test_find_replace_bar.py) (34), [`test_code_editor_widget_highlighting.py`](../../tests/unit/editors/test_code_editor_widget_highlighting.py) (23), [`test_quick_open_dialog.py`](../../tests/unit/editors/test_quick_open_dialog.py) (19).

## 5. Brittleness patterns catalog

| # | Pattern | Example paths | Risk | Preferred rewrite |
| --- | --- | --- | --- | --- |
| B1 | Private widget field assertions | `test_search_sidebar_widget.py`, `test_settings_dialog.py` | Breaks on any rename/refactor of internal layout | Assert public methods, Qt signals, model roles, or exported presenter state |
| B2 | Partial `MainWindow` / `__new__` harness | `test_main_window_background_teardown.py:92`, format/reference-rename tests | Hides missing host protocols; skips real init/teardown | Extend [`tests/support/shell_host_stubs.py`](../../tests/support/shell_host_stubs.py) or workflow host protocols |
| B3 | `objectName()` layout contracts | `test_toolbar.py:56`, `test_debug_panel_widget.py:90`, integration runtime dialogs | Couples tests to Qt Designer-style names | Keep only where manual acceptance explicitly requires stable object names; otherwise delete |
| B4 | Icon cache identity | `test_outline_panel.py:471` (`cacheKey()`) | Theme/icon pipeline noise | Assert tree content or visibility, not cache keys |
| B5 | Full `MainWindow()` integration probing | 12 files under `tests/integration/shell/` | Slow, Qt-session heavy, private-field brittle | Use `testing/main_window_test_helpers.py` lifecycle + public panel APIs |
| B6 | `# noqa: E402` import blocks | 50+ shell/editor test modules | Often masks late imports after `importorskip`; acceptable when required for Qt | Do not "fix" unless moving imports improves clarity without circular imports |
| B7 | `# type: ignore` in shell tests | ~393 hits in shell unit+integration | Mostly `# type: ignore[no-untyped-def]` on fixtures | Reduce only when touching the same file for B1–B5 |

**Not in scope for wholesale deletion:** tests that protect subprocess/runner contracts, manifest serialization, or risk-first gates listed in [.cursor/rules/testing_when_to_write.mdc](../../.cursor/rules/testing_when_to_write.mdc).

## 6. Decision record — no new repo-wide tools

**Decision:** Do **not** add Ruff, Vulture, Radon, Lizard, or another complexity linter in R6.

| Candidate | Why deferred |
| --- | --- |
| **Ruff** | Requires AppRun/no-venv execution story, Python 3.9 pin alignment, and CI wiring; existing `pyright` + pytest already gate merges with 0 errors. |
| **Vulture** | High false-positive rate on PySide2 slots, plugin entrypoints, and test-only imports; would need extensive allowlists before signal. |
| **Radon / Lizard** | Complexity metrics duplicate the manual god-module tracking already in [AUDIT_app.md](AUDIT_app.md); no recurring failure class tied to cyclomatic score. |
| **Custom private-access linter** | Tempting for B1, but brittle regex over `._` would flag legitimate protocol stubs; better addressed by targeted test rewrites (§7). |

**Triggers to revisit:** repeated regressions from renamed private fields after R3 shell splits; or CI time lost to undetected dead test helpers.

**Existing tooling kept explicit:**

- `npx pyright` / `pyrightconfig.json` — source + test typing ([AGENTS.md](../../AGENTS.md))
- `python3 testing/run_test_shard.py fast` — AppRun pytest harness
- `pytest` markers in `pyproject.toml` (`unit`, `integration`, `slow`, `performance`, `runtime_parity`)
- [`requirements-dev.txt`](../../requirements-dev.txt) — empty placeholder; dev deps live in vendor + `package.json` (pyright pin)

## 7. Recommended rewrite briefs (for future PRs)

Each brief is intentionally smaller than "fix all shell tests."

### R6-T1 — Search + settings widget public seams (M)

**Files:** `test_search_sidebar_widget.py`, `test_settings_dialog.py`  
**Goal:** Replace B1 private label/input probes with signal emissions or small public query methods on `SearchSidebarWidget` / settings dialog if missing.  
**Acceptance:** Same behavior coverage; private `._` hits down ≥80% in touched files; fast shard green.

### R6-T2 — Format actions + reference rename host stubs (M)

**Files:** `test_main_window_format_actions.py`, `test_main_window_reference_rename_actions.py`, `test_project_tree_refresh_state.py`  
**Goal:** Collapse hand-built partial MainWindow objects onto typed stubs in `shell_host_stubs.py` (pattern B2).  
**Acceptance:** No new `MainWindow.__new__` blocks; tests assert workflow outcomes not host field names.

### R6-T3 — Integration shell quick-open + shutdown (L)

**Files:** top three integration files by private-hit count (§4)  
**Goal:** Route through `prepare_main_window_for_test` / public panel APIs; delete redundant private tree/dialog field reads.  
**Acceptance:** Integration shard green; no increase in leaked `run_plugin_host`/`run_runner` children (see `testing/preflight_test_env.py`).

### R6-T4 — Debug panel + test explorer layout contracts (S)

**Files:** `test_debug_panel_widget.py`, `test_test_explorer_panel.py`, `test_toolbar.py`  
**Goal:** Drop B3 `objectName()` assertions unless tied to documented accessibility IDs; keep outcome assertions.  
**Acceptance:** Manual acceptance note if any objectName test removed that maps to [docs/ACCEPTANCE_TESTS.md](../ACCEPTANCE_TESTS.md).

### R6-T5 — Editors find/replace + quick open (S)

**Files:** `tests/unit/editors/test_find_replace_bar.py`, `test_quick_open_dialog.py`  
**Goal:** Mirror shell stub pattern for editor widgets; assert dialog result codes and document text, not `_`-prefixed controls.

## 8. Validation reference

```bash
python3 testing/run_test_shard.py fast
python3 run_tests.py tests/unit/shell/test_search_sidebar_widget.py  # when rewriting
npx pyright
```

## 9. R6 acceptance (this pass)

| Criterion | Status |
| --- | --- |
| Concrete shell brittleness findings documented | ✅ §3–§5 |
| Tooling decision explicit with rationale | ✅ §6 |
| No new tools added | ✅ |
| No broad coverage-chasing tests added | ✅ |
| Small agent briefs for follow-up rewrites | ✅ §7 |

End of R6 test/tooling audit.
