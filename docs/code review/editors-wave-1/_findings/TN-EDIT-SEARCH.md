# TN-EDIT-SEARCH — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-SEARCH
**Date:** 2026-06-17
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`
**Scope:** `app/editors/search_panel.py` (233 LOC), `app/editors/find_replace_bar.py` (286 LOC), `app/editors/code_editor_search.py` (192 LOC), `app/shell/search_sidebar_widget.py` (669 LOC), `app/shell/diagnostics_search_coordinator.py` (130 LOC), `app/shell/find_replace_workflow.py` (153 LOC). Cross-read: `app/project/file_inventory.py` (`iter_text_file_paths`), `app/project/file_excludes.py` (`merge_search_exclude_globs`, `effective_excludes_for`), `app/shell/project_load_surface.py`, `app/shell/project_rescan_workflow.py`, `app/shell/shell_composition.py`, `tests/unit/editors/test_search_panel.py`, `tests/unit/project/test_inventory_parity.py`. Gates: R4 inventory SSOT, ARCHITECTURE.md §7 bounded regex, §17.1 cooperative-cancel search, four-theme UI.

---

## Executive verdict

**Not thermo-clean — R4 migration landed in `search_panel`, but search semantics fork across three layers and replace/cancel contracts leak.** `find_in_files` correctly routes through `iter_text_file_paths` with `merge_search_exclude_globs`, and shell load/rescan pushes `effective_excludes_for` into the sidebar — the right direction for Project SSOT Wave 1. Dominant risks are **(1) project replace-all ignores the capped match list and rewrites whole files**, **(2) inline vs project search duplicate `FindOptions`/`SearchOptions` and twin `_compile_pattern` implementations**, **(3) async sidebar results apply without query/generation guard so stale trees can paint after rapid re-query**, plus dead `SearchResultsCoordinator`, missing shutdown cancel for the live `SearchWorker`, and a second include/exclude glob plane that bypasses inventory matchers. Would **REJECT** further search-surface growth until pattern/options SSOT, replace scope, and result-generation gating are collapsed.

---

### TN-EDIT-SEARCH-1 — `search_panel` uses R4 `iter_text_file_paths`; inventory walk is SSOT-compliant

- **Persona:** TN-EDIT-SEARCH
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/search_panel.py:14,106-109` — `from app.project.file_inventory import iter_text_file_paths` and `for file_path, rel_path in iter_text_file_paths(root, exclude_patterns=effective.as_list())`. `app/project/file_inventory.py:224-244` — text search forces `PATTERN_MODE_RELATIVE_PATH`. `tests/unit/editors/test_search_panel.py:30-36` — cbcs prune regression; `tests/unit/project/test_inventory_parity.py:81-103` — glob/pattern parity test.
- **Code-judo alternative:** Keep this call site as the canonical R4 consumer; do not reintroduce `os.walk` or local skip-dir sets in editors or shell.
- **Suggested remediation:** None required for walk SSOT; reference this module in R4 completion checklist as the verified text-search consumer.
- **Tests that would prove fix:** Existing `test_find_in_files_ignores_cbcs_metadata_directory` and `test_search_glob_equivalent_to_exclude_pattern` remain green after refactors.
- **Handoff overlap:** R4

---

### TN-EDIT-SEARCH-2 — Second exclude/include plane (`exclude_globs` / `include_globs`) bypasses inventory matchers

