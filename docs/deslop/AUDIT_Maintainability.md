**A. Executive Summary**

Overall maintainability grade: **B-**.

The codebase looks **mixed but mostly human-directed**: there is strong architectural documentation, clear runtime constraints, and many good contract tests, but also AI-like accumulation patterns: oversized orchestration files, repeated helper logic, broad extension surfaces, and tests that over-pin implementation details.

Top risks:

- `app/shell/main_window.py` is a ~6.7k-line composition root that still owns too many workflows.
- Project traversal/exclusion logic is repeated across search, indexing, diagnostics, packaging, and import rewrites.
- Dependency/runtime classification is split between diagnostics and packaging.
- UI tests often reach into private widget internals, making refactors noisy.
- No configured lint/complexity/dead-code gate beyond `pyright`.

Highest-ROI cleanup:

- Extract more `MainWindow` responsibilities into focused shell controllers.
- Centralize project file iteration and exclude policy.
- Unify dependency/native-extension/runtime classification.
- Replace brittle private-widget tests with public behavior tests where practical.
- Add a minimal lint/dead-code quality gate after choosing tools.

## **B. Architecture Map**

Main flow is sound and matches `docs/ARCHITECTURE.md`: `shell` owns Qt composition, `project` loads folders/manifests, `run` launches supervised processes, `runner` executes user code, `persistence` stores settings/history, `plugins` manages extension contracts, and `intelligence` handles editor analysis.

Business rules mostly live in sensible places:

- Paths/constants: `app/core/constants.py`, `app/bootstrap/paths.py`
- Project shape: `app/project/project_service.py`, `app/project/project_manifest.py`
- Run/debug contracts: `app/run/run_service.py`, `app/run/run_manifest.py`, `app/debug/`*, `app/runner/`*
- Packaging rules: `app/packaging/*`

Unclear boundaries:

- `app/shell/main_window.py` imports and coordinates nearly every subsystem.
- `app/run/` mixes user run lifecycle with pytest workflows.
- `app/packaging/` contains both in-app project packaging and product release/build logic.

## **C. AI Slop Findings**

1. **Monolithic Shell Orchestrator**

- Severity: High
- Evidence: `app/shell/main_window.py`, `MainWindow`
- Why: Too many workflows share one change surface.
- Fix: Continue extracting save, run/debug, runtime center, external file change, and editor preference controllers.
- Effort: L
- Risk: Medium

1. **Repeated Project Traversal Rules**

- Severity: Medium
- Evidence: `app/project/project_service.py`, `app/editors/search_panel.py`, `app/intelligence/symbol_index.py`, `app/intelligence/import_rewrite.py`, `app/packaging/dependency_audit.py`
- Why: Excludes and traversal can drift.
- Fix: Add one project inventory/iterator API.
- Effort: M
- Risk: Medium

1. **Split Dependency Classification**

- Severity: Medium
- Evidence: `app/intelligence/diagnostics_service.py`, `app/packaging/dependency_audit.py`
- Why: Runtime/import/native-extension rules are business rules and should not diverge.
- Fix: Extract shared classifier.
- Effort: M
- Risk: Medium

1. **Overloaded Constants Module**

- Severity: Medium
- Evidence: `app/core/constants.py`
- Why: UI, plugins, run modes, paths, and settings all share one hotspot.
- Fix: Split by domain with compatibility re-export if needed.
- Effort: M
- Risk: Low

1. **Brittle Private UI Tests**

- Severity: Medium
- Evidence: `tests/unit/shell/test_test_explorer_panel.py`, `tests/unit/shell/test_outline_panel.py`, `tests/integration/shell/test_main_window_quick_open_integration.py`
- Why: Tests break on internal layout changes, not user behavior.
- Fix: Prefer public signals/state transitions; delete low-signal layout assertions.
- Effort: M
- Risk: Low

1. **Silent Exception Paths**

