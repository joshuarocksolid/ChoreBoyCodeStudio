# TN-EDIT-AUX — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-AUX  
**Date:** 2026-06-17  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/editors/text_editing.py` (525 LOC), `app/editors/quick_open.py` (172 LOC), `app/editors/quick_open_dialog.py` (458 LOC). Cross-read: `app/shell/file_project_commands_workflow.py` (`handle_quick_open_action`, host dialog lifecycle). Focus: pure-text module size, AST/parso paste-repair tiering, fuzzy-open UI boundaries, extract-vs-keep decisions. Gates: §12.4 mixin model (indirect — consumers in `code_editor_editing.py` / hub), four-theme `ShellThemeTokens`, canonical layer for file indexing.

---

## Executive verdict

**Not thermo-clean — the quick-open split is exemplar code-judo, but `text_editing.py` is two unrelated programs in one file and the dialog carries a dual-model workaround.** `quick_open.py` (pure rank/match) vs `quick_open_dialog.py` (Qt overlay) is the right ownership boundary and should be **kept**. The flat-Python paste repair engine (~380 LOC of regex stack machine, bracket tokenizer, triple-string state, AST + parso tiering) belongs in a dedicated sibling module, not cohabiting with `indent_lines` / `toggle_comment_lines` / `smart_backspace_columns`. `QuickOpenDialog` sidesteps Qt’s model contract with `_QuickOpenItemModel` parallel to `QStringListModel`, forcing the delegate to reach into a side channel. Shell wiring in `file_project_commands_workflow.py` is acceptable orchestration (lazy singleton + four signal lambdas) but will sprawl if quick-open gains more modes. No file crosses 1k; `text_editing.py` is the third-largest editor module and will absorb the next paste edge case unless split now. **REJECT** until flat-Python repair extracts to `flat_python_indent_repair.py` (or equivalent) and the dialog collapses to one list model (or a documented `QAbstractListModel`).

---

### TN-EDIT-AUX-1 — `text_editing.py` conflates trivial transforms with a paste-repair engine

- **Persona:** TN-EDIT-AUX
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/text_editing.py:1,49-98,100-484,482-525` — module docstring claims “Pure text-editing helper functions”; lines 49–98 and 482–525 are small line/offset utilities (`indent_lines`, `toggle_comment_lines`, `smart_backspace_columns`, `map_offset_through_text_change`); lines 100–484 are a self-contained flat-Python detection + reindent + AST/parso validation pipeline (`looks_like_flat_python_paste`, `repair_flat_python_indentation`, `_reindent_flat_python_lines`, `_count_unclosed_brackets`, etc.). Manifest lists file at **525 LOC**, third-largest under `app/editors/`.
- **Code-judo alternative:** **Extract** flat-Python repair to `app/editors/flat_python_indent_repair.py` (or `paste_indent_repair.py`); **keep** `text_editing.py` as the thin pure-text surface (~145 LOC). Re-export public repair API from `text_editing` only if callers need a stable import path, then hard-cutover imports in `code_editor_editing.py`, `code_editor_widget.py`, tests.
- **Suggested remediation:** One extraction PR; no behavior change. Delete duplicated module-level regex constants from the slim file. Cap `text_editing.py` at ~200 LOC in architecture notes.
- **Tests that would prove fix:** Existing flat-Python tests in `tests/unit/editors/test_code_editor_widget.py` pass unchanged; optional move to `test_flat_python_indent_repair.py`. `wc -l app/editors/text_editing.py` ≤ 200 post-split.
- **Handoff overlap:** §12.4, CC-02

---

### TN-EDIT-AUX-2 — AST + parso tiering is stringly-typed policy buried in the repair pipeline

