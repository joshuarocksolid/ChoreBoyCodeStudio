# TN-PROJ-REWRITE — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-PROJ-REWRITE  
**Date:** 2026-06-16  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/project/import_rewrite.py` (88 LOC), `app/project/import_layout.py` (318 LOC), `app/shell/project_tree_controller.py` (rename/move rewrite seam), `app/intelligence/code_actions.py` (source-root quick fix / layout overlap). Cross-read tests: `tests/unit/intelligence/test_import_rewrite.py`, `tests/unit/project/test_import_layout.py`, `tests/integration/project/test_tree_file_operations_integration.py`, `tests/unit/intelligence/test_code_actions.py`. Prior wave: TN-INT-07-5/6 (CC-22), TN-INT-05-12. Architecture gates: 1, 3, 4, 10.

---

## Executive verdict

**Hard cutover on package placement is done; module-identity SSOT is not.** `import_rewrite` correctly lives in `app/project/`, routes its scan through `iter_python_files` (cbcs skip parity), and delegates batch writes to `atomic_write_batch` — resolving TN-INT-07-5 and partially TN-INT-07-4. `project_tree_controller` is a clean shell seam with no intelligence imports for rewrite. Dominant remaining risks: **(1) move/rename rewrite computes module names with a private path→dotted helper that ignores `ProjectImportLayout` source-root stripping**, so `src/`-layout projects rewrite the wrong symbol (`src.pkg.mod` vs `pkg.mod`) — a file-set / import-identity disagreement with diagnostics, completion, and inventory snapshot naming; **(2) three parallel path→module implementations** (`import_rewrite`, `import_layout`, `completion_providers` fallback); **(3) source-root suggestion and quick-fix apply are split across `import_layout`, `code_actions`, and `python_style_workflow`** with no single contract. Secondary debt: layout helpers bypass inventory via `iterdir`/`glob`, reserved-name policy is a third plane beside `file_inventory`/`file_excludes`, rewrite scans ignore user exclude patterns, and tests still live under `tests/unit/intelligence/` for a project-layer module. Would approve the relocation; would **not** approve further rewrite or PY200 quick-fix growth until module naming routes through `import_layout` and `add_source_root` has one plan/apply owner.

---

### TN-PROJ-REWRITE-1 — Move/rename rewrite ignores source-root stripping; breaks `src/` layouts

- **Persona:** TN-PROJ-REWRITE
- **Severity:** BLOCKER
- **Evidence:** `app/project/import_rewrite.py:34-35,62-72` — `_module_name_from_relative_path("src/my_pkg/foo.py")` → `"src.my_pkg.foo"`. `app/project/import_layout.py:212-238` — `module_name_from_relative_path(layout, ...)` strips configured/auto-detected source-root prefix → `"my_pkg.foo"`. `tests/unit/project/test_import_layout.py:20-32` — `src/` layout resolves `import my_pkg.util`. `tests/unit/intelligence/test_import_rewrite.py:16-35` — only flat `app/` layout; no `src/` case.
- **Code-judo alternative:** Delete `_module_name_from_relative_path` from `import_rewrite`. Accept `ProjectImportLayout` (or load via `resolve_project_import_layout`) and call `module_name_from_relative_path(layout, old_relative)` / `new_relative` for old/new module symbols. One naming contract for rewrite, diagnostics, snapshot, and completion.
- **Suggested remediation:** Thread layout into `plan_import_rewrites(project_root, old_relative, new_relative, *, metadata=None)`; resolve layout once at plan time; add parametrized tests for manifest-configured and auto-detected `src/` roots.
- **Tests that would prove fix:** Move `src/my_pkg/module.py` → `src/my_pkg/renamed.py` with consumer `from my_pkg.module import x`; assert rewrite updates to `my_pkg.renamed`. Regression: flat `pkg/module.py` case stays green.
- **Handoff overlap:** R4, CC-22

---

### TN-PROJ-REWRITE-2 — Triplicate path→module helpers; rewrite and completion bypass layout SSOT

- **Persona:** TN-PROJ-REWRITE
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/import_rewrite.py:62-72` — standalone `_module_name_from_relative_path`. `app/intelligence/completion_providers.py:408-428` — `_module_name_from_path` tries `module_name_for_file` then falls back to duplicate `_module_name_from_relative_path`. `app/project/file_inventory.py:275-294` — `_module_name_from_python_path` duplicates the same fallback chain. `app/project/import_layout.py:202-238` — canonical `module_name_for_file` / `module_name_from_relative_path`.
- **Code-judo alternative:** One exported helper in `import_layout` (e.g. `module_name_from_relative_path_for_root(project_root, relative, metadata=None)`) used by rewrite, inventory snapshot, and completion. Delete private copies; completion fallback becomes unreachable when layout always resolves.
- **Suggested remediation:** Extract shared helper; hard-cutover the three call sites in one PR; grep gate: no `_module_name_from_relative_path` outside `import_layout`.
- **Tests that would prove fix:** Shared parametrized fixture in `test_import_layout.py` consumed by rewrite/completion tests; identical module names across all three paths for `src/`, flat, and `__init__` packages.
- **Handoff overlap:** R4, CC-12

