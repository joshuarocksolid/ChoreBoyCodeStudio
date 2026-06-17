# TN-PROJ-INV — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-PROJ-INV  
**Date:** 2026-06-16  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/project/file_inventory.py`, `app/project/file_excludes.py`, `app/project/project_service.py` (enumeration + entry inference), `app/editors/search_panel.py`. Cross-read: `tests/unit/project/test_file_inventory.py`, `tests/unit/project/test_file_excludes.py`, `tests/unit/project/test_project_service.py`, `tests/unit/editors/test_search_panel.py`. Architecture gates #1–#5.

---

## Executive verdict

**Not thermo-clean.** `walk_project` is a credible SSOT kernel — deterministic `os.walk`, explicit `cbcs/` prune, and sorted yields — and the historical `rglob('*.py')` migration is real. But the **public API encodes three incompatible exclude semantics** (name-mode tree enumeration, relative-path search, packaging `extra_top_level_skips`) without a single policy object, so tree, search, intelligence walks, and packaging can disagree on the same user-configured pattern. Entry inference still **bypasses the inventory** via `iterdir()` and direct path probes, and `build_project_inventory_snapshot` duplicates `import_layout.discover_canonical_project_modules` while re-resolving layout once per file. `ProjectInventorySnapshot` — the R4 module-list contract — has **zero dedicated tests** and no production orchestration in this slice. Dominant risk: **file-set SSOT exists at the walk primitive but not at the composed product surfaces** (tree vs search vs snapshot vs entry inference).

---

### TN-PROJ-INV-1 — Tree enumeration ignores slash patterns; search honors them

- **Persona:** TN-PROJ-INV
- **Severity:** BLOCKER
- **Evidence:** `app/project/file_inventory.py:53-59` — name mode calls `should_exclude_name(name, patterns)` only on the leaf segment. `app/project/file_inventory.py:204-208` — `iter_project_entries` hardcodes `pattern_mode=PATTERN_MODE_NAME`. `app/project/file_inventory.py:174-177` — `iter_text_file_paths` hardcodes `pattern_mode=PATTERN_MODE_RELATIVE_PATH`. `app/project/file_excludes.py:105-108` — `should_exclude_name` skips any pattern containing `/`. Shell passes user settings + manifest patterns into tree enumeration via `compute_effective_excludes` (`app/shell/editor_tab_workflow.py:781-788`, `app/project/project_service.py:83-88`).
- **Code-judo alternative:** One `InventoryPolicy` (or single `pattern_mode` default derived from pattern shape) applied consistently per use case, documented in the type: tree enumeration and search both use relative-path matching when effective excludes can contain `/`, or normalize all stored patterns to name-mode segments at settings parse time so iterators never silently ignore patterns.
- **Suggested remediation:** Either switch `iter_project_entries` to `PATTERN_MODE_RELATIVE_PATH` (with characterization tests for historical name-only patterns) or reject/normalize slash patterns at `load_effective_exclude_patterns` time with an explicit contract. Add parity test: same `exclude_patterns` → same pruned subtree for tree and search.
- **Tests that would prove fix:** Parametrized fixture with `exclude_patterns=["src/generated/*"]`: `enumerate_project_entries` and `find_in_files(..., exclude_patterns=...)` agree that `src/generated/code.py` is absent; regression for bare-name patterns like `"vendor"`.
- **Handoff overlap:** R4, CC-15

---

### TN-PROJ-INV-2 — Three vendor policies; DEFAULT excludes are not walk defaults

- **Persona:** TN-PROJ-INV
- **Severity:** BLOCKER
- **Evidence:** `app/project/file_excludes.py:18-26` — `DEFAULT_EXCLUDE_PATTERNS` includes `"vendor"`. `app/project/file_inventory.py:134-159` — bare `iter_python_files(root)` prunes only `cbcs/`, not vendor. `app/packaging/dependency_audit.py:58` — uses `extra_top_level_skips=("vendor",)` instead of exclude patterns. `app/project/import_rewrite.py:41` — `iter_python_files(root)` with no excludes (vendor scanned). Entry inference (`app/project/project_service.py:393-396`, `460-465`, `469-470`) uses bare `iter_python_files`.
- **Code-judo alternative:** Collapse vendor (and other reserved roots) into one named primitive — e.g. `InventoryScope.INTELLIGENCE` vs `InventoryScope.TREE` vs `InventoryScope.PACKAGING_AUDIT` — each mapping to explicit `(include_meta_dir, exclude_patterns, top_level_skips)` instead of three ad-hoc knobs callers must remember.
- **Suggested remediation:** Document and test the product policy: intelligence/import rewrite omit vendor via a shared scope constant; tree omits vendor only when effective excludes say so; packaging audit uses the same exclude mechanism as intelligence (not a parallel skip list) unless audit truly needs a different file set — then name and test that exception.
- **Tests that would prove fix:** Contract matrix: scope × `{vendor present}` → expected file paths; packaging audit and `iter_python_files(..., scope=INTELLIGENCE)` agree on vendor omission without `extra_top_level_skips`.
- **Handoff overlap:** R4

---

### TN-PROJ-INV-3 — Entry inference bypasses inventory SSOT via `iterdir` and direct path checks

- **Persona:** TN-PROJ-INV
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/project_service.py:375-379` — priority entry names checked with `project_root / name` existence, not inventory. `app/project/project_service.py:381-387` — `project_root.iterdir()` for top-level `.py` discovery, bypassing exclude patterns, symlink policy, and walk ordering. Only later fallbacks call `iter_python_files` (`393-396`, `460-465`). `_infer_default_entry_file` runs during `assess_project_root` / lazy manifest **before** `open_project` applies `compute_effective_excludes` to enumeration (`83-88`).
- **Code-judo alternative:** Single `_first_runnable_entry(project_root) -> str | None` built on `iter_python_files` with a documented entry-selection ordering helper (priority names → sorted top-level from walk → package `__main__` → first nested), so entry inference and “any python file?” share walk semantics.
- **Suggested remediation:** Replace `iterdir` and direct `exists()` probes with filtered inventory iteration; apply the same reserved-root policy as intelligence (vendor/cbcs) for entry candidacy.
- **Tests that would prove fix:** Project with only `vendor/run.py` and no top-level entry: inference must not select vendor path; project with excluded `build/out.py` as only `.py`: inference respects excludes when manifest carries them.
- **Handoff overlap:** R4

