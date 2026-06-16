# Intelligence Wave 1 — Remediation Plan (Phase 2)

Status: ready for implementation approval  
Baseline: `ce176983f3d3434b390718692047583c9b38c4ed`  
Source review: [`intelligence_wave_1_thermo_review_2026-06-16.md`](intelligence_wave_1_thermo_review_2026-06-16.md)  
Integration themes: [`_findings/TN-INT-INTEG.md`](_findings/TN-INT-INTEG.md)

**Do not start implementation until this plan is approved.** Phase 1 (document-only review) is complete.

**Executable plan:** [`intelligence_wave_1_implementation_plan.md`](intelligence_wave_1_implementation_plan.md) — 18 PRs, CC closure matrix, parallel agent batches, verification gates.

---

## Goals

1. Close all **P0** themes CC-01 … CC-07 before new intelligence features.
2. Split **`semantic_navigation_workflow.py`** below 1k LOC (CC-06 / CC-10).
3. Establish **single-owner** broker/session lane (AD-016) and **single stale gate** (AD-018).
4. Advance **R4** inventory and **R5** diagnostics SSOT without long-lived parallel paths.

---

## Non-negotiable rules (every PR)

- Hard cutover — no legacy fallback chains.
- Python 3.9 syntax; no dot-prefixed storage paths.
- `semantic_navigation_workflow.py` LOC must **decrease** in any PR that touches it until split complete.
- Broker mutation (`complete_fast`, `record_acceptance`, cache writes) **worker-serialized only** after Wave 1a.
- One prefix/context owner: `build_completion_context` — delete editor `extract_completion_prefix` import.
- Four-theme manual validation recorded for shell UI changes (see `docs/ACCEPTANCE_TESTS.md`).
- Tests only when risk-first gate applies (thread races, tier merge, revision stale-apply, rename safety).

---

## Wave 0 — R1 hygiene + shared stale gate

**Gate:** `python3 testing/run_test_shard.py fast` + targeted unit tests per PR.

### Step 0.1 — Extract `editor_stale_result_policy.py`

**CC:** CC-18 (partial)

**Files:**
- New: `app/shell/editor_stale_result_policy.py`
- Update: `app/shell/semantic_navigation_workflow.py`, `app/shell/lint_workflow.py`

**Work:**
1. Move `is_stale_revision_gated_editor_request` and `deliver_revision_gated_editor_result` from `semantic_navigation_workflow.py`.
2. Add optional `requested_generation: int | None` parameter for generation-aware drops.
3. Hard cutover `lint_workflow.py` inline stale checks to shared helpers.

**Proof:** Parametrized unit tests: widget mismatch drops; revision mismatch drops; generation mismatch drops.

### Step 0.2 — Dead surface removal

**CC:** CC-22 (partial), CC-19 (partial)

**Work:**
1. Delete unused `complete_blocking` from session + controller if zero callers confirmed.
2. Remove dead sync `_completion_provider` path from `code_editor_semantics.py`.
3. Add signature unsupported metadata in facade (mirror hover) — one-line return shape change.

**Proof:** `rg complete_blocking\|_completion_provider` empty in `app/`.

---

## Wave 1 — P0 session lane + editor prefix contract

**Blocks:** CC-01, CC-04, CC-05, CC-07, CC-09 (partial)

### Step 1.1 — Worker-serialized broker access

**CC:** CC-01, CC-07

**Files:** `semantic_session.py`, `completion_broker.py`, `semantic_navigation_workflow.py`, `editor_tab_factory.py`, `editor_intelligence_controller.py`

**Work:**
1. Add worker task `priority=0` for fast completion tier; remove UI-thread `complete_fast`.
2. Route `record_completion_acceptance` through session queue (via workflow, not factory → controller).
3. Add lock **or** enforce worker-only broker mutation (prefer worker-only per AD-016).

**Proof:** Stress characterization test or documented manual repro showing no dict mutation errors under concurrent fast + semantic paths.

### Step 1.2 — Async menu hover/signature

**CC:** CC-04

