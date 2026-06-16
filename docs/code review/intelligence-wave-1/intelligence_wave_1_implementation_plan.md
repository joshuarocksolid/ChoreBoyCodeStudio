# Intelligence Wave 1 — End-to-End Implementation Plan

Status: **implementation-ready** (Phase 2 execution)  
Baseline: `ce176983f3d3434b390718692047583c9b38c4ed`  
Source review: [`intelligence_wave_1_thermo_review_2026-06-16.md`](intelligence_wave_1_thermo_review_2026-06-16.md)  
Strategy doc: [`intelligence_wave_1_remediation_plan.md`](intelligence_wave_1_remediation_plan.md) (unchanged — this document expands it)  
Integration themes: [`_findings/TN-INT-INTEG.md`](_findings/TN-INT-INTEG.md)

This plan is the **executable** companion to the remediation plan: every CC theme CC-01 … CC-23 maps to concrete steps, files, PRs, verification gates, and dependencies. Use this document to drive implementation agents and PR reviews.

---

## 1. Program scope and completion definition

### In scope

- Close all **P0** themes CC-01 … CC-07 (mandatory).
- Close all **P1** themes CC-08 … CC-18 (mandatory for program completion).
- Close **P2** themes CC-19 … CC-23 per disposition table below (partial mandatory, partial backlog).
- Split `semantic_navigation_workflow.py` below 1k LOC; no `app/` file may exceed 1k at program end.
- Establish AD-016 worker-only broker lane and AD-018 single stale gate module.
- Advance R4 inventory + R5 diagnostics SSOT without long-lived parallel paths.

### Program complete when (all must pass)

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | CC-01 … CC-07 closed with evidence | P0 closure checklist (§4) |
| 2 | CC-08 … CC-18 closed | CC matrix (§3) status = closed |
| 3 | CC-19, CC-21, CC-22 closed; CC-20, CC-23 disposition satisfied | §3 + §14 |
| 4 | No `app/` Python file >1000 LOC | `find app -name '*.py' -exec wc -l {} + \| awk '$1>1000'` → empty |
| 5 | Broker mutation worker-only | `rg 'complete_fast\|record_completion_acceptance' app/shell/` → no UI callers |
| 6 | Zero direct intelligence imports in nav layer | `rg '^from app\.intelligence' app/shell/semantic_*` → empty |
| 7 | Fast shard + runtime_parity + targeted intelligence tests green | §11 |
| 8 | `npx pyright` → 0 errors | §11 |
| 9 | Four-theme manual acceptance recorded for every UI-touching PR | §12 |
| 10 | Raw finding coverage: 117/119 mapped findings closed; 2 backlog-only waived | §3 footnote |

**Footnote:** `TN-INT-04-11` and `TN-INT-SHELL-EDITORS-10` are P2 backlog with no CC owner — waive without ticket if no product impact at program end.

### P0-only milestone (optional early ship gate)

Ship **P0 milestone** after INT-R-01 … INT-R-06 + INT-R-07 + INT-R-08 land (CC-01 … CC-07 except CC-06 monolith split). CC-06 requires INT-R-11 … INT-R-13. Do not add intelligence features before P0 milestone unless product-waived per TN-INT-INTEG approval bar.

---

## 2. Non-negotiable rules (every PR)

1. **Hard cutover** — delete old paths in the same PR; no `try new / fallback old` chains.
2. **Python 3.9** syntax; no dot-prefixed storage paths.
3. **`semantic_navigation_workflow.py` LOC must decrease** on any PR touching it until INT-R-12 completes.
4. **Broker mutation worker-only** after INT-R-03: no UI-thread `complete_fast`, `record_acceptance`, or cache writes.
5. **One prefix owner:** `build_completion_context` in editors — delete `extract_completion_prefix` import from `code_editor_semantics.py`.
6. **One stale gate:** `editor_stale_result_policy.py` — no new inline revision checks in workflows.
7. **Four-theme validation** for shell/editor UI PRs (Light, Dark, HC Light, HC Dark) — record in PR summary.
8. **Tests** only when risk-first gate applies (races, tier merge, stale-apply, rename safety, subprocess on lint path).

---

## 3. CC theme closure matrix

