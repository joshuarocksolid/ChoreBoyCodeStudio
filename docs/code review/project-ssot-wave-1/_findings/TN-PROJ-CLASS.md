# TN-PROJ-CLASS — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-PROJ-CLASS  
**Date:** 2026-06-16  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/project/dependency_classifier.py` (246 LOC), `app/project/dependency_ingest.py` (223 LOC), `app/project/dependency_manifest.py` (130 LOC), `app/plugins/auditor.py` (126 LOC). Cross-read: `tests/unit/project/test_dependency_classifier.py`, `test_dependency_ingest.py`, `test_dependency_manifest.py`, `tests/unit/plugins/test_auditor.py`, `tests/unit/packaging/test_dependency_audit.py`, `tests/unit/intelligence/test_diagnostics_service.py`. Architecture gates: manifest §7 gates 7–8, 10, 12; R5 brief in `docs/deslop/AUDIT_app_remaining_handoff.md`.

---

## Executive verdict

**Not thermo-clean — the classifier module exists but is not yet a true SSOT.** Constants and unit tests are strong, and packaging audit correctly delegates to `classify_module`. Dominant risks: **(1) a deliberate but undocumented policy fork between `classify_module` and `is_module_resolvable` that makes packaging and PY200 diagnostics disagree once a non-empty runtime inventory is loaded** (architecture gate 8); **(2) layer inversion — the project-layer SSOT imports `app.intelligence.import_resolver` and `app.intelligence.runtime_import_probe`** (gate 10); **(3) native-extension detection is implemented three different ways** (`has_compiled_extension_candidate`, ingest archive/directory scans, plugin auditor file walk) with no shared primitive beyond the suffix tuple (gate 12). Secondary debt: ingest and manifest use a parallel `pure_python` / `native_extension` taxonomy that never routes through the classifier; `dependency_ingest` only borrows suffix constants; runtime-inventory semantics are a tri-state (`None`, empty `frozenset()`, non-empty set) with behavior split across functions; and cross-consumer parity tests called out in the wave manifest remain absent. Would not approve R5 completion without unifying resolution policy, inverting the dependency arrow, and collapsing native detection into one named primitive consumed by ingest, audit, and plugin paths.

---

### TN-PROJ-CLASS-1 — `classify_module` and `is_module_resolvable` disagree when runtime inventory is loaded

- **Persona:** TN-PROJ-CLASS
- **Severity:** BLOCKER
- **Evidence:** `app/project/dependency_classifier.py:152-157` — `classify_module` always returns `CATEGORY_STDLIB` when `top_level in STDLIB_TOP_LEVELS`, before consulting `known_runtime_modules`. `app/project/dependency_classifier.py:229-232` — `is_module_resolvable` replaces `STDLIB_TOP_LEVELS` entirely when `known_runtime_modules` is non-empty: `effective_modules = known_runtime_modules if known_runtime_modules else STDLIB_TOP_LEVELS`. `tests/unit/project/test_dependency_classifier.py:134-146` — documents that `json` is **not** resolvable when inventory is `frozenset({"freecad_only_module"})`, while no test asserts the packaging-side `classify_module` outcome for the same case (it would still be `stdlib`). `app/packaging/dependency_audit.py:187-192` — audit uses `classify_module`; `app/intelligence/import_diagnostics.py:41-48` — PY200 uses `is_module_resolvable`.
- **Code-judo alternative:** One resolution core with an explicit `RuntimeInventoryPolicy` enum (`fallback_stdlib`, `inventory_authoritative`, `probe_pending`) passed by callers — or make `is_module_resolvable` a thin adapter over `classify_module` with shared policy, not a second decision tree. Delete the stdlib-first branch from one path or document and test the product rule that packaging labels stdlib while diagnostics flags slim-runtime gaps.
- **Suggested remediation:** Pick one authoritative rule for “runtime inventory loaded” and implement it once. If diagnostics’ slim-inventory behavior is correct, move stdlib membership behind the same gate in `classify_module` (or add `CATEGORY_RUNTIME_STDlib` only when inventory confirms). Add parametrized parity tests for representative modules (`json`, `tomllib`, `FreeCAD`, vendored native).
- **Tests that would prove fix:** `tests/unit/project/test_dependency_classifier_parity.py` (new): for each `(module, inventory)` tuple, assert explicit expected `(classify_module.category, is_module_resolvable)` pair or a documented exception table; packaging + diagnostics integration fixtures must match.
- **Handoff overlap:** R5, CC-14 (gate 8)

---

### TN-PROJ-CLASS-2 — Project-layer SSOT imports intelligence resolver and runtime probe (layer inversion)

- **Persona:** TN-PROJ-CLASS
- **Severity:** BLOCKER
- **Evidence:** `app/project/dependency_classifier.py:33-34` — `from app.intelligence.import_resolver import resolve_project_import` and `from app.intelligence.runtime_import_probe import is_runtime_module_importable`. `00-manifest.md` architecture gate 10 — “Dependency direction should be `intelligence -> project`, not `project -> intelligence`.” `app/intelligence/import_resolver.py:11-15` — resolver itself lives under intelligence but already depends on `app.project.import_layout` (filesystem layout is project-owned; probe is intelligence-owned).
- **Code-judo alternative:** Split `resolve_project_import` into `app/project/import_resolution.py` (filesystem + layout only, no probe). Move runtime probe orchestration to intelligence; intelligence adapters call project primitives and add probe layers. Classifier becomes pure project policy composing layout resolution + category labels; intelligence diagnostics import classifier, not the reverse dependency for probes.
- **Suggested remediation:** Extract project-owned `resolve_project_import` (layout bases only) into `app/project/`. Keep `allow_runtime_import_probe` path in intelligence facade that wraps project resolution. Update classifier imports to project-only modules; pyright proves `app/project/dependency_classifier.py` has zero `app.intelligence` imports.
- **Tests that would prove fix:** Move existing `tests/unit/intelligence/test_import_resolver.py` layout cases to `tests/unit/project/`; classifier tests unchanged; `rg "from app\.intelligence" app/project/dependency_classifier.py` empty.
- **Handoff overlap:** R5 (gate 10)

---

### TN-PROJ-CLASS-3 — Native-extension detection is forked three ways with different scan semantics

- **Persona:** TN-PROJ-CLASS
- **Severity:** BLOCKER
- **Evidence:** `app/project/dependency_classifier.py:106-120` — `has_compiled_extension_candidate` globs `{top_level}*{suffix}` at base and `*{suffix}` inside `base/top_level/` only. `app/project/dependency_ingest.py:175-201` — `_classify_wheel` / `_classify_zip` scan **any** archive member ending in suffix; `_classify_directory` uses `dir_path.rglob("*")` with `child.suffix in _COMPILED_EXTENSION_SUFFIXES`. `app/plugins/auditor.py:48-66` — `rglob("*")` + `path.suffix.lower() in _NATIVE_EXTENSION_SUFFIXES` on installed plugin tree. All share `COMPILED_EXTENSION_SUFFIXES` but not scan scope or naming rules. `tests/unit/project/test_dependency_ingest.py:78-90` — ingest native tests never call `has_compiled_extension_candidate`; `tests/unit/plugins/test_auditor.py:35` — only exercises `.so`, not `.pyd`/`.dll`.
- **Code-judo alternative:** One module `app/project/native_extension_scan.py` with typed entry points: `scan_vendor_tree(base, top_level)`, `scan_archive_namelist(names)`, `scan_directory_tree(path)`, `scan_plugin_package(root)` — each implemented in terms of shared suffix + path rules. Ingest, classifier, and auditor become thin callers; delete duplicated loops.
- **Suggested remediation:** Extract primitive; migrate ingest `_classify_*` and auditor suffix walk to it; align wheel/zip semantics with post-extract vendor layout expectations (top-level package vs any nested `.so`).
- **Tests that would prove fix:** Parametrized fixture matrix: same synthetic tree/wheel classified identically by ingest, `has_compiled_extension_candidate`, and plugin auditor where domains overlap; regression for `vendor/fastthing*.so` only-so case (`test_dependency_classifier.py:76-84`).
- **Handoff overlap:** R5 (gate 12)

---

### TN-PROJ-CLASS-4 — `dependency_ingest` classifies packages without calling the classifier SSOT

- **Persona:** TN-PROJ-CLASS
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/dependency_ingest.py:38-47` — public `classify_package_path` delegates to private `_classify_wheel` / `_classify_zip` / `_classify_directory`, not `classify_module` or a shared native primitive. `app/project/dependency_ingest.py:10` — imports only `COMPILED_EXTENSION_SUFFIXES` from classifier. `app/project/dependency_manifest.py:16-18` — persists `CLASSIFICATION_PURE_PYTHON` / `CLASSIFICATION_NATIVE_EXTENSION` strings unrelated to classifier `CATEGORY_*` labels. Ingest never updates manifest via classifier after extract.
- **Code-judo alternative:** Ingest calls `scan_archive_for_native_extensions` (from TN-PROJ-CLASS-3 primitive) and maps result to manifest constants via one `to_manifest_classification(is_native: bool)` helper — or store classifier-aligned labels in manifest v2. Delete parallel `_classify_*` trio.
- **Suggested remediation:** Route ingest classification through shared native scan; add explicit mapping table manifest ↔ audit categories in one module (see TN-PROJ-CLASS-5).
- **Tests that would prove fix:** Ingest native/pure tests assert same outcome as native scan primitive on identical fixtures; manifest entry classification stable after re-ingest.
- **Handoff overlap:** R5

