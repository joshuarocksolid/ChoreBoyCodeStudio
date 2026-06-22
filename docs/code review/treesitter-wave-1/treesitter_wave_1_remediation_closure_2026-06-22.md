# Tree-Sitter Wave 1 — Remediation Closure Report

**Date:** 2026-06-22  
**Program:** Tree-Sitter Wave 1 thermo review + ACCEPT verification  
**Baseline review:** [treesitter_wave_1_thermo_review_2026-06-22.md](treesitter_wave_1_thermo_review_2026-06-22.md) @ `6eb9e4fc8885aab4452efc83da10cf28c9f4fe60`  
**Verified commit:** `313dbf3d36b12a01ca431f814aafd8c38a801566` (+ this closure doc)  
**Verdict:** **ACCEPT (Tree-Sitter Wave 1 thermo bar)** — review-only wave; P1/P2 hardening deferred to follow-on slices

---

## 1. CC-TS theme closure matrix

Thermo review was **document-only** (no remediation PRs in this round). TN-TS-INTEG **ACCEPT** at baseline; metrics and boundary gates **unchanged** @ verified commit (`git log 6eb9e4fc..313dbf3 -- app/treesitter/` → empty).

| CC | Priority | Status | Evidence / notes |
|----|----------|--------|------------------|
| — | P0 | **n/a (none)** | No P0 blockers in thermo review |
| CC-TS-01 | P1 | **deferred** | 31 `: Any` / `-> Any` / `cast(Any)` lines @ HEAD (review baseline 40 incl. container annotations); `runtime_types.py` not landed |
| CC-TS-02 | P1 | **deferred** | Five per-mixin `_host()` Protocol adapters unchanged |
| CC-TS-03 | P1 | **deferred** | `capture_pipeline.py` **671** LOC — under 700 smell gate; split not required for ACCEPT |
| CC-TS-04 | P1 | **deferred** | Injection path still instantiates full `TreeSitterHighlighter` per content node |
| CC-TS-05 | P1 | **deferred** | Sniff heuristics remain in `language_registry.py:177-256` |
| CC-TS-06 | P1 | **deferred** | Markdown/jsonc conditionals remain in `_query_capture_ranges` |
| CC-TS-07 | P2 | **deferred** | `_PointRange` duck-typing seam unchanged |
| CC-TS-08 | P2 | **deferred** | `_query_settings` on locals mixin; injection consumes via Protocol |
| CC-TS-09 | P2 | **deferred** | `_OPEN_FDS` memfd list; no `shutdown_tree_sitter_runtime()` |
| CC-TS-10 | P2 | **deferred** | `_CaptureSpan`, `_PendingEdit` still cross-imported as private types |
| CC-TS-11 | P2 | **deferred** | Parser/Language API version shims in `highlighter_core.py`, `language_registry.py` |
| CC-TS-12 | P2 | **deferred** | Edit-sync + signal orchestration remains in `highlighter_core.py` |

**Cross-wave gates (closed @ baseline, preserved @ HEAD):**

| Prior theme | Status |
|-------------|--------|
| Editors **CC-EDIT-19** (syntax↔treesitter coupling) | **closed** — `rg 'from app\.editors' app/treesitter/` → empty; orchestration in `app/editors/syntax_registry.py` |
| ARCHITECTURE §12.5 highlighter split | **closed** — 11 focused modules + registry/loader |
| Shell syntax palette SSOT | **closed** — `ThemedSyntaxHighlighter` + `syntax_palette` only |
| Python 3.9 / no dot-paths | **closed** — `from __future__ import annotations` on 11/11 modules; no dot-prefixed storage paths |

---

## 2. Metric gates @ verified commit

| Metric | Kickoff (2026-06-22 @ `6eb9e4fc`) | Closure @ `313dbf3` |
|--------|-------------------------------------|---------------------|
| Python modules in `app/treesitter/` | 11 | **11** |
| Total package LOC | 2,469 | **2,469** |
| Files ≥1,000 LOC | 0 | **0** |
| Files ≥700 LOC (smell) | 0 | **0** |
| Largest file | `capture_pipeline.py` **671** | **`capture_pipeline.py` 671** |
| `: Any` / `-> Any` / `cast(Any)` (line matches) | 40 (review sweep) | **31** (same code; narrower rg line count) |
| Dot-prefixed storage paths | 0 | **0** |
| Python 3.10+ syntax (`match`/`case`) | 0 | **0** |
| `app.editors` imports in `app/treesitter/` | 0 | **0** |