| CC | Priority | Primary PR | Wave step | Key files | Verification | Depends on |
|----|----------|------------|-----------|-----------|--------------|------------|
| CC-01 | P0 | INT-R-03 | 1.1 | `semantic_session.py`, `completion_broker.py`, `semantic_navigation_workflow.py`, `editor_tab_factory.py` | Stress test; `rg complete_fast app/shell/` empty | INT-R-01 |
| CC-02 | P0 | INT-R-07 | 2.1 | `completion_broker.py`, `completion_models.py`, `completion_item_model.py` | Contract test: approximate items never in exact envelope | INT-R-03 |
| CC-03 | P0 | INT-R-08 | 2.2 | `completion_broker.py`, `completion_context.py` | Revision bump → reuse returns None | INT-R-03 |
| CC-04 | P0 | INT-R-04 | 1.2 | `semantic_navigation_workflow.py`, `editor_intelligence_controller.py`, `semantic_session.py` | Menu test never calls `resolve_*_blocking` | INT-R-01, INT-R-03 |
| CC-05 | P0 | INT-R-05 | 1.3 | `code_editor_semantics.py`, `completion_context.py` | Dotted/import accept span tests | INT-R-03 |
| CC-06 | P0 | INT-R-11, INT-R-12 | 3.1 | `semantic_navigation_workflow.py` → split modules | `awk '$1>1000'` empty | INT-R-01, INT-R-10 |
| CC-07 | P0 | INT-R-03 | 1.1 | `editor_tab_factory.py`, workflow acceptance API | Grep: factory → workflow not controller | INT-R-03 |
| CC-08 | P1 | INT-R-09, INT-R-13 | 2.3, 3.3 | `semantic_session.py`, `editor_intelligence_controller.py`, `intelligence_composition.py` | Session LOC ↓ ~150; priority table test | INT-R-03 |
| CC-09 | P1 | INT-R-06 | 1.4 | `semantic_session.py` | Two-file concurrent nav callbacks | INT-R-03 |
| CC-10 | P1 | INT-R-13 | 3.2 | All `app/shell/semantic_*` | Seven-import checklist (§8) + `rg` gate | INT-R-07, INT-R-11 |
| CC-11 | P1 | INT-R-15 | 4.2 | `symbol_index.py`, `intelligence_cache_workflow.py`, `background_tasks.py` | No `SymbolIndexWorker`; empty SQLite → degraded metadata | INT-R-14 |
| CC-12 | P1 | INT-R-16 | 4.3 | New `python_structure.py`, `outline_service.py`, `completion_providers.py` | Shared fixture across projections | INT-R-14 |
| CC-13 | P1 | INT-R-13 | 3.4 | `editor_tab_workflow.py`, nav outline cache | Outline off UI thread + AD-018 gate | INT-R-01, INT-R-11 |
| CC-14 | P1 | INT-R-13, INT-R-18 | 3.4, 5.1 | `diagnostics_service.py`, `lint_workflow.py`, nav import analysis | PY200 in Pyflakes mode; probe mock test | INT-R-13 (shell) |
| CC-15 | P1 | INT-R-14 | 4.1 | `file_inventory.py`, callers | One walk per generation spy | — |
| CC-16 | P1 | INT-R-17 | 4.4 | `jedi_engine.py` → split modules | Each module <300 LOC; `test_jedi_engine.py` | INT-R-03 (RLock) |
| CC-17 | P1 | INT-R-18 | 5.2 | `semantic_facade.py`, `refactor_engine.py`, `import_rewrite.py` | Buffer ≠ disk → fail closed | INT-R-12 |
| CC-18 | P1 | INT-R-01, INT-R-10, INT-R-13 | 0.1, 2.4, 3.4 | `editor_stale_result_policy.py`, all async callbacks | Generation bump without edit → no repaint | INT-R-01 |
| CC-19 | P2 | INT-R-02, INT-R-18 | 0.2, 5.3 | `semantic_facade.py`, outline tier metadata | Signature unsupported metadata test | INT-R-02 |
| CC-20 | P2 | INT-R-19 (optional) | 3.3, 4.4 | `semantic_session.py`, host protocols | `cast`/`Any` count reduction | INT-R-13 |
| CC-21 | P2 | INT-R-18 | 5.3 | New tests per §15 | Risk-first tests land | Waves 1–4 |
| CC-22 | P2 | INT-R-02, INT-R-13 | 0.2, 3.3 | Dead code, `import_rewrite.py` move | `rg complete_blocking\|_completion_provider` empty | — |
| CC-23 | P2 | INT-R-02, INT-R-16 | 0.2, 4.3 | `semantic_worker.py`, `outline_service.py` | Worker logs exceptions; outline parser latch | INT-R-02 |

---

## 4. P0 blocker closure checklist

Copy-paste verification after Wave 1 + Wave 2 + Wave 3 P0 slices:

| CC | Done when | Command / test |
|----|-----------|----------------|
| **CC-01** | No UI-thread broker mutation | `rg 'complete_fast\|record_completion_acceptance' app/shell/` → no matches; `test_completion_broker_concurrency.py` passes |
| **CC-02** | Tier separation in envelope + popup | `test_completion_merge_policy.py`: approximate+semantic → distinct tiers; no envelope `confidence="exact"` with approximate items |
| **CC-03** | Cache respects revision | `test_completion_broker.py`: same prefix, revision 1→2 → `_reuse_cached_envelope` returns None |
| **CC-04** | Menu hover/signature async | `test_semantic_navigation_workflow.py`: menu handlers never invoke `resolve_*_blocking` |
| **CC-05** | Single prefix contract | `rg extract_completion_prefix app/editors/` → empty; dotted-member accept tests pass |
| **CC-06** | No file >1k + unified gates | `find app -name '*.py' -exec wc -l {} + \| awk '$1>1000'` → empty; resolve path uses shared gate |
| **CC-07** | Acceptance via workflow | `rg record_completion_acceptance app/shell/editor_tab_factory.py` → routes through workflow |