---

### TN-PROJ-CLASS-5 — Manifest taxonomy and classifier category taxonomy are parallel unmapped planes

- **Persona:** TN-PROJ-CLASS
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/dependency_manifest.py:16-18` — `pure_python | native_extension | runtime` (ingest bookkeeping). `app/project/dependency_classifier.py:88-93` — `stdlib | first_party | vendored | vendored_native | runtime | missing` (import resolution). `app/packaging/dependency_audit.py:35-42` — `_CATEGORY_TO_CLASSIFICATION` maps classifier → audit strings (duplicate naming: `vendored_native` vs manifest `native_extension`). No function maps manifest entries to import categories or vice versa; `cbcs/dependencies.json` is invisible to `classify_module`.
- **Code-judo alternative:** Single typed enum module `DependencyTaxonomy` with views: `ImportCategory`, `ManifestClassification`, `AuditClassification` and explicit `convert()` functions — or collapse manifest to store audit-aligned strings. Manifest `runtime` source entries should feed `known_runtime_modules`, not a third vocabulary.
- **Suggested remediation:** Document and implement one conversion module; decide whether manifest native flag is advisory or authoritative for packaging blocks.
- **Tests that would prove fix:** Round-trip tests: ingest native wheel → manifest `native_extension` → `classify_module("pkg")` → `vendored_native`; no string literals duplicated across three modules.
- **Handoff overlap:** R5

---

### TN-PROJ-CLASS-6 — Runtime inventory tri-state (`None`, empty, non-empty) is implicit and inconsistently documented

- **Persona:** TN-PROJ-CLASS
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/dependency_classifier.py:184` — `if known_runtime_modules and top_level in known_runtime_modules` treats empty `frozenset()` as “no inventory” (falsy). `app/project/dependency_classifier.py:229-230` — `is_module_resolvable` uses empty frozenset as falsy → falls back to `STDLIB_TOP_LEVELS`. `tests/unit/intelligence/test_diagnostics_service.py:467-479` — expects stdlib not flagged when `known_runtime_modules=frozenset()`. `tests/unit/packaging/test_dependency_audit.py:19` — audit passes `known_runtime_modules=frozenset()` expecting stdlib/missing behavior via `classify_module` stdlib-first path. Non-empty inventory triggers TN-PROJ-CLASS-1 fork. Callers (`test_runtime_probe_relint.py:143`, shell workflows) pass empty set to mean “probe pending” vs `None` meaning “use fallback” — same runtime behavior today, different future hazard.
- **Code-judo alternative:** Replace `frozenset[str] | None` with `RuntimeModuleInventory` dataclass: `state: Literal["unknown", "empty", "loaded"]`, `modules: frozenset[str]` — eliminates truthiness bugs and makes policy explicit at type level.
- **Suggested remediation:** Introduce typed inventory carrier; normalize at shell probe boundary; document in classifier module docstring.
- **Tests that would prove fix:** Three explicit tests for `unknown`/`empty`/`loaded` states; no reliance on `if frozenset()` truthiness.
- **Handoff overlap:** R5, TN-PROJ-DIAG

