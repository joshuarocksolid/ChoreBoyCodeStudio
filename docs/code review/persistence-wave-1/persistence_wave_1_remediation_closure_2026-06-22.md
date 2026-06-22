# Persistence Wave 1 — Remediation Closure Report

**Date:** 2026-06-22  
**Program:** Persistence Wave 1 thermo review (TN-PERSIST-INTEG)  
**Baseline review:** [persistence_wave_1_thermo_review_2026-06-22.md](persistence_wave_1_thermo_review_2026-06-22.md) @ `6eb9e4fc8885aab4452efc83da10cf28c9f4fe60`  
**Remediation commit:** **none** — document-only review round (contrast packaging `a9645c1`)  
**Verified commit:** `313dbf3` (+ this closure doc)  
**Verdict:** **ACCEPT (Persistence Wave 1 review + baseline verification)** — P1/P2 CC themes documented as deferred Wave 2 backlog

---

## 1. CC-PERSIST theme closure matrix

| CC | Priority | PR(s) | Status | Evidence / notes |
|----|----------|-------|--------|------------------|
| — | P0 | — | **none** | Zero ship-blocking themes at review baseline |
| CC-PERSIST-01 | P1 | — | **deferred** | `local_history_repository.py` **725** LOC monolith — sole ≥700 smell; no split landed |
| CC-PERSIST-02 | P1 | — | **deferred** | `sqlite_index.py` triplicated symbol `INSERT` + row mappers |
| CC-PERSIST-03 | P1 | — | **deferred** | `settings_store.py` temp+replace without directory fsync vs `atomic_write_text` |
| CC-PERSIST-04 | P1 | — | **deferred** | `local_history_identity.py` imports `ensure_project_id` from `app.project` |
| CC-PERSIST-05 | P1 | — | **deferred** | Triple draft DTO (`DraftEntry`, `LocalHistoryDraft`, `LocalHistoryDraftRecord`) + `AutosaveStore` wrapper |
| CC-PERSIST-06 | P1 | — | **deferred** | `sqlite_index.py` placement + SQLite PRAGMA drift vs `LocalHistorySchema` |
| CC-PERSIST-07 | P1 | — | **deferred** | Per-method `with self._schema.connect()` — no unit-of-work for multi-step ops |
| CC-PERSIST-08 | P2 | — | **deferred** | Dead `merge_window_seconds` + unused history kind constants |
| CC-PERSIST-09 | P2 | — | **deferred** | `local_history_writer.py` returns `Optional[object]` |
| CC-PERSIST-10 | P2 | — | **deferred** | Checkpoint prune does not garbage-collect orphaned blobs |
| CC-PERSIST-11 | P2 | — | **deferred** | Silent settings/blob load failures (default-on-corrupt) |
| CC-PERSIST-12 | P2 | — | **deferred** | `SettingsService` in-process cache without external invalidation |
| CC-PERSIST-13 | P2 | — | **deferred** | `LocalHistoryRepository.resolve_subject` passthrough duplicates store facade |

**Cross-wave overlap (acknowledged, not re-litigated):** Intelligence TN-INT-04 (symbol index split commits) **PARTIAL** — `apply_index_delta` exists; worker still uses split upserts. Project SSOT manifest identity **PARTIAL** — persistence still walks manifest in identity helper (CC-PERSIST-04). Program manifest flags `local_history_repository.py` at 725 LOC — **OPEN** (CC-PERSIST-01).

**Wave 2 remediation sequencing (from review §6):** repository split (W0) → atomic settings + draft cutover (W1–W2, parallel) → symbol-index dedup/move (W3) → identity inversion (W4) → blob GC + typing polish (W5).

---

## 2. Metric gates @ verified baseline

| Metric | Kickoff (2026-06-22 @ `6eb9e4f`) | Closure @ `313dbf3` |
|--------|-----------------------------------|---------------------|
| `local_history_repository.py` LOC | **725** (≥700 smell) | **725** |
| Largest `app/persistence/` module | `local_history_repository.py` 725 | **725** |
| `app/persistence/` files ≥1000 LOC | 0 | **0** |
| `app/persistence/` files ≥700 LOC | 1 (smell) | **1** (`local_history_repository.py`) |
| `window: Any` in `app/persistence/` | 0 | **0** |
| Bare `: Any` parameter | 1 (`settings_store._coerce_schema_version`) | **1** |
| `dict[str, Any]` JSON boundary | 23 | **23** (intentional schemaless settings seam) |
| Total `app/persistence/` LOC | 2,732 (15 files) | **2,732** |
| Dot-prefixed storage paths in package | 0 | **0** |
| Autosave legacy JSON read fallback | removed (hard cutover) | **removed** |

---

## 3. Grep preservation gates