- **Persona:** TN-EDIT-SEARCH
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/search_panel.py:60-80,114-115` — `_matches_glob_list` / `_should_include_file` apply UI globs **after** `iter_text_file_paths`, matching both full relative path and basename via `fnmatch`. `app/editors/search_panel.py:103-104` — project excludes merge via `merge_search_exclude_globs` at walk time; session globs are orthogonal. `app/shell/search_sidebar_widget.py:398-410,490-498` — sidebar exposes separate include/exclude filter fields. Contrast `app/project/file_excludes.py:168-187` — `should_exclude_relative_path` segment-aware semantics differ from basename-only fallback in `_matches_glob_list`.
- **Code-judo alternative:** Fold UI filters into `EffectiveExcludes` (or `SearchInventoryPolicy`) before walk; delete `_should_include_file` post-filter. Include globs become positive allow-list on inventory extension set, not a second fnmatch pass per file.
- **Suggested remediation:** Hard cutover: sidebar filter fields write into merged exclude/include lists consumed only by `iter_text_file_paths`; one matcher owns pruning. If session filters stay intentional, document and add parity tests against `should_exclude_relative_path` for nested paths.
- **Tests that would prove fix:** `exclude_patterns=["build"]` ≡ sidebar `exclude_globs=["build/**"]` for nested `build/out.py`; `include_globs=["*.py"]` does not walk `.txt` files (walk short-circuit, not post-filter).
- **Handoff overlap:** R4, CC-PROJ-01

---

### TN-EDIT-SEARCH-3 — `replace_in_files` replaces every match in a file, not the capped result set

- **Persona:** TN-EDIT-SEARCH
- **Severity:** BLOCKER
- **Evidence:** `app/editors/search_panel.py:155-167` — groups `matches` by `absolute_path` but applies `pattern.sub(replacement, content)` to **entire file content**. `app/shell/search_sidebar_widget.py:551-554,648-668` — sidebar caps collection at `max_results=500` then calls `replace_in_files(self._last_matches, ...)`. A file with 50 occurrences where only 3 appear in `_last_matches` still gets all 50 replaced. Count uses `pattern.finditer(content)` on pre-replace content, not scoped replacements.
- **Code-judo alternative:** Replace only at `(line_number, column, match_length)` tuples from `SearchMatch`, bottom-up per file; or re-scan with `max_replacements=len(file_matches)` per file. Project replace-all must mean “replace what search showed,” not “rewrite file globally.”
- **Suggested remediation:** Implement line/column-scoped replace using stored match spans; reject replace-all when result set was truncated (surface “results capped” in UI). Align count with actual edits.
- **Tests that would prove fix:** File with 10 `needle` lines, `max_results=3` → replace-all changes exactly 3 occurrences; multi-match line replaces only listed columns.
- **Handoff overlap:** R4, none

---

### TN-EDIT-SEARCH-4 — Forked `FindOptions` / `SearchOptions` and duplicate regex compilers

- **Persona:** TN-EDIT-SEARCH
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/find_replace_bar.py:22-28` — `FindOptions(case_sensitive, whole_word, regex)`. `app/editors/search_panel.py:29-37` — `SearchOptions` duplicates the same three toggles plus globs. `app/editors/search_panel.py:45-57` — `_compile_pattern`. `app/editors/code_editor_search.py:179-192` — `_compile_search_pattern` is byte-for-byte equivalent for the shared fields. `app/shell/find_replace_workflow.py:73-119` — inline bar uses `FindOptions`; sidebar uses `SearchOptions` (`search_sidebar_widget.py:490-498`).
- **Code-judo alternative:** One `SearchPatternOptions` (or shared `MatchOptions`) in `search_panel.py` imported by bar mixin and sidebar; single `compile_search_pattern(options, query) -> Pattern | None` owns case/whole-word/regex/length bounds per ARCHITECTURE.md §7.
- **Suggested remediation:** Delete `FindOptions`; alias or extend unified options type; route `FindReplaceBar.find_options()` through shared compiler. Hard cutover — no parallel option structs.
- **Tests that would prove fix:** Parametrized compiler test covers both `find_in_files` and `highlight_all_matches` with identical match counts on fixture buffer; `rg "_compile_search_pattern|_compile_pattern"` collapses to one function.
- **Handoff overlap:** R4

---

### TN-EDIT-SEARCH-5 — Bounded regex budgets exist but are duplicated and incomplete on the editor path

