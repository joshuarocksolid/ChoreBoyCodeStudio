# ChoreBoy Code Studio Plugin Compatibility Policy

## 1. Scope

This policy defines what Code Studio promises to workflow-plugin authors in phase 1 and
what authors must do to stay within the supported contract.

It applies to:

* `plugin.json` manifest fields
* declarative contributions
* runtime commands
* workflow providers
* `cbcs/plugins.json` project policy interaction

## 2. Stability model

The public plugin contract is versioned by `api_version`.

Current rules:

* plugin `api_version` must exactly match the editor plugin API version
* new optional fields may be added without breaking older manifests
* removing or renaming existing manifest fields requires an API version bump
* workflow provider `kind` and `lane` semantics are part of the compatibility contract

## 3. Phase-1 support boundary

Phase 1 intentionally keeps the supported plugin surface narrow:

* pure Python only
* runtime code executes through the isolated plugin host
* no native extensions
* no hidden metadata directories
* no assumption of unrestricted subprocess execution
* editor-owned workflows keep ownership of buffer writes and UI state

If a plugin needs capabilities outside that boundary, it is considered unsupported until a
future runtime-parity spike explicitly expands the contract.

## 4. Bundled plugins as reference implementations

Bundled first-party plugins are the compatibility canary for the SDK:

* `cbcs.python_tools`
* `cbcs.python_diagnostics`
* `cbcs.pytest`
* `cbcs.templates.standard`
* `cbcs.packaging_tools`
* `cbcs.runtime_explainers`
* `cbcs.freecad_helpers`
* `cbcs.dependency_audit`

If the platform changes, these plugins must be updated in the same change whenever
practical. A contract change is not considered complete if the bundled providers do not
still work.

## 5. Deprecation policy

Deprecations must be explicit.

Rules:

* do not silently reinterpret an existing manifest field
* keep deprecated fields/behaviors working for at least one compatible editor release when
  practical
* document the replacement path in `docs/plugins/AUTHORING_GUIDE.md` and
  `docs/plugins/API_REFERENCE.md`
* add or update automated coverage for the migration path before removing the deprecated
  behavior

## 6. Compatibility diagnostics

Compatibility failures should be actionable, not generic.

Expected diagnostics include:

* API version mismatch
* app-version range mismatch
* missing runtime entrypoint for workflow providers
* phase-1 safety audit failures
* trust/quarantine state when runtime activation is blocked

## 7. Author validation checklist

Before shipping a plugin or changing the SDK, validate at minimum:

1. Manifest parses successfully and uses only supported fields.
2. Source remains Python 3.9-compatible.
3. Install/discovery audit passes with no hidden-path or native-extension violations.
4. Query/job handlers return JSON-serializable payloads.
5. Project pinning and preferred-provider behavior remain deterministic.
6. Runtime host execution works through the isolated provider IPC path.

Repository validation commands for the workflow-plugin contract:

```bash
python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/
python3 run_tests.py -q --import-mode=importlib tests/integration/plugins/test_support_bundle_plugins_integration.py
python3 run_tests.py -q --import-mode=importlib tests/runtime_parity/plugins/test_workflow_plugin_runtime.py
npx pyright app/plugins/ app/shell/plugins_panel.py
```

## 8. Compatibility change procedure

When changing the SDK:

1. Update the canonical docs.
2. Update bundled reference plugins.
3. Add or adjust unit/integration/runtime-parity coverage.
4. Add acceptance-linkage updates in `docs/ACCEPTANCE_TESTS.md` and `docs/TASKS.md`.
5. Only then change user-facing Plugin Manager or support-bundle behavior if needed.