---

### TN-PROJ-CLASS-7 — `is_module_resolvable` is a second classifier engine instead of an adapter

- **Persona:** TN-PROJ-CLASS
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/dependency_classifier.py:212-246` — reimplements top-level membership, `resolve_project_import`, and probe gate independently of `classify_module` (lines 123-209). Module docstring lines 7-11 acknowledges “two slightly different classifier implementations” were unified into one file but kept as two functions with divergent stdlib policy. No shared `_resolve_category()` helper; duplication guarantees future drift beyond stdlib ordering.
- **Code-judo alternative:** Implement `is_module_resolvable` as `return classify_module(..., policy=RESOLVABILITY_POLICY).category not in (CATEGORY_MISSING,)` with policy controlling stdlib vs inventory — one branch tree, two public facades.
- **Suggested remediation:** Collapse to single classification pipeline; export policy enum for diagnostics vs packaging if product requires different labels, not different resolution.
- **Tests that would prove fix:** All existing classifier + diagnostics tests green with one internal function; delete redundant branches in `is_module_resolvable`.
- **Handoff overlap:** R5, CC-14

---

### TN-PROJ-CLASS-8 — `classify_module` disables runtime inventory during filesystem resolution

- **Persona:** TN-PROJ-CLASS
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/dependency_classifier.py:159-165` — calls `resolve_project_import(..., known_runtime_modules=frozenset(), allow_runtime_import_probe=False)` even when caller supplied `known_runtime_modules`. Contrast `app/intelligence/import_resolver.py:36-37` — resolver honors inventory for early resolve. Effect: `classify_module` always filesystem-probes before runtime category (steps 2 then 3), while `is_module_resolvable` can short-circuit on inventory without filesystem. A module only in runtime inventory but shadowed by a broken project path prefix could classify differently between the two APIs.
- **Code-judo alternative:** Pass through `known_runtime_modules` to `resolve_project_import` consistently, or document that audit intentionally ignores runtime during filesystem pass — then remove runtime short-circuit from resolver for packaging callers.
- **Suggested remediation:** Align parameter forwarding; add test where project stub path exists but runtime inventory is authoritative.
- **Tests that would prove fix:** Fixture: empty `vendor/foo/__init__.py` stub + `import FreeCAD` with inventory containing `FreeCAD` — both APIs agree on runtime vs first_party.
- **Handoff overlap:** R5