---

### TN-PROJ-REWRITE-3 — `add_source_root` quick fix: intelligence plans, shell applies — split contract

- **Persona:** TN-PROJ-REWRITE
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/code_actions.py:246-256` — emits `QuickFix(action_kind="add_source_root", replacement_text=missing_root)`. `:101-113` — `apply_quick_fixes` handles only `remove_line`, `replace_import_module`, `create_module_file`; **`add_source_root` silently dropped** if called directly. `app/shell/python_style_workflow.py:237-240,262-288` — shell partitions fixes and applies source roots via `_apply_source_root_fixes` + `append_project_source_root`. `tests/unit/intelligence/test_code_actions.py` — no `add_source_root` plan or apply coverage.
- **Code-judo alternative:** Move PY200 source-root planning to `app/project/` (e.g. `plan_source_root_fixes`) returning a typed `SourceRootFix` dataclass; shell orchestrates manifest write; **or** inject manifest writer into `apply_quick_fixes` and handle `add_source_root` there — not both. Replace `_extract_unresolved_module_name` message parsing with structured PY200 metadata.
- **Suggested remediation:** Pick one apply owner; document in ARCHITECTURE §import layout; add end-to-end test through `PythonStyleWorkflow` or project-layer apply helper.
- **Tests that would prove fix:** Plan + apply `add_source_root` without routing through shell-only filter; assert manifest `source_roots` updated and PY200 clears after rescan.
- **Handoff overlap:** R5, CC-22, TN-INT-05-12

---

### TN-PROJ-REWRITE-4 — Two source-root suggestion APIs with divergent semantics

- **Persona:** TN-PROJ-REWRITE
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/import_layout.py:298-303` — `detect_suggested_source_root` returns **first configured** root from `resolve_project_import_layout(..., metadata=None)` (auto-detect `src/` when no manifest). `:306-318` — `suggest_missing_source_root` scans top-level dirs via `iterdir()` for dirs where `_module_path_prefix_exists_at_base(child, module_name)` and root not yet configured. `app/shell/source_root_workflow.py:65-84` — first-open prompt uses `detect_suggested_source_root`. `app/intelligence/code_actions.py:246` — PY200 quick fix uses `suggest_missing_source_root`.
- **Code-judo alternative:** Single `SourceRootSuggestion` API: `(reason: Literal["auto_detect","missing_for_module"], relative_path: str) | None` with explicit precedence table. First-open and quick-fix become thin callers; delete duplicate resolution paths.
- **Suggested remediation:** Merge helpers behind one function; update `SourceRootWorkflow` and `_plan_py200_quick_fix` to share it; document when each reason surfaces in product copy.
- **Tests that would prove fix:** Parametrized cases: empty manifest + `src/` tree (auto_detect); manifest `source_roots=[]` + unresolved `my_pkg` under `src/` (missing_for_module); configured root → no suggestion.
- **Handoff overlap:** R4

