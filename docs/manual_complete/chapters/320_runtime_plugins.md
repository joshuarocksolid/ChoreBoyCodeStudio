# Runtime Plugins & Workflow Providers

This chapter covers plugins that run code: runtime commands and, more importantly,
**workflow providers**. Workflow providers are the recommended way to extend editor-owned
Python workflows such as formatting, diagnostics, and testing.

## Declaring a runtime

A plugin that runs code declares an entry point and what it needs:

```json
{
  "id": "acme.python_tools",
  "name": "Acme Python Tools",
  "version": "1.0.0",
  "api_version": 1,
  "runtime": { "entrypoint": "runtime.py" },
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

Runtime workflow plugins require `runtime.entrypoint`, `capabilities`, and
`contributes.workflow_providers`; `permissions` is optional.

## Query providers (fast request/response)

A **query** provider handles a single structured request and returns a structured result.
The handler signature is `handle(provider_key, request)`:

```python
from __future__ import annotations
from typing import Any, Mapping


def handle_formatter_query(provider_key: str, request: Mapping[str, Any]) -> dict[str, Any]:
    source_text = request["source_text"]
    # ... format source_text ...
    return {
        "formatted_text": source_text,
        "changed": False,
        "status": "unchanged",
        "error_message": None,
    }
```

The editor sends fields such as `project_root`, `file_path`, and `source_text`, and
applies the returned result itself. Your plugin never edits the file directly.

## Job providers (long-running, streaming)

A **job** provider handles long-running work and streams progress events. The handler
signature is `handle(provider_key, request, emit_event, is_cancelled)`:

```python
from __future__ import annotations
from typing import Any, Mapping


def handle_pytest_job(provider_key, request, emit_event, is_cancelled) -> dict[str, Any]:
    emit_event("job_started", {"project_root": request["project_root"]})
    if is_cancelled():
        return {"cancelled": True}
    emit_event("job_progress", {"completed": 1})
    return {"return_code": 0, "stdout": "", "stderr": "", "failures": []}
```

The job's manifest entry sets `"lane": "job"` and a `start_handler`. Streaming keeps the
editor responsive while the work runs, and `is_cancelled()` lets the plugin stop
cleanly when the user cancels.

## Runtime commands

Beyond providers, a manifest command can be backed by runtime code via `runtime: true`
and a `runtime_handler`. The handler signature is `handle_command(command_id, payload)`.
Event hooks (see the previous chapter) route shell events to such commands with structured
payloads.

## Provider kinds

The supported workflow provider kinds are: `formatter`, `import_organizer`,
`diagnostics`, `test`, `template`, `packaging`, `runtime_explainer`, `freecad_helper`,
and `dependency_audit`. Choose the kind that matches the workflow you are extending.

## Letting projects prefer your provider

A project can choose your provider for a workflow kind via `cbcs/plugins.json`:

```json
{
  "preferred_providers": {
    "formatter:python": "acme.python_tools:formatter"
  }
}
```

Your provider is always addressed as `<plugin_id>:<provider_id>` (for example,
`acme.python_tools:formatter`). Users set this from the Plugin Manager's **Prefer
Provider** action.

## Isolation and responsiveness

Runtime handlers execute in the plugin host process across two lanes (query and job),
never inside the editor. If your plugin fails repeatedly, the application quarantines it
so the editor stays stable. Long jobs run on the job lane so the UI never freezes.

## A complete worked example: a "shout" formatter

This minimal, end-to-end example shows the full shape of a query-provider plugin. It is a
toy formatter that uppercases comments — enough to demonstrate the contract without real
formatting logic.

### Files

```text
acme.shout/
  plugin.json
  runtime.py
```

### `plugin.json`

```json
{
  "id": "acme.shout",
  "name": "Acme Shout Formatter",
  "version": "1.0.0",
  "api_version": 1,
  "runtime": { "entrypoint": "runtime.py" },
  "activation_events": ["on_provider:formatter"],
  "capabilities": ["workflow.formatter"],
  "permissions": ["project.read"],
  "contributes": {
    "workflow_providers": [
      {
        "id": "shout",
        "kind": "formatter",
        "lane": "query",
        "title": "Acme Shout",
        "languages": ["python"],
        "file_extensions": [".py"],
        "query_handler": "handle_format"
      }
    ]
  }
}
```

### `runtime.py`

```python
from __future__ import annotations
from typing import Any, Mapping


def handle_format(provider_key: str, request: Mapping[str, Any]) -> dict[str, Any]:
    source = request["source_text"]
    lines = []
    changed = False
    for line in source.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            upper = line.upper()
            changed = changed or upper != line
            lines.append(upper)
        else:
            lines.append(line)
    formatted = "\n".join(lines)
    if source.endswith("\n"):
        formatted += "\n"
    return {
        "formatted_text": formatted,
        "changed": changed,
        "status": "formatted" if changed else "unchanged",
        "error_message": None,
    }
```

### Install and try it

1. Zip the `acme.shout/` folder as `acme.shout.cbcs-plugin.zip` (or keep it as a folder).
2. **Tools > Plugin Manager... > Install...** and select it.
3. In a project, choose **Prefer Provider** for the `formatter:python` workflow and select
   `acme.shout:shout`.
4. Open a Python file with a comment and run **Format Current File** — the comment is
   uppercased, and the editor applies the returned text.

### What this demonstrates

- The handler receives plain request data (`source_text`, `project_root`, `file_path`)
  and returns plain result data.
- The **editor** applies the edit; the plugin never writes the file directly.
- The plugin runs in the isolated host process and only requested `project.read`.

For a long-running job instead of a quick transform, use the **job** lane with a
`start_handler` and `emit_event` (see the bundled `cbcs.pytest` plugin).

## Where to go next

- Look up the exact manifest, IPC, and handler contract in "Plugin API reference &
  distribution".
- Study the bundled reference plugins under `bundled_plugins/`.