---

## 5. Wave 0 — R1 hygiene + shared stale gate

**Gate:** `python3 testing/run_test_shard.py fast` + new unit tests per PR.

### Step 0.1 — Extract `editor_stale_result_policy.py` (INT-R-01)

**CC:** CC-18 (partial)

**Depends on:** none

**Create:** `app/shell/editor_stale_result_policy.py`

**Modify:**
- `app/shell/semantic_navigation_workflow.py` — move lines 33–66; re-import helpers
- `app/shell/lint_workflow.py` — replace inline stale checks (lines ~125–133) with `deliver_revision_gated_editor_result`

**Work:**
1. Move `is_stale_revision_gated_editor_request` and `deliver_revision_gated_editor_result`.
2. Add optional `requested_generation: int | None` and `current_generation: int | None`.
3. Stale if: widget identity mismatch OR revision mismatch OR (when both generations provided) generation mismatch.
4. Hard cutover lint `on_success` to shared helper — delete inline checks.

**Hard cutover deletes:** inline stale logic in `lint_workflow.py`.

**Proof:**
```bash
python3 run_tests.py tests/unit/shell/test_editor_stale_result_policy.py
python3 testing/run_test_shard.py fast
```

**Tests (new):** `tests/unit/shell/test_editor_stale_result_policy.py`
- `test_is_stale_when_active_widget_differs`
- `test_is_stale_when_revision_differs`
- `test_is_stale_when_generation_differs`
- `test_deliver_skips_stale` / `test_deliver_runs_when_current`

---

### Step 0.2 — Dead surface + signature metadata + worker logging (INT-R-02)

**CC:** CC-22 (partial), CC-19 (partial), CC-23 (partial)

**Depends on:** none (parallel with INT-R-01)

**Modify:**
- `app/intelligence/semantic_session.py` — delete `complete_blocking` (lines 61–69)
- `app/shell/editor_intelligence_controller.py` — delete `complete_blocking` passthrough (40–41)
- `app/editors/code_editor_semantics.py` — delete sync `_completion_provider` path (153–160); remove unused provider field if dead
- `app/intelligence/semantic_facade.py` — signature unsupported metadata (mirror hover, lines 115–131)
- `app/shell/editor_intelligence_controller.py` — format signature degradation text
- `app/intelligence/semantic_worker.py` — log exceptions in task wrapper (CC-23); no silent swallow

**Hard cutover deletes:** `complete_blocking`, `_completion_provider` sync path.

**Proof:**
```bash
rg 'complete_blocking|_completion_provider' app/   # empty
python3 run_tests.py tests/unit/intelligence/test_semantic_facade.py -k signature
```

**Four themes:** N/A (metadata-only; verify signature menu in one theme smoke).

---

## 6. Wave 1 — P0 session lane + editor prefix contract

**Blocks:** CC-01, CC-04, CC-05, CC-07, CC-09

### Step 1.1 — Worker-serialized broker access (INT-R-03)

**CC:** CC-01, CC-07

**Depends on:** INT-R-01 (recommended), INT-R-02

**Modify:**
- `app/intelligence/semantic_session.py` — add `request_completion_fast` (priority=0, key `completion_fast:{path}`); add `request_record_completion_acceptance` (priority=5); **delete** public sync `complete_fast` (71–74) and sync `record_completion_acceptance` (57–59)
- `app/shell/editor_intelligence_controller.py` — passthrough new request methods; **delete** sync `complete_fast`, `record_completion_acceptance`
- `app/shell/semantic_navigation_workflow.py` — replace line 535 UI `complete_fast` with async fast tier + revision gate; add `record_editor_completion_acceptance`
- `app/shell/editor_tab_factory.py` — line 159: factory → workflow, not controller

**Hard cutover deletes:** UI-thread `complete_fast`; direct acceptance on controller.

**Proof:**
```bash
rg 'complete_fast|record_completion_acceptance' app/shell/   # only request_* variants
python3 run_tests.py tests/unit/intelligence/test_semantic_session.py tests/unit/intelligence/test_completion_broker_concurrency.py
```

**Four themes:** completion popup still paints — verify fast tier in Light + Dark.

---

### Step 1.2 — Async menu hover/signature (INT-R-04)

**CC:** CC-04

**Depends on:** INT-R-01, INT-R-03

**Modify:**
- `app/shell/semantic_navigation_workflow.py` — rewrite `handle_signature_help_action` (252–269), `handle_hover_info_action` (271–288) to async pattern matching `request_inline_*_text_async`; delete `_build_inline_*` blocking wrappers (689–703, 976–990)
- `app/shell/editor_intelligence_controller.py` — delete `build_inline_signature_text`, `build_inline_hover_text`; privatize/remove `resolve_*_blocking` from shell API
- `app/intelligence/semantic_session.py` — remove blocking resolvers from public surface (296–338)

**Proof:** `test_semantic_navigation_workflow.py` — menu never calls blocking resolvers.

**Four themes:** F1/help menu in all four themes — no UI freeze.

---

### Step 1.3 — Single prefix contract (INT-R-05)

**CC:** CC-05