**Work:**
1. Replace `handle_hover_info_action` / `handle_signature_help_action` sync paths with async `request_hover_info` / `request_signature_help`.
2. Privatize or delete `resolve_*_blocking` from shell-facing controller API.

**Proof:** Unit test asserts menu handlers never call blocking resolvers.

### Step 1.3 — Single prefix contract

**CC:** CC-05

**Files:** `code_editor_semantics.py`, `completion_context.py`, completion popup

**Work:**
1. Delete `from app.intelligence.completion_providers import extract_completion_prefix`.
2. Use `build_completion_context` (or broker-provided prefix/replacement on items) for trigger gating and accept fallback.
3. Align popup prefix reuse with `CompletionContext.prefix`.

**Proof:** Tests for dotted-member and `from x import y` accept paths — correct replacement span.

### Step 1.4 — Per-file navigation worker keys

**CC:** CC-09

**Work:** Change keys to `f"definition:{path}"`, etc.

**Proof:** Two-file concurrent navigation — both callbacks fire.

---

## Wave 2 — Broker merge policy + AD-018 completion cache

**Blocks:** CC-02, CC-03, CC-08 (partial), CC-18 (remainder)

### Step 2.1 — Tiered merge policy

**CC:** CC-02

**Files:** `completion_broker.py`, `completion_models.py`, shell popup

**Work:**
1. Introduce explicit tier separation in envelope (fast / semantic / runtime) per §17.4.2.
2. Move runtime introspection merge from `semantic_navigation_workflow` into broker/session.
3. Popup renders tier sections or distinct `source` styling — no silent flat merge.

**Proof:** Contract test: approximate items never carry envelope-level `confidence="exact"`.

### Step 2.2 — Revision-safe cache reuse

**CC:** CC-03

**Work:** `_reuse_cached_envelope` must match `buffer_revision` in fingerprint.

**Proof:** Same prefix, revision bump → reuse returns None.

### Step 2.3 — Session submit collapse

**CC:** CC-08

**Work:** Generic `_submit[T]` in `semantic_session.py`; delete controller passthrough duplicates.

**Proof:** Session LOC reduction ~150+; priority table parametrized test.

### Step 2.4 — Unified async delivery gate

**CC:** CC-18

**Work:** All async editor callbacks use `deliver_revision_gated_editor_result` + generation where applicable.

---

## Wave 3 — CC-10 shell decomposition (R2/R3)

**Blocks:** CC-06, CC-10, CC-13 (shell), CC-14 (shell paths)

### Step 3.1 — Split navigation monolith

**CC:** CC-06

**Target modules (from TN-INT-SHELL-NAV-15):**
- `semantic_navigation_host.py` — `MainWindowSemanticNavigationHost`
- `editor_completion_orchestration.py` — async completion + runtime merge (until Wave 2.1 moves merge)
- `import_analysis_workflow.py` — analyze imports action
- `semantic_rename_workflow.py` — rename multi-step flow
- Keep thin `SemanticNavigationWorkflow` coordinator

**Gate:** `find app -name '*.py' -exec wc -l {} + | awk '$1>1000'` → empty.

### Step 3.2 — Zero direct intelligence imports in nav layer

**CC:** CC-10

**Gate:** `rg '^from app\.intelligence' app/shell/semantic_*` → no matches (types-only exceptions documented).

### Step 3.3 — Composition + misplaced modules

**CC:** CC-08, CC-22

**Work:**
1. Move `import_rewrite.py` to `app/project/` (hard cutover importers).
2. Extract intelligence bootstrap from `main_window_composition.py` to `intelligence_composition.py`.
3. `PythonStyleWorkflowHost` Protocol — remove `window: Any`.

### Step 3.4 — Outline + lint shell paths

**CC:** CC-13, CC-14

**Work:**
1. Outline refresh off UI thread via background task + AD-018 gate before panel update.
2. Route import analysis through `LintWorkflow` only; delete duplicate orchestration in nav.

---

## Wave 4 — R4 inventory + python structure SSOT

