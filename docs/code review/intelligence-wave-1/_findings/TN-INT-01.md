# TN-INT-01 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-01  
**Date:** 2026-06-16  
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`  
**Scope:** `app/intelligence/semantic_session.py` (354 LOC), `app/intelligence/semantic_worker.py` (156 LOC), `app/intelligence/semantic_facade.py` (228 LOC), `app/intelligence/completion_service.py` (54 LOC), `app/intelligence/semantic_models.py` (195 LOC). Cross-read: `tests/unit/intelligence/test_semantic_session.py`, `test_semantic_worker.py`, `test_semantic_facade.py`, `test_completion_service.py`; shell seam `app/shell/editor_intelligence_controller.py`, `app/shell/semantic_navigation_workflow.py`. Gates: AD-016, `docs/ARCHITECTURE.md` §17.4.1–§17.4.3.

---

## Executive verdict

**Not thermo-clean — AD-016 ownership is structurally right but two main-path contract violations block approval.** The slice correctly centralizes `SemanticFacade`, `CompletionService`, and `SemanticWorker` under one `SemanticSession`, implements keyed generation stale-skip, completion-first priority, facade degradation metadata, and worker shutdown. `SemanticWorker` tests are strong. Dominant risks: **(1) menu hover/signature still block the Qt UI thread** via `resolve_*_blocking` despite §17.4.3’s non-blocking rule; **(2) `complete_fast` and `record_acceptance` mutate shared `CompletionBroker` state from the UI thread while semantic completion runs on the worker**, creating a real cache/ranking race. Secondary debt: `semantic_session.py` is 354 lines of near-identical `request_*` wrappers (spaghetti-by-copy-paste), global navigation keys cancel cross-file work, and signature-help degradation is silent where hover is explicit. Would not approve further session surface growth without fixing thread ownership for broker mutation, eliminating UI-thread blocking resolvers, and collapsing the submit boilerplate.

---

### TN-INT-01-1 — Menu hover/signature block the Qt UI thread via `resolve_*_blocking`

- **Persona:** TN-INT-01
- **Severity:** BLOCKER
- **Evidence:** `docs/ARCHITECTURE.md:1262` — “Semantic queries must not block the Qt UI thread.” `app/intelligence/semantic_session.py:296-338` — `resolve_hover_info_blocking` / `resolve_signature_help_blocking` call `self._worker.call(...)` with default `timeout_seconds=5.0`, blocking the caller until the worker finishes. `app/shell/editor_intelligence_controller.py:198-220` — `build_inline_*` invokes those blocking resolvers synchronously. `app/shell/semantic_navigation_workflow.py:261-287` — menu actions `handle_signature_help_action` / `handle_hover_info_action` call `build_inline_*` on the UI thread (no revision gate, no async dispatch).
- **Code-judo alternative:** Delete blocking resolvers from the public session API for shell use. Menu actions dispatch the same async paths as the editor (`request_hover_info` / `request_signature_help` with generation + AD-018 gate) and show calltips on success. Keep `worker.call` only for tests or internal diagnostics behind a `@pytest`-only port.
- **Suggested remediation:** Hard cutover menu handlers to async session requests; remove or privatize `resolve_*_blocking` from controller public surface. Pair with TN-INT-SHELL-NAV / TN-SHELL-MW-06-5 shell follow-up.
- **Tests that would prove fix:** Session/controller test asserting menu workflow calls `request_hover_info`, never `resolve_hover_info_blocking`. Characterization test with delayed facade stub: UI thread returns before callback fires.
- **Handoff overlap:** AD-016, R2

---

### TN-INT-01-2 — `complete_fast` and `record_acceptance` race `CompletionBroker` with the worker lane

- **Persona:** TN-INT-01
- **Severity:** BLOCKER
- **Evidence:** `app/intelligence/semantic_session.py:71-74` — `complete_fast` calls `self._completion_service.complete_fast(request)` on the **caller thread** (UI via `semantic_navigation_workflow.py:535`). `app/intelligence/semantic_session.py:57-59` — `record_completion_acceptance` mutates broker acceptance scores from UI (`editor_tab_factory.py:159`). `app/intelligence/semantic_session.py:87-102` — `request_completion` runs `complete_semantic` on `SemanticWorker`. `app/intelligence/completion_broker.py:79-80,152-156,222-229` — `_result_cache` and `_acceptance_scores` are unsynchronized dicts read/written from both threads. `docs/ARCHITECTURE.md:1274` — worker is the only thread for owned semantic state; broker merge/cache is session-owned state touched concurrently.
- **Code-judo alternative:** Route **all** broker entry points through the worker: fast tier as `priority=0` worker tasks (or split broker into lock-free immutable fast tier + worker-only semantic tier). Alternatively, make broker caches thread-safe with one lock owned by session and document “broker only callable from worker” — then delete UI-thread `complete_fast` entirely and use async fast paint + revision gate only.
- **Suggested remediation:** Pick one ownership rule and enforce at session boundary. Prefer worker-serialized broker access to preserve AD-016 single-lane semantics without adding locks everywhere.
- **Tests that would prove fix:** Stress test: worker running `complete_semantic` while UI thread hammers `complete_fast` + `record_acceptance` — no dict mutation errors, deterministic ranking. Or static contract test that session never calls broker except inside worker tasks.
- **Handoff overlap:** AD-016, TN-INT-02

---

### TN-INT-01-3 — `semantic_session.py` is 354 lines of copy-pasted `request_*` submit wrappers

- **Persona:** TN-INT-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/semantic_session.py:76-354` — ten methods follow the identical shape: inner `task` lambda, `self._worker.submit(key=..., task=..., on_success=cast(...), on_error=..., priority=N)`. Only key string, priority int, and facade call differ. `app/shell/editor_intelligence_controller.py:46-188` mirrors the same passthrough surface (~140 LOC duplicated).
- **Code-judo alternative:** One private generic helper, e.g. `_submit[T](*, key, priority, task: Callable[[], T], on_success, on_error)` with proper `Generic` typing — or a small `@dataclass SemanticJobSpec` table mapping operation → `(key_fn, priority, runner)`. Deletes ~200 LOC across session+controller and makes priority policy one file to read.
- **Suggested remediation:** Extract `semantic_session_jobs.py` or collapse to `_submit` in-session before adding any new operation. Hard cutover controller to thin delegate or eliminate passthrough methods by having shell call session directly through a typed port object.
- **Tests that would prove fix:** Existing session/worker tests green; one parametrized test asserting priority table matches §17.4.3 ordering (completion 10 < resolve 5 < hover 30 < definition 40 …).
- **Handoff overlap:** R4

---

### TN-INT-01-4 — Eleven `cast(Callable[[object], None], on_success)` calls paper over worker typing debt

- **Persona:** TN-INT-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/semantic_session.py:99,125,153,181,211,231,261,291,349` — every typed callback is erased and recast at submit boundary. `app/intelligence/semantic_worker.py:38-47` — `submit` accepts `Callable[[object], None]` because `PriorityQueue` tasks are untyped.
- **Code-judo alternative:** Make `SemanticWorker.submit` generic: `def submit[T](..., on_success: Callable[[T], None] | None = None, task: Callable[[], T], ...)`. `_QueuedSemanticTask` stores typed callbacks; delete all session-level casts.
- **Suggested remediation:** Generic worker API first; remove `cast` imports from `semantic_session.py`. pyright on intelligence package should prove callback types end-to-end.
- **Tests that would prove fix:** Typecheck gate (`npx pyright` on `app/intelligence/semantic_session.py`) with zero casts; existing worker stale/priority tests unchanged.
- **Handoff overlap:** none

---

### TN-INT-01-5 — Global navigation keys (`go_to_definition`, `find_references`, `rename_symbol`) cancel unrelated editors

- **Persona:** TN-INT-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/semantic_session.py:151,179,209` — keys are bare operation names, not scoped by `current_file_path` or editor id. Contrast per-file keys: `hover:{current_file_path}`, `completion:{request.current_file_path}`. Worker generation replace (`semantic_worker.py:52-53`) means a definition request in file A invalidates a queued definition in file B.
- **Code-judo alternative:** Uniform key scheme: `f"definition:{current_file_path}"`, `f"references:{current_file_path}"`, etc. — same pattern as hover/completion. One helper `_job_key(operation, file_path)`.
- **Suggested remediation:** Hard cutover key strings in session; document in ARCHITECTURE §17.4.3 that cancel scope is per `(operation, file)` unless explicitly global.
- **Tests that would prove fix:** Worker/session test: submit definition for `a.py`, then `b.py`; both callbacks fire (neither dropped as stale).
- **Handoff overlap:** AD-016

---

### TN-INT-01-6 — `request_custom` is an unbounded AD-016 escape hatch

- **Persona:** TN-INT-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/semantic_session.py:340-354` — exposes arbitrary `task`/`key` on the semantic worker with default `priority=50` and no facade guard. Any caller can run non-facade code on the Jedi/Rope lane or bypass priority policy.
- **Code-judo alternative:** Delete `request_custom` until a concrete extension needs it; add typed extension methods instead. If retained, require `priority`, document invariants, and restrict to internal package (`_request_custom`) with allowlisted keys.
- **Suggested remediation:** Grep for callers; if none outside tests, remove. If needed for shell extensions, move to `semantic_session_extensions.py` with explicit operation enum.
- **Tests that would prove fix:** `rg request_custom` shows zero production callers or all pass through typed wrapper; no arbitrary lambdas in shell.
- **Handoff overlap:** AD-016, R5

---

### TN-INT-01-7 — Hover returns explicit unsupported metadata; signature help returns silent `None`

- **Persona:** TN-INT-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/semantic_facade.py:101-113` — when Jedi fails, hover synthesizes `SemanticHoverResult` with `unsupported_metadata("jedi", unsupported_reason="dynamic_or_unresolved")`. `app/intelligence/semantic_facade.py:129-131` — signature path returns bare `None` with no metadata carrier. §17.4.1 requires typed degradation; AD-009 expects visible confidence/reason, not silent absence.
- **Code-judo alternative:** Mirror hover policy: return `SemanticSignatureResult` with empty signature text and `unsupported_metadata`, or introduce `SemanticSignatureResult | SemanticUnsupportedSentinel` shared with hover. UI can show “unresolved callable” instead of generic “No … available.”
- **Suggested remediation:** Align signature fallback in facade; session/controller formatting already reads metadata for hover — extend formatter for signature unsupported case.
- **Tests that would prove fix:** Extend `test_dynamic_code_returns_explicit_degradation_reason` pattern for signature on dynamic fixture; assert `metadata.unsupported_reason != ""` instead of `None`.
- **Handoff overlap:** R3, AD-016

---

### TN-INT-01-8 — `CompletionService` can construct a second orphan `SemanticFacade`

- **Persona:** TN-INT-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_service.py:32-37` — `semantic_facade or SemanticFacade(cache_db_path=self._cache_db_path)` creates a **new** facade (new `JediEngine`/`RopeRefactorEngine`) when omitted. Session always passes one facade (`semantic_session.py:38-45`), but the optional param invites dual-engine bugs if a future caller constructs `CompletionService` without injection.
- **Code-judo alternative:** Require `semantic_facade: SemanticFacade` (non-optional) on `CompletionService.__init__`; session is the only factory. Tests inject fakes via constructor param on session, not by standalone `CompletionService(...)`.
- **Suggested remediation:** Remove default facade construction; update any direct `CompletionService(cache_db_path=...)` test call sites to pass explicit stub/facade.
- **Tests that would prove fix:** pyright proves `semantic_facade` required; `rg "CompletionService\("` shows all production paths originate from `SemanticSession`.
- **Handoff overlap:** AD-016

---

### TN-INT-01-9 — `complete_blocking` is dead weight on the public session API

- **Persona:** TN-INT-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/semantic_session.py:61-69` — runs full semantic completion synchronously via `worker.call`. `rg complete_blocking` shows only `EditorIntelligenceController` passthrough (`editor_intelligence_controller.py:40-41`); **no shell or test caller** invokes it. Same blocking smell as TN-INT-01-1 but currently unused — API surface still invites UI-thread misuse.
- **Code-judo alternative:** Remove from public API or rename `_complete_blocking_for_tests` behind test helper module. Production completion path is `complete_fast` + async `request_completion` only.
- **Suggested remediation:** Delete method + controller passthrough in hard cutover; keep worker `call` tested directly in `test_semantic_worker.py`.
- **Tests that would prove fix:** `rg complete_blocking` empty in `app/` and `app/shell/`; completion UX unchanged under manual acceptance.
- **Handoff overlap:** none

---

### TN-INT-01-10 — Session-level AD-016 contracts undertested vs worker/facade depth

- **Persona:** TN-INT-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/intelligence/test_semantic_session.py` — two tests stub private `_completion_service` / `_semantic_facade` (`:38`, `:94`); no coverage for `cancel_all`, `shutdown`, `complete_fast` thread routing, priority constants, or `record_completion_acceptance`. `tests/unit/intelligence/test_semantic_worker.py` — strong worker tests but session never asserts `cancel_all()` forwards to worker or that shutdown stops accepts. Worker tests never exercise `cancel_all()` directly.
- **Code-judo alternative:** Session tests through public API with injected worker double (not private attr assignment). Parametrized priority-order test at session boundary. `cancel_all` + `shutdown` characterization tests.
- **Suggested remediation:** Add session integration-style unit tests when fixing TN-INT-01-1/2; delete private attr stubbing per test anti-pattern catalog.
- **Tests that would prove fix:** `test_session_cancel_all_bumps_generation_without_running_stale_callbacks`; `test_session_shutdown_rejects_new_submits`; `test_session_priority_table_matches_architecture`.
- **Handoff overlap:** R5

---

### TN-INT-01-11 — Worker swallows task exceptions when `on_error` is omitted

- **Persona:** TN-INT-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/semantic_worker.py:139-147` — on exception, if `queued.on_error is None`, the worker `continue`s with no log. Session always passes `on_error` from shell for user-facing ops, but `request_custom` and internal `call` paths may not.
- **Code-judo alternative:** Default to logging at warning + optional session-level error hook; or make `on_error` required on `submit` for production builds.
- **Suggested remediation:** Add `_logger.exception` in bare except path; tests assert log when on_error missing.
- **Tests that would prove fix:** Worker unit test: task raises, no on_error → caplog contains exception, no hang.
- **Handoff overlap:** none

---

### TN-INT-01-12 — `SemanticFacade.apply_rename` drops return type annotation

- **Persona:** TN-INT-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/semantic_facade.py:222-223` — `def apply_rename(self, plan: SemanticRenamePlan):` missing `-> SemanticRenameApplyResult` despite `SemanticRenameApplyResult` defined in `semantic_models.py:191-195` and refactor engine contract.
- **Code-judo alternative:** Add return type; pyright proves session `request_apply_rename` callback typing without casts.
- **Suggested remediation:** One-line annotation + import if needed.
- **Tests that would prove fix:** pyright on `semantic_facade.py`; existing rename tests unchanged.
- **Handoff overlap:** none

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| AD-016 single-owner session | Facade + completion + worker composed correctly; broker/UI-thread bypass breaks lane purity (TN-INT-01-1, TN-INT-01-2) |
| Worker priority + stale skip | Implemented and tested at worker level; not validated at session API (TN-INT-01-10) |
| Facade fallback metadata | Strong for definition/references/hover; signature silent (TN-INT-01-7) |
| Shutdown / cancel | Forwarded from session; no session tests; `cancel_all` not tested on worker either (TN-INT-01-10) |
| 1k-line rule | All files well under 1k; risk is duplication growth not single-file sprawl (TN-INT-01-3) |
| Spaghetti | Not branching spaghetti — **copy-paste orchestration spaghetti** across session + controller (TN-INT-01-3) |

**Approval bar:** Block on TN-INT-01-1 and TN-INT-01-2 before expanding session surface. Structural cleanup (TN-INT-01-3 through TN-INT-01-6) should ride along with the blocker fixes, not defer.