**Depends on:** INT-R-03

**Modify:**
- `app/editors/code_editor_semantics.py` — delete `extract_completion_prefix` import; use `build_completion_context` in `trigger_completion` (106–121) and accept fallback (332–345)
- `app/shell/semantic_navigation_workflow.py` — align popup prefix with `CompletionContext.prefix` (510–521, 555, 637)
- `app/editors/completion_popup/completion_controller.py` — consume broker-provided prefix/replacement only

**Hard cutover deletes:** `from app.intelligence.completion_providers import extract_completion_prefix` in editors.

**Out of scope:** `app/runner/repl_completion.py` keeps `extract_completion_prefix` until REPL track (§14).

**Proof:**
```bash
rg extract_completion_prefix app/editors/   # empty
python3 run_tests.py tests/unit/editors/test_semantic_editor_interactions.py -k prefix
```

**Four themes:** accept dotted completion in HC Light + HC Dark.

---

### Step 1.4 — Per-file navigation worker keys (INT-R-06)

**CC:** CC-09

**Depends on:** INT-R-03

**Modify:** `app/intelligence/semantic_session.py` — keys at lines 150–151, 178–179, 208–209:
- `go_to_definition` → `f"definition:{current_file_path}"`
- `find_references` → `f"references:{current_file_path}"`
- `rename_symbol` → `f"rename:{current_file_path}"`

**Proof:** `test_semantic_session.py` — two-file concurrent nav, both callbacks fire.

**Four themes:** N/A

---

## 7. Wave 2 — Broker merge policy + AD-018 completion cache

**Blocks:** CC-02, CC-03, CC-08, CC-18 (remainder)

### Step 2.1 — Tiered merge policy (INT-R-07)

**CC:** CC-02

**Depends on:** INT-R-03

**Modify:**
- `app/intelligence/completion_models.py` — tiered envelope shape (fast / semantic / runtime sections per §17.4.2)
- `app/intelligence/completion_broker.py` — stop flat extend+rank (107–145); typed `CompletionMergePolicy`; move runtime introspection merge from shell into broker/session
- `app/shell/semantic_navigation_workflow.py` — delete `_merge_completion_items` and runtime merge orchestration (510–600); shell gates + paints pre-merged envelope only
- `app/editors/completion_popup/completion_item_model.py` — tier section headers or distinct `source` styling (lines 96–102)

**Hard cutover deletes:** shell third merge locus; flat ranked list presentation.

**Proof:** `tests/unit/intelligence/test_completion_merge_policy.py`

**Four themes:** tier labels readable in HC modes.

---

### Step 2.2 — Revision-safe cache reuse (INT-R-08)

**CC:** CC-03

**Depends on:** INT-R-03

**Modify:** `app/intelligence/completion_broker.py` — `_reuse_cached_envelope` (222–242):
```python
if context.buffer_revision != cached.context.buffer_revision:
    return None
```
Optional follow-up: key `_result_cache` by fingerprint not `file_path` alone.

**Proof:** `test_completion_broker.py` — revision bump → reuse None.

---

### Step 2.3 — Session `_submit` collapse (INT-R-09)

**CC:** CC-08 (partial)

**Depends on:** INT-R-03

**Modify:**
- `app/intelligence/semantic_session.py` — generic `_submit[T]`; collapse 8× `request_*` boilerplate (76–354)
- Keep `EditorIntelligenceController` as thin shell boundary — delete only redundant duplication, not the port

**Proof:** Session LOC ↓ ~150; parametrized priority table test.

---

### Step 2.4 — Unified async delivery gate (INT-R-10)

**CC:** CC-18 (remainder)

**Depends on:** INT-R-01, INT-R-09

**Modify:** All async editor callbacks use `deliver_revision_gated_editor_result` with generation where applicable:
- Fast completion inline gate (538–544) → shared deliver helper
- Runtime introspection repaint (570–576) → add generation args
- Completion resolve bespoke gate (957–961) → shared helper + widget identity
- Delete sync menu paths (already gone in 1.2)

**Proof:** Generation bump without edit → no repaint test.

**Four themes:** N/A

---

## 8. Nav monolith decomposition map

Reconciles remediation plan module names with TN-INT-SHELL-NAV-15. **Canonical names** (use these in PRs):

| Module | Approx LOC | Owns (current line ranges) | PR |
|--------|----------:|----------------------------|-----|
| `editor_stale_result_policy.py` | 35 | Stale gate (was 33–66) | INT-R-01 |
| `semantic_navigation_host.py` | 215 | Protocol 69–169 + adapter 993–1103 | INT-R-11 |
| `editor_completion_workflow.py` | 175–230 | Merge helper 172–184, completion async 481–659, resolve 933–974 | INT-R-12 |
| `import_analysis_workflow.py` | 65 | Analyze imports 290–352 (deleted after 3.4 lint routing) | INT-R-13 |
| `symbol_navigation_handlers.py` | 220 | Go-to-def 192–250, symbol-in-file 354–391, choose 661–687, refs 705–799 | INT-R-11 |
| `semantic_rename_workflow.py` | 135 | Rename 801–931 | INT-R-12 |
| `inline_intelligence_handlers.py` | 155 | Async hover/signature 393–479 (sync removed in 1.2) | INT-R-11 |
| `semantic_navigation_workflow.py` | 80–120 | Thin coordinator + factory re-export | INT-R-12 |

