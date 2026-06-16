# TN-INT-07 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-07  
**Date:** 2026-06-16  
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`  
**Scope:** `app/intelligence/refactor_engine.py` (126 LOC), `app/intelligence/refactor_runtime.py` (48 LOC), `app/intelligence/import_rewrite.py` (99 LOC), `app/intelligence/latency_tracker.py` (68 LOC). Cross-read: `app/intelligence/semantic_facade.py` (rename seam), `app/shell/project_tree_controller.py` (import rewrite caller), `tests/unit/intelligence/test_refactor_engine.py` (61 LOC), `tests/unit/intelligence/test_import_rewrite.py` (90 LOC), `tests/integration/intelligence/test_no_hidden_metadata.py` (53 LOC), `tests/unit/intelligence/test_semantic_rename_integration.py`, `tests/runtime_parity/intelligence/test_semantic_engine_runtime.py`. Gates: §17.4.5 refactor rule, §17.4.6 I06/I07 rollout, AD-016 facade ownership, visible-cache rule (no dot-prefixed metadata).

---

## Executive verdict

**Conditionally thermo-clean on the core §17.4.5 rename contract — not on orchestration boundaries.** The slice correctly hard-cuts semantic rename to Rope (`ropefolder=None`, no silent token-replace fallback on the rename menu path) and keeps move/rename import rewrites as a separate, policy-gated workflow (`ImportUpdatePolicy.ASK|ALWAYS|NEVER`). File sizes are healthy (largest module 126 LOC). Dominant risks: **(1) a split-brain rename contract** where Jedi proves references from in-memory `source_text` but Rope plans from on-disk project state, with no cross-check between `reference_hits` and Rope patches; **(2) `import_rewrite.py` living in the intelligence package though it is a project-tree filesystem concern**, forcing shell → intelligence imports for non-semantic work; **(3) duplicated multi-file apply+rollback orchestration** copied between rename and import rewrite with no canonical persistence helper. Secondary debt: brittle `getattr` Rope change introspection, facade exception masking that collapses runtime-unavailable into “could not prove safe rename,” rename latency tracked ad hoc in shell instead of through `RollingLatencyTracker`, and unit tests that prove rollback but not the Rope planning contract itself. Would approve the no-fallback rename direction; would not approve further refactor-surface growth without unifying the Jedi/Rope input contract and extracting shared apply orchestration.

---

### TN-INT-07-1 — Split-brain rename contract: Jedi gates on `source_text`, Rope plans from disk

- **Persona:** TN-INT-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/semantic_facade.py:189-205` — `find_references(..., source_text=source_text)` (Jedi `_script` uses buffer text for the active file). `app/intelligence/refactor_engine.py:49-62` — `Project(str(root))` + `Path(absolute_path).read_text()`; `source_text` is never passed or consumed. `app/intelligence/jedi_engine.py:90-94` — current-file references resolved against `source_text`; other files read from disk. `app/shell/semantic_navigation_workflow.py:834-839` — save-all gate before rename, but enforcement lives in shell, not engine contract.
- **Code-judo alternative:** Single input model for rename planning: either (A) pass `source_text` into `RopeRefactorEngine.plan_rename` and write it into the Rope resource before `Rename.get_changes`, matching Jedi’s buffer-aware proof, or (B) drop `source_text` from the facade rename API entirely and require callers to flush buffers first with an explicit `RenameInputSnapshot` type that records `disk_revision` / save token. Delete the implicit “shell saved so it’s fine” assumption from the intelligence layer.
- **Suggested remediation:** Extend `plan_rename` to accept optional per-file text overrides (at minimum the active file’s `source_text`) and inject into Rope before planning; add a contract test where buffer text differs from disk and assert plan is rejected or buffer wins consistently.
- **Tests that would prove fix:** New unit/integration test: unsaved buffer variant of `imported_project` fixture — facade raises or plans from buffer, never silently plans from stale disk. Existing rename integration tests stay green when buffer == disk.
- **Handoff overlap:** AD-016, R2

---

### TN-INT-07-2 — `reference_hits` decorate the plan but are never validated against Rope output

