# Python Tools Wave 1 — Remediation Closure Report

**Date:** 2026-06-22  
**Program:** Python Tools Wave 1 (`TN-PYTOOL-INTEG`)  
**Baseline review:** [python_tools_wave_1_thermo_review_2026-06-22.md](python_tools_wave_1_thermo_review_2026-06-22.md) @ `6eb9e4fc8885aab4452efc83da10cf28c9f4fe60`  
**Verified commit:** `313dbf3d36b12a01ca431f814aafd8c38a801566` (+ this closure doc)  
**Verdict:** **ACCEPT (Python Tools Wave 1 — review-only; no remediation PRs)** — P1/P2 themes documented as pre-growth gates

---

## 1. CC-PYTOOL theme closure matrix

Review round was **document-only** (no PYTOOL-R PRs). Thermo integration verdict **ACCEPT** stands @ HEAD: package is thermo-clean at current scale; P1 themes are code-judo backlog, not ship blockers.

| CC | Priority | Status @ `313dbf3` | Evidence / disposition |
|----|----------|-------------------|------------------------|
| CC-PYTOOL-01 | P1 | **deferred (pre-growth)** | Mirror adapter prelude in `black_adapter.py` / `isort_adapter.py`; land shared pipeline before any third transform adapter |
| CC-PYTOOL-02 | P1 | **deferred (pre-growth)** | Double runtime probe in `vendor_runtime.py:86-94`; land module-level ready cache before high-frequency format-on-save |
| CC-PYTOOL-03 | P1 | **deferred (pre-growth)** | `ensure_vendor_path_on_sys_path()` in `config.py:24`; decouple vendor bootstrap from config resolution (Wave 2) |
| CC-PYTOOL-04 | P2 | **deferred** | `tuple[Any, Any, Any]` on `import_python_tooling_modules` — Wave 3 typing polish |
| CC-PYTOOL-05 | P2 | **deferred** | Untyped Black target-version resolver — Wave 3 |
| CC-PYTOOL-06 | P2 | **deferred** | Inline `packaging` import in `config.py` — Wave 3 |
| CC-PYTOOL-07 | P2 | **deferred** | isort syntax-error string heuristic — Wave 3 |
| CC-PYTOOL-08 | P2 | **deferred** | Opaque Python minor encoding — Wave 3 |
| CC-PYTOOL-09 | P2 | **deferred** | Plain `str` status on `PythonTextTransformResult` — Wave 3 |
| CC-PYTOOL-10 | P2 | **deferred** | Dual TOML availability paths (`toml_io` vs `vendor_runtime`) — Wave 2 alignment |
| CC-PYTOOL-11 | P2 | **deferred** | Package naming vs intelligence scope — doc cross-ref only |
| CC-PYTOOL-12 | P2 | **deferred** | Empty `__init__.py` public surface — optional curated re-exports |

**Remediation commits since baseline:** none (`git log 6eb9e4fc..HEAD -- app/python_tools/` empty).

---

## 2. Metric gates @ verified baseline

| Metric | Kickoff @ `6eb9e4fc` | Closure @ `313dbf3` |
|--------|----------------------|---------------------|
| Python modules | 6 | **6** |
| Total LOC | **549** | **549** |
| Largest file | `config.py` — **179** | **179** |
| Files ≥700 LOC | **0** | **0** |
| Files ≥1000 LOC | **0** | **0** |
| `: Any` / `tuple[Any` boundary hits | **8** | **8** (`vendor_runtime.py` 3; `config.py` 5 coercion/TOML surfaces) |
| `dict[str, Any]` TOML coercion surfaces | **3** (+ config-only helpers) | **unchanged** |

**Per-file LOC (sorted):**

| File | Kickoff | Closure |
|------|--------:|--------:|
| `__init__.py` | 1 | 1 |
| `models.py` | 49 | 49 |
| `black_adapter.py` | 85 | 85 |
| `isort_adapter.py` | 92 | 92 |
| `vendor_runtime.py` | 143 | 143 |
| `config.py` | 179 | 179 |

---

## 3. Architecture gate scorecard (AD-010)

| AD-010 requirement | @ `313dbf3` |
|--------------------|-------------|
| In-process vendored Black/isort | **Pass** |
| Project-local `pyproject.toml` only | **Pass** |
| Black final formatting authority | **Pass** |
| No formatter CLI subprocesses | **Pass** |
| Failures must not discard user edits | **Pass** (adapter contract tests) |
| ChoreBoy visible paths (no dot-prefixed dirs) | **Pass** |
| Python 3.9 syntax compliance | **Pass** |
| Hard-cutover legacy fallbacks in package | **Pass** (defensive defaults only) |

---

## 4. Verification results

| Gate | Result | Notes |
|------|--------|-------|
| `tests/unit/python_tools/` | **PASS** | 13 selected — config, black/isort adapters, vendor_runtime |
| `tests/runtime_parity/python_tools/` | **PASS** | 1 selected — vendor runtime + no hidden paths |
| Combined python_tools sweep | **PASS** | **14/14** @ `313dbf3` |
| `npx pyright app/python_tools/` | **PASS** | 0 errors, 0 warnings |
| fast shard | **not rerun** | Targeted sweep only (review closure scope) |
| Four-theme manual | **N/A** | No UI-touching changes this wave |

**Test inventory:**

| Module | Tests |
|--------|------:|
| `test_config.py` | 3 |
| `test_black_adapter.py` | 3 |
| `test_isort_adapter.py` | 4 |
| `test_vendor_runtime.py` | 3 |
| `test_python_format_runtime.py` | 1 |

---

## 5. Conditional acceptance gates (carry forward)

From baseline review §8 — **still in force** before next growth PR:

1. Land **CC-PYTOOL-01** (shared transform pipeline) before any new transform adapter.
2. Land **CC-PYTOOL-02** (runtime ready cache) before wiring format-on-save to high-frequency paths beyond current save workflow.
3. Do **not** add jedi/rope/parso to `app/python_tools/` — keep semantic tooling in `app/intelligence/`.
4. No new module may exceed **400 LOC** without a split plan.

---

## 6. Residual debt (non-blockers for Wave 1 ACCEPT)

1. **P1 adapter/runtime/config coupling** — CC-PYTOOL-01 … CC-PYTOOL-03; presumptive blockers only when adding a third adapter or expanding save-time transform frequency.
2. **P2 typing and SSOT polish** — CC-PYTOOL-04 … CC-PYTOOL-12; route to Waves 2–3 if/when a dedicated PYTOOL remediation slice is scheduled.
3. **Bootstrap seam** — `capability_probe` upward import of `python_tools.vendor_runtime` noted in core-batch review (CC-CORE-07); out of Wave 1 scope.

---

## 7. Sign-off

Python Tools Wave 1 **ACCEPT is confirmed @ `313dbf3`**: metrics unchanged from thermo baseline, AD-010 alignment holds, targeted test sweep **14/14 PASS**, pyright **0 errors**. No remediation was required or landed for this wave; P1 themes remain documented pre-growth gates.

**Next program item:** Update `PROGRAM_STATUS` for `python-tools-wave-1` ACCEPT; continue P2 parallel closures (persistence, plugins, treesitter, core-batch, pytest/templates).
