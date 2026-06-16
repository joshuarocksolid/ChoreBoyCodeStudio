# TN-INT-06 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-06  
**Date:** 2026-06-16  
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`  
**Scope:** `app/intelligence/outline_service.py` (510 LOC). Cross-read: `app/shell/editor_tab_workflow.py` (outline refresh seam), `app/shell/semantic_navigation_workflow.py` (Go to Symbol cache miss path), `app/shell/main_window_composition.py` (300 ms debounce timer), `tests/unit/intelligence/test_outline_service.py`. Duplication context: `app/intelligence/symbol_index.py`, `app/intelligence/completion_providers.py`, `app/intelligence/diagnostics_service.py`.

---

## Executive verdict

**Not thermo-clean.** The slice correctly places parsing in `app/intelligence/` and uses tree-sitter for the headline value (partial trees during mid-edit syntax errors), but it ships **two full extractors** (tree-sitter ~340 LOC + AST ~60 LOC) whose outputs diverge on properties, decorators, fields, detail strings, and nested scopes. That dual path sits beside **three other independent AST walks** in the intelligence package with no shared structure module. Worse, the shell applies outline results **synchronously on the UI thread** with only a 300 ms debounce and **no AD-018 buffer-revision gate**, while semantic navigation already revision-gates other async editor results. Dominant risk: **extractor sprawl + UI-thread parse jank + stale outline application** that will compound as more features consume `OutlineSymbol` or reuse the same tree walks.

---

### TN-INT-06-1 — Tree-sitter and AST paths are parallel implementations with large semantic drift

- **Persona:** TN-INT-06
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/outline_service.py:59-62` — primary path returns tree-sitter result; fallback calls `_build_outline_with_ast`. Tree-sitter path: property/setter merge (`163-181`), decorator handling (`288-351`), class fields (`354-383`), function detail (`408-418`), nested body walk (`273-275`). AST path: `_ast_symbol_for_node` (`462-510`) handles only bare `ClassDef`, `FunctionDef`/`AsyncFunctionDef`, and module-level `Assign` constants; functions always get `children=()`, no `@property`/`staticmethod`/`classmethod`, no class fields, no `detail`, no nested inner functions.
- **Code-judo alternative:** One extractor contract: tree-sitter is the sole producer of `OutlineSymbol` trees in production; AST fallback either (a) delegates to a **shared** `python_structure` module that both outline and tests use, with an explicit `OutlineTier.DEGRADED_AST` flag, or (b) is deleted and headless tests stub/mount tree-sitter like runtime parity tests do. Do not maintain two divergent hierarchies.
- **Suggested remediation:** Document and test a parity matrix; narrow AST fallback to "best-effort flat class/function list" with UI badge, or invest in one AST walker that mirrors tree-sitter kinds via shared classification helpers.
- **Tests that would prove fix:** Parametrized fixture run through both tiers asserting identical `qualified_name`/`kind` sets where parity is promised; property/field/decorator cases fail loudly on AST until implemented or explicitly excluded.
- **Handoff overlap:** AD-016, none

---

### TN-INT-06-2 — Third fork of Python symbol/structure extraction beside symbol_index and completion_providers