- **Persona:** TN-INT-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/refactor_engine.py:32,92-94` — `reference_hits` optional; only used for `_extract_old_symbol(reference_hits)` and copied into `plan.hits`. `:55-83` — patch list built purely from Rope `changes`; no comparison to hit file/line set. `app/intelligence/refactor_engine.py:113-115` — `changed_occurrences=len(plan.hits) if plan.hits else len(updated_files)` conflates reference count with file count. `app/shell/semantic_navigation_workflow.py:887` — UI displays `len(plan.hits)` as occurrence count regardless of patch content.
- **Code-judo alternative:** After Rope planning, derive occurrences from patches (`changed_line_numbers` sum or diff hunk count) and optionally assert every hit file appears in `preview_patches`. If validation fails, raise “could not prove safe rename” instead of returning a plan with mismatched metadata. Drop `reference_hits` from the engine API — facade attaches hits after validation, or engine returns `(patches, proven_hits)`.
- **Suggested remediation:** Post-plan validator in facade or engine; fix `changed_occurrences` to count real edit sites; reject plans where hit files ⊄ patched files.
- **Tests that would prove fix:** Fixture where Jedi finds N references but Rope produces M≠N edits — assert hard failure, not silent plan. Apply-result test asserts occurrence count matches patch line deltas.
- **Handoff overlap:** AD-016

---

### TN-INT-07-3 — Facade `old_symbol` reconciliation can mislabel a Rope plan without re-planning

- **Persona:** TN-INT-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/semantic_facade.py:183-185,212-219` — `old_symbol = extract_symbol_under_cursor(source_text, cursor_position)`; if `plan.old_symbol != old_symbol`, facade returns a new `SemanticRenamePlan` swapping `old_symbol` to the cursor value while reusing `plan.preview_patches` unchanged. `app/intelligence/refactor_engine.py:119-121` — engine `old_symbol` comes from `reference_hits[0].symbol_name`, which can differ from cursor extraction when hits are empty (direct engine calls) or ordering differs.
- **Code-judo alternative:** Treat `old_symbol` as a single canonical field computed once at the facade gate (cursor extraction). Engine returns patches-only (`SemanticRenamePatchPlan`); facade wraps with validated symbol metadata. If cursor symbol ≠ first reference hit symbol, fail closed — do not relabel patches.
- **Suggested remediation:** Remove the relabel branch; raise when symbols disagree. Engine stops owning `old_symbol`.
- **Tests that would prove fix:** Parametrized facade test: mismatched cursor vs hit symbol → `ValueError`. Existing rename integration tests unchanged.
- **Handoff overlap:** AD-016

---

### TN-INT-07-4 — Duplicate multi-file apply+rollback orchestration across rename and import rewrite

- **Persona:** TN-INT-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/refactor_engine.py:99-112` — read originals → `atomic_write_text` loop → rollback dict on `OSError`. `app/intelligence/import_rewrite.py:56-69` — identical structure. `app/intelligence/code_actions.py:373-386` — third `_rollback_quick_fix_changes` variant. `app/persistence/atomic_write.py` — only single-file atomic write; no batch helper.
- **Code-judo alternative:** One canonical `atomic_write_batch(updates: Mapping[str, str]) -> list[str]` in `app/persistence/` (or `app/project/file_mutations.py`) owning read-snapshot, ordered apply, reverse rollback. Rename and import rewrite become one-liner delegates; code_actions quick-fix path reuses the same primitive.
- **Suggested remediation:** Extract batch helper in a focused PR; point `apply_rename` and `apply_import_rewrites` at it without behavior change.
- **Tests that would prove fix:** Existing rollback tests in `test_refactor_engine.py` and `test_import_rewrite.py` green against shared helper; one new test for three-file partial failure rollback via the helper directly.
- **Handoff overlap:** R5

---

### TN-INT-07-5 — `import_rewrite.py` is project-tree filesystem policy, not intelligence semantics

- **Persona:** TN-INT-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/import_rewrite.py:1-11` — module docstring scopes “deterministic move/rename rewrite previews only,” explicitly not organize-imports. `app/shell/project_tree_controller.py:8,111-132` — shell tree controller imports and orchestrates policy + confirmation. `app/project/file_operation_models.py:9-14` — `ImportUpdatePolicy` already lives in project layer. `docs/ARCHITECTURE.md:1424-1427` — move/rename import rewrites must stay separate from organize-imports; deferred to trusted-semantics lane long-term.
- **Code-judo alternative:** Move module to `app/project/import_rewrite.py` (alongside `file_operations`, `file_operation_models`). Intelligence package exports semantic rename only; shell imports project layer for tree moves. Keeps §17.4.5 “semantic rename vs explicit text workflow” boundary visible in package graph.
- **Suggested remediation:** Hard cutover import paths in `project_tree_controller`, integration tests, and `test_project_tree_controller.py` mocks; leave intelligence package free of regex move helpers.
- **Tests that would prove fix:** `grep` shows no `app/intelligence/import_rewrite` imports outside moved module; tree + integration tests green.
- **Handoff overlap:** R3, R5