---

### TN-PROJ-INV-4 — `ProjectInventorySnapshot` is untested and resolves layout per file

- **Persona:** TN-PROJ-INV
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/file_inventory.py:243-267` — `build_project_inventory_snapshot` walks once, then `_module_name_from_python_path` runs per path. `app/project/file_inventory.py:275-278` — inline import; `resolve_project_import_layout(project_root)` inside per-file helper. `tests/unit/project/test_file_inventory.py` — no tests for snapshot builders (manifest gap: `00-manifest.md` “None | **High**”). `grep` shows production callers in intelligence slice only; no orchestration in this slice.
- **Code-judo alternative:** Resolve layout **once** per snapshot; delegate module-name set to `discover_canonical_project_modules(layout, iter_python_files=partial(...))` and delete parallel fallback logic — one function, one ordering rule (`sorted` module names from canonical layout).
- **Suggested remediation:** Extract `build_module_snapshot(root, *, exclude_patterns, layout=None) -> ProjectInventorySnapshot`; add unit tests for `src/`-layout stripping, `__init__.py` package names, exclude propagation, and deterministic ordering of `python_file_paths` + `module_names`.
- **Tests that would prove fix:** New `test_build_project_inventory_snapshot_*` cases; assert `resolve_project_import_layout` called once (monkeypatch counter); snapshot module names match `discover_canonical_project_modules` for same tree.
- **Handoff overlap:** R4, CC-15

---

### TN-PROJ-INV-5 — Snapshot module fallback can diverge from canonical import layout

- **Persona:** TN-PROJ-INV
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/file_inventory.py:280-294` — when `module_name_for_file` returns `None`, fallback builds dotted names from raw relative paths without `_strip_source_root_prefix` (`app/project/import_layout.py:225-239`). `app/project/import_layout.py:242-256` — `discover_canonical_project_modules` uses layout-only naming with no naive fallback.
- **Code-judo alternative:** Delete the fallback branch; snapshot module list is exactly `discover_canonical_project_modules` output. Files that are not canonically importable are omitted from `module_names`, not aliased to wrong dotted paths.
- **Suggested remediation:** Hard cutover: `_module_name_from_python_path` becomes a thin call to `module_name_for_file`; if `None`, file contributes to `python_file_paths` only when callers need paths, not spurious module names.
- **Tests that would prove fix:** `src/pkg/mod.py` with configured source root → snapshot `module_names` contains `pkg.mod`, not `src.pkg.mod`; non-importable path under `cbcs/` never appears in `module_names`.
- **Handoff overlap:** R4