**Extraction order (dependency-safe):**
1. Stale gate (INT-R-01) — zero behavior change
2. Host protocol (INT-R-11a)
3. Symbol + inline handlers (INT-R-11b)
4. Completion + rename workflows (INT-R-12)
5. Zero imports + lint/outline paths (INT-R-13)

### CC-10: seven intelligence import removal checklist

After INT-R-13, `rg '^from app\.intelligence' app/shell/semantic_*` must be empty. Explicit removals from `semantic_navigation_workflow.py`:

| # | Import | Replacement |
|---|--------|-------------|
| 1 | `build_completion_context` | Controller/session `build_completion_context_for_editor` port |
| 2 | `completion_models.*` | Re-export via `app/shell/intelligence_types.py` (types-only) OR controller return types |
| 3 | `CompletionRequest` | Controller factory method |
| 4 | `find_unresolved_imports`, `CodeDiagnostic` | `LintWorkflow.run_import_analysis` only |
| 5 | `resolve_lint_rule_settings`, severities | Lint workflow / problems controller |
| 6 | `build_outline_from_source`, `flatten_symbols` | Session `request_outline` async |
| 7 | `runtime_introspection.*` | Broker-owned runtime tier (post INT-R-07) |

Document any **types-only** exceptions in module docstring; runtime values must not import intelligence directly.

---

## 9. Wave 3 — CC-10 shell decomposition (R2/R3)

### Step 3.1a — Host + handler extraction (INT-R-11)

**CC:** CC-06 (partial), CC-08 (partial)

**Depends on:** INT-R-01, INT-R-10

**Create:** `semantic_navigation_host.py`, `symbol_navigation_handlers.py`, `inline_intelligence_handlers.py`

**Modify:** `semantic_navigation_workflow.py` — delegate; LOC must drop ≥300.

**Proof:** `wc -l app/shell/semantic_navigation_workflow.py` < 800.

---

### Step 3.1b — Completion + rename extraction (INT-R-12)

**CC:** CC-06 (complete)

**Depends on:** INT-R-07, INT-R-11

**Create:** `editor_completion_workflow.py`, `semantic_rename_workflow.py`

**Modify:** Coordinator ≤120 LOC.

**Proof:**
```bash
find app -name '*.py' -exec wc -l {} + | awk '$1>1000'   # empty
```

---

### Step 3.2–3.4 — Zero imports, composition, outline/lint (INT-R-13)

**CC:** CC-10, CC-13, CC-14 (shell), CC-08, CC-22, CC-18

**Depends on:** INT-R-12, INT-R-07

**Work:**
1. **Zero imports** — seven-import checklist (§8); extend controller or `EditorIntelligencePort`.
2. **Move** `app/intelligence/import_rewrite.py` → `app/project/import_rewrite.py`; hard cutover `project_tree_controller.py` importer.
3. **Extract** `app/shell/intelligence_composition.py` from `main_window_composition.py` (lines 266, 327–344 bootstrap).
4. **Add** `PythonStyleWorkflowHost` Protocol — replace `window: Any` in `python_style_workflow.py`.
5. **Outline:** move `build_outline_from_source` off UI thread in `editor_tab_workflow.py` (234–258); AD-018 gate before panel update; delete nav duplicate (365–370).
6. **Import analysis:** route menu through `LintWorkflow` only; delete nav `handle_analyze_imports_action` duplicate (290–352); rewire `menu_wiring.py:116`.

**Hard cutover deletes:** nav import analysis orchestration; direct outline parse in nav.

**Proof:**
```bash
rg '^from app\.intelligence' app/shell/semantic_*
rg find_unresolved_imports app/shell/semantic_navigation_workflow.py   # empty
```

**Four themes:** outline panel + import analysis in all four themes.

---

## 10. Wave 4 — R4 inventory + python structure SSOT

### Step 4.1 — Project inventory snapshot (INT-R-14)

**CC:** CC-15

**Depends on:** none (parallel after Wave 2b)

**Create:** extend `app/project/file_inventory.py` with `ProjectInventorySnapshot`, `build_project_inventory_snapshot`, `module_names_from_snapshot`

**Modify callers:** `symbol_index.py`, `diagnostics_service.py`, `completion_providers.py`, `import_rewrite.py`, `save_workflow.py`

**Replace:** `_PROJECT_MODULE_CACHE` global in `completion_providers.py:21`

**Proof:** Spy test — one walk per project generation.

---

### Step 4.2 — AD-017 symbol index worker (INT-R-15)

**CC:** CC-11

**Depends on:** INT-R-14

**Modify:**
- Delete `SymbolIndexWorker` thread class (`symbol_index.py:38–71`)
- `IntelligenceCacheWorkflow.start_symbol_indexing` → `GeneralTaskScheduler` in `background_tasks.py`
- Add cache-as-acceleration metadata on empty SQLite reads (`completion_providers.py:135–159`)