```text
find app/persistence -name '*.py' -exec wc -l {} + | awk '$1>=1000 && $2!="total"'     → empty
find app/persistence -name '*.py' -exec wc -l {} + | awk '$1>=700 && $2!="total"'     → local_history_repository.py 725
rg 'window: Any' app/persistence/                                                      → empty
rg 'from app\.project' app/persistence/                                                → local_history_identity.py (CC-PERSIST-04)
rg 'merge_window_seconds' app/ --glob '*.py' | rg -v 'history_retention.py'            → empty (field dead; CC-PERSIST-08)
rg '\.cbcs/|\.choreboy' app/persistence/                                               → empty
```

---

## 4. Architecture gate scorecard (persistence-specific)

| Gate | Kickoff | Closure |
|------|---------|---------|
| Visible-path storage (`cbcs/`, `choreboy_code_studio_state/`) | Pass | **Pass** |
| Python 3.9 syntax compliance | Pass | **Pass** |
| No `app/` persistence file ≥1000 LOC | Pass | **Pass** |
| Autosave hard cutover (no legacy JSON tree read) | Pass | **Pass** |
| `LocalHistoryStore` facade + schema/rows/blobs/retention split | Pass | **Pass** |
| Canonical `atomic_write_text` for all user-state JSON | Fail (CC-PERSIST-03) | **Fail** (deferred) |
| Persistence free of `app.project.*` imports | Fail (CC-PERSIST-04) | **Fail** (deferred) |
| Symbol index durability / placement | Partial (CC-PERSIST-06) | **Partial** (deferred) |
| Repository below 700 LOC smell threshold | Fail (725 LOC) | **Fail** (deferred) |

---

## 5. Verification results

| Gate | Result | Notes |
|------|--------|-------|
| `python3 run_tests.py tests/unit/persistence/ -q` | **PASS** | **49 passed** @ `313dbf3` |
| `local_history_repository.py` LOC | **PASS** | **725** — below 1k blocker, above 700 smell |
| No `app/persistence/` file ≥1000 LOC | **PASS** | Largest module 725 |
| `npx pyright app/persistence/` | **NOT RUN** | Document-only closure; no production edits |
| `python3 testing/run_test_shard.py fast` | **NOT RUN** | Not required for document-only ACCEPT per review §8 |
| Four-theme manual UI | **NOT APPLICABLE** | No persistence UI changes this wave |

---

## 6. Residual debt (Wave 2 backlog — non-blockers for ACCEPT)

### P1 structural (mandatory before adding repository features)

1. **CC-PERSIST-01** — Split `local_history_repository.py` below 500 LOC per module; do not add features to monolith without split plan.
2. **CC-PERSIST-02** — Deduplicate `sqlite_index.py` symbol SQL and row mappers.
3. **CC-PERSIST-03** — Route `save_json_object` through `atomic_write_text` (single durability contract).
4. **CC-PERSIST-04** — Invert identity dependency: callers pass `ResolvedHistorySubject`; remove manifest walk from persistence.
5. **CC-PERSIST-05** — Hard cutover: delete `AutosaveStore` / `DraftEntry`; collapse draft DTOs.
6. **CC-PERSIST-06** — Move symbol index to intelligence or share SQLite PRAGMA helper.
7. **CC-PERSIST-07** — Expose unit-of-work / optional connection on repository methods.

### P2 hygiene

8. **CC-PERSIST-08** — Implement or delete `merge_window_seconds`; wire or remove kind constants.
9. **CC-PERSIST-09** — Return `Optional[LocalHistoryCheckpoint]` from writer.
10. **CC-PERSIST-10** — Blob GC after checkpoint prune.
11. **CC-PERSIST-11** — Warning logs on corrupt/missing settings/blobs (keep default-on-corrupt).
12. **CC-PERSIST-12** — Document single-writer assumption or mtime check on `SettingsService` cache.
13. **CC-PERSIST-13** — Remove repository `resolve_subject` passthrough.

### Pre-merge gates for future persistence-touching PRs (from review §8)

1. No file in `app/persistence/` may cross **900 LOC** without split plan.
2. New JSON/settings writes should use `atomic_write_text` after CC-PERSIST-03 remediation.
3. No new imports from `app.project.*` into persistence without architecture sign-off.
4. Run `python3 testing/run_test_shard.py fast` and `tests/unit/persistence/` before closing remediation PRs.

---

## 7. Sign-off

Persistence Wave 1 **review + baseline verification milestones are met**: TN-PERSIST-INTEG verdict **ACCEPT** at `6eb9e4f`, zero P0 blockers, no 1k-line violations, successful autosave hard cutover and local-history decomposition, and **49/49** persistence unit tests green @ `313dbf3`. No remediation commit was required for wave landing; seven P1 and six P2 CC themes remain **documented deferred backlog** for Persistence Wave 2 (or cross-wave hygiene), not closure blockers.

**Next program item:** Update `PROGRAM_STATUS` for persistence-wave-1 ACCEPT; route CC-PERSIST-01…13 to Wave 2 implementation plan; enforce pre-merge gates on any persistence-touching PRs until P1 themes land.