- **Persona:** TN-INT-06
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/outline_service.py:140-383` — bespoke tree-sitter child walk. `app/intelligence/outline_service.py:462-510` — bespoke AST stmt walk. Contrast `app/intelligence/symbol_index.py:171-188` — `ast.walk` for flat defs. `app/intelligence/completion_providers.py:268-288` and `350-372` — separate `_collect_symbols_from_ast` / `_collect_top_level_symbols_from_ast` including imports/assignments. `app/intelligence/diagnostics_service.py:149` and `import_diagnostics.py:42` — additional `ast.parse` + `ast.walk` passes. TN-INT-04-6 already flagged symbol_index vs completion_providers duplication; outline adds a **hierarchical third model** (`OutlineSymbol`) with its own kind taxonomy.
- **Code-judo alternative:** `app/intelligence/python_structure.py` (or extend R4 inventory): one parse entry (`parse_python_source` → tree-sitter or AST with tier metadata), shared node classifiers, projections `to_outline_tree()`, `to_flat_symbols()`, `to_completion_names()`. Outline service becomes ~80 LOC of projection + public API.
- **Suggested remediation:** Extract shared class/function/assignment recognition; outline imports classifiers instead of re-walking raw nodes; symbol_index flat index becomes `flatten_symbols(extract_outline(...))` or shared flat extractor.
- **Tests that would prove fix:** Single parametrized AST/tree-sitter fixture module consumed by outline, symbol_index, and completion provider tests; kind/name sets stay consistent across projections.
- **Handoff overlap:** R4, none

---

### TN-INT-06-3 — Outline refresh blocks the UI thread with synchronous tree-sitter parse

- **Persona:** TN-INT-06
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_workflow.py:253-255` — `build_outline_from_source(source or "")` called directly inside `refresh_outline_for_active_tab`, invoked from `main_window_composition.py:416` timer timeout and immediately on tab switch (`436-437`). `app/intelligence/outline_service.py:111-137` — each call initializes runtime, builds parser, encodes source, parses full buffer. Contrast `app/intelligence/symbol_index.py:79-107` — project symbol extraction runs on `SymbolIndexWorker` background thread.
- **Code-judo alternative:** Outline parse as a keyed background task (AD-017 scheduler or lightweight `BackgroundTaskScheduler` job `"outline:{path}"`) returning `(revision, symbols)`; panel updates only when revision matches. Keeps tree-sitter on worker thread; UI applies immutable result.
- **Suggested remediation:** Mirror realtime lint pattern: capture revision at schedule time, parse off-thread, apply on main thread only if revision unchanged.
- **Tests that would prove fix:** Integration test with large synthetic module: outline job does not run on main thread (or measurable UI stall below budget); tab switch during in-flight parse drops stale result.
- **Handoff overlap:** AD-016, AD-018

---

### TN-INT-06-4 — No AD-018 buffer revision gate before mutating outline UI state

- **Persona:** TN-INT-06
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_workflow.py:234-258` — debounced refresh reads buffer, parses, writes `outline_symbols_by_path`, calls `outline_panel.set_outline` with no `buffer_revision` check. `app/shell/main_window_composition.py:288-290` — 300 ms single-shot timer. Contrast `app/shell/semantic_navigation_workflow.py:39-63` — `_is_stale_buffer_result` gates semantic callbacks on revision; `docs/ARCHITECTURE.md` AD-018 / §17.4.7 — async editor results must verify current revision before UI mutation.
- **Code-judo alternative:** `refresh_outline_for_active_tab` captures `requested_revision = buffer_revision(file_path)` before scheduling; parse callback applies only if `buffer_revision(file_path) == requested_revision`. Tab switch stops timer and bumps revision — stale timer fires become no-ops.
- **Suggested remediation:** Add revision capture to timer start (`377`) and tab refresh (`437`); skip `set_outline` when stale (optionally show "updating…" tier metadata).
- **Tests that would prove fix:** Unit/integration: edit → wait partial debounce → switch tab → assert prior tab outline does not overwrite new tab panel; rapid typing does not flash superseded tree.
- **Handoff overlap:** AD-018

---

### TN-INT-06-5 — Silent parser-tier degradation violates acceleration-not-truth contract

- **Persona:** TN-INT-06
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/outline_service.py:48-62` — `build_outline_from_source` returns bare `tuple[OutlineSymbol, ...]` with no tier metadata when tree-sitter unavailable (`114-115`, `122-123`, `133-135`) or AST fallback used. Tree-sitter partial parse on syntax error (`test_syntax_error_partial_parse_returns_what_we_can`) vs AST fallback returning `()` on `SyntaxError` (`449-453`, `test_ast_fallback_returns_empty_for_syntax_error`) — opposite behavior, indistinguishable to consumers. Architecture gate #12: "SQLite/tree-sitter/index = acceleration, not semantic truth" — consumers need explicit degradation signals.
- **Code-judo alternative:** Return `OutlineResult(symbols, tier="treesitter" | "ast" | "empty", reason=...)` or attach `OutlineTierMetadata` parallel to completion/diagnostics degradation fields; panel shows subtle "outline limited" when tier != tree-sitter.
- **Suggested remediation:** Extend public API with frozen result type; shell panel reads tier for empty-vs-degraded vs partial messaging.
- **Tests that would prove fix:** Forced tree-sitter unavailable → result includes `tier="ast"`; broken source → tree-sitter tier partial vs AST tier empty encoded explicitly.
- **Handoff overlap:** AD-016, AD-007