**Proof:** AD-017 gate; empty SQLite → degraded not silently empty.

---

### Step 4.3 — `python_structure.py` SSOT (INT-R-16)

**CC:** CC-12, CC-23 (partial — outline parser latch)

**Depends on:** INT-R-14

**Create:** `app/intelligence/python_structure.py` — shared AST extractors + projections

**Modify:** `outline_service.py`, `symbol_index.py`, `completion_providers.py`, `import_diagnostics.py`, diagnostic rules

**Also:** latch tree-sitter parser init in `outline_service.py:113` (CC-23)

**Proof:** Shared parametrized fixture across outline/index/completion tests.

---

### Step 4.4 — Jedi engine split (INT-R-17)

**CC:** CC-16

**Depends on:** INT-R-03 (worker-only; remove redundant RLock)

**Split into:** `jedi_project_cache.py`, `jedi_script_factory.py`, `jedi_mappers.py`, `jedi_definitions.py`, thin `jedi_engine.py` (<200 LOC)

**Create:** `tests/unit/intelligence/test_jedi_engine.py`

**Proof:** `find app/intelligence/jedi*.py -exec wc -l {} +` — no file >300 LOC.

---

## 11. Wave 5 — R5 diagnostics + rename contract

### Step 5.1 — Diagnostics decomposition (INT-R-18a)

**CC:** CC-14

**Depends on:** INT-R-16 (structure SSOT)

**Split `diagnostics_service.py` (~614 LOC) into:**
- `diagnostics_models.py`
- `python_lint_orchestrator.py`
- `pyflakes_adapter.py`
- `import_explanations.py`
- Thin facade or hard cutover imports

**Fix PY200 fork:** Pyflakes mode must still emit `collect_unresolved_import_diagnostics` (lines 167–189 bug).

**Break circular imports** with `import_diagnostics.py`.

**Proof:** Parametrized test — PY200 under default and Pyflakes providers.

---

### Step 5.2 — Static-only lint probe policy (INT-R-18b)

**CC:** CC-14 (probe)

**Depends on:** INT-R-18a

**Modify:**
- `import_diagnostics.py` — `allow_runtime_import_probe=False` on collect path
- `python_style_workflow.py:149` — static only for safe-fix
- Keep probe only: manual lint (`lint_workflow.py:106`), explain, explicit import audit

**Proof:** Mock — `collect_unresolved_import_diagnostics` never calls subprocess.

---

### Step 5.3 — Rename buffer contract + atomic writes (INT-R-18c)

**CC:** CC-17

**Depends on:** INT-R-12

**Work:**
1. Introduce `RenameInputSnapshot` — buffer-aware Rope planning matches Jedi proof.
2. Remove facade relabel branch (`semantic_facade.py:212–219`).
3. Validate `reference_hits` ⊆ patched files before apply.
4. Extract `atomic_write_batch` in `app/persistence/atomic_write.py`; delegate from `refactor_engine.py`, `import_rewrite.py`, `code_actions.py`.

**Proof:** Buffer ≠ disk → fail closed; partial batch failure rollback test.

**Four themes:** rename preview/apply dialog in HC modes.

---

### Step 5.4 — Degradation metadata + risk-first tests (INT-R-18d)

**CC:** CC-19, CC-21

**Depends on:** prior steps

**Work:**
- Outline tier metadata on results
- Session public API tests (no private attr stubbing)
- Gate regression tests from §13

**Proof:** Tests pass; manual acceptance doc update for tier UI.

---

## 12. PR catalog (18 PRs + 1 optional)

| PR | Wave | CC primary | UI / four themes | Parallel batch | Est. LOC Δ (nav) |
|----|------|------------|-------------------|----------------|------------------|
| INT-R-01 | 0.1 | CC-18 | No | B0 | −34 |
| INT-R-02 | 0.2 | CC-22,19,23 | Smoke | B1 | 0 |
| INT-R-03 | 1.1 | CC-01,07 | Yes | B2 | −20 |
| INT-R-04 | 1.2 | CC-04 | Yes | B3 | −30 |
| INT-R-05 | 1.3 | CC-05 | Yes | B3 | 0 |
| INT-R-06 | 1.4 | CC-09 | No | B3 | 0 |
| INT-R-07 | 2.1 | CC-02 | Yes | B4 | −80 |
| INT-R-08 | 2.2 | CC-03 | No | B4 | 0 |
| INT-R-09 | 2.3 | CC-08 | No | B4 | 0 |
| INT-R-10 | 2.4 | CC-18 | No | B4 | −15 |
| INT-R-11 | 3.1a | CC-06 | No | B5 | −350 |
| INT-R-12 | 3.1b | CC-06 | No | B5 | −400 |
| INT-R-13 | 3.2–3.4 | CC-10,13,14 | Yes | B5 | −200 |
| INT-R-14 | 4.1 | CC-15 | No | B6 | 0 |
| INT-R-15 | 4.2 | CC-11 | No | B6 | 0 |
| INT-R-16 | 4.3 | CC-12,23 | No | B6 | 0 |
| INT-R-17 | 4.4 | CC-16 | No | B6 | 0 |
| INT-R-18 | 5.x | CC-14,17,19,21 | Yes | B7 | 0 |
| INT-R-19 | optional | CC-20 | No | after R-13 | 0 |

