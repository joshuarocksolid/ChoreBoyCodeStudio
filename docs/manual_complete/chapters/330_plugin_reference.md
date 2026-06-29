# Plugin API Reference & Distribution

This chapter summarizes the plugin manifest fields, handler contracts, compatibility
rules, and how to distribute and validate a plugin. For the authoritative, always-current
contract, see the in-repository documents under `docs/plugins/` and the bundled reference
plugins under `bundled_plugins/`.

## Manifest fields

| Field | Required | Meaning |
| --- | --- | --- |
| `id` | yes | Unique, namespaced plugin id. |
| `name` | yes | Display name. |
| `version` | yes | Plugin version. |
| `api_version` | yes | Targeted plugin API version (currently `1`). |
| `runtime.entrypoint` | for runtime plugins | Python module that holds the handlers. |
| `capabilities` | for runtime plugins | Declared workflow capabilities (e.g. `workflow.formatter`). |
| `permissions` | optional | Access the plugin requests (e.g. `project.read`, `runner.invoke`). |
| `activation_events` | optional | When to activate (e.g. `on_provider:test`). |
| `engine_constraints` | optional | App/API version gating. |
| `contributes.commands` | optional | Declarative or runtime commands. |
| `contributes.workflow_providers` | optional | Workflow providers. |
| `contributes.event_hooks` | optional | Routes shell events to commands. |

## Workflow provider entry

| Field | Meaning |
| --- | --- |
| `id` | Provider id (addressed as `<plugin_id>:<id>`). |
| `kind` | One of: `formatter`, `import_organizer`, `diagnostics`, `test`, `template`, `packaging`, `runtime_explainer`, `freecad_helper`, `dependency_audit`. |
| `lane` | `query` or `job`. |
| `title` | Display title. |
| `languages` / `file_extensions` | Optional applicability filters. |
| `query_handler` | Handler name (query lane). |
| `start_handler` | Handler name (job lane). |

## Handler signatures

| Handler | Signature |
| --- | --- |
| Query provider | `handle(provider_key, request) -> dict` |
| Job provider | `handle(provider_key, request, emit_event, is_cancelled) -> dict` |
| Runtime command | `handle_command(command_id, payload) -> dict` |

Handlers receive plain data (mappings) and return plain data. The editor applies any
resulting edits, renders diagnostics, and shows provider provenance.

## Permissions

Known permissions include `project.read`, `project.write`, `runner.invoke`,
`support.bundle`, `freecad.headless`, `network.loopback`, `settings.read`, and
`settings.write`. Request only what you need.

## Activation events

- `on_provider:<kind>` — when a workflow of that kind is requested.
- `on_command:<command_id>` — when a command is invoked.
- `on_event:<event_type>` — on a shell event (`run_start`, `run_output`, `run_exit`,
  `project_opened`, `project_open_failed`).

## Compatibility gating

```json
"engine_constraints": {
  "min_app_version": "0.2.0",
  "max_app_version": "0.9.0",
  "min_api_version": 1,
  "max_api_version": 1
}
```

If constraints are not satisfied, the plugin stays installed but does not activate, and the
Plugin Manager shows the compatibility reason.

## Phase-1 limits (part of the contract)

- Pure Python only — no native extensions.
- No hidden metadata directories (`.cbcs`, `.pytest_cache`, `.ropeproject`, `.jedi`).
  (The `.cbcs-plugin.zip` distribution **filename** is allowed — it is not a hidden
  directory.)
- No unrestricted subprocess assumptions and no terminal dependence.
- No editor-process mutation by plugin runtime code — return structured results instead.

## Distributing a plugin

1. Package the plugin folder as a `.cbcs-plugin.zip` containing exactly one plugin root
   with `plugin.json` (you can use the Plugin Manager's **Export...** action).
2. Share the file (USB, network share) — no internet or app store is involved.
3. The recipient installs it via **Plugin Manager > Install...**.

## Validating a plugin

Validate against the bundled test lanes before relying on changes:

```bash
python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/
python3 run_tests.py -q --import-mode=importlib tests/integration/plugins/test_support_bundle_plugins_integration.py
python3 run_tests.py -q --import-mode=importlib tests/runtime_parity/plugins/test_workflow_plugin_runtime.py
```

## A compatibility worked example

Suppose your plugin uses a contract introduced in app version 0.4 and should not load on
older builds. Declare:

```json
"engine_constraints": {
  "min_app_version": "0.4.0",
  "min_api_version": 1
}
```

On an older build, the Plugin Manager shows the plugin as **installed but not activated**,
with the compatibility reason. On a compatible build, it activates normally. This lets you
ship one package safely across app versions.

## Testing a plugin before shipping

Validate against the bundled test lanes (these run through the FreeCAD AppRun runtime):

```bash
python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/
python3 run_tests.py -q --import-mode=importlib tests/integration/plugins/test_support_bundle_plugins_integration.py
python3 run_tests.py -q --import-mode=importlib tests/runtime_parity/plugins/test_workflow_plugin_runtime.py
```

For your own plugin's logic, write ordinary pytest tests against your handler functions —
they take plain mappings and return plain mappings, so they are easy to test without the
editor running.

## A distribution checklist

Before sharing a plugin:

- [ ] `plugin.json` validates (correct `id`, `version`, `api_version`).
- [ ] Pure Python only; no native extensions or hidden directories.
- [ ] Handlers return structured results; the plugin does not write project files directly.
- [ ] `engine_constraints` set if you depend on a specific app/API version.
- [ ] Packaged as a `.cbcs-plugin.zip` with exactly one plugin root, or shared as a folder.
- [ ] Tested with the lanes above and with your own unit tests.

## Authoritative sources

- `docs/plugins/SDK.md` — the SDK map and validation commands.
- `docs/plugins/API_REFERENCE.md` — exact manifest, IPC, and handler contract.
- `docs/plugins/AUTHORING_GUIDE.md` — concrete authoring examples.
- `docs/plugins/COMPATIBILITY_POLICY.md` — what is stable, unsupported, and how
  deprecations work.
- `bundled_plugins/` — live, first-party reference plugins.

## Where to go next

- Manage installed plugins as a user in "Using plugins".
- See plugin diagnostics in support bundles in "Diagnostics & support tools".
