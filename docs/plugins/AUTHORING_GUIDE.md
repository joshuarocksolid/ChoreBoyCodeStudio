# ChoreBoy Code Studio Plugin Authoring Guide

## 1. What to build

Code Studio now supports three authoring patterns:

* declarative commands
* runtime commands
* workflow providers

For Python-workflow ecosystem work, prefer workflow providers. They plug into editor-owned
surfaces such as formatting, diagnostics, tests, templates, packaging, and runtime
explanation without letting plugins mutate the editor process directly.

## 2. Package structure

Each plugin installs as a normal folder containing `plugin.json`.

Minimal structure:

```text
my_plugin/
  plugin.json
  runtime.py
```

The installer accepts either:

* a plugin folder
* a `.zip` archive containing exactly one plugin root with `plugin.json`

## 3. Manifest minimum

Smallest valid plugin:

```json
{
  "id": "acme.sample",
  "name": "Acme Sample",
  "version": "1.0.0",
  "api_version": 1,
  "contributes": {
    "commands": []
  }
}
```

Runtime workflow plugins additionally require:

* `runtime.entrypoint`
* `capabilities`
* optional `permissions`
* `contributes.workflow_providers`

## 4. Real reference plugins

The best examples now live in-tree as real plugins:

* `bundled_plugins/cbcs.python_tools`
* `bundled_plugins/cbcs.python_diagnostics`
* `bundled_plugins/cbcs.pytest`
* `bundled_plugins/cbcs.templates.standard`
* `bundled_plugins/cbcs.packaging_tools`
* `bundled_plugins/cbcs.runtime_explainers`

Use those as the primary source of truth before inventing a new manifest shape.

If you want the shortest path through the author-facing docs, start with
`docs/plugins/SDK.md`.

## 5. Workflow provider manifest example

Query-provider example based on the bundled formatter plugin:

```json
{
  "id": "acme.python_tools",
  "name": "Acme Python Tools",
  "version": "1.0.0",
  "api_version": 1,
  "runtime": {
    "entrypoint": "runtime.py"
  },
  "activation_events": ["on_provider:formatter"],
  "capabilities": ["workflow.formatter"],
  "permissions": ["project.read"],
  "contributes": {
    "workflow_providers": [
      {
        "id": "formatter",
        "kind": "formatter",
        "lane": "query",
        "title": "Acme Formatter",
        "languages": ["python"],
        "file_extensions": [".py"],
        "query_handler": "handle_formatter_query"
      }
    ]
  }
}
```

Job-provider example based on the bundled pytest plugin:

```json
{
  "id": "acme.pytest",
  "name": "Acme Pytest",
  "version": "1.0.0",
  "api_version": 1,
  "runtime": {
    "entrypoint": "runtime.py"
  },
  "activation_events": ["on_provider:test"],
  "capabilities": ["workflow.test"],
  "permissions": ["project.read", "runner.invoke"],
  "contributes": {
    "workflow_providers": [
      {
        "id": "pytest",
        "kind": "test",
        "lane": "job",
        "title": "Acme Pytest",
        "start_handler": "handle_pytest_job"
      }
    ]
  }
}
```

## 6. Runtime handler examples

Query-provider example:

```python
from __future__ import annotations

from typing import Any, Mapping


def handle_formatter_query(provider_key: str, request: Mapping[str, Any]) -> dict[str, Any]:
    source_text = request["source_text"]
    return {
        "formatted_text": source_text,
        "changed": False,
        "status": "unchanged",
        "settings": {
            "project_root": request["project_root"],
            "file_path": request["file_path"],
            "config_source": "defaults",
            "python_target_minor": 39,
            "black_line_length": 88,
            "black_target_versions": ["py39"],
            "black_string_normalization": True,
            "black_magic_trailing_comma": True,
            "black_preview": False,
            "isort_profile": "black",
            "isort_line_length": 88,
            "isort_src_paths": [],
            "isort_known_first_party": []
        },
        "error_message": None
    }
```

Job-provider example:

```python
from __future__ import annotations

from typing import Any, Mapping


def handle_pytest_job(
    provider_key: str,
    request: Mapping[str, Any],
    emit_event,
    is_cancelled,
) -> dict[str, Any]:
    emit_event("job_started", {"project_root": request["project_root"]})
    if is_cancelled():
        return {"cancelled": True}
    emit_event("job_progress", {"completed": 1})
    return {"return_code": 0, "stdout": "", "stderr": "", "failures": []}
```

## 7. Declarative commands and event hooks

Declarative commands still work and are useful for simple UI affordances.

Command fields:

* `id`
* `title`
* `menu_id`
* `shortcut`
* `status_tip`
* `tool_tip`
* `message`
* `runtime`
* `runtime_payload`
* `runtime_handler`

Event hooks still target existing commands:

```json
"event_hooks": [
  {"event_type": "run_exit", "command_id": "acme.runtime.echo"}
]
```

Supported shell events:

* `run_start`
* `run_output`
* `run_exit`
* `project_opened`
* `project_open_failed`

Event-hook execution now receives structured event payload data through the runtime
command payload path.

## 8. Project pinning and provider selection

Projects can prefer your provider through `cbcs/plugins.json`.

Example:

```json
{
  "preferred_providers": {
    "formatter:python": "acme.python_tools:formatter"
  }
}
```

Your provider id is always resolved as `<plugin_id>:<provider_id>`.

## 9. Safety rules for authors

Workflow plugins must respect ChoreBoy constraints:

* keep imports at module top-level
* ship pure Python only for phase 1
* do not rely on native extensions or arbitrary binaries
* do not assume terminal access
* do not create hidden directories such as `.cbcs`, `.pytest_cache`, `.ropeproject`, or
  `.jedi`
* do not write project files directly for formatting/refactoring flows; return structured
  results and let the editor apply them

## 10. Activation and compatibility guidance

Use specific activation events where possible:

* `on_provider:formatter`
* `on_provider:diagnostics`
* `on_provider:test`
* `on_command:<command_id>`
* `on_event:<event_type>`

Optional `engine_constraints` can gate app/API compatibility:

```json
"engine_constraints": {
  "min_app_version": "0.2.0",
  "max_app_version": "0.9.0",
  "min_api_version": 1,
  "max_api_version": 1
}
```

If constraints are not satisfied, the plugin stays installed but will not activate.

## 11. Compatibility policy

Before relying on a field or behavior long term, review
`docs/plugins/COMPATIBILITY_POLICY.md`.

That document defines:

* what is stable in phase 1
* what is intentionally unsupported
* how deprecations must be introduced
* the validation checklist expected before SDK changes ship
