# Plugins Wave 1 — Remediation Closure Report

**Date:** 2026-06-22  
**Program:** Plugins Wave 1 remediation (CC-PLUGIN-01 … CC-PLUGIN-07)  
**Baseline review:** [plugins_wave_1_thermo_review_2026-06-22.md](plugins_wave_1_thermo_review_2026-06-22.md) @ `6eb9e4fc8885aab4452efc83da10cf28c9f4fe60`  
**Remediation commit:** `ab854a6ed92f6b4140fd79bc0bf7228a1f17fef7`  
**Verified commit:** `313dbf3` (+ this closure doc)  
**Verdict:** **ACCEPT (Plugins Wave 1 P1 milestones)** — P2 residuals documented below

---

## 1. CC-PLUGIN theme closure matrix

All seven P1 themes from the thermo review **closed** @ remediation commit (present in HEAD ancestry).

| CC | Priority | Status | Evidence |
|----|----------|--------|----------|
| CC-PLUGIN-01 | P1 | **closed** | New `workflow_payload_codec.py` (403 LOC) owns symmetric `serialize_*` / `parse_*`; `runtime_serializers.py` is a 27-line re-export shim; `workflow_adapters.py` delegates to `parse_*` only; `builtin_workflows.py` calls `serialize_pytest_run_result` / `serialize_package_result`; no `_coerce_*`, `_pytest_run_result_to_dict`, or `_package_result_to_dict` |
| CC-PLUGIN-02 | P1 | **closed** | Public `provider_matches_context()` in `workflow_catalog.py:164-184` uses `Path(file_path).suffix.lower()`; `workflow_broker.py` delegates; `_descriptor_matches` deleted; `test_provider_matches_context_uses_path_suffix_for_multi_dot_filenames` |
| CC-PLUGIN-03 | P1 | **closed** | `contributions.py` imports `app.plugins.events` only; shell event dataclass map injected via `resolve_event_type` at composition time (`shell_composition.py:175-190`); `rg 'from app\.shell|import app\.shell' app/plugins/` → empty |
| CC-PLUGIN-04 | P1 | **closed** | Coercion monolith collapsed into codec; `workflow_adapters.py` **196** LOC (was 467) — thin `*_with_workflow` wrappers + typed returns |
| CC-PLUGIN-05 | P1 | **closed** | Editor IPC returns narrowed: `runtime_manager.invoke_*` / `wait_for_workflow_job` → `object`; `workflow_broker.invoke_query` / `run_job` → `tuple[..., WorkflowIpcPayload]`; adapters return per-kind typed tuples; explicit `: Any` count **22 → 8** (remaining: `rpc_protocol.py` wire slots ×2, `builtin_workflows.py` host-side request parsers ×6, `host_runtime.py` host-process invoke ×3) |
| CC-PLUGIN-06 | P1 | **closed** | Dead module-level `_load_runtime_module` removed; `RuntimePluginIndex.iter_command_ids()` public API; `load_runtime_command_handlers` iterates `iter_command_ids()` not `_command_bindings` |
| CC-PLUGIN-07 | P1 | **closed** | `_raise_if_cancelled(is_cancelled)` polled in pytest/packaging builtin job loops; `test_builtin_workflows_cancel.py` covers pre-start cancel for both jobs |

**P2 backlog (deferred, non-blockers):**

| CC | Priority | Status | Notes |
|----|----------|--------|-------|
| CC-PLUGIN-08 | P2 | **deferred** | `manifest.py` still 533 LOC; split when past 600 |
| CC-PLUGIN-09 | P2 | **partial** | String helpers folded into codec module; exception-type unification not pursued |
| CC-PLUGIN-10 | P2 | **deferred** | `PluginApiBroker` still thin pass-through |
| CC-PLUGIN-11 | P2 | **deferred** | Descriptor construction still duplicated in broker |
| CC-PLUGIN-12 | P2 | **deferred** | Contributions lambda registration soup unchanged |
| CC-PLUGIN-13 | P2 | **deferred** | `project_metadata` typed in adapters via `ProjectMetadata \| None` import; full boundary typing optional |
| CC-PLUGIN-14 | P2 | **deferred** | `run_plugin_host.py` IPC loop still at repo root |