- **Persona:** TN-EDIT-SEARCH
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/search_panel.py:41-42,47-48,122-123` — `MAX_REGEX_QUERY_CHARS = 512`, `MAX_SEARCH_LINE_CHARS = 20_000`; overlong regex returns `None`; long lines skipped during scan. `app/editors/code_editor_search.py:12-13,50-53,182-183` — `MAX_EDITOR_REGEX_QUERY_CHARS = 512`, `MAX_EDITOR_SEARCH_TEXT_CHARS = 1_000_000`; skips regex only when buffer > 1M chars — non-regex `finditer` on megabyte buffers still runs on UI thread. `docs/ARCHITECTURE.md:213-216` — documents bounded budgets for find-in-files **and** editor-local regex; no shared constants module. `docs/DISCOVERY.md` — no numeric canon (constants live only in code).
- **Code-judo alternative:** `app/editors/search_limits.py` (or `app/project/search_policy.py`) exports shared caps; editor path applies line-chunk or refuse-large-buffer policy for all modes; document values in ARCHITECTURE §17.1.
- **Suggested remediation:** Unify constants; extend editor mixin to refuse or chunk-scan buffers over budget for literal search too; add parity test that 513-char regex is rejected in both paths.
- **Tests that would prove fix:** `test_find_in_files_rejects_overlong_regex_query` plus editor equivalent; 2MB literal query does not block UI thread (skip or incremental scan).
- **Handoff overlap:** R4

---

### TN-EDIT-SEARCH-6 — Sidebar async results lack generation guard; `_pending_query` is written never read

- **Persona:** TN-EDIT-SEARCH
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/search_sidebar_widget.py:562-565,570-573` — worker callback sets `_pending_results` and `_pending_query`, emits `_apply_results_requested`; `_apply_search_results` applies `_pending_results` with **no** query or generation check. `app/shell/search_sidebar_widget.py:533-535` — new search cancels prior worker but a worker that finished just before cancel can still queue a stale apply on the main thread after a newer query started. `app/editors/search_panel.py:221` — worker suppresses `on_results` when cancelled, but cannot prevent already-queued Qt slot ordering.
- **Code-judo alternative:** Monotonic `search_generation` incremented in `_run_search`; worker captures generation at start; `_apply_search_results` drops stale generation; mirror AD-018 revision-gating pattern used for intelligence paint.
- **Suggested remediation:** Add generation token to `SearchWorker` callback envelope; ignore applies when `generation != self._search_generation`. Read `_pending_query` against current input before tree rebuild.
- **Tests that would prove fix:** Rapid double-query test: second query’s summary label wins; tree never shows first query files after second query text committed.
- **Handoff overlap:** AD-018, R4

---

### TN-EDIT-SEARCH-7 — `SearchResultsCoordinator` is dead code bundled with diagnostics orchestrator

