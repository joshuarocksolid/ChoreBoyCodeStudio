# TN-PROJ-PKG — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-PROJ-PKG
**Date:** 2026-06-16
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`
**Scope:** Packaging enumeration, dependency audit, artifact/product builders, layout excludes, validator orchestration — contrast with R4 inventory SSOT and R5 classifier SSOT.

---

## Executive verdict

Packaging is **not thermo-clean** for Project SSOT Wave 1. Dependency audit partially migrated to `iter_python_files` and `classify_module`, but project payload copy, hidden-path discovery, and checksum enumeration still use raw `rglob`, so R4 gate 2 is open. Worse, **copy and audit disagree on the effective file set**: audit skips `vendor/` and entire `cbcs/` at the inventory walk while copy ships both (plus all non-`.py` payloads audit never inspects). `is_packaging_excluded_path` docstring claims full `cbcs/` exclusion but code only prunes `cbcs/runs`, `cbcs/logs`, and `cbcs/cache` — tests intentionally assert `cbcs/package.json` lands in the artifact, so policy is implicit and scattered. `check_manifest_consistency` is implemented and tested but never wired into `build_package_validation_report`. Relative imports bypass `dependency_classifier`. Product builder shows the right pattern (allowlists, filtered copy, native binding validation); project packaging has no equivalent guard for vendor native artifacts that are never imported. Dominant risk: **ship-blocking payloads that the audit never considered**, and **classification drift** on relative imports.

---

### TN-PROJ-PKG-1 — Project payload copy bypasses inventory SSOT via raw rglob

- **Persona:** TN-PROJ-PKG
- **Severity:** BLOCKER
- **Evidence:** `app/packaging/artifact_builder.py:334` — `for path in sorted(source_root.rglob("*")):`
- **Code-judo alternative:** Replace `_copy_project_tree` with a single packaging file-set builder that walks through `walk_project` / `iter_project_entries` (or a dedicated `iter_packaging_payload_paths`) and applies `is_packaging_excluded_path` once at the inventory layer. Copy and audit become two consumers of the same ordered path list.
- **Suggested remediation:** Add `iter_packaging_payload_entries(project_root)` in `layout.py` or `file_inventory.py` that owns traversal + packaging excludes; call it from `_copy_project_tree` and from audit enumeration. Delete `rglob` from project export path.
- **Tests that would prove fix:** Parametrized parity test: for a fixture tree with `vendor/`, `cbcs/`, hidden dirs, user exclude patterns, and `cbcs/runs` — assert the set of relative paths from the iterator equals the set copied into `payload/app_files` and equals the set of `.py` files audited (modulo explicit documented exceptions).
- **Handoff overlap:** R4

---

### TN-PROJ-PKG-2 — Payload copy file-set disagrees with dependency audit file-set

- **Persona:** TN-PROJ-PKG
- **Severity:** BLOCKER
- **Evidence:** `app/packaging/dependency_audit.py:58-61` — `for file_path in iter_python_files(root, extra_top_level_skips=("vendor",)):` then `if is_packaging_excluded_path(rel_path): continue`; contrast `app/packaging/artifact_builder.py:334-343` — `rglob("*")` with only `is_packaging_excluded_path`, copying directories and all file types including `vendor/` contents.
- **Code-judo alternative:** One `PackagingPayloadPolicy` dataclass: `include_vendor: True`, `audit_vendor_python: False`, `include_cbcs_metadata: True`, `prune_cbcs_subtrees: (...)`. Copy and audit read the same policy object instead of encoding divergent rules in separate loops.
- **Suggested remediation:** Document product policy explicitly (vendor must ship but need not be statically audited; non-`.py` assets ship without import audit). Implement via shared iterator with `kinds=frozenset({"all"})` vs `kinds=frozenset({"py"})` filters so divergence is intentional and test-locked, not accidental.
- **Tests that would prove fix:** Fixture with `vendor/native.so` not imported, `assets/logo.png`, and `orphan.py` under a user-excluded folder — assert copy includes/excludes per policy and audit scans only the declared audit subset; assert blocking issues cannot reference files that were copied when policy says they should be blocked pre-copy.
- **Handoff overlap:** R4

---

### TN-PROJ-PKG-3 — cbcs metadata inclusion vs audit pruning is split across three mechanisms

- **Persona:** TN-PROJ-PKG
- **Severity:** BLOCKER
- **Evidence:** `app/project/file_inventory.py:102-103` — `if name == constants.PROJECT_META_DIRNAME and not include_meta_dir: continue`; `app/packaging/layout.py:8-11` — `_EXCLUDED_RELATIVE_PREFIXES = ("cbcs/runs", "cbcs/logs", "cbcs/cache")`; `tests/integration/packaging/test_project_packaging_workflow.py:47` — `assert (artifact_root / "payload" / "app_files" / "cbcs" / "package.json").is_file()`
- **Code-judo alternative:** Centralize cbcs policy: `cbcs/` never audited for imports; `cbcs/{package.json,project.json,dependencies.json}` always copied; `cbcs/{runs,logs,cache}` never copied. Express as one table consumed by inventory, layout, and tests.
- **Suggested remediation:** Extend `is_packaging_excluded_path` (or inventory flags) to match the tested product behavior; align `iter_python_files` audit path with the same cbcs subtree rules; remove implicit reliance on inventory cbcs prune for copy while layout allows cbcs root.
- **Tests that would prove fix:** Matrix test: `cbcs/package.json` copied not audited; `cbcs/runs/foo` neither copied nor audited; `cbcs/stray.py` neither copied nor audited (or copied-not-audited if product requires — pick one and lock it).
- **Handoff overlap:** R4

---

### TN-PROJ-PKG-4 — is_packaging_excluded_path docstring lies about cbcs exclusion

- **Persona:** TN-PROJ-PKG
- **Severity:** STRUCTURAL
- **Evidence:** `app/packaging/layout.py:122-130` — docstring: ``cbcs/``, build artefacts, ``*.pyc`` etc.`; implementation `122:143` only checks `_EXCLUDED_RELATIVE_PREFIXES` for `cbcs/runs`, `cbcs/logs`, `cbcs/cache` — not `cbcs/` root or `cbcs/package.json`.
- **Code-judo alternative:** Doc describes behavior; if behavior is wrong, fix code; if behavior is right, fix doc to say "cbcs runtime/cache subtrees" and link to the canonical cbcs policy table from TN-PROJ-PKG-3.
- **Suggested remediation:** Correct docstring and add a short module-level comment in `layout.py` pointing to the single cbcs policy owner. Consider renaming to `is_packaging_payload_excluded_path` if semantics differ from inventory meta-dir pruning.
- **Tests that would prove fix:** Unit tests for `is_packaging_excluded_path` covering `cbcs/package.json`, `cbcs/project.json`, `cbcs/dependencies.json`, `cbcs/runs/x`, and a top-level `.py` under `cbcs/` if that case matters.
- **Handoff overlap:** R4