---

## 2. Metric gates @ verified baseline

| Metric | Kickoff (2026-06-22 @ `6eb9e4f`) | Closure @ `313dbf3` |
|--------|----------------------------------|---------------------|
| Python files in `app/plugins/` | 23 | **24** (+`events.py`, +`workflow_payload_codec.py`; net +1) |
| Total `app/plugins/` LOC | 4,725 | **4,748** (+23 net) |
| Largest module | `manifest.py` 533 | `manifest.py` **533** (unchanged) |
| `workflow_adapters.py` LOC | 467 | **196** |
| Files ≥700 LOC (smell) | 0 | **0** |
| Files ≥1000 LOC (blocker) | 0 | **0** |
| Explicit `: Any` annotations | 22 | **8** |
| Cross-package `app.shell` imports from plugins | 1 module | **0** |

---

## 3. Grep preservation gates

```text
rg '_coerce_|_pytest_run_result_to_dict|_package_result_to_dict' app/plugins/     → empty
rg '_descriptor_matches' app/plugins/                                              → empty
rg 'from app\.shell|import app\.shell' app/plugins/                                → empty
rg '^def _load_runtime_module' app/plugins/host_runtime.py                           → empty (instance method only)
find app/plugins -name '*.py' -exec wc -l {} + | awk '$1>=700'                      → empty
```

Re-accept criteria from thermo review §8 — all **met**:

- CC-PLUGIN-01: single codec SSOT ✓
- CC-PLUGIN-02: one provider-match function ✓
- CC-PLUGIN-03: no `app.shell` imports from `app/plugins` ✓
- CC-PLUGIN-05: broker/adapter typing materially reduced ✓
- No new file crosses 700 LOC ✓

---

## 4. Architecture gate scorecard (plugins-specific)

| Gate | Kickoff | Closure |
|------|---------|---------|
| 1k-line rule | Pass | **Pass** |
| 700 LOC smell | Pass (watch) | **Pass** |
| Python 3.9 | Pass | **Pass** |
| No dot-prefixed storage paths | Pass | **Pass** |
| Process isolation (AD-005) | Pass | **Pass** |
| Workflow IPC codec SSOT | Fail (CC-PLUGIN-01) | **Pass** |
| Provider context match SSOT | Fail (CC-PLUGIN-02) | **Pass** |
| Layer graph (plugins ↛ shell) | Fail (CC-PLUGIN-03) | **Pass** |
| Hard-cutover / no legacy fallback chains | Pass | **Pass** |

---

## 5. Verification results

| Gate | Result | Notes |
|------|--------|-------|
| `tests/unit/plugins/` | **PASS** | 89 collected, 89 passed @ `313dbf3` |
| New remediation tests | **PASS** | `test_workflow_payload_codec.py`, `test_builtin_workflows_cancel.py`, `test_workflow_catalog.py` provider-match case, updated `test_contributions.py` |
| `npx pyright app/plugins/` | **PASS** | 0 errors, 0 warnings |

---

## 6. Residual debt (non-blockers for P1 ACCEPT)

1. **CC-PLUGIN-08** — Extract `manifest_parsing.py` when `manifest.py` exceeds 600 LOC.
2. **CC-PLUGIN-10/11/12** — Broker façade consolidation and descriptor factory (Wave 2 hygiene).
3. **CC-PLUGIN-14** — Optional move of host IPC loop into `app/plugins/host_main.py`.
4. **Host-runtime `Any`** — `host_runtime.py` invoke paths retain `Any` at the in-process host boundary (acceptable; editor-side typing tightened).

---

## 7. Sign-off

Plugins Wave 1 **P1 remediation milestones are met**: workflow IPC serialize/parse SSOT unified in `workflow_payload_codec.py`, provider matching consolidated, shell layer inversion removed via injected `resolve_event_type`, coercion monolith deleted, dead host-runtime surface removed, and builtin job cancel contract wired. Thermo re-accept criteria from the baseline review are satisfied @ HEAD.

**Next program item:** Update `PROGRAM_STATUS` for plugins-wave-1 ACCEPT; route P2 tail (CC-PLUGIN-08 … CC-PLUGIN-14) to hygiene backlog.
