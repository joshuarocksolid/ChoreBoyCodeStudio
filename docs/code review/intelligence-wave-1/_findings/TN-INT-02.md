# TN-INT-02 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-02  
**Date:** 2026-06-16  
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`  
**Scope:** `app/intelligence/completion_broker.py` (453 LOC), `app/intelligence/completion_context.py` (354 LOC), `app/intelligence/completion_providers.py` (433 LOC), `app/intelligence/completion_resolver.py` (50 LOC), `app/intelligence/completion_models.py` (113 LOC), `app/intelligence/completion_metrics.py` (53 LOC). Cross-read: `app/intelligence/completion_service.py`, `app/intelligence/semantic_session.py`, `app/shell/semantic_navigation_workflow.py`, `tests/unit/intelligence/test_completion_service.py`; gates: AD-016, AD-018, `docs/ARCHITECTURE.md` §17.4.1–§17.4.2.

---

## Executive verdict

**Not thermo-clean — merge policy and cache ownership violate §17.4.2 and AD-016 on the main completion path.** The slice correctly extracts tiered `complete_fast` / `complete_semantic`, stamps approximate items with `source`/`confidence`, and surfaces `semantic_engine_error` on Jedi exceptions. Dominant risks: **(1) semantic merge still flattens heuristic and semantic candidates into one ranked list with envelope-level `confidence="exact"`**, which is exactly the silent merge §17.4.2 forbids; **(2) `_result_cache` and `_acceptance_scores` are unsynchronized session state mutated from both the UI thread (`complete_fast`, `record_acceptance`) and `SemanticWorker` (`complete_semantic`)**; **(3) result reuse ignores `buffer_revision` despite fingerprinting it**, so prefix-filtered stale items can paint after edits. Secondary debt: `complete_semantic` re-fans-out all fast providers instead of reusing the fast tier, `_PROJECT_MODULE_CACHE` is a process-global unbounded dict with no thread safety, syntactic-context regexes are duplicated across context/providers, and the declared `CompletionProvider` protocol is dead code while merge policy lives in ad-hoc imperative branches. Would not approve further broker growth without a typed merge policy object, worker-serialized broker mutation, revision-gated reuse, and explicit tier separation for the popup.

---

### TN-INT-02-1 — §17.4.2 violation: semantic merge produces one flat ranked list

- **Persona:** TN-INT-02
- **Severity:** BLOCKER
- **Evidence:** `docs/ARCHITECTURE.md:1257-1258` — “The editor must not silently combine lexical hits and semantic hits under the same feature label.” `app/intelligence/completion_broker.py:116-140` — `complete_semantic` extends fast candidates with semantic candidates, then `_rank_candidates` dedupes into a **single** sorted list with no tier boundary. `app/intelligence/completion_broker.py:294-305` — envelope sets `confidence="exact"` whenever `source_phase == "semantic"` even though the list still contains `source="approximate"` items tagged only in per-item fields. `docs/deslop/AUDIT_app.md:658` — explicit requirement: group with section headers or stamp each item so the formatter renders tiers differently; broker does neither at the envelope layer.
- **Code-judo alternative:** Replace `extend + rank` with a typed `CompletionMergePolicy` that returns `CompletionEnvelope(tiers=(semantic_tier, approximate_tier), …)` or ordered sections with stable headers. Ranking runs **within** tier; UI formatter owns section labels. Delete envelope-level `confidence="exact"` — derive display confidence only from item metadata or tier.
- **Suggested remediation:** Hard cutover broker to emit tiered structure (or `is_incomplete` + `items` grouped by `source` with mandatory sort keys). Update shell popup formatter to render sections; never present mixed tiers as one homogeneous semantic list.
- **Tests that would prove fix:** Contract test: semantic+approximate merge yields two distinguishable tiers; no envelope-level `confidence="exact"` when any item has `source="approximate"`. Golden snapshot of tier ordering under Jedi failure (approximate-only tier visible).
- **Handoff overlap:** AD-016, R4

---

### TN-INT-02-2 — `_result_cache` and `_acceptance_scores` are racy shared mutable state

- **Persona:** TN-INT-02
- **Severity:** BLOCKER
- **Evidence:** `app/intelligence/completion_broker.py:78-80,244-246,152-156` — `_result_cache: dict[str, _CachedCompletionEnvelope]` and `_acceptance_scores: dict[str, int]` with no lock. `app/intelligence/semantic_session.py:71-74` — `complete_fast` invokes broker on **caller thread** (UI). `app/intelligence/semantic_session.py:87-88` — `complete_semantic` invokes broker on `SemanticWorker`. `app/shell/editor_tab_factory.py:159` — `record_acceptance` mutates scores from UI. `docs/ARCHITECTURE.md:1274-1277` — semantic ownership is serialized through one worker lane; broker cache violates that boundary.
- **Code-judo alternative:** **All** broker mutation through the worker (fast tier as highest-priority queued task), or split into immutable fast snapshot + worker-only semantic merge with no shared dicts on UI thread. Locks are a weaker second choice — they preserve dual entry points and complicate AD-016 reasoning.
- **Suggested remediation:** Enforce single-lane broker access at `SemanticSession` boundary (pairs with TN-INT-01-2). If fast paint must stay synchronous, make fast tier pure (no `_remember_envelope` / no acceptance mutation on UI thread) and defer caching to worker-only semantic path.
- **Tests that would prove fix:** Concurrent stress: worker `complete_semantic` + UI `complete_fast` + `record_acceptance` — no `RuntimeError`, no lost updates; or static test that broker is only imported/called from worker tasks.
- **Handoff overlap:** AD-016, TN-INT-01-2

---

### TN-INT-02-3 — Result reuse ignores `buffer_revision` (AD-018 stale apply risk)

- **Persona:** TN-INT-02
- **Severity:** BLOCKER
- **Evidence:** `app/intelligence/completion_context.py:299-307` — `_fingerprint` includes `buffer_revision`. `app/intelligence/completion_broker.py:222-242` — `_reuse_cached_envelope` checks `valid_for.matches`, prefix extension, and prefix filter only; **never** compares `context.buffer_revision` to `cached.context.buffer_revision` or `cached.envelope.buffer_revision`. `app/intelligence/completion_broker.py:223` — cache keyed by `file_path` only, so reuse can serve items computed from an older buffer snapshot if syntactic keys still align after an edit elsewhere in the file.
- **Code-judo alternative:** Make reuse a pure function of `(file_path, buffer_revision, valid_for, prefix)` — reject cache when revision differs. Or delete `_result_cache` until revision-aware invalidation exists; rely on fast provider recompute (already cheap for indexed paths).
- **Suggested remediation:** Add explicit revision gate in `_reuse_cached_envelope`; include `buffer_revision` in cache key or in `CompletionValidFor`. Align with shell AD-018 gate — broker must not be a bypass path for stale items.
- **Tests that would prove fix:** Build envelope at revision 1; mutate source off-cursor; request at revision 2 with same prefix/context — reuse returns `None`, not filtered stale items.
- **Handoff overlap:** AD-018, R5

---

### TN-INT-02-4 — Envelope-level `confidence="exact"` mislabels degraded semantic responses

- **Persona:** TN-INT-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_broker.py:129-141,294-299` — on semantic exception, `degradation_reason = COMPLETION_DEGRADATION_SEMANTIC_ENGINE_ERROR` but `_envelope(..., source_phase="semantic")` still sets `confidence="exact" if source_phase == "semantic"`. `tests/unit/intelligence/test_completion_service.py:121-123` — test asserts degradation_reason but not envelope confidence; approximate-only failure path still carries envelope `confidence="exact"`.
- **Code-judo alternative:** Delete envelope-level `confidence`; use `degradation_reason`, `source_phase`, and per-item `source`/`confidence` only. If an envelope field remains, derive it: `exact` only when semantic tier non-empty **and** no degradation.
- **Suggested remediation:** Set `confidence="approximate"` when `degradation_reason` is set or when no semantic-sourced items survive ranking. Add test assertion on envelope confidence under failure.
- **Tests that would prove fix:** `_FailingSemanticFacade` path → `envelope.confidence == "approximate"` and `degradation_reason == "semantic_engine_error"`.
- **Handoff overlap:** R4, AD-016