---

### TN-PROJ-PKG-5 — Third unowned exclude plane between packaging layout and file_inventory

- **Persona:** TN-PROJ-PKG
- **Severity:** STRUCTURAL
- **Evidence:** `app/packaging/layout.py:8-19` — `_EXCLUDED_RELATIVE_PREFIXES`, `_EXCLUDED_DIR_NAMES`, `_EXCLUDED_SUFFIXES`; `app/project/file_excludes.py:18-26` — `DEFAULT_EXCLUDE_PATTERNS` includes `vendor`, `.git`, `node_modules`; packaging copy/audit neither calls `load_effective_exclude_patterns` nor passes `exclude_patterns` to `iter_python_files`.
- **Code-judo alternative:** Packaging export should either (a) honor project effective excludes for copy with an explicit override list (`vendor` always ships), or (b) document that packaging ignores user excludes and add a preflight advisory when excluded paths contain `.py` files that will still ship.
- **Suggested remediation:** Wire `exclude_patterns` into audit via inventory; for copy, apply the same patterns minus packaging-specific allowlist (`vendor`). Single function `packaging_effective_excludes(project_root, settings_service)`.
- **Tests that would prove fix:** Project with `build/` in user excludes and `build/generated.py` — assert documented behavior (exclude from copy or advisory issue) matches search panel behavior or an explicit exception.
- **Handoff overlap:** R4