---

## 13. Parallel execution batches (implementation agents)

Use separate git worktrees/branches per batch row. **Never parallelize** PRs that touch the same files.

| Batch | PRs | Mode | Preconditions |
|-------|-----|------|---------------|
| **B0** | INT-R-01 | Solo | None — start immediately |
| **B1** | INT-R-02 | Solo | Can overlap B0 if different files |
| **B2** | INT-R-03 | **Critical path** | INT-R-01 landed |
| **B3** | INT-R-04, R-05, R-06 | **3 parallel agents** | INT-R-03 |
| **B4** | INT-R-07 → R-08 → R-09 → R-10 | Sequential | INT-R-03; R-10 needs R-01 |
| **B5** | INT-R-11 → R-12 → R-13 | Sequential | B4 complete |
| **B6** | INT-R-14, R-15, R-16, R-17 | **4 parallel agents** | INT-R-08 recommended; avoid B5 file conflicts |
| **B7** | INT-R-18 | Solo (or 18a–d sub-branches) | INT-R-13 + INT-R-16 |

**Aggressive parallelization window:** After INT-R-03 merges, run **B3 (3 agents) + B6 prep branches** for inventory/structure design-only PRs that don't touch `semantic_*`.

**Bottleneck PRs:** INT-R-01, INT-R-03, INT-R-07, INT-R-11.

---

## 14. Out of scope and boundaries

| Item | Disposition | Reference |
|------|-------------|-----------|
| `editor_tab_workflow.py` (937 LOC) full decomposition | Flag only; separate R2 slice | Remediation plan OOS |
| REPL completion deep refactor | Separate track; keep `extract_completion_prefix` in `repl_completion.py` | TN-INT-SHELL-SEAM-7 |
| REPL→editor runtime merge | **Decision required:** Wave 2.1 moves runtime tier to broker; editor must not call `runner_port` for completion (add regression test) | §17.4.8 |
| Console generation-only gate | Document; fix if touched in shell seam PR | TN-INT-SHELL-SEAM-8 |
| R6 full test audit | Risk-first gaps only (§15) | CC-21 |
| CC-20 full typing sweep | Optional INT-R-19 after INT-R-13 | CC-20 |
| `TN-INT-04-11`, `TN-INT-SHELL-EDITORS-10` | Waivable P2 backlog | §1 footnote |
| `api_index` duplicate tuples (CC-23) | Backlog unless touched | TN-INT-04-9 |

---

## 15. Risk-first test register

| Test file | CC | Justification |
|-----------|-----|---------------|
| `tests/unit/shell/test_editor_stale_result_policy.py` | CC-18 | Stale-apply race |
| `tests/unit/intelligence/test_completion_broker_concurrency.py` | CC-01 | Dict mutation under concurrent tiers |
| `tests/unit/intelligence/test_completion_broker.py` (extend) | CC-03 | Revision bump → `_reuse_cached_envelope` returns None |
| `tests/unit/intelligence/test_completion_merge_policy.py` | CC-02 | External tier contract §17.4.2 |
| `tests/unit/shell/test_semantic_navigation_workflow.py` (extend) | CC-04 | Menu handlers never call `resolve_*_blocking` |
| `tests/unit/editors/test_semantic_editor_interactions.py` (extend) | CC-05 | Wrong delete span = user-visible corruption |
| `tests/unit/intelligence/test_semantic_session.py` (extend) | CC-09, CC-21 | Worker key + session boundary |
| `tests/unit/intelligence/test_symbol_index.py` (adapt) | CC-11 | AD-017 scheduler + stale generation gate |
| `tests/unit/intelligence/test_completion_providers.py` (extend) | CC-11 | Empty SQLite → degraded metadata, not silent empty |
| `tests/unit/intelligence/test_python_structure.py` (new) | CC-12 | Shared fixture across outline/index/completion projections |
| `tests/unit/intelligence/test_jedi_engine.py` | CC-16 | Engine boundary + cache |
| `tests/unit/project/test_inventory_snapshot.py` | CC-15 | One-walk orchestration |
| `tests/unit/intelligence/test_diagnostics_py200_pyflakes.py` | CC-14 | Provider fork regression (PY200 under Pyflakes) |
| `tests/unit/intelligence/test_import_diagnostics_probe.py` (new) | CC-14 | `collect_unresolved_import_diagnostics` never subprocess on default path |
| `tests/unit/intelligence/test_rename_buffer_contract.py` | CC-17 | Multi-file refactor safety |
| `tests/unit/persistence/test_atomic_write_batch.py` | CC-17 | Rollback on partial failure |
| `tests/unit/intelligence/test_semantic_facade.py` (extend) | CC-19 | Signature unsupported metadata parity with hover |
| `tests/unit/intelligence/test_semantic_worker.py` (extend) | CC-23 | Worker task exceptions logged, not swallowed |
| `tests/unit/shell/test_lint_workflow_stale_gate.py` (optional) | CC-18 | Lint `on_success` uses shared stale gate |