---

### TN-INT-06-6 — Duplicate parse orchestration between outline refresh and Go to Symbol cache miss

- **Persona:** TN-INT-06
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_workflow.py:253-254` — parse on every debounced edit, cache in `_outline_symbols_by_path`. `app/shell/semantic_navigation_workflow.py:365-370` — on cache miss, reads same editor buffer and calls `build_outline_from_source` again, then `set_outline_symbols_for_path`. Two shell entry points own "get symbols for active file" with no shared coordinator; Ctrl+R can re-parse immediately after timer already scheduled/parsed.
- **Code-judo alternative:** Single `OutlineCache` service (intelligence or shell workflow): `get_or_compute(path, source, revision) -> OutlineResult` with in-flight dedupe; editor refresh and Go to Symbol both call it.
- **Suggested remediation:** Extract cache + revision from MainWindow dict into workflow helper; semantic navigation never parses directly — always requests through cache.
- **Tests that would prove fix:** Spy test: open file, edit, trigger Go to Symbol before debounce fires → at most one parse per revision; cache hit returns same tuple object.
- **Handoff overlap:** none

---

### TN-INT-06-7 — `initialize_tree_sitter_runtime()` on every outline build adds hot-path overhead

- **Persona:** TN-INT-06
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/outline_service.py:113` — `_build_outline_with_treesitter` calls `initialize_tree_sitter_runtime()` on every invocation before `runtime_status()`. Debounced outline refresh (`300 ms`) means this runs repeatedly during active typing, not just once at app boot (unlike syntax highlighting init paths that typically gate on first use elsewhere).
- **Code-judo alternative:** Module-level `_OUTLINE_RUNTIME_READY` latch set once after successful init; or rely on loader idempotence but skip redundant registry/parser allocation via cached `Parser` per language on the service module.
- **Suggested remediation:** Cache parser instance on first successful init; document thread-safety if moving parse off UI thread (TN-INT-06-3).
- **Tests that would prove fix:** Mock counting: N outline builds → one `initialize_tree_sitter_runtime` call; parse still succeeds.
- **Handoff overlap:** none

---

### TN-INT-06-8 — Weak shell typing at outline cache boundary (`list[object]`)