- **Persona:** TN-EDIT-AUX
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/text_editing.py:12-19,38-46,164-207,472-479` — confidence is `"high" | "medium" | "low"` string literals; `auto_paste_accepts_repair` gates on `result.reason == _REPAIR_REASON_PARSO_CLEAN` (magic string equality). `_parso_error_count` uses `importlib.import_module("parso")` and `except Exception: return None`, silently collapsing parso failures into “no medium tier.” HIGH = `ast.parse` ok; MEDIUM = parso error count improved to zero; otherwise LOW.
- **Code-judo alternative:** Introduce a frozen `RepairConfidence` enum (or `Literal`) and `PasteRepairDecision` dataclass with explicit fields (`ast_ok`, `parso_errors_before`, `parso_errors_after`) so `auto_paste_accepts_repair` reads policy, not reason strings. Narrow parso `except` to import/parse failures; log unexpected exceptions once.
- **Suggested remediation:** Colocate enum/policy with extracted flat-Python module (TN-EDIT-AUX-1). Hub and mixin call `decision.auto_apply` instead of comparing reason strings.
- **Tests that would prove fix:** Existing `test_auto_paste_*` cases unchanged; add one test that parso `None` (simulated import failure) never auto-applies MEDIUM.
- **Handoff overlap:** none

---

### TN-EDIT-AUX-3 — `_reindent_flat_python_lines` state machine is maintainable only if isolated

- **Persona:** TN-EDIT-AUX
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/text_editing.py:269-376,379-454` — single loop tracks `stack`, `bracket_depth`, `in_triple_string`, `pending_decorators`, `previous_terminal`, with inline comment blocks for triple-string passthrough, bracket continuation, decorator transparency, and clause dedent. `_count_unclosed_brackets` is a 40-line char walker duplicating string/comment skip logic. `triple_delim` assigned then `del triple_delim` (`:372-374`) — dead symmetry variable.
- **Code-judo alternative:** **Keep** the algorithm in the extracted repair module (not inline in widget); optionally split `_reindent_flat_python_lines` + bracket/triple helpers into `flat_python_reindent.py` private to that package if the parent file still exceeds ~350 LOC. Delete unused `triple_delim` or use it to validate closing delimiter.
- **Suggested remediation:** Move as a unit with TN-EDIT-AUX-1; do not further split until a second consumer appears. Document invariants (decorator stack, `for/while…else` via `_stack_for_clause`) at module top.
- **Tests that would prove fix:** Existing decorator/bracket/docstring/`for…else` tests in `test_code_editor_widget.py` remain green after file move only.
- **Handoff overlap:** none

---

### TN-EDIT-AUX-4 — `quick_open.py` / `quick_open_dialog.py` split is the correct boundary (keep)

- **Persona:** TN-EDIT-AUX
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/quick_open.py:1-172` — pure dataclasses, fuzzy match, scoring, `rank_candidates` with no Qt imports. `app/editors/quick_open_dialog.py:33-37` — UI imports ranker only. Tests: `tests/unit/editors/test_quick_open.py`, `test_quick_open_dialog.py`; integration `tests/integration/shell/test_main_window_quick_open_integration.py`.
- **Code-judo alternative:** **Keep** this split; do not fold ranking into the dialog or move delegate paint into `quick_open.py`. If dialog grows past ~550 LOC, extract `QuickOpenDelegate` to `quick_open_delegate.py` without merging logic layers.
- **Suggested remediation:** None — use as template for other editor overlays (pure policy module + thin Qt shell).
- **Tests that would prove fix:** N/A — affirmative pattern.
- **Handoff overlap:** none

---

### TN-EDIT-AUX-5 — `QuickOpenDialog` dual-model pattern sidesteps Qt list contract

- **Persona:** TN-EDIT-AUX
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/quick_open_dialog.py:51-59,292-300,407-411,96-99` — `_QuickOpenItemModel` is a plain list holder, not `QAbstractListModel`. `QStringListModel` stores display strings only; `QuickOpenDelegate.paint` reads `RankedCandidate` + `match_positions` from `_item_model.items[row]`. Every refresh must sync `_item_data.set_items`, `_list_model.setStringList`, and selection index manually (`:404-417`).
- **Code-judo alternative:** Replace with one `QuickOpenListModel(QAbstractListModel)` exposing `Qt.DisplayRole` (path) and `Qt.UserRole` (`RankedCandidate`); delegate reads roles from `index.data()`. Deletes `_QuickOpenItemModel`, halving refresh sync points.
- **Suggested remediation:** Refactor in place before adding icons/badges/multi-column rows. Hard cutover — no parallel model path.
- **Tests that would prove fix:** `tests/unit/editors/test_quick_open_dialog.py` selection, debounce, and `:line` jump tests pass; delegate highlight positions unchanged for query `"qod"`.
- **Handoff overlap:** none

---

### TN-EDIT-AUX-6 — Shell quick-open wiring is lazy glue with repeated lambda shapes