---

### TN-PROJ-REWRITE-5 — `suggest_missing_source_root` bypasses inventory walk (top-level `iterdir` only)

- **Persona:** TN-PROJ-REWRITE
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/import_layout.py:309-317` — `for child in sorted(layout.project_root.iterdir())`. Gate 1: project traversal should route through `file_inventory`. Nested source roots (e.g. `packages/backend/`) never considered; symlinks/excludes not honored. `_RESERVED_ROOT_NAMES` skips `vendor`/`cbcs` ad hoc instead of inventory cbcs prune + exclude SSOT.
- **Code-judo alternative:** Build candidate roots from `walk_project` top-level directory names (or manifest-normalized entries) filtered by `_is_valid_source_root_candidate`; probe module existence via `module_path_prefix_exists_at_base` only on validated candidates.
- **Suggested remediation:** Replace `iterdir()` loop with inventory-backed top-level dir enumeration; align reserved skips with `constants.PROJECT_META_DIRNAME` and packaging vendor policy explicitly.
- **Tests that would prove fix:** Fixture with excluded top-level dir still skipped; `cbcs/` never suggested; nested non-top-level layout documented or supported.
- **Handoff overlap:** R4, gate 1

---

### TN-PROJ-REWRITE-6 — `resolve_import_at_base` uses ad-hoc `glob("*.py")` for namespace packages

- **Persona:** TN-PROJ-REWRITE
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/import_layout.py:291-294` — `if any(package_dir.glob("*.py"))`. Used by `module_path_prefix_exists_at_base`, `suggest_missing_source_root`, and PY200 create-module target probing (`code_actions.py:290-301`). Not a full-tree walk, but still a `.py` discovery path outside `iter_python_files`.
- **Code-judo alternative:** Replace glob probe with `iter_python_files(base, ...)` early-exit any `.py` directly under `package_dir`, or a dedicated `has_python_modules_in_dir(dir: Path) -> bool` in `file_inventory` that does not enumerate the whole project.
- **Suggested remediation:** Add narrow inventory primitive for single-directory probe; cut over `resolve_import_at_base` namespace branch.
- **Tests that would prove fix:** Namespace package dir with one `.py` resolves; empty dir does not; respects cbcs/vendor if ever probed under those paths.
- **Handoff overlap:** R4, gate 1

---

### TN-PROJ-REWRITE-7 — Reserved-name / exclude policy is a third unowned plane in `import_layout`

- **Persona:** TN-PROJ-REWRITE
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/import_layout.py:13,115-116,312-313` — `_RESERVED_ROOT_NAMES = frozenset({"vendor", "cbcs"})` for source-root validation and suggestion skips. `app/project/file_inventory.py:102-103` — cbcs via `constants.PROJECT_META_DIRNAME`. `app/project/file_excludes.py:18-26` — `DEFAULT_EXCLUDE_PATTERNS` includes `"vendor"` but not `cbcs`. Gate 4: avoid a third plane between `file_excludes`, packaging layout, and import layout.
- **Code-judo alternative:** Import `constants.PROJECT_META_DIRNAME` for cbcs; reference a single `RESERVED_TOP_LEVEL_DIR_NAMES` tuple owned by `file_inventory` or `constants.py` consumed by layout, excludes docs, and packaging. Vendor: explicit product policy — import search base vs exclude vs non-source-root.
- **Suggested remediation:** Centralize reserved top-level names; document vendor triple role (sys.path base, default exclude, non-configurable source root) in ARCHITECTURE.
- **Tests that would prove fix:** Assert layout rejects `cbcs/` and `vendor/` as source roots using same constant as inventory meta dirname; packaging audit skip parity test.
- **Handoff overlap:** R4, gate 3, gate 4

---

### TN-PROJ-REWRITE-8 — Import rewrite scan ignores project exclude patterns

- **Persona:** TN-PROJ-REWRITE
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/import_rewrite.py:41` — `iter_python_files(root)` with default empty `exclude_patterns`. Search and other flows pass effective excludes via `load_effective_exclude_patterns`. User excluding `tests/` or `build/` still gets import rewrites under those trees on move/rename.
- **Code-judo alternative:** Accept optional `exclude_patterns` on `plan_import_rewrites`; shell passes effective excludes from settings when invoking tree rewrite (same as search). Default remains cbcs-only for backward compatibility if product wants rewrite-everywhere; make the choice explicit.
- **Suggested remediation:** Thread excludes from `project_tree_controller.maybe_rewrite_imports_for_move` through to `plan_import_rewrites`; document whether rewrite intentionally ignores excludes or not.
- **Tests that would prove fix:** Project with `tests/` excluded — move under `tests/` either skipped or documented; excluded generated dir not rewritten when policy says skip.
- **Handoff overlap:** R4, gate 4