- **Persona:** TN-INT-06
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/semantic_navigation_workflow.py:99-103` — host protocol declares `outline_symbols_for_path(...) -> list[object] | None` and `set_outline_symbols_for_path(..., symbols: list[object])`. Actual storage: `dict[str, tuple[OutlineSymbol, ...]]` (`main_window_composition.py:287`, `editor_tab_workflow.py:44`). Type erasure hides the canonical contract and blocks static checks on `flatten_symbols(symbols)`.
- **Code-judo alternative:** Import `OutlineSymbol` in host protocol; use `tuple[OutlineSymbol, ...] | None` consistently across editor_tab_workflow, semantic_navigation_workflow, and MainWindow storage.
- **Suggested remediation:** Align protocol types with intelligence export; pyright on shell workflows should see outline cache as typed.
- **Tests that would prove fix:** Pyright clean on `semantic_navigation_workflow.py` without casts at `flatten_symbols` call site.
- **Handoff overlap:** none

---

### TN-INT-06-9 — Tree-sitter walk is untyped (`Any`) with no shared node utilities

- **Persona:** TN-INT-06
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/outline_service.py:125-142` — `parser: Any`, `module_node: Any`, `_symbol_for_node(node: Any, ...)`, `_node_text(node: Any, ...)`. Parser API compatibility branch (`126-129`) duplicated concern. No reuse from `app/treesitter/capture_pipeline.py` or highlight layer for `child_by_field_name`, text extraction, or node type constants.
- **Code-judo alternative:** Thin typed wrapper (`TreeSitterNode` protocol or shared `app/treesitter/node_utils.py`) for text, line range, field access; outline and capture pipeline share it — deletes `_node_text` / point-to-line duplication across intelligence and editor.
- **Suggested remediation:** Extract node text + 1-based line helpers to treesitter package; outline imports them; reduce `Any` surface to parser handle only.
- **Tests that would prove fix:** Unit tests on shared node_utils; outline tests unchanged behavior.
- **Handoff overlap:** none

---

### TN-INT-06-10 — Python extension gating triplicated across shell and service

- **Persona:** TN-INT-06
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_tab_workflow.py:243-247` — `{".py", ".pyw", ".pyi"}` check before parse. `app/shell/semantic_navigation_workflow.py:362-364` — identical set. `app/intelligence/outline_service.py:73-74` — same suffix set in `build_file_outline`. `build_outline_from_source` also gates `language != "python"` (`54-55`) while shell already filtered by extension.
- **Code-judo alternative:** One `is_python_source_path(path) -> bool` in `app/project/file_inventory.py` (R4 SSOT) or `outline_service.is_supported_path`; shell calls that instead of inline sets.
- **Suggested remediation:** Replace three literal sets with shared helper; optional: `build_outline_for_path(path, source)` that centralizes extension + read logic.
- **Tests that would prove fix:** Single test on helper; shell tests use `.pyw`/`.pyi` cases without duplicating suffix literals.
- **Handoff overlap:** R4

---

### TN-INT-06-11 — Tests validate rich tree-sitter behavior but not cross-tier parity or revision safety

- **Persona:** TN-INT-06
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/intelligence/test_outline_service.py` — 22 tests cover properties, setters, fields, partial parse (`171-181`), AST fallback only when monkeypatched unavailable (`268-305`). No shell test for debounce + revision stale apply; no test that Go to Symbol reuses cache; no contract test linking outline kinds to `symbol_index`/`completion_providers` name sets for the same fixture file.
- **Code-judo alternative:** One golden-file fixture (`outline_fixtures.py`) driving outline, flat symbol projection, and (future) shared extractor tests; one editor_tab_workflow test with fake timer proving revision gate.
- **Suggested remediation:** After TN-INT-06-3/4 fixes, add integration tests for stale outline suppression; add shared-fixture smoke test when python_structure module lands.
- **Tests that would prove fix:** As above — revision stale test fails before fix, passes after; shared fixture test catches extractor drift.
- **Handoff overlap:** AD-018, none

---

### TN-INT-06-12 — `OutlineKind = str` invites unbounded kind strings across panel and icons

- **Persona:** TN-INT-06
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/outline_service.py:24` — `OutlineKind = str  # one of: class, function, ...`. Kind strings assigned in multiple builders (`265-269`, `369`, `476-487`) with no exhaustiveness check; shell outline icons/map (`app/shell/outline/`) must stay in sync manually.
- **Code-judo alternative:** `enum.Enum` or `Literal[...]` alias for kinds; `match`/`if` chains in panel use exhaustive default with `assert_never`; pyright flags new kind without icon mapping.
- **Suggested remediation:** Replace str alias with frozen enum in outline_service; update panel icon lookup to enum keys.
- **Tests that would prove fix:** Pyright exhaustiveness on kind→icon map; adding `"protocol"` kind without panel update fails typecheck.
- **Handoff overlap:** none