**Blocks:** CC-11, CC-12, CC-15, CC-16 (partial)

### Step 4.1 — Project inventory snapshot

**CC:** CC-15

**Files:** new snapshot API in `app/project/file_inventory.py`; callers in symbol index, diagnostics, completion providers.

**Gate:** One walk per project generation (metric or spy test).

### Step 4.2 — AD-017 index worker

**CC:** CC-11

**Work:** Replace `SymbolIndexWorker` bespoke thread with bounded scheduler; add cache-as-acceleration metadata on symbol reads.

### Step 4.3 — `python_structure.py` SSOT

**CC:** CC-12

**Work:** Shared AST extractors; outline becomes projection; dedupe completion_providers walks.

### Step 4.4 — Jedi engine split

**CC:** CC-16

**Work:** Split `jedi_engine.py` into mappers + project cache; remove redundant RLock; add `test_jedi_engine.py`.

---

## Wave 5 — R5 diagnostics + rename contract

**Blocks:** CC-14, CC-17, CC-19, CC-21

### Step 5.1 — Diagnostics decomposition

**CC:** CC-14

**Work:**
1. Split `diagnostics_service.py` into focused modules (<400 LOC each).
2. Unified pipeline: syntax + PY200 + provider in all modes (Pyflakes mode must not drop PY200).
3. Static-only default lint path; subprocess probe only on explain/manual audit.

### Step 5.2 — Rename input contract

**CC:** CC-17

**Work:**
1. Rope plans from same buffer snapshot Jedi used for reference proof.
2. Validate `reference_hits` against patches.
3. Shared `atomic_write_batch` for refactor/import_rewrite/code_actions.

### Step 5.3 — Test gap fill (risk-first)

**CC:** CC-21

**Candidates:** broker concurrency, revision gate regressions, `test_jedi_engine.py`, session public API tests (no private attr stubbing).

---

## Verification gate (full program)

Run after each wave; full gate before declaring Phase 2 complete:

```bash
python3 testing/run_test_shard.py fast
python3 testing/run_test_shard.py runtime_parity
python3 run_tests.py tests/unit/intelligence/ tests/integration/intelligence/ tests/runtime_parity/intelligence/
python3 run_tests.py tests/unit/shell/test_semantic_navigation_integration.py
npx pyright
find app -name '*.py' -exec wc -l {} + | awk '$1>1000'
```

**Manual acceptance (four themes):** completion tier labeling, go-to-definition/rename, outline refresh after edit, import analysis — document themes verified in completion summary.

---

## Suggested PR sequence (small reviewable slices)

| PR | Wave step | Est. focus |
|----|-----------|------------|
| INT-R-01 | 0.1 | Stale gate module |
| INT-R-02 | 0.2 | Dead code + signature metadata |
| INT-R-03 | 1.1 | Worker broker lane |
| INT-R-04 | 1.2 | Async menu hover/signature |
| INT-R-05 | 1.3 | Prefix contract cutover |
| INT-R-06 | 1.4 | Per-file nav keys |
| INT-R-07 | 2.1–2.2 | Tier merge + revision cache |
| INT-R-08 | 2.3–2.4 | Session collapse + gate unify |
| INT-R-09 | 3.1 | Nav monolith split (part 1: host + revision) |
| INT-R-10 | 3.1 | Nav monolith split (part 2: completion + rename) |
| INT-R-11 | 3.2–3.4 | Import zero + outline/lint paths |
| INT-R-12 | 4.x | Inventory + structure SSOT |
| INT-R-13 | 5.x | Diagnostics + rename hardening |

---

## Out of scope for this remediation program

- Full `editor_tab_workflow.py` (937 LOC) decomposition — flag only; separate R2 slice if needed.
- REPL completion deep refactor — boundary documented in TN-INT-SHELL-SEAM; separate track.
- R6 full test audit — only risk-first gaps listed in Wave 5.3.

---

*Remediation plan derived from Intelligence Wave 1 thermo review @ `ce17698`. Update this document when CC themes close or scope shifts.*