---

### TN-PROJ-CLASS-9 — Module docstring advertises a re-export that does not exist

- **Persona:** TN-PROJ-CLASS
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/project/dependency_classifier.py:22-24` — docstring lists `:func:`resolve_project_import`` as “re-exported from :mod:`app.intelligence.import_resolver``” but the symbol is not imported in `__all__` or re-exported at module level (only used internally at line 159). Misleading for R5 “one public module” consumers searching for canonical import resolution entry point.
- **Code-judo alternative:** Either re-export `resolve_project_import` from project layer after moving it (TN-PROJ-CLASS-2), or delete the re-export claim from the docstring.
- **Suggested remediation:** Fix docstring now; re-export only after layer inversion is resolved.
- **Tests that would prove fix:** Docstring/code consistency review; optional `test_dependency_classifier_public_api` asserting exported names match `__all__`.
- **Handoff overlap:** R5

---

### TN-PROJ-CLASS-10 — `STDLIB_TOP_LEVELS` embeds runtime policy inside project SSOT without probe coupling

- **Persona:** TN-PROJ-CLASS
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/dependency_classifier.py:42-83` — 40+ line hardcoded Python 3.9 stdlib frozenset with comment “broad but not exhaustive”. `tests/unit/intelligence/test_diagnostics_service.py:498-510` — `tomllib` flagged when fallback active (3.11-only module). Packaging with `known_runtime_modules=frozenset()` still classifies `json` as stdlib via step 1 regardless of ChoreBoy AppRun reality. No linkage to `app/bootstrap/runtime_module_probe.py` output for packaging audit when inventory unavailable.
- **Code-judo alternative:** Move stdlib fallback list next to runtime probe bootstrap; project classifier accepts `stdlib_fallback: frozenset[str]` injected from bootstrap defaults — single maintenance point for “ChoreBoy 3.9 surface”.
- **Suggested remediation:** Co-locate with probe; version the fallback set; document diff vs CPython 3.9 for packaging acceptance.
- **Tests that would prove fix:** Probe snapshot test: every module in fallback imports successfully on reference AppRun or is documented exception.
- **Handoff overlap:** R5, TN-PROJ-DIAG

---

### TN-PROJ-CLASS-11 — Cross-consumer parity tests absent despite strong unit matrix

- **Persona:** TN-PROJ-CLASS
- **Severity:** STRUCTURAL
- **Evidence:** `00-manifest.md` test gap table — “Classifier vs packaging audit vs diagnostics parity | None | **High**”. `tests/unit/project/test_dependency_classifier.py` — 15 focused unit tests, no `allow_runtime_import_probe` case for `classify_module`, no packaging/diagnostics cross-import. `tests/unit/packaging/test_dependency_audit.py` — never asserts stdlib import classification with loaded inventory. `tests/unit/intelligence/test_diagnostics_service.py` — exercises `is_module_resolvable` indirectly but not vs `classify_module` on same fixture.
- **Code-judo alternative:** One parametrized parity module under `tests/unit/project/test_dependency_classifier_parity.py` consumed by packaging and intelligence test modules via shared fixtures (not copy-paste).
- **Suggested remediation:** Add parity suite as R5 acceptance gate before closing wave.
- **Tests that would prove fix:** Manifest gap row flips to Low; CI runs parity module in fast shard.
- **Handoff overlap:** R5, R6

---

### TN-PROJ-CLASS-12 — Plugin auditor shares suffix constants but not scan primitive or policy doc

- **Persona:** TN-PROJ-CLASS
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/plugins/auditor.py:9-11` — imports `COMPILED_EXTENSION_SUFFIXES` only. `app/plugins/auditor.py:59-66` — phase-1 plugin policy blocks **any** native suffix in package; classifier `has_compiled_extension_candidate` scopes to import top-level under `vendor/`. Correct product difference, but undocumented in SSOT module — future suffix changes require remembering plugin walk is intentionally broader. `tests/unit/plugins/test_auditor.py:35` — uses `native.so` only.
- **Code-judo alternative:** Import shared `iter_native_extension_paths(root)` from native scan primitive with `scope="plugin_package"` vs `scope="vendor_top_level"` parameter — suffix list stays one constant, scan policy is named.
- **Suggested remediation:** After TN-PROJ-CLASS-3, wire auditor to primitive; extend auditor test to `.pyd` rejection using constant tuple.
- **Tests that would prove fix:** `test_audit_plugin_package_rejects_pyd_extension` parametrized over `COMPILED_EXTENSION_SUFFIXES`.
- **Handoff overlap:** R5, R7 (plugin boundary only)