- Severity: Medium
- Evidence: `app/shell/main_window.py`, `app/runner/debug_runner.py`, `app/treesitter/capture_pipeline.py`
- Why: Failures can look like no-ops.
- Fix: Narrow exceptions or log debug/warning with context.
- Effort: S
- Risk: Low

1. **Tooling Gap**

- Severity: Medium
- Evidence: no root Ruff/mypy config, empty `requirements-dev.txt`, no CI config found
- Why: Dead code, import hygiene, and complexity drift rely on review/manual inspection.
- Fix: Add chosen lint/dead-code gate after explicit dependency decision.
- Effort: S/M
- Risk: Low

## **D. SSOT/DRY Findings**

Best current SSOT examples are `app/bootstrap/paths.py`, `app/project/file_excludes.py`, and `app/core/constants.py`.

Needs consolidation:

- File traversal and structural excludes should centralize around `app/project/file_excludes.py` or a new `app/project/file_inventory.py`.
- Module-name/path conversion appears in intelligence and code action helpers.
- Native dependency detection appears in diagnostics and packaging.
- Entry path validation appears in packaging and shell paths.

Recommended source-of-truth locations:

- Project traversal: `app/project/file_inventory.py`
- Path containment/entry validation: `app/project/project_paths.py` or `app/packaging/layout.py` if packaging remains the main consumer
- Dependency classification: `app/intelligence/import_resolver.py` or a new `app/project/dependency_classifier.py`

## **E. SOLID/Design Findings**

The architecture is generally modular, but `MainWindow` violates single responsibility. It should remain a composition root, not the home for workflow behavior.

Design improvements:

- Keep `MainWindow` wiring-only.
- Move save/style automation to a save workflow/controller.
- Move runtime center/onboarding to a runtime workflow.
- Move debug command UI routing to a debug controller.
- Keep plugin workflow APIs stable, but avoid expanding provider lanes until actual product need proves them.

## **F. Testing Findings**

Current test structure is strong: unit, integration, runtime parity, performance, and manual acceptance are clearly separated.

Well covered:

- Project manifests and opening.
- Run service, runner, subprocess lifecycle.
- Plugin manifest/runtime protocols.
- Tree-sitter query/token contracts.
- Local history/autosave behavior.

Risky weak spots:

- `app/persistence/local_history_schema.py` has indirect coverage but needs direct tests before migrations.
- `app/run/host_process_manager.py` is mostly covered through `RunService`.
- Product packaging internals have private-helper tests, useful but brittle.

Characterization tests before refactor:

- Shared project inventory/exclude behavior.
- Dependency classification for stdlib, project, vendor, native, runtime, missing.
- Entry path containment.
- `MainWindow` save/run behavior through public-ish workflow seams.

## **G. Tooling Findings**

Ran diagnostics:

- `npx pyright` -> passed, `0 errors`.
- `python3 testing/run_test_shard.py fast` -> passed.
- `python3 -m ruff check app tests` -> unavailable, `No module named ruff`.
- `vulture`, `radon`, `lizard` -> unavailable.

Minimum quality gate:

- `python3 testing/run_test_shard.py fast`
- `npx pyright`

Future stricter gate:

- Add Ruff or equivalent lint.
- Add dead-code scan such as Vulture.
- Add complexity report such as Radon/Lizard for audit-only use.
- Pin dev tooling in `requirements-dev.txt` or docs-backed installer path.

## **H. Prioritized Refactor Roadmap**

Phase 0: Safety net only

- Objective: protect behavior before moving code.
- Files: tests around `project`, `intelligence`, `packaging`, `shell`.
- Tests: fast shard, pyright, targeted characterization.
- Risk: Low
- Rollback: delete characterization additions if scope changes.

Phase 1: Low-risk cleanup

- Objective: remove small slop without changing contracts.
- Files: `app/shell/main_window.py`, `app/runner/debug_runner.py`, low-signal UI tests.
- Changes: add logging, remove dead branches, extract tiny helpers.
- Risk: Low
- Rollback: revert individual commits.