---

### TN-INT-02-5 — `complete_semantic` re-runs full fast fan-out instead of reusing the fast tier

- **Persona:** TN-INT-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_broker.py:82-105` — `complete_fast` computes `_fast_candidates`, ranks, caches. `app/intelligence/completion_broker.py:116-117` — `complete_semantic` calls `_fast_candidates(context)` again under telemetry span `fast_providers_for_merge` with **no** read of `_reuse_cached_envelope` or prior fast envelope. UI already painted fast results (`semantic_navigation_workflow.py:535-557`) before semantic work finishes — semantic tier recomputes a potentially different fast set and replaces the popup.
- **Code-judo alternative:** `complete_semantic(fast_envelope: CompletionEnvelope | None)` merges semantic into the **already ranked fast tier** (immutable snapshot from fast phase), or broker stores last fast envelope keyed by `(file_path, fingerprint)` for merge-only semantic pass. Deletes duplicate provider fan-out and stabilizes fast→semantic paint.
- **Suggested remediation:** Pass fast snapshot from session into semantic merge, or have broker retrieve cached fast envelope by fingerprint before semantic call. Single ranking pass after merge.
- **Tests that would prove fix:** Spy on `provide_project_symbol_items` — semantic path does not re-invoke fast providers when valid fast snapshot exists. Semantic popup items are superset of fast items at same revision.
- **Handoff overlap:** TN-INT-01, R4

---

### TN-INT-02-6 — `_PROJECT_MODULE_CACHE` is global, unbounded, and thread-unsafe

- **Persona:** TN-INT-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_providers.py:21` — `_PROJECT_MODULE_CACHE: dict[tuple[str, str], tuple[int, list[str]]] = {}` at module scope, no eviction, no lock. `app/intelligence/completion_providers.py:177-194` — populated from `complete_fast` (UI thread) and `complete_semantic` (worker) via `provide_project_module_items`. Invalidation uses only SQLite file `st_mtime_ns`; filesystem fallback path (`:196-207`) never writes cache, so repeated scans bypass optimization and behave inconsistently.
- **Code-judo alternative:** Move module-name index behind `SQLiteSymbolIndex` (already owns indexed paths) or a session-scoped cache owned by `SemanticSession` with project-scoped invalidation on index rebuild. Delete module-global dict entirely.
- **Suggested remediation:** Session-owned cache with `(project_root, cache_db_path, index_generation)` key; or query index only without second cache layer. Thread safety follows session lane ownership.
- **Tests that would prove fix:** Index rebuild without mtime change (if possible) or explicit invalidation hook clears module list; concurrent access test under worker+UI load.
- **Handoff overlap:** TN-INT-04, AD-016