---

### TN-PROJ-INV-6 — Search panel adds a second exclude plane (`exclude_globs` / `include_globs`)

- **Persona:** TN-PROJ-INV
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/search_panel.py:59-79` — `_matches_glob_list` / `_should_include_file` apply UI globs **after** inventory walk. `app/editors/search_panel.py:72-79` — matches both full relative path and basename, unlike `file_excludes`. Shell sets inventory excludes via `compute_effective_excludes` (`app/shell/shell_composition.py:196-202`), but search options globs are orthogonal (`SearchOptions.exclude_globs`). Tests cover globs (`test_find_in_files_exclude_globs`) but not parity with `file_excludes` semantics.
- **Code-judo alternative:** Search UI globs merge into the same effective exclude list passed to `iter_text_file_paths` (or a single `SearchInventoryPolicy` built by shell), so one matcher (`should_exclude_relative_path`) owns all pruning; UI only edits that list’s source layers (global, project, manifest, session).
- **Suggested remediation:** Document product intent: if session globs are intentional, add parity tests against `should_exclude_relative_path`; if not, remove duplicate glob matching and route UI filters through `file_excludes`.
- **Tests that would prove fix:** `exclude_patterns=["build"]` vs `exclude_globs=["build/**"]` produce identical file sets; nested segment patterns behave same as tree when both use relative-path mode.
- **Handoff overlap:** R4

---

### TN-PROJ-INV-7 — `compute_effective_excludes` orchestration duplicated across shell and project service

- **Persona:** TN-PROJ-INV
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/project_service.py:83-87` — inline import + merge caller excludes with manifest. `app/shell/editor_tab_workflow.py:781-785`, `app/shell/shell_composition.py:196-202`, `app/shell/intelligence_cache_workflow.py:66-68`, `app/shell/project_tree_utils.py:28-36` — same two-layer merge repeated. `load_effective_exclude_patterns` already merges global+project (`file_excludes.py:74-86`) but manifest layer is always re-applied at call sites.
- **Code-judo alternative:** Extend `file_excludes` with `effective_excludes_for_project(settings_service, loaded_project) -> list[str]` (or use `project_tree_utils.effective_excludes_for` everywhere including `open_project`) so every subsystem imports one function; delete inline imports in `project_service.open_project`.
- **Suggested remediation:** Hard cutover callers to `effective_excludes_for`; single test module for merge order: global → project settings → manifest → optional caller override.
- **Tests that would prove fix:** Parametrized merge test shared by project open, search sidebar refresh, and intelligence indexing; no caller manually lists `compute_effective_excludes` twice.
- **Handoff overlap:** R4

---

### TN-PROJ-INV-8 — `pattern_mode` is a caller footgun with no unified default