### Per-file LOC @ `313dbf3`

| LOC | File |
|----:|------|
| 671 | `capture_pipeline.py` |
| 448 | `highlighter_core.py` |
| 263 | `language_registry.py` |
| 255 | `local_semantics.py` |
| 231 | `loader.py` |
| 151 | `injection_highlights.py` |
| 140 | `language_specs.py` |
| 110 | `jsonc_lexical.py` |
| 94 | `markdown_lexical.py` |
| 81 | `python_tokens.py` |
| 25 | `__init__.py` |

---

## 3. Grep preservation gates

```text
rg 'from app\.editors' app/treesitter/                                    → empty
rg 'from app\.treesitter' app/editors/syntax_registry.py                 → present (correct orchestration seam)
find app/treesitter -name '*.py' -exec wc -l {} + | awk '$1>=700'        → empty
find app/treesitter -name '*.py' -exec wc -l {} + | awk '$1>=1000'       → empty
rg 'match |case ' app/treesitter/*.py                                    → empty (regex `.match` only)
rg '"/\.' app/treesitter/                                               → empty
```

**Conditional guard (TN-TS-INTEG):** Next treesitter PR adding **>30 LOC** to `capture_pipeline.py` must net-split per CC-TS-03 or thermo verdict flips to **REJECT**.

---

## 4. Architecture gate scorecard

| Gate | Kickoff | Closure |
|------|---------|---------|
| No file ≥700/1k LOC | Pass | **Pass** |
| ARCHITECTURE §12.5 editor boundary (no `app.editors` in treesitter) | Pass | **Pass** |
| Intentional module decomposition | Pass | **Pass** |
| Incremental parse + changed-range cache refresh | Pass | **Pass** (code unchanged) |
| `language_specs.py` grammar SSOT | Pass | **Pass** |
| cp39 SOABI binding resolution (no silent wrong-wheel fallback) | Pass | **Pass** (`test_loader.py`) |
| Python 3.9 syntax compliance | Pass | **Pass** |
| No dot-prefixed storage paths | Pass | **Pass** |

---

## 5. Verification results

| Gate | Result | Notes |
|------|--------|-------|
| `tests/unit/treesitter/test_loader.py` | **PASS** (5) | SOABI rejection, memfd load, optional languages |
| `tests/unit/treesitter/test_language_registry.py` | **PASS** (5) | Extension + sniff resolution contracts |
| `tests/unit/treesitter/test_query_contract.py` | **PASS** (2) | Capture→token map + syntax palette reachability |
| `tests/unit/treesitter/` total | **PASS** (12/12) | `python3 run_tests.py tests/unit/treesitter/` @ `313dbf3` |
| `npx pyright app/treesitter/` | **PASS** | 0 errors, 0 warnings |
| fast shard | **not rerun** | Treesitter-only delta empty since baseline; targeted suite green |
| Four-theme manual | **DOCUMENTED GAP** | No UI-visible highlighting changes @ HEAD; defer to release QA if injection/capture refactors land |

---

## 6. Residual debt (non-blockers for ACCEPT)

Follow thermo review §5 fix-agent sequencing when touching this package:

1. **Wave 0 (CC-TS-01)** — `runtime_types.py` Protocol types; reduce mixin `Any` surface.
2. **Wave 1 (CC-TS-03)** — Split `capture_pipeline.py` before it crosses 700 LOC.
3. **Wave 2 (CC-TS-04)** — Headless `capture_spans_for_source` for injection (Qt perf).
4. **Wave 3 (CC-TS-05, CC-TS-06)** — `language_sniff.py` + `LanguageSpanExtension` registry.
5. **Wave 4 (CC-TS-02)** — Unified `TreeSitterHighlighterHost` Protocol.
6. **Wave 5 (CC-TS-07…12)** — Public types, FD lifecycle, query_utils hoist, edit-sync extraction.

---

## 7. Sign-off

Tree-Sitter Wave 1 **meets the thermo ACCEPT bar @ `313dbf3`**: zero files ≥700/1k LOC, clean editors boundary, real incremental-parse pipeline, loader SOABI contract tested, query/token contracts green. No P0 blockers; no treesitter code changes since review baseline. P1/P2 themes remain **documented backlog** for targeted follow-on PRs — not wave blockers per TN-TS-INTEG conditional ACCEPT.

**Next program item:** Update `PROGRAM_STATUS.md` for treesitter-wave-1 ACCEPT; route CC-TS-01/03 to next treesitter feature PR guardrails.