**Do not add:** constant pinning, `to_dict` snapshots, source-text lint tests, mock-dominated broker-only tests.

---

## 16. Verification gates

### Per-PR (minimum)

```bash
python3 testing/run_test_shard.py fast
npx pyright
```

### Per-wave

| Wave | Extra gates |
|------|-------------|
| 0 | `python3 run_tests.py tests/unit/shell/test_editor_stale_result_policy.py` |
| 1 | P0 checklist §4 (partial) |
| 2 | `python3 run_tests.py tests/unit/intelligence/test_completion_broker.py tests/unit/intelligence/test_completion_merge_policy.py` |
| 3 | `find app -name '*.py' -exec wc -l {} + \| awk '$1>1000'`; `rg '^from app\.intelligence' app/shell/semantic_*` |
| 4 | `python3 run_tests.py tests/unit/intelligence/test_jedi_engine.py` |
| 5 | `python3 run_tests.py tests/unit/intelligence/` + probe mock test |

### Full program (before declaring complete)

```bash
python3 testing/run_test_shard.py fast
python3 testing/run_test_shard.py runtime_parity
python3 run_tests.py tests/unit/intelligence/ tests/integration/intelligence/ tests/runtime_parity/intelligence/
python3 run_tests.py tests/unit/shell/test_semantic_navigation_integration.py
npx pyright
find app -name '*.py' -exec wc -l {} + | awk '$1>1000'
rg 'complete_fast|record_completion_acceptance' app/shell/
rg '^from app\.intelligence' app/shell/semantic_*
rg 'complete_blocking|_completion_provider' app/
rg extract_completion_prefix app/editors/
```

---

## 17. Manual acceptance register (four themes)

Record in each UI PR summary: themes verified + date.

| Scenario | PRs | AT reference |
|----------|-----|--------------|
| Completion tier labeling / popup sections | INT-R-03, R-07 | Completion after edit; verify approximate vs semantic labels |
| Go-to-definition / find references / rename | INT-R-04, R-11, R-12, R-18 | Cross-file navigation; rename preview |
| Outline refresh after edit | INT-R-13 | Outline updates without stale tree |
| Import analysis / problems panel | INT-R-13, R-18 | Analyze imports; PY200 visible |
| Menu hover/signature (no freeze) | INT-R-04 | F1/help responsive |

**Themes:** Light, Dark, HC Light (`#FFFFFF` surfaces), HC Dark (`#000000` surfaces) — per `.cursor/rules/ui_light_dark_mode.mdc`.

---

## 18. Implementation agent playbook

1. Read §4 P0 checklist and §3 CC row for assigned PR.
2. Check **Depends on** — do not start until preconditions merged.
3. Implement with **hard cutover** — delete old path same PR.
4. If touching `semantic_navigation_workflow.py`: `wc -l` must decrease until INT-R-12.
5. Run per-PR gates (§16).
6. Record four themes if UI PR (§17).
7. Update CC matrix status in PR description (`Closes CC-XX`).

### Suggested agent parallel launch (first sprint)

| Agent | PR | Focus |
|-------|-----|-------|
| Agent A | INT-R-01 | Stale gate extract |
| Agent B | INT-R-02 | Dead code + signature metadata |
| — wait for merge — | | |
| Agent C | INT-R-03 | Worker broker lane |
| Agent D | INT-R-04 | Async menu |
| Agent E | INT-R-05 | Prefix contract |
| Agent F | INT-R-06 | Nav keys |

---

## 19. Self-review checklist (plan author — passed 2026-06-16)

- [x] Every CC-01…CC-23 has ≥1 step with concrete file paths
- [x] Every CC has verification gate and primary PR
- [x] Every step lists Depends on (via §3 matrix + §5–11)
- [x] P0 closure table with copy-paste commands (§4)
- [x] Seven intelligence imports explicit checklist (§8)
- [x] Nav LOC monotonic decrease rule (§2)
- [x] Split map reconciled with TN-INT-SHELL-NAV-15 (§8)
- [x] REPL boundary documented (§14)
- [x] Hard cutover deletes enumerated per wave
- [x] CC-20 optional INT-R-19; CC-23 in INT-R-02 + INT-R-16
- [x] Program completion definition (§1)
- [x] Four-theme matrix (§17)
- [x] Step 2.4 / generation proof (§7)
- [x] CC-11 empty SQLite gate (§10 + §15)
- [x] CC-14 probe split (§11 + §15)
- [x] §15 covers all P0/P1 tests referenced in §4–§11
- [x] 18 PRs + optional INT-R-19 (§12)
- [x] Parallel batches with conflict notes (§13)
- [x] Cross-links to AD-016, AD-018, §17.4, ACCEPTANCE_TESTS

**Plan status: implementation-ready.**

---

*Derived from Intelligence Wave 1 thermo review @ `ce17698`. Update CC status columns in PRs; update this document only when scope shifts.*