- **Persona:** TN-PROJ-INV
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/file_inventory.py:35-36` — two mode constants. `iter_python_files` defaults to name mode (`138`); `iter_text_file_paths` forces relative path (`177`); `iter_project_entries` forces name mode (`207`). Docstring (`8-14`) maps modes to historical callers but does not state which mode **effective user excludes** require. Tests demonstrate opt-in relative mode for python iteration (`test_iter_python_files_relative_path_pattern_mode_respects_slashes`) but tree path never uses it (TN-PROJ-INV-1).
- **Code-judo alternative:** Drop dual mode from public iterators; `walk_project` accepts pre-classified pattern lists (`name_patterns`, `path_patterns`) split at settings load, or auto-promote any pattern containing `/` to path matching inside `_matches_excludes` regardless of caller mode flag.
- **Suggested remediation:** Centralize mode selection in `file_excludes.load_effective_exclude_patterns` return type (`EffectiveExcludes` with split lists) so iterators cannot misconfigure.
- **Tests that would prove fix:** Mixed pattern list `["vendor", "src/*.gen.py"]` excludes correctly in tree, search, and snapshot without caller passing `pattern_mode`.
- **Handoff overlap:** R4

---

### TN-PROJ-INV-9 — `cbcs/` include/exclude split is correct but unowned as explicit policy

- **Persona:** TN-PROJ-INV
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/file_inventory.py:74-76`, `102-103` — prune unless `include_meta_dir=True`. `iter_project_entries` sets `include_meta_dir=True` (`209`); python/text iterators omit it (default False). Tests assert split (`test_iter_python_files_skips_cbcs`, `test_iter_project_entries_includes_cbcs_meta_dir_for_full_tree`, `test_find_in_files_ignores_cbcs_metadata_directory`). No typed enum/doc on **which subsystem gets which cbcs policy** beyond module docstring.
- **Code-judo alternative:** Replace boolean with `MetaDirPolicy.INCLUDE | PRUNE` on each public iterator (or scope enum from TN-PROJ-INV-2); forbid raw `include_meta_dir` at call sites outside `file_inventory`.
- **Suggested remediation:** Export scope constants used by `project_service`, `search_panel`, intelligence iterators; add regression test that packaging/intelligence paths never set `include_meta_dir=True`.
- **Tests that would prove fix:** Table-driven test per public iterator API; accidental `include_meta_dir=True` in intelligence call sites fails review test (grep/architecture gate).
- **Handoff overlap:** R4

---

### TN-PROJ-INV-10 — Path root resolution contracts disagree across consumers

- **Persona:** TN-PROJ-INV
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/file_inventory.py:39-40` — `_resolve_root`: `expanduser().resolve()`, relative roots allowed. `app/project/project_service.py:473-477` — `_resolve_project_root` **requires absolute** path or raises `ValueError`. `app/editors/search_panel.py:100` — `expanduser().resolve()` without absolute guard. `enumerate_project_entries` uses absolute-only resolver; inventory iterators use permissive resolver when called directly from tests.
- **Code-judo alternative:** One `resolve_project_root(path, *, require_absolute: bool = False) -> Path` in `bootstrap.paths` or `file_inventory`; all consumers share it.
- **Suggested remediation:** Align `iter_*` and `enumerate_project_entries` on the same root validation; document whether relative roots are supported for search/inventory.
- **Tests that would prove fix:** Relative `tmp_path` input behaves consistently or fails consistently across `enumerate_project_entries`, `find_in_files`, and `iter_python_files`.
- **Handoff overlap:** R4

---

### TN-PROJ-INV-11 — Symlink policy tested only for `iter_python_files`; text/tree paths unverified

- **Persona:** TN-PROJ-INV
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/project/file_inventory.py:68`, `140`, `166`, `189` — `follow_symlinks=False` default on all paths. `tests/unit/project/test_file_inventory.py:154-167` — symlink test only on `iter_python_files`. No coverage for `iter_text_file_paths` / `iter_project_entries` / search through symlinked dirs.
- **Code-judo alternative:** One parametrized symlink fixture run against all public iterators and `find_in_files`.
- **Suggested remediation:** Extend existing symlink test to text search and tree enumeration; document ChoreBoy symlink expectations in module docstring.
- **Tests that would prove fix:** Symlinked directory excluded consistently for python, text, and entry list APIs with default flags.
- **Handoff overlap:** R4

---

### TN-PROJ-INV-12 — `discover_canonical_project_modules` and snapshot duplicate the same walk+name pipeline