- **Persona:** TN-EDIT-SEARCH
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/diagnostics_search_coordinator.py:117-130` — `SearchResultsCoordinator` is a one-line main-thread dispatch wrapper. `rg SearchResultsCoordinator app/` — **no production wiring** (only `tests/unit/shell/test_diagnostics_search_coordinator.py`). `app/shell/main_window_composition.py:44,431` — imports/wires `DiagnosticsOrchestrator` only. Live search path: `SearchSidebarWidget._run_search` → `SearchWorker` (`search_sidebar_widget.py:533-560`). Shell Wave 1 CC-17 ghost MainWindow pipeline removed at this baseline; coordinator remnant persists.
- **Code-judo alternative:** Hard cutover delete `SearchResultsCoordinator` and its tests; keep `DiagnosticsOrchestrator` in this file or rename module to `diagnostics_orchestrator.py`. Search async ownership stays entirely in sidebar + `search_panel.SearchWorker`.
- **Suggested remediation:** Delete class; if thread-marshal helper is needed, inline `dispatch_to_main_thread` at the single live callback site (sidebar already uses Qt signal for apply).
- **Tests that would prove fix:** `rg SearchResultsCoordinator` empty in `app/`; diagnostics coordinator tests cover lint/probe only.
- **Handoff overlap:** none

---

### TN-EDIT-SEARCH-8 — Shutdown omits sidebar `SearchWorker` cancel; daemon thread can callback during teardown

- **Persona:** TN-EDIT-SEARCH
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_lifecycle.py:45-77` — `begin_shutdown_teardown` stops timers, cancels background tasks and intelligence, but **no** `search_sidebar` / `SearchWorker.cancel()`. `app/shell/search_sidebar_widget.py:269,203-204,533-535` — sidebar owns `_active_worker`; cancel only on re-query. `app/editors/search_panel.py:200-201` — worker threads are `daemon=True`; `on_results`/`on_done` can still fire into Qt widgets mid-teardown.
- **Code-judo alternative:** `SearchSidebarWidget.cancel_active_search()` called from `MainWindowLifecycle.begin_shutdown_teardown`; widget sets shutdown flag so `_apply_search_results` no-ops when `window._is_shutting_down`.
- **Suggested remediation:** Add explicit cancel hook on lifecycle; guard apply slot with shutdown flag.
- **Tests that would prove fix:** Start search, trigger teardown, assert no tree mutation after shutdown flag; worker `on_results` not invoked when cancel precedes completion (extend `test_search_worker_cancel_prevents_results_callback` pattern to widget).
- **Handoff overlap:** R4

---

### TN-EDIT-SEARCH-9 — `SearchSidebarWidget` hardcodes light-theme delegate colors before token push

- **Persona:** TN-EDIT-SEARCH
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/search_sidebar_widget.py:52-55` — `SearchResultDelegate` defaults `match_bg="#FFE066"`, `text_primary="#212529"`, `text_muted="#6C757D"`, `badge_bg="#E9ECEF"`. `app/shell/search_sidebar_widget.py:456-470` — `apply_theme_tokens` updates delegate when theme runs (`shell_composition.py:487-489`). Widgets constructed or tested before first theme pass render with light literals; HC modes depend entirely on later token push (reconfirms TN-SHELL-MW-10-7).
- **Code-judo alternative:** Require tokens at construction via host callback, or read `ShellThemeTokens` defaults from `theme_tokens.py` instead of duplicating hex literals in widget.
- **Suggested remediation:** R3 sidebar polish; extend `test_apply_theme_tokens` to assert delegate fields match tokens immediately after construction path used by `main_window_panels.py`.
- **Tests that would prove fix:** Four-theme manual acceptance on search result tree (match highlight, badge, selected row); unit test fails if delegate defaults diverge from `ShellThemeTokens` light preset.
- **Handoff overlap:** none

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| R4 `iter_text_file_paths` SSOT | **Met** in `find_in_files`; exclude merge via `merge_search_exclude_globs` + shell `effective_excludes_for` |
| Exclude parity (tree vs search) | **Improved** — search uses relative-path mode; tree/poll name-mode drift is out of slice but affects same `exclude_patterns` list pushed to sidebar |
| Bounded regex (ARCHITECTURE §7) | **Partial** — project search bounded; editor duplicates constants; megabyte literal scan unbounded |
| Cooperative cancel (§17.1) | **Partial** — `cancel_event` in walk/line loop; missing shutdown cancel and stale-result guard |
| Shell/editor duplication | **Open** — twin option types, twin compilers, 669 LOC sidebar UI vs thin `FindReplaceWorkflow` |
| Hard-cutover bias | **Violated** — dead `SearchResultsCoordinator`; file-wide `replace_in_files` vs capped UI results |

**Approval bar:** **REJECT.** Do not extend search filters, replace UX, or sidebar rendering until TN-EDIT-SEARCH-3 (replace scope), TN-EDIT-SEARCH-4 (stale async guard), and TN-EDIT-SEARCH-5 (options/compiler SSOT) land. R4 walk migration (TN-EDIT-SEARCH-1) is necessary but not sufficient for thermo-clean.