---

### TN-INT-02-7 — `_result_cache` model: one slot per file, prefix-only refinement

- **Persona:** TN-INT-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_broker.py:223-224,244-246` — `_result_cache.get(context.file_path)` stores a single `_CachedCompletionEnvelope` per file; each new completion overwrites prior cursor contexts. `app/intelligence/completion_broker.py:228-229` — reuse requires `context.prefix.startswith(cached.context.prefix)`, so cache helps only when lengthening the same prefix, not when moving cursor to a different identifier in the same file.
- **Code-judo alternative:** Key cache by `context.fingerprint` (already computed) or `(file_path, valid_for, replacement_start)` instead of file alone. Or remove `_result_cache` — fingerprint already exists for request identity; prefix filtering is cheap relative to semantic Jedi call.
- **Suggested remediation:** Replace file-keyed dict with fingerprint-keyed LRU bounded cache, or delete reuse until model is revision-safe (TN-INT-02-3).
- **Tests that would prove fix:** Complete at identifier A, move to identifier B in same file — no incorrect reuse from A. Prefix extension at same position still reuses when revision matches.
- **Handoff overlap:** AD-018, none

---

### TN-INT-02-8 — Prefix matching rules disagree across reuse, providers, and ranking

- **Persona:** TN-INT-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_context.py:264-269` — `context_matches_prefix` requires `label.lower().startswith(prefix.lower())`. `app/intelligence/completion_providers.py:409-414` — `_matches_prefix` also accepts `prefix_lower in candidate_lower` (substring). `app/intelligence/completion_broker.py:413-427` — `_base_match_score` awards 70 points for substring containment. Reuse filter can drop items the user already saw in fast paint when prefix matching used substring logic in providers.
- **Code-judo alternative:** One canonical `completion_prefix_matches(label, prefix, *, mode: Literal["strict","rank"])`` in `completion_context.py`; providers and broker import it. Reuse and rank share the same contract.
- **Suggested remediation:** Hard cutover to one matcher; document whether substring match is intentional for ranking only and exclude reuse from substring semantics.
- **Tests that would prove fix:** Parametrized cases where substring matches rank but strict prefix does not — reuse behavior matches chosen policy consistently.
- **Handoff overlap:** none

---

### TN-INT-02-9 — Declared `CompletionProvider` protocol is dead; merge policy is imperative spaghetti

- **Persona:** TN-INT-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_broker.py:39-63` — `CompletionProvider` protocol and `CompletionProviderResult` dataclass defined. Grep shows **no** implementors or registry — `_fast_candidates` (`:172-220`) is a nested if-chain calling `provide_*` functions directly. `docs/ARCHITECTURE.md:1272-1273` assigns “fast-provider fan-out, ranking, and semantic merge policy” to `CompletionBroker`, but policy is embedded in unstructured branches, not a composable provider list or merge object.
- **Code-judo alternative:** Either **delete** the unused protocol and document the syntactic dispatcher table explicitly, or **use** it: `FAST_PROVIDERS: tuple[CompletionProvider, ...]` selected by `context.syntactic_context` via a dict, plus `MergePolicy.merge(fast, semantic) -> TieredEnvelope`. Second path deletes the if-chain and makes §17.4.2 merge testable in isolation.
- **Suggested remediation:** Pick one — dead-code deletion (minimal) or provider registry + merge policy module (correct for growth). Do not leave both protocol and imperative fan-out.
- **Tests that would prove fix:** Table-driven test: each `CompletionSyntacticContext` invokes expected provider set; merge policy unit-tested without broker construction.
- **Handoff overlap:** R4