Phase 2: SSOT consolidation

- Objective: unify traversal/excludes/classification.
- Files: `app/project/file_excludes.py`, `app/intelligence/`*, `app/packaging/`*.
- Changes: shared iterator/classifier APIs.
- Risk: Medium
- Rollback: keep old call sites until tests pass, then hard cut over.

Phase 3: Architecture/layering

- Objective: reduce `MainWindow` ownership.
- Files: `app/shell/main_window.py`, new/existing shell controllers.
- Changes: extract save/run/debug/runtime workflows.
- Risk: Medium
- Rollback: controller-by-controller.

Phase 4: Type/test hardening

- Objective: make future refactors less noisy.
- Files: `tests/unit/shell/*`, `tests/unit/editors/*`, tooling config if approved.
- Changes: public behavior tests, lint gate.
- Risk: Low/Medium

Phase 5: Optional deeper redesign

- Objective: reassess plugin platform and packaging split.
- Files: `app/plugins/*`, `app/packaging/*`.
- Risk: High
- Do only with product confirmation.

## **I. Do Not Touch Yet**

- Plugin workflow/provider architecture: broad but appears intentional.
- Debug evaluate behavior in `app/runner/debug_runner.py`: `eval` is expected debugger functionality, not general unsafe eval.
- Product packaging/release code: separate from in-app packaging and easy to break without release context.
- Local history schema internals: add explicit migration/schema tests before refactoring.

# App Maintainability Refactor Roadmap

## Scope

- Audit/refactor target: `[app/](app/)` only, with tests under `[tests/](tests/)` only where they characterize risky app behavior.
- Preserve the documented editor/runner/process boundaries in `[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)`.
- Do not rewrite subsystems; prefer small extraction and source-of-truth consolidation.

## Key Evidence

- `[app/shell/main_window.py](app/shell/main_window.py)` is the largest risk concentration: ~6.7k lines and ~370 class/function definitions, spanning project open, save transforms, run/debug, REPL, settings, runtime explanation, theming, external-file polling, and event queues.
- Traversal and exclusion policies are repeated across `[app/project/project_service.py](app/project/project_service.py)`, `[app/editors/search_panel.py](app/editors/search_panel.py)`, `[app/intelligence/symbol_index.py](app/intelligence/symbol_index.py)`, `[app/intelligence/import_rewrite.py](app/intelligence/import_rewrite.py)`, `[app/intelligence/diagnostics_service.py](app/intelligence/diagnostics_service.py)`, and `[app/packaging/dependency_audit.py](app/packaging/dependency_audit.py)`.
- Dependency/runtime classification logic is duplicated between `[app/intelligence/diagnostics_service.py](app/intelligence/diagnostics_service.py)` and `[app/packaging/dependency_audit.py](app/packaging/dependency_audit.py)`.
- Tests are extensive and diagnostics pass, but several UI tests assert private widget internals and exact presentation details, especially under `[tests/unit/shell/](tests/unit/shell/)` and `[tests/unit/editors/test_syntax_highlighters.py](tests/unit/editors/test_syntax_highlighters.py)`.

## Refactor Phases

### Phase 0: Safety Net Only

- Run and record baseline: `python3 testing/run_test_shard.py fast`, `npx pyright`, targeted tests around project traversal/search/packaging/intelligence.
- Add characterization tests only for high-risk behavior before extraction: project file iteration/excludes, entrypoint replacement, dependency audit classification, and save-transform error behavior.

### Phase 1: Low-Risk Cleanup

- Move shell-only helper constants and small helper widgets out of `[app/shell/main_window.py](app/shell/main_window.py)` where already separable.
- Normalize silent exception paths into either logged debug/warning outcomes or documented benign probes.
- Prune low-signal tests that only assert object names, icon cache identity, or private layout widgets when not protecting behavior.