- **Persona:** TN-EDIT-AUX
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/file_project_commands_workflow.py:521-570` — builds full candidate list from `loaded_project.entries` on every Ctrl+P; lazy-creates `QuickOpenDialog` once via `quick_open_dialog()` / `set_quick_open_dialog()` host ports (`:107-110,212-216`); four near-identical lambdas for preview vs permanent × plain vs `:line` (`:547-566`). Dialog lifetime stored on `main_window._quick_open_dialog` (`app/shell/main_window.py:99`).
- **Code-judo alternative:** Extract `_ensure_quick_open_dialog() -> QuickOpenDialog` on the workflow with a private `_connect_quick_open_signals(dialog)`; optionally pass a small `QuickOpenActions` dataclass (preview/open × line/noline callables) to collapse four lambdas to two method refs. **Keep** orchestration in shell — do not move candidate building into `app/editors/`.
- **Suggested remediation:** Defer until next quick-open feature; not a blocker if dual-model (TN-EDIT-AUX-5) and text split land first.
- **Tests that would prove fix:** `tests/unit/shell/test_main_window_quick_open.py` singleton reuse + signal wiring still pass.
- **Handoff overlap:** CC-02

---

### TN-EDIT-AUX-7 — Quick-open overlay shadow collapses four themes to `is_dark`

- **Persona:** TN-EDIT-AUX
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/quick_open_dialog.py:259-264` — `QGraphicsDropShadowEffect.setColor(QColor(0, 0, 0, 80 if self._tokens.is_dark else 40))`; tokens captured at construct time (`:244`), no `apply_theme` on theme switch while dialog cached on main window. Row chrome correctly uses `tree_selected_bg`, `tree_hover_bg`, `text_primary`, `accent` (`:92-94,160-171`).
- **Code-judo alternative:** Add optional `popup_shadow_alpha` (or reuse an existing chrome elevation token) on `ShellThemeTokens` for HC Light/Dark tuning; call `apply_theme(tokens)` when shell theme changes before `open_dialog()`.
- **Suggested remediation:** Backlog with other four-theme HC findings (cf. TN-EDIT-CORE-5/6); manual acceptance in Light/Dark/HC Light/HC Dark per `ui_light_dark_mode.mdc`.
- **Tests that would prove fix:** `test_quick_open_can_open_under_light_and_dark_themes` extended to HC modes; visual check shadow readable on `#FFFFFF` / `#000000` editor chrome.
- **Handoff overlap:** none

---

### TN-EDIT-AUX-8 — `rank_candidates` default limit diverges from dialog without contract comment

- **Persona:** TN-EDIT-AUX
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/quick_open.py:138-143` — `rank_candidates(..., limit: int = 100)`. `app/editors/quick_open_dialog.py:400` — `_rank_current_query` calls `rank_candidates(..., limit=50)`. Empty-query path in ranker returns open-then-rest with no fuzzy filter (`:147-156`); dialog count label shows `total_count` from full candidate set (`:321-323,424-428`).
- **Code-judo alternative:** Name the dialog cap explicitly (`QUICK_OPEN_RESULT_LIMIT = 50`) at module top or pass through constructor; document that 50 is a UI perf cap, not algorithm default. Optional: pre-sort open files in shell before `set_candidates` so empty-query order is stable without re-walking project entries each keystroke.
- **Suggested remediation:** Constant + one-line doc when touching dialog; no behavior change required for wave-1.
- **Tests that would prove fix:** `test_quick_open_dialog` debounce test already stubs `limit`; assert dialog never requests more than cap when project has >100 files.
- **Handoff overlap:** none

---

## Extract vs keep summary

| Piece | Verdict | Rationale |
|-------|---------|-----------|
| `quick_open.py` (pure rank/match) | **Keep** separate | Testable, Qt-free; correct layer |
| `quick_open_dialog.py` (overlay UI) | **Keep** file; **refactor** model inside | UI belongs in editors; dual-model is internal debt |
| `text_editing.py` simple helpers | **Keep** in slim `text_editing.py` | Small, shared by editing mixin + tests |
| Flat-Python repair engine | **Extract** to sibling module | ~70% of file LOC; distinct domain and test surface |
| Shell `handle_quick_open_action` | **Keep** in workflow | Canonical orchestration; minor lambda cleanup optional |
| AST/parso acceptance policy | **Extract** with repair module | String reasons → typed decision object |

---

## Approval bar checklist

| Criterion | Status |
|-----------|--------|
| No >1k file in slice | Pass (525 max) |
| Pure logic separated from Qt (quick open) | Pass |
| Obvious decomposition for largest module | **Fail** — `text_editing.py` dual-domain |
| No spaghetti dual-model in dialog | **Fail** — `_QuickOpenItemModel` side channel |
| Four-theme tokens for primary chrome | Pass (shadow excepted) |
| Canonical shell layer for open orchestration | Pass |

**Verdict: REJECT** — merge is blocked until TN-EDIT-AUX-1 (flat-Python extract) and TN-EDIT-AUX-5 (single Qt list model) land. Quick-open package split (TN-EDIT-AUX-4) already meets the bar and should not be regressed.