---

### TN-PROJ-REWRITE-9 — Hard cutover verified: no stale `app/intelligence/import_rewrite` importers

- **Persona:** TN-PROJ-REWRITE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/project_tree_controller.py:8` — `from app.project.import_rewrite import ...`. `rg 'app/intelligence/import_rewrite' app` → no matches; `app/intelligence/import_rewrite.py` absent. `tests/unit/intelligence/test_import_rewrite.py:10` — imports `app.project.import_rewrite`. Resolves CC-22 relocation item from TN-INT-INTEG Wave 3c intent.
- **Code-judo alternative:** Move test module to `tests/unit/project/test_import_rewrite.py` to match ownership; keep integration tree test under `tests/integration/project/`.
- **Suggested remediation:** Relocate test file only (no behavior change); update `test_project_tree_controller.py` mock paths if needed.
- **Tests that would prove fix:** Test discovery unchanged; grep shows zero intelligence-package imports for rewrite.
- **Handoff overlap:** CC-22

---

### TN-PROJ-REWRITE-10 — `atomic_write_batch` adopted in rewrite; `code_actions` still owns bespoke rollback

- **Persona:** TN-PROJ-REWRITE
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/import_rewrite.py:19,56-59` — `atomic_write_batch(writes)`. `app/intelligence/code_actions.py:115-143,373-394` — manual snapshot dict + `_rollback_quick_fix_changes` for line removes and module creation. TN-INT-07-4 triplication partially fixed (rewrite path only).
- **Code-judo alternative:** Route multi-file quick-fix edits through `atomic_write_batch` where all changes are full-file replacements; keep create-module orchestration as a thin wrapper that builds the batch dict including new files.
- **Suggested remediation:** Refactor `apply_quick_fixes` file mutation path to batch writes; retain line-level planning logic.
- **Tests that would prove fix:** Existing rollback tests in `test_code_actions.py` and `test_import_rewrite.py` green against shared primitive.
- **Handoff overlap:** CC-17, R5

---

### TN-PROJ-REWRITE-11 — Regex rewrite contract under-specified; no negative or `src/`-layout matrix

- **Persona:** TN-PROJ-REWRITE
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/import_rewrite.py:75-88` — line regex on `import`/`from` only; no relative imports, aliases, or layout-aware symbols. `tests/unit/intelligence/test_import_rewrite.py:16-35` — happy path flat layout only. `tests/integration/project/test_tree_file_operations_integration.py:15-35` — single consumer rewrite after `move_path`; no shell policy gate, no ASK/NEVER. TN-INT-07-6 carryover still open.
- **Code-judo alternative:** Label strategy explicitly (`ImportRewriteStrategy.REGEX`); expand negative tests; shell confirmation copy says "textual import line update." Layout-aware module names (REWRITE-1) must land before claiming move/rename safety on real projects.
- **Suggested remediation:** Parametrized unit tests: `from .mod`, `import pkg as alias`, comment lines unchanged; integration test for `ImportUpdatePolicy.NEVER` skip.
- **Tests that would prove fix:** Negative cases assert zero previews; `src/` layout move case (after REWRITE-1 fix) in integration shard.
- **Handoff overlap:** AD-016, CC-22

---

### TN-PROJ-REWRITE-12 — `discover_canonical_project_modules` drives typo fixes but rewrite scan does not share layout context

- **Persona:** TN-PROJ-REWRITE
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/code_actions.py:257,304-311` — `_suggest_module_replacement` uses `discover_canonical_project_modules(layout)` (inventory + layout naming). `app/project/import_rewrite.py:32-53` — full-project scan without layout; module identity from raw paths (REWRITE-1). Typo quick-fix and move rewrite can disagree on "canonical module" strings for the same file tree.
- **Code-judo alternative:** `plan_import_rewrites` loads layout once and optionally reuses `discover_canonical_project_modules` to validate old module exists in canonical set before scanning; log/degrade when old symbol not in canonical module list.
- **Suggested remediation:** After REWRITE-1, add assertion in plan: `old_module in discover_canonical_project_modules(layout) or warn in preview`.
- **Tests that would prove fix:** Move file whose canonical import name differs from path-dotted name — plan empty or explicit warning until layout-aware naming fixed.
- **Handoff overlap:** R4, CC-15