- **Persona:** TN-PROJ-INV
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/import_layout.py:242-256` — walk via `iter_python_files`, map with `module_name_for_file`, return `set`. `app/project/file_inventory.py:243-267` — walk via `iter_python_files`, map with `_module_name_from_python_path` (which calls the same layout helpers plus fallback), return frozen snapshot. Two module-list builders will drift (already diverge on fallback — TN-PROJ-INV-5).
- **Code-judo alternative:** `build_project_inventory_snapshot` calls `discover_canonical_project_modules` for `module_names` and stores walk paths once; delete `_module_name_from_python_path` fallback.
- **Suggested remediation:** Single function owns module discovery; snapshot is paths + sorted module names from that function.
- **Tests that would prove fix:** Assert snapshot `module_names == sorted(discover_canonical_project_modules(...))` for shared fixtures.
- **Handoff overlap:** R4, CC-15

---

### TN-PROJ-INV-13 — Double sort in enumeration is harmless but hides walk yield order

- **Persona:** TN-PROJ-INV
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/project/file_inventory.py:101`, `119` — per-directory sorted names. `app/project/project_service.py:325-339` — `list(iter_project_entries(...))` then `sorted(entries, key=lambda e: e.relative_path)`. `iter_project_entries` yields directories-before-files per level (`212-215`), but final API sorts flat by relative path anyway.
- **Code-judo alternative:** Either document that only final sort order is contractual and simplify walk yields, or yield in final sorted order inside `iter_project_entries` and drop redundant sort in `enumerate_project_entries`.
- **Suggested remediation:** Pick one ordering owner; remove duplicate sort if walk already guarantees global lexical order (may require collecting entries in walk or single pass sort at end of iterator).
- **Tests that would prove fix:** Existing `test_enumerate_project_entries_is_deterministic_and_includes_cbcs` unchanged; optional perf assertion on sort call count.
- **Handoff overlap:** none

---

### TN-PROJ-INV-14 — Inline imports in inventory hot path violate repo import rule

- **Persona:** TN-PROJ-INV
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/project/file_inventory.py:276-277` — `from app.project.import_layout import module_name_for_file, resolve_project_import_layout` inside `_module_name_from_python_path`. `app/project/project_service.py:83` — inline `compute_effective_excludes` import in `open_project`. `.cursor/plugins/.../no-inline-imports.mdc` — imports at top unless documented circular dependency.
- **Code-judo alternative:** Top-level imports with explicit cycle break (extract snapshot builder to `inventory_snapshot.py` imported by both layout and intelligence) rather than function-body imports.
- **Suggested remediation:** Move snapshot construction to a sibling module or document the cycle and consolidate imports at module top after extraction.
- **Tests that would prove fix:** Import graph / lint rule passes; no behavior change.
- **Handoff overlap:** none

---

### TN-PROJ-INV-15 — Strong iterator tests, weak cross-surface parity tests

- **Persona:** TN-PROJ-INV
- **Severity:** STRUCTURAL
- **Evidence:** `tests/unit/project/test_file_inventory.py` — thorough per-iterator tests. `tests/unit/editors/test_search_panel.py:165-176` — `exclude_patterns=["generated"]` on search only. `tests/unit/project/test_file_excludes.py:102-116` — vendor skip on `iter_project_entries` with name pattern. **No test** asserts tree vs search vs `iter_python_files` file-set equality for the same effective excludes and cbcs policy. Manifest lists this as high gap for snapshot (`00-manifest.md` test coverage table).
- **Code-judo alternative:** One shared parametrized fixture module (`inventory_parity_fixtures.py`) consumed by project, editors, and future packaging parity tests — SSOT contract tests live once.
- **Suggested remediation:** Add parity tests as part of R4 acceptance; minimum: tree/search/python-file set agreement for vendor, cbcs, slash patterns, and nested segment excludes.
- **Tests that would prove fix:** Single parametrized matrix green across three APIs; fails if TN-PROJ-INV-1 or TN-PROJ-INV-2 regress.
- **Handoff overlap:** R4, CC-15