---

### TN-INT-02-10 — Duplicate syntactic-context detection across context and providers

- **Persona:** TN-INT-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_context.py:94-102,190-211` — dotted/import context via `_DOTTED_MEMBER_CONTEXT_PATTERN`, `_IMPORT_FROM_CONTEXT_PATTERN`, etc. `app/intelligence/completion_providers.py:19-20,33-49` — parallel `_MODULE_MEMBER_CONTEXT_PATTERN` and `detect_module_member_completion_context` re-parse the same buffer slice. `completion_context.py:254-261` vs `completion_providers.py:80-87` — `extract_identifier_prefix` duplicates `extract_completion_prefix` with identical regex.
- **Code-judo alternative:** `build_completion_context` is the single classifier; providers receive `CompletionContext` only — delete `detect_module_member_completion_context`, `extract_completion_prefix`, and provider-side regex constants. Module-member provider reads `context.base_expression`, `context.prefix`, `context.module_name`.
- **Suggested remediation:** Hard cutover providers to context fields; remove duplicate patterns. One file owns syntactic classification (`completion_context.py`).
- **Tests that would prove fix:** Delete provider context-detection tests; existing context + integration tests remain green.
- **Handoff overlap:** none

---

### TN-INT-02-11 — Degradation taxonomy stops at exception path; success-path gaps remain

- **Persona:** TN-INT-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_models.py:9` — only `COMPLETION_DEGRADATION_SEMANTIC_ENGINE_ERROR` constant. `app/intelligence/completion_broker.py:115-132` — degradation set only in `except Exception`; empty semantic return (`semantic_candidates = []` without exception) produces no degradation flag while envelope still claims semantic phase. `app/intelligence/completion_models.py:67,70` — `is_incomplete` and `stale_reason` on `CompletionEnvelope` are **never** assigned in broker. `app/intelligence/completion_broker.py:82-87` — fast path never surfaces partial-state metadata for pending semantic refinement.
- **Code-judo alternative:** Typed degradation enum (`semantic_engine_error`, `semantic_empty`, `fast_only`, `unsupported_context`) and set `is_incomplete=True` on fast envelope when semantic follow-up is queued. Success-path empty semantic with approximate items → `degradation_reason="semantic_empty"` or tier label, not silent equivalence.
- **Suggested remediation:** Extend constants; populate envelope fields in both tiers; shell status bar maps reasons (already partially wired at `semantic_navigation_workflow.py:608-614`).
- **Tests that would prove fix:** Stub returning `[]` without raise → explicit degradation or tier marker; fast envelope has `is_incomplete=True` when async semantic pending.
- **Handoff overlap:** R4, AD-016