### Phase 0/1 Progress: MainWindow Refactor (2026-04-25)

- Completed the `MainWindow`-focused Phase 0 baseline: `npx pyright` passed with `0 errors`; an existing baseline fast shard passed; post-refactor `python3 testing/run_test_shard.py fast` passed.
- Replaced legacy private `_active_session_mode` test setup with `RunSessionController`-style seams, then removed the `MainWindow` fallback branch so run output state has one owner.
- Deleted dead `_create_placeholder_panel` code and moved the editor tab bar into `[app/shell/editor_tab_bar.py](app/shell/editor_tab_bar.py)`.
- Extracted focused shell helpers from `[app/shell/main_window.py](app/shell/main_window.py)`:
  - `[app/shell/main_window_layout.py](app/shell/main_window_layout.py)` for top-level frame/layout helpers.
  - `[app/shell/save_workflow.py](app/shell/save_workflow.py)` for save, auto-save-to-file, and style-on-save behavior.
  - `[app/shell/project_tree_presenter.py](app/shell/project_tree_presenter.py)` for project tree presentation/state restoration.
  - `[app/shell/editor_tabs_coordinator.py](app/shell/editor_tabs_coordinator.py)` for tab chrome, preview promotion, and buffer revision helpers.
  - `[app/shell/run_debug_presenter.py](app/shell/run_debug_presenter.py)` for run/debug session start presentation.
  - `[app/shell/problems_controller.py](app/shell/problems_controller.py)` for diagnostics/problems-panel mirroring.
- Normalized silent restore/onboarding/recent-project probe failures to debug logging where the benign fallback remains intentional.
- Validation evidence after the refactor:
  - `python3 run_tests.py tests/unit/shell/test_main_window_format_actions.py tests/unit/shell/test_main_window_debug_routing.py tests/unit/shell/test_project_tree_refresh_state.py tests/unit/shell/test_main_window_tree_delete_copy.py tests/unit/shell/test_main_window_quick_open.py tests/integration/shell/test_main_window_shutdown_integration.py` passed.
  - `python3 run_tests.py tests/unit/shell/ tests/integration/shell/` passed (`661` collected).
  - `npx pyright` passed with `0 errors, 0 warnings, 0 informations`.
  - `python3 testing/run_test_shard.py fast` passed.

### Phase 2: SSOT Consolidation

- Introduce a shared project file iterator/exclusion policy, likely in `[app/project/file_excludes.py](app/project/file_excludes.py)` or a sibling inventory module.
- Route search, symbol indexing, import rewrite, diagnostics, project enumeration, and packaging through that shared policy.
- Centralize compiled-extension/runtime dependency classification currently split across diagnostics and packaging.

### Phase 2 Progress: SSOT Consolidation (2026-04-25)

- Added two new SSOT modules and routed every previously duplicated call site through them (hard cutover, no fallbacks):
  - `[app/project/file_inventory.py](app/project/file_inventory.py)` owns the single project-tree walker (`walk_project`) and the public helpers `iter_python_files`, `iter_text_file_paths`, and `iter_project_entries`. `cbcs/` pruning, `vendor/` skip, and pattern-based exclusion (name vs relative-path mode) live in one place.
  - `[app/project/dependency_classifier.py](app/project/dependency_classifier.py)` owns `STDLIB_TOP_LEVELS`, `COMPILED_EXTENSION_SUFFIXES`, `has_compiled_extension_candidate`, the labeled `classify_module` (returning `ClassifiedModule`), and the diagnostics-flavored `is_module_resolvable`.