---

### TN-PROJ-REWRITE-13 — Thin duplicate alias `_module_path_prefix_exists_at_base` / public export

- **Persona:** TN-PROJ-REWRITE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/project/import_layout.py:267-279` — public `module_path_prefix_exists_at_base` and private `_module_path_prefix_exists_at_base` identical. `app/intelligence/diagnostics_service.py:245` — imports private `_module_path_prefix_exists_at_base` across layer boundary.
- **Code-judo alternative:** Keep one public function; delete alias; fix diagnostics to import public symbol (gate 10: intelligence → project direction only via public API).
- **Suggested remediation:** Remove `_module_path_prefix_exists_at_base`; update diagnostics import.
- **Tests that would prove fix:** Existing `test_import_layout.py` and diagnostics tests green; pyright on diagnostics_service.
- **Handoff overlap:** R5, gate 10

---

### TN-PROJ-REWRITE-14 — `project_tree_controller` rewrite seam is thermo-clean; policy/UI separation holds

- **Persona:** TN-PROJ-REWRITE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/project_tree_controller.py:87-137` — `maybe_rewrite_imports_for_move` delegates plan/apply to project layer; injects `ImportUpdatePolicy`, confirmation, and warning callbacks; no intelligence imports. `tests/unit/shell/test_project_tree_controller.py:176-182` — mocks project-layer functions.
- **Code-judo alternative:** None required — replicate this pattern for future project SSOT callers (pass excludes + metadata into plan when REWRITE-1/8 land).
- **Suggested remediation:** When extending rewrite API, extend controller kwargs only; avoid inlining scan logic in shell workflows.
- **Tests that would prove fix:** Controller unit tests continue to mock project imports only.
- **Handoff overlap:** none

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| CC-22 `import_rewrite` relocation | **Done** — project layer, inventory scan, no intelligence importers (REWRITE-9) |
| TN-INT-07-4 batch apply | **Partial** — rewrite uses `atomic_write_batch`; code_actions rollback bespoke (REWRITE-10) |
| Module naming SSOT | **Open BLOCKER** — rewrite ignores source-root stripping (REWRITE-1, REWRITE-2) |
| Source-root quick fix | **Split brain** — plan in intelligence, apply in shell (REWRITE-3, REWRITE-4) |
| Inventory gate 1 | **Partial** — rewrite scan OK; layout suggestion/probe uses iterdir/glob (REWRITE-5, REWRITE-6) |
| Exclude policy gate 4 | **Open** — reserved names fork + rewrite ignores user excludes (REWRITE-7, REWRITE-8) |
| Test placement / depth | **Gap** — intelligence test dir for project module; no src-layout rewrite tests (REWRITE-9, REWRITE-11) |

**Approval bar:** Approve the CC-22 hard cutover and `project_tree_controller` seam. **Do not approve** further import rewrite or PY200 quick-fix features until REWRITE-1 (layout-aware module names) and REWRITE-3 (single apply owner for source roots) land — those are the highest-leverage code-judo moves preventing the next wave from compounding split module identity and shell/intelligence orchestration debt.