---

## Summary table

| ID | Severity | Theme |
|----|----------|-------|
| TN-PROJ-CLASS-1 | BLOCKER | `classify_module` vs `is_module_resolvable` policy fork |
| TN-PROJ-CLASS-2 | BLOCKER | Layer inversion (`project` → `intelligence`) |
| TN-PROJ-CLASS-3 | BLOCKER | Native-extension detection fork |
| TN-PROJ-CLASS-4 | STRUCTURAL | Ingest bypasses classifier |
| TN-PROJ-CLASS-5 | STRUCTURAL | Manifest vs category taxonomy |
| TN-PROJ-CLASS-6 | STRUCTURAL | Runtime inventory tri-state |
| TN-PROJ-CLASS-7 | STRUCTURAL | Duplicate classifier engines |
| TN-PROJ-CLASS-8 | STRUCTURAL | Inventory stripped during resolve |
| TN-PROJ-CLASS-9 | NICE-TO-HAVE | Misleading re-export docstring |
| TN-PROJ-CLASS-10 | STRUCTURAL | Stdlib fallback ownership |
| TN-PROJ-CLASS-11 | STRUCTURAL | Missing cross-consumer parity tests |
| TN-PROJ-CLASS-12 | NICE-TO-HAVE | Plugin auditor scan policy undocumented |

**Approval bar:** Not met. Blockers TN-PROJ-CLASS-1 through TN-PROJ-CLASS-3 must be resolved (or explicitly accepted with product-signed policy docs and parity tests) before R5 can be marked complete. TN-PROJ-INTEG should dedupe TN-PROJ-CLASS-1/7/8 with TN-PROJ-DIAG explain-tree findings under a single `CC-PROJ-*` theme.