---

### TN-INT-07-6 — Regex import rewrite is an explicit non-semantic workflow (§17.4.5 OK) but under-specified and undertested

- **Persona:** TN-INT-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/import_rewrite.py:86-99` — line-level regex `\b{old_module}(?=\.|\b)` on `import`/`from` lines only; no AST, no relative-import handling, no `import pkg as alias` edge cases. `tests/unit/intelligence/test_import_rewrite.py:16-35` — happy path only (`from app.module` / `import app.module`). Module header `:8-10` acknowledges future “structural import rewrites” but ships regex as the only implementation.
- **Code-judo alternative:** Keep regex path explicitly labeled `ImportRewriteStrategy.REGEX` with user-visible “textual import update” copy in confirmation dialog; document non-goals (relative imports, string literals in imports, re-exports). Add negative tests asserting no rewrite for `from .module`, `import app.module as m`, and comment-only lines. Longer term: AST-based rewriter in project layer shares parser with diagnostics — do not bolt into Rope rename.
- **Suggested remediation:** Expand test matrix for known false-positive/negative cases; update shell confirmation copy to say “textual import line update,” not “semantic.” Track AST rewrite as separate backlog item tied to §17.5.4.
- **Tests that would prove fix:** Parametrized tests for relative imports, aliases, unchanged string literals; integration move test still passes for canonical absolute-import fixtures.
- **Handoff overlap:** AD-016, none

---

### TN-INT-07-7 — §17.4.5 no-fallback rename is satisfied; facade still masks runtime failures as proof failures

- **Persona:** TN-INT-07
- **Severity:** STRUCTURAL
- **Evidence:** Grep across `app/intelligence/*refactor*` — no token-replace or text-search fallback on rename path (compliant with `docs/ARCHITECTURE.md:1296-1298,1313-1314`). `app/intelligence/semantic_facade.py:206-209` — broad `except Exception` re-raises as `ValueError("Semantic rename could not prove a safe rename plan: ...")`, same message as `:210-211` for empty plan. `app/intelligence/refactor_engine.py:36-37` — `RuntimeError(status.message)` when Rope unavailable is caught by that broad handler. `app/shell/semantic_navigation_workflow.py:865-870,920-921` — UI treats all failures as “no safe plan” or generic warning, losing `SemanticOperationMetadata` degradation shape used elsewhere.
- **Code-judo alternative:** Let `RuntimeError` / `RefactorRuntimeStatus` propagate as typed degradation (`confidence="unavailable"`, engine=`rope`); reserve `ValueError` for proof failures only. Shell shows distinct copy: “Rename engine unavailable” vs “Symbol cannot be safely renamed.”
- **Suggested remediation:** Narrow facade except clause; map runtime status to `SemanticDegradedResult` or re-raise; shell branches on exception type or metadata.
- **Tests that would prove fix:** Facade test with mocked unavailable runtime → specific exception/metadata, not generic proof failure. Existing semantic rename tests unchanged when Rope ready.
- **Handoff overlap:** AD-016, R2

---

### TN-INT-07-8 — `test_refactor_engine.py` proves rollback only; Rope `plan_rename` contract untested at engine seam

- **Persona:** TN-INT-07
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/intelligence/test_refactor_engine.py:15-61` — single test `test_apply_rename_rolls_back_on_write_failure`; constructs patches via `.replace("task_name", "renamed_task")` (test data only, not production fallback). No `plan_rename` coverage at engine level. `tests/unit/intelligence/test_semantic_rename_integration.py` and `tests/integration/intelligence/test_no_hidden_metadata.py` exercise facade/runtime parity but skip engine-only boundaries (cursor offset, empty changes, out-of-root path). `tests/runtime_parity/intelligence/test_semantic_engine_runtime.py:62-67` — calls `engine.plan_rename` without `reference_hits`.
- **Code-judo alternative:** Add focused engine unit tests: out-of-root `ValueError`, empty patch → `None`, metadata latency populated, `ropefolder=None` side effect (no dot dirs — may stay integration). Keep rollback test; delete redundant facade overlap where engine tests are sufficient.
- **Suggested remediation:** Extend `test_refactor_engine.py` with 2–3 engine contract tests behind Rope availability skip guard (same pattern as `test_no_hidden_metadata.py:29-31`).
- **Tests that would prove fix:** New tests pass under AppRun when Rope available; skip cleanly otherwise. Fast shard stays sub-budget via `@pytest.mark.unit` + skip.
- **Handoff overlap:** none

---

### TN-INT-07-9 — I07 latency tooling exists but rename path uses ad hoc shell logging, not `RollingLatencyTracker`

- **Persona:** TN-INT-07
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/latency_tracker.py:21-57` — clean rolling p50/p95 tracker. `app/intelligence/completion_metrics.py:10-40` — canonical consumer for completion ops. `app/intelligence/refactor_engine.py:34,90` — inline `_elapsed_ms` → `exact_metadata(..., latency_ms=...)` on plan only; no rolling window. `app/shell/semantic_navigation_workflow.py:841-864` — duplicate `time.perf_counter()` logging with hard-coded 800 ms warning threshold, not tied to tracker snapshots. `docs/ARCHITECTURE.md:1315-1316` — I07 slice includes “latency gates” for trust UX.
- **Code-judo alternative:** Introduce `RefactorTelemetry` (mirror `CompletionTelemetry`) wrapping `RollingLatencyTracker("rename_plan_ms")` / `("rename_apply_ms")`; record in `semantic_session.request_rename_plan` / `request_apply_rename` so shell reads snapshots instead of one-off timers. Single gate constant owned by intelligence, not shell magic number.
- **Suggested remediation:** Wire tracker at session layer; expose snapshot callback or log hook for shell metrics flag; remove duplicated perf_counter block from navigation workflow when session emits snapshots.
- **Tests that would prove fix:** `test_latency_tracker.py` pattern reused for refactor telemetry; session test asserts `record` called after rename task.
- **Handoff overlap:** R2, I07

---

### TN-INT-07-10 — Brittle Rope boundary: inline imports, `getattr` change walk, per-call `Project` lifecycle

- **Persona:** TN-INT-07
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/refactor_engine.py:39-40` — inline `from rope.base.project import Project` / `Rename` after runtime init (violates repo no-inline-imports rule without documented cycle exception). `:55-57` — `getattr(changes, "changes", [])`, `getattr(change, "resource", None)`, `getattr(change, "new_contents", None)` untyped. `:49-85` — new `Project` + `project.close()` on every `plan_rename` call; no reuse unlike Jedi project cache in `jedi_engine.py`.
- **Code-judo alternative:** Top-level imports guarded by runtime init (or thin `rope_adapter.py` owning all Rope types). Typed `RopeChange` NamedTuple parsed once from Rope objects. Optional `RefactorProjectPool` keyed by `project_root` on semantic worker thread — amortize Project construction for I07 latency.
- **Suggested remediation:** Extract `rope_adapter.py` with typed change extraction + characterization tests; document inline-import exception if adapter imports rope at module level post-vendor-path bootstrap.
- **Tests that would prove fix:** Adapter unit tests with fake change objects; runtime parity rename test still passes; optional perf note for repeated rename on same project.
- **Handoff overlap:** R4

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| §17.4.5 no silent token-replace rename fallback | **Compliant** — Rope-only semantic rename; Find/Replace remains separate shell workflow |
| Move/rename import rewrite vs semantic rename | **Correct separation** — regex path is policy-gated tree operation, not rename fallback (TN-INT-07-5, TN-INT-07-6) |
| Visible cache / no dot metadata | **Compliant** — `Project(..., ropefolder=None)`; covered by `test_no_hidden_metadata.py` + runtime parity |
| Jedi/Rope input contract | **Split-brain** — buffer vs disk sources diverge at engine boundary (TN-INT-07-1) |
| Plan metadata vs patches | **Unvalidated** — hits decorate UI but aren't checked against Rope output (TN-INT-07-2, TN-INT-07-3) |
| Persistence orchestration | **Triplicated** rollback loops (TN-INT-07-4) |
| Package placement | **import_rewrite in wrong layer** (TN-INT-07-5) |
| I07 latency gates | **Partial** — plan metadata has point latency; no rolling tracker on rename path (TN-INT-07-9) |
| Test depth | Rollback strong; engine plan contract thin (TN-INT-07-8) |

**Approval bar:** Approve the §17.4.5 / I06 direction (no silent token fallback, visible Rope metadata, hidden-dir guard). **Do not approve** additional rename or import-rewrite features until TN-INT-07-1 (unified input contract) and TN-INT-07-4 (shared batch apply) land — those are the highest-leverage code-judo moves that prevent the next shell/intelligence wave from compounding dual-engine and copy-paste rollback debt.