---

### TN-INT-02-12 — `CompletionBroker` accepts `request: Any` at the merge boundary

- **Persona:** TN-INT-02
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/completion_broker.py:82,107,147,158-170` — `complete_fast(self, request: Any)`, `complete_semantic(self, request: Any)`, `_context_from_request` duck-types `request.source_text`, etc. `app/intelligence/completion_service.py:13-26` — typed `CompletionRequest` exists but broker does not consume it.
- **Code-judo alternative:** Broker methods take `CompletionRequest | CompletionContext`; delete `_context_from_request` duck typing. Typing error at compile time if shell sends wrong shape.
- **Suggested remediation:** Import `CompletionRequest` in broker (or define protocol dataclass in `completion_models.py` shared by service and tests).
- **Tests that would prove fix:** `pyright` on broker with `request: CompletionRequest` — zero errors; remove `Any`.
- **Handoff overlap:** none

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| §17.4.2 engine boundaries | **BLOCKER** — flat merge + envelope `confidence="exact"` (TN-INT-02-1, TN-INT-02-4) |
| Merge policy ownership | Broker owns extend+rank but no tiers; shell adds runtime introspection merge outside broker (TN-INT-02-1, TN-INT-02-5) |
| `_result_cache` thread safety | **BLOCKER** — UI + worker mutation (TN-INT-02-2) |
| `_result_cache` correctness | **BLOCKER** — no `buffer_revision` gate (TN-INT-02-3); weak file-only key (TN-INT-02-7) |
| `_PROJECT_MODULE_CACHE` | **STRUCTURAL** — global, unbounded, racy (TN-INT-02-6) |
| `complete_fast` vs `complete_semantic` | Duplicate fast work; semantic replaces UI paint (TN-INT-02-5) |
| Degradation surfacing | Exception path OK; empty semantic + envelope fields unused (TN-INT-02-11) |
| Provider architecture | Dead protocol + duplicated context regexes (TN-INT-02-9, TN-INT-02-10) |
| File size | All files &lt;500 LOC — no 1k-line violation; decomposition still warranted before growth |
| Handoff to TN-INT-01 | Thread ownership of broker (TN-INT-02-2 ↔ TN-INT-01-2) |
| Handoff to TN-INT-04 | Module cache vs SQLite index ownership (TN-INT-02-6) |
