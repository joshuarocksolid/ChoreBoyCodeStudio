# ChoreBoy Code Studio Workflow Plugin SDK

## 1. Purpose

This is the entry point for authors building workflow plugins for Code Studio.

Use it as the map to the supported SDK surface:

* manifest and IPC contract
* authoring patterns
* compatibility/deprecation rules
* reference plugins
* validation commands

## 2. Start here

1. Read `docs/plugins/PRD.md` for platform intent and rollout scope.
2. Read `docs/plugins/API_REFERENCE.md` for the exact manifest, IPC, and handler contract.
3. Read `docs/plugins/AUTHORING_GUIDE.md` for concrete authoring examples.
4. Read `docs/plugins/COMPATIBILITY_POLICY.md` before depending on a behavior long term.

## 3. Reference implementations

Bundled first-party plugins are the authoritative live samples:

* `bundled_plugins/cbcs.python_tools`
* `bundled_plugins/cbcs.python_diagnostics`
* `bundled_plugins/cbcs.pytest`
* `bundled_plugins/cbcs.templates.standard`
* `bundled_plugins/cbcs.packaging_tools`
* `bundled_plugins/cbcs.runtime_explainers`
* `bundled_plugins/cbcs.freecad_helpers`
* `bundled_plugins/cbcs.dependency_audit`

## 4. Supported workflow model

Prefer workflow providers over raw commands when integrating editor-owned Python
workflows.

Provider lanes:

* `query` for fast structured requests
* `job` for long-running streaming work

The editor remains responsible for:

* applying edits
* rendering diagnostics
* showing workflow provenance
* persisting project policy in `cbcs/plugins.json`

## 5. Validation commands

Use these commands before claiming SDK or plugin changes are ready:

```bash
python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/
python3 run_tests.py -q --import-mode=importlib tests/integration/plugins/test_support_bundle_plugins_integration.py
python3 run_tests.py -q --import-mode=importlib tests/runtime_parity/plugins/test_workflow_plugin_runtime.py
npx pyright app/plugins/ app/support/support_bundle.py app/shell/main_window.py app/shell/plugins_panel.py
```

## 6. Phase-1 limits

The current SDK intentionally excludes:

* native extensions
* hidden metadata paths
* unrestricted subprocess assumptions
* editor-process mutation by plugin runtime code

Those constraints are part of the SDK, not temporary implementation details.
