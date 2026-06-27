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

## Where to go next

- Look up the exact manifest, IPC, and handler contract in "Plugin API reference &
  distribution".
- Study the bundled reference plugins under `bundled_plugins/`.