---

### TN-PROJ-PKG-6 — Relative import classification lives outside dependency_classifier

- **Persona:** TN-PROJ-PKG
- **Severity:** STRUCTURAL
- **Evidence:** `app/packaging/dependency_audit.py:211-254` — `_classify_relative_import` and `_resolve_module_candidates` implement filesystem resolution parallel to `classify_module`; `app/project/dependency_classifier.py` — no relative-import entry point.
- **Code-judo alternative:** Add `classify_relative_import(project_root, file_path, module_name, level)` to `dependency_classifier.py` using `import_layout` canonical module resolution; dependency_audit becomes a thin AST adapter only.
- **Suggested remediation:** Move relative resolution into classifier; delete `_resolve_module_candidates`; map classifier categories to audit record strings in one adapter dict (already partially done for absolute imports via `_CATEGORY_TO_CLASSIFICATION`).
- **Tests that would prove fix:** Parity tests: relative import resolved/missing cases produce same classification whether called from classifier or audit; cross-read with diagnostics relative-import cases when TN-PROJ-DIAG lands.
- **Handoff overlap:** R5

---

### TN-PROJ-PKG-7 — check_manifest_consistency is dead validation path

- **Persona:** TN-PROJ-PKG
- **Severity:** STRUCTURAL
- **Evidence:** `app/packaging/dependency_audit.py:458` — `def check_manifest_consistency`; `app/packaging/validator.py:79-88` — `build_package_validation_report` calls only `run_dependency_audit`, never `check_manifest_consistency`; `grep` shows production callers only in tests.
- **Code-judo alternative:** Fold manifest consistency into `run_dependency_audit` or `build_package_validation_report` as a single "dependency validation" stage so wizard-written `cbcs/dependencies.json` cannot drift from `vendor/` at export time.
- **Suggested remediation:** Call `check_manifest_consistency` inside `build_package_validation_report` after static import audit (or merge into `run_dependency_audit`). Ensure blocking severity surfaces in `issue_report`.
- **Tests that would prove fix:** Extend `test_validator` integration: project with active manifest entry and missing vendor dir fails `build_package_validation_report` with `package.dependency.manifest_missing_vendor.*` without a separate manual call.
- **Handoff overlap:** R5

---

### TN-PROJ-PKG-8 — Dependency audit double-filters with overlapping exclude logic

- **Persona:** TN-PROJ-PKG
- **Severity:** STRUCTURAL
- **Evidence:** `app/packaging/dependency_audit.py:58-61` — inventory walk then `is_packaging_excluded_path`; overlap: `__pycache__` pruned by inventory name patterns only if in exclude_patterns (default inventory walk does not skip `__pycache__` by name — actually walk doesn't skip __pycache__ unless in excludes). `is_packaging_excluded_path` checks `_EXCLUDED_DIR_NAMES` including `__pycache__`.
- **Code-judo alternative:** Packaging audit should call `iter_python_files(..., exclude_patterns=packaging_payload_excludes())` once and drop the second filter, or push all packaging excludes into inventory `exclude_patterns` so one walk applies everything.
- **Suggested remediation:** Consolidate exclude application into inventory call; remove redundant `is_packaging_excluded_path` check in audit loop if inventory already enforces it.
- **Tests that would prove fix:** Regression test that `__pycache__/foo.py` is never audited; single code path reference in test comment.
- **Handoff overlap:** R4

---

### TN-PROJ-PKG-9 — Unreferenced vendor native binaries can ship without audit coverage

- **Persona:** TN-PROJ-PKG
- **Severity:** BLOCKER
- **Evidence:** `app/packaging/dependency_audit.py:58` — audit skips walking `vendor/`; `classify_module` only flags `vendored_native` when an import references the module (`app/project/dependency_classifier.py:170-176`, `198-203`); `app/packaging/artifact_builder.py:334-343` — copies entire `vendor/` including `.so` files; contrast `app/packaging/product_builder.py:369-402` — `validate_choreboy_tree_sitter_bundle` requires explicit binding contract.
- **Code-judo alternative:** Post-copy or pre-copy scan: `audit_vendor_payload(vendor_root)` using `has_compiled_extension_candidate` / classifier native taxonomy on all vendor top-level names, blocking export if any native artifact lacks approved loader manifest entry — mirror product builder discipline.
- **Suggested remediation:** After inventory migration, add vendor tree walk for compiled extensions independent of import graph; integrate with `check_manifest_consistency` and dependency manifest classifications.
- **Tests that would prove fix:** `vendor/orphan.so` with no imports — export blocked with native-extension issue; imported `fastmath` with `.so` still blocked per existing test; allowlisted pure vendor packages still pass.
- **Handoff overlap:** R5

---

### TN-PROJ-PKG-10 — Validator hidden-path discovery uses another raw rglob bypass

- **Persona:** TN-PROJ-PKG
- **Severity:** STRUCTURAL
- **Evidence:** `app/packaging/validator.py:323-334` — `_discover_hidden_paths` — `for path in sorted(root.rglob("*")):` checking dot-prefix segments.
- **Code-judo alternative:** Use `iter_project_entries` or inventory walk with `include_meta_dir=True` and filter `any(part.startswith('.') for part in rel.parts)` — same hidden detection, same traversal contract as tree UI.
- **Suggested remediation:** Replace `_discover_hidden_paths` with inventory-based scan; optionally share helper with search/tree "hidden path" detection.
- **Tests that would prove fix:** Hidden fixture tree — `_discover_hidden_paths` results match inventory-derived hidden list.
- **Handoff overlap:** R4

---

### TN-PROJ-PKG-11 — Product builder shows the packaging pattern project export lacks

- **Persona:** TN-PROJ-PKG
- **Severity:** STRUCTURAL
- **Evidence:** `app/packaging/product_builder.py:35-41` — `INCLUDE_DIRS`, `INCLUDE_FILES` allowlist; `330-340` — `_copytree_filtered` with `_should_prune_dir`; `243-244` — `_copy_vendor_allowlisted`; `369-402` — `validate_choreboy_tree_sitter_bundle`; vs `app/packaging/artifact_builder.py:333-343` — unfiltered `rglob` copy of entire project tree.
- **Code-judo alternative:** Treat project packaging as "product builder for arbitrary tree" — payload policy + optional vendor native validation + filtered copy — instead of a separate blind copy implementation.
- **Suggested remediation:** Extract shared `copytree_with_policy(src, dst, policy)` from product_builder; project export supplies policy (include all first-party except packaging excludes; vendor included; native scan required).
- **Tests that would prove fix:** Shared unit tests for prune/skip rules used by both product and project paths.
- **Handoff overlap:** R4, R5

---

### TN-PROJ-PKG-12 — Checksum enumeration rglob is acceptable but multiplies traversal patterns

- **Persona:** TN-PROJ-PKG
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/packaging/installer_manifest.py:245` — `for file_path in sorted(root.rglob("*")):`; `packaging/install.py:325` — `payload_root.rglob("*")` for install staging.
- **Code-judo alternative:** Checksums run on artifact output, not source project — lower risk than TN-PROJ-PKG-1. Still, a shared `iter_files_under(root)` helper would reduce the packaging module's traversal vocabulary.
- **Suggested remediation:** Defer until project source traversal is unified; optionally reuse artifact payload list for checksum input when manifest is built.
- **Tests that would prove fix:** Low priority; checksum count matches files on disk after export.
- **Handoff overlap:** none

---

### TN-PROJ-PKG-13 — Test suite encodes cbcs inclusion but omits copy/audit parity gate

- **Persona:** TN-PROJ-PKG
- **Severity:** STRUCTURAL
- **Evidence:** `tests/unit/packaging/test_packager.py:91-113` — asserts `cbcs/logs` and `cbcs/runs` excluded from payload; `tests/integration/packaging/test_project_packaging_workflow.py:47` — asserts `cbcs/package.json` in payload; manifest lists **no** `packaging copy vs inventory file-set parity` test (`docs/code review/project-ssot-wave-1/00-manifest.md:114-115` — gap severity **High**).
- **Code-judo alternative:** One characterization module `tests/unit/packaging/test_packaging_file_set_parity.py` owned by R4 remediation.
- **Suggested remediation:** Add parity tests as part of TN-PROJ-PKG-1/2 remediation; extend existing packager tests with vendor native orphan and user-exclude cases.
- **Tests that would prove fix:** The parity module itself.
- **Handoff overlap:** R4

---

### TN-PROJ-PKG-14 — Export blocks on validation before copy (native blocking is not a TOCTOU gap)

- **Persona:** TN-PROJ-PKG
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/packaging/artifact_builder.py:76-88` — `if not validation.is_ready: return ...`; `app/packaging/models.py:243-244` — `is_ready` requires `dependency_audit.is_ready`; `tests/unit/packaging/test_dependency_audit.py:25-35` — vendored native import blocks audit.
- **Code-judo alternative:** No change needed for ordering — validation gate is correct. Residual risk is TN-PROJ-PKG-9 (unimported native files), not copy-before-audit.
- **Suggested remediation:** Document in remediation plan that blocking import audit does not imply full vendor binary audit; address via TN-PROJ-PKG-9.
- **Tests that would prove fix:** Already partially covered; extend for unreferenced native vendor files.
- **Handoff overlap:** R5

---

## Architecture gate scorecard (this slice)

| Gate | Status | Notes |
|------|--------|-------|
| 1. All `.py` discovery via `file_inventory` | **Fail** | Audit partial; copy/validator/checksums use `rglob` |
| 2. Packaging enumeration via inventory or documented exception | **Fail** | No documented exception; no parity tests |
| 3. Explicit `cbcs/` policy per API | **Fail** | Three mechanisms; doc/code mismatch |
| 4. One exclude source per use case | **Fail** | layout vs file_excludes vs inventory defaults |
| 5. One walk per generation | **N/A** | Packaging export is batch, not editor hot path |
| 6. `ProjectInventorySnapshot` as module-list contract | **N/A** | Not used in packaging |
| 7. Classification via `dependency_classifier` | **Partial** | Absolute imports yes; relative fork in audit |
| 8. `classify_module` vs `is_module_resolvable` parity | **Out of slice** | See TN-PROJ-DIAG |
| 9. Explain path adapts classifier | **Out of slice** | See TN-PROJ-DIAG |
| 10. `intelligence -> project` dependency direction | **Partial** | Classifier still imports intelligence probe/resolver |
| 11. Packaging no private intelligence imports | **Pass** | `dependency_audit` uses public classifier |
| 12. Native-extension detector fork | **Fail** | Product validates; project copy does not scan vendor tree |

---

## Approval bar (this slice)

**Do not approve** packaging SSOT work until:

- project payload enumeration routes through inventory (or a single documented packaging iterator tested for parity);
- cbcs and vendor copy/audit policy is explicit and test-locked;
- `check_manifest_consistency` runs on every export validation;
- relative imports route through `dependency_classifier`;
- vendor native payload gets parity with product builder native discipline or an explicit documented exception.