- Cut over the eight `rglob('*.py') + cbcs skip` duplicates and the search panel walker:
  - `[app/intelligence/diagnostics_service.py](app/intelligence/diagnostics_service.py)` — deleted local `_STDLIB_FALLBACK`, `_COMPILED_EXTENSION_SUFFIXES`, `_is_import_resolvable`, and `_has_compiled_extension_candidate`.
  - `[app/packaging/dependency_audit.py](app/packaging/dependency_audit.py)` — dropped the cross-module private import `from app.intelligence.diagnostics_service import _STDLIB_FALLBACK`, removed the duplicated `_COMPILED_EXTENSION_SUFFIXES`/`_has_compiled_extension_candidate`, and replaced the bespoke `_classify_import` body with `classify_module(...)` plus a small category->classification adapter.
  - `[app/intelligence/symbol_index.py](app/intelligence/symbol_index.py)`, `[app/intelligence/import_rewrite.py](app/intelligence/import_rewrite.py)`, `[app/intelligence/completion_providers.py](app/intelligence/completion_providers.py)`, `[app/intelligence/code_actions.py](app/intelligence/code_actions.py)`, `[app/shell/main_window.py](app/shell/main_window.py)` (entry replacement dialog), and `[app/editors/search_panel.py](app/editors/search_panel.py)` (replacing the manual `os.walk` + local `_STRUCTURAL_SKIP_DIRS`) all delegate to `iter_python_files` / `iter_text_file_paths`.
  - `[app/project/project_service.py](app/project/project_service.py)` — `enumerate_project_entries`, `_infer_recursive_package_main`, `_contains_any_python_file`, and the recursive scan inside `_infer_default_entry_file` route through `iter_project_entries` / `iter_python_files`. Dead `_build_project_entry` / `_build_project_entry_from_walk` helpers and the unused `os` import were removed.
- Resolved the real name collision between `app/project/file_excludes.should_exclude_relative_path(str, patterns, *, is_directory)` and `app/packaging/layout.should_exclude_relative_path(Path)`: the packaging variant is now `is_packaging_excluded_path`, and the four packaging callers (`[app/packaging/dependency_audit.py](app/packaging/dependency_audit.py)`, `[app/packaging/artifact_builder.py](app/packaging/artifact_builder.py)`, `[app/packaging/validator.py](app/packaging/validator.py)`, `[app/support/preflight.py](app/support/preflight.py)`) were updated.
- New focused tests cover the SSOT modules: `[tests/unit/project/test_file_inventory.py](tests/unit/project/test_file_inventory.py)` (10 cases) and `[tests/unit/project/test_dependency_classifier.py](tests/unit/project/test_dependency_classifier.py)` (15 cases). The pre-existing `test_diagnostics_service.py` monkeypatch was retargeted from `app.intelligence.diagnostics_service.is_runtime_module_importable` to `app.project.dependency_classifier.is_runtime_module_importable` to match the new call site.
- Validation evidence:
  - `npx pyright` -> `0 errors, 0 warnings, 0 informations`.
  - `python3 testing/run_test_shard.py fast` -> exit 0 (full suite, including the 25 new SSOT tests).
  - `python3 testing/run_test_shard.py integration` -> exit 0.
  - Targeted re-run of `tests/unit/intelligence/`, `tests/unit/editors/`, `tests/unit/packaging/`, `tests/unit/support/`, and `tests/unit/project/` after the cutover all passed.

### Phase 3: Architecture/Layering Improvements

- Continue extracting `[MainWindow](app/shell/main_window.py)` into focused controllers: save/style transforms, run/debug commands, runtime center/onboarding, external file changes, and editor preferences.
- Keep `MainWindow` as composition root only, matching the explicit architecture decision.
- Avoid touching plugin runtime architecture until product scope confirms the plugin platform remains v1-critical.

### Phase 4: Type/Test Hardening

- Keep `pyright` as the minimum static gate.
- Add ruff or equivalent lint only after explicitly choosing config and installing policy.
- Convert brittle UI implementation tests toward public signals/state transitions or manual acceptance where appropriate.

### Phase 5: Optional Deeper Redesign

- Reassess plugin workflow/provider complexity after the core shell and SSOT consolidations.
- Consider a shared UI component/icon factory only if repeated widget code remains a clear source of change pain.