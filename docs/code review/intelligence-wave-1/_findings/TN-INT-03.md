# TN-INT-03 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-03  
**Date:** 2026-06-16  
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`  
**Scope:** `app/intelligence/jedi_engine.py` (502 LOC), `app/intelligence/jedi_runtime.py` (62 LOC), `app/intelligence/semantic_utils.py` (88 LOC). Cross-read: `app/intelligence/semantic_facade.py`, `app/intelligence/semantic_worker.py`, `tests/unit/intelligence/test_jedi_runtime.py`, `tests/unit/intelligence/test_semantic_utils.py`, `tests/unit/intelligence/test_semantic_facade.py`, `docs/ARCHITECTURE.md` §17.4 / AD-016.

---

## Executive verdict

**Not thermo-clean — approval blocked on structural debt, not behavior.** The slice delivers a working Jedi adapter with sensible extraction of cursor/line helpers into `semantic_utils` and a small runtime bootstrap, but `jedi_engine.py` is already a 502-line orchestration monolith that mixes project lifecycle, six public semantic APIs, completion mapping, reference post-processing, and eight module-level converters behind a single `Any`-typed Jedi boundary. Dominant risks: **inconsistent locking** (RLock held across expensive analysis yet bypassed for cache invalidation and reference disk reads), **silent `except Exception` degradation** on manifest and docstring paths, and a **test vacuum at the engine layer** — all Jedi behavior is probed only through `SemanticFacade` integration tests, so engine refactors lack a direct safety net. Would not approve the next intelligence feature landing inline in `jedi_engine.py` without decomposition and targeted unit tests.

---

### TN-INT-03-1 — `jedi_engine.py` is a 502 LOC monolith absorbing every Jedi concern

- **Persona:** TN-INT-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/jedi_engine.py:1-502` — single module owns `JediEngine` (6 public methods), `_project` cache + manifest wiring, `_ordered_definition_names` dedup/sort policy, reference hit assembly with disk reads, completion list + resolve enrichment, and eight free functions. Only consumer: `SemanticFacade` (`app/intelligence/semantic_facade.py:28`).
- **Code-judo alternative:** Split into focused modules: `jedi_project_cache.py`, `jedi_name_mapping.py`, `jedi_completion_mapping.py`, `jedi_references.py`. Keep `JediEngine` as a thin orchestrator (~120 LOC).
- **Suggested remediation:** Hard cutover in one PR before adding signature/hover/reference edge cases.
- **Tests that would prove fix:** Existing facade tests stay green; new `test_jedi_engine.py` targets extracted pure mappers.
- **Handoff overlap:** R4, AD-016

---

### TN-INT-03-2 — RLock scope is inconsistent: hot path locked, cache + disk I/O not

- **Persona:** TN-INT-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/jedi_engine.py:54-66` — `lookup_definition` holds `self._lock` through `_script`, `infer`, and `goto`. `app/intelligence/jedi_engine.py:98-128` — reference hit assembly **outside** the lock, including `Path.read_text`. `app/intelligence/jedi_engine.py:351-359` — `invalidate_project_cache` mutates cache with **no lock**.
- **Code-judo alternative:** Pick one serialization owner: `SemanticWorker` alone (delete engine RLock) or engine RLock covering all `_project_cache` access including invalidation.
- **Suggested remediation:** Wrap `invalidate_project_cache` in `self._lock`; document invalidation must run on semantic worker thread.
- **Tests that would prove fix:** Thread stress: worker runs `find_references` while another thread calls `invalidate_project_cache`.
- **Handoff overlap:** R4, AD-016

---

### TN-INT-03-3 — RLock serializes expensive Jedi work on top of `SemanticWorker` serialization

- **Persona:** TN-INT-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/semantic_worker.py:24-36` — single background thread. `app/intelligence/jedi_engine.py:34` — `threading.RLock()` on every public method. Double serialization: queue wait + RLock acquire.
- **Code-judo alternative:** Delete `self._lock` and rely on `SemanticWorker` + AD-016 ownership; use debug assert for worker-thread-only calls.
- **Suggested remediation:** Remove RLock after TN-INT-03-2 makes cache invalidation worker-safe.
- **Tests that would prove fix:** Fast shard green; worker queue still serializes concurrent facade calls.
- **Handoff overlap:** R4, AD-016

---

### TN-INT-03-4 — Broad `except Exception` silently degrades manifest and docstring contracts

- **Persona:** TN-INT-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/jedi_engine.py:330-333` — manifest failures become `metadata = None`. `app/intelligence/jedi_engine.py:421-424`, `475-483` — docstring helpers return `""` on any exception.
- **Code-judo alternative:** Catch narrow exceptions; surface structured degradation via `unsupported_metadata` or logged warnings.
- **Suggested remediation:** Replace bare `except Exception` in `_project` and doc helpers.
- **Tests that would prove fix:** Corrupt `cbcs/project.json` asserts degraded metadata, not silent success.
- **Handoff overlap:** R5, AD-016

---

### TN-INT-03-5 — `Any`-typed Jedi boundary forces getattr spaghetti

- **Persona:** TN-INT-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/jedi_engine.py:35` — `_project_cache: dict[..., Any]`. `app/intelligence/jedi_engine.py:368-400` — `_ordered_definition_names` returns `list[Any]` with repeated `getattr` chains throughout.
- **Code-judo alternative:** Frozen `JediNameView` / `JediCompletionView` dataclasses at the Jedi seam.
- **Suggested remediation:** Introduce view types in extracted mapping module.
- **Tests that would prove fix:** Parametrized mapper tests with stub views; pyright clean on engine surface.
- **Handoff overlap:** R5

---

### TN-INT-03-6 — Duplicate completion pipelines in `complete` and `resolve_completion_item`

- **Persona:** TN-INT-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/jedi_engine.py:209-249` vs `251-302` — two scans of `script.complete` with nearly identical `CompletionItem` construction.
- **Code-judo alternative:** Single `_completion_items_from_jedi(..., enrich_label: str | None = None)` helper.
- **Suggested remediation:** Extract shared builder; ensure resolve does not mutate insert text/ranges.
- **Tests that would prove fix:** Mock counter asserts one `script.complete` call per resolve.
- **Handoff overlap:** R2, AD-016

---

### TN-INT-03-7 — `_ordered_definition_names` merges infer + goto with ad-hoc dedup/sort policy

- **Persona:** TN-INT-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/jedi_engine.py:361-400` — concatenates infer + goto, dedupes, sorts with current-file preference. Used by definition and hover paths.
- **Code-judo alternative:** Extract pure `rank_definition_names(names, *, current_file_path)` with documented precedence.
- **Suggested remediation:** Move to `jedi_name_mapping.py`; add module docstring tying to AD-016 definition semantics.
- **Tests that would prove fix:** Direct ranker unit tests mirroring facade shadowed-local tests.
- **Handoff overlap:** R4, AD-016

---

### TN-INT-03-8 — Test vacuum: no direct `jedi_engine` tests

- **Persona:** TN-INT-03
- **Severity:** STRUCTURAL
- **Evidence:** `grep jedi_engine|JediEngine tests/` → no matches. Coverage indirect via `test_semantic_facade.py`, navigation integration, runtime parity only.
- **Code-judo alternative:** Add `tests/unit/intelligence/test_jedi_engine.py` for mappers, ranker, cache invalidation.
- **Suggested remediation:** After TN-INT-03-1 decomposition, unit-test pure helpers; keep facade tests as integration smoke.
- **Tests that would prove fix:** New `test_jedi_engine.py` module.
- **Handoff overlap:** none

---

### TN-INT-03-9 — `semantic_utils.py` undertested for coordinate helpers

- **Persona:** TN-INT-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/intelligence/test_semantic_utils.py` — only `extract_symbol_under_cursor` (2 tests). `offset_to_line_column`, `changed_line_numbers` untested but used on every Jedi call.
- **Code-judo alternative:** Parametrized round-trip tests for line/offset and edit detection.
- **Suggested remediation:** Extend `test_semantic_utils.py` before touching coordinate logic.
- **Tests that would prove fix:** `test_offset_line_column_round_trip`, `test_changed_line_numbers_detects_edits`.
- **Handoff overlap:** none

---

### TN-INT-03-10 — `jedi_runtime` global init has narrow first-call race

- **Persona:** TN-INT-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/jedi_runtime.py:35-36` — check-then-set without lock; `_script` calls init on every query (`jedi_engine.py:311-313`).
- **Code-judo alternative:** `threading.Lock` around first init or lazy import once.
- **Suggested remediation:** Add init lock; keep test-only reset pattern.
- **Tests that would prove fix:** Concurrent init from two threads returns identical status.
- **Handoff overlap:** R3

---

### TN-INT-03-11 — Reference assembly reimplements line fetch instead of canonical utils

- **Persona:** TN-INT-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/jedi_engine.py:109-119` — inline file read cache; `semantic_utils.line_text_at` already canonical.
- **Code-judo alternative:** Pure helper `resolve_reference_line_text(...)` in `semantic_utils`.
- **Suggested remediation:** Extract when splitting TN-INT-03-1.
- **Tests that would prove fix:** Missing file returns empty line text; current-file skips disk.
- **Handoff overlap:** none

---

### TN-INT-03-12 — `invalidate_project_cache` is dead API with unlocked mutation

- **Persona:** TN-INT-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `grep invalidate_project_cache` → only definitions; zero call sites. Cache grows unbounded.
- **Code-judo alternative:** Wire to manifest/import-layout reload on worker, or delete until wired.
- **Suggested remediation:** Fix TN-INT-03-2 locking when connecting; add eviction policy.
- **Tests that would prove fix:** `test_invalidate_project_cache_forces_project_rebuild_on_next_lookup`.
- **Handoff overlap:** R4
