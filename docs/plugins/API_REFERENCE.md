# ChoreBoy Code Studio Plugin API Reference

## 1. Manifest API

Manifest file: `plugin.json`

Top-level schema:

```json
{
  "id": "string",
  "name": "string",
  "version": "string",
  "api_version": 1,
  "runtime": {
    "entrypoint": "relative/path.py"
  },
  "activation_events": ["string"],
  "capabilities": ["string"],
  "permissions": ["string"],
  "engine_constraints": {
    "min_app_version": "string",
    "max_app_version": "string",
    "min_api_version": 1,
    "max_api_version": 1
  },
  "contributes": {
    "commands": [],
    "event_hooks": [],
    "workflow_providers": []
  }
}
```

### Known workflow provider kinds

* `formatter`
* `import_organizer`
* `diagnostics`
* `test`
* `template`
* `packaging`
* `runtime_explainer`
* `freecad_helper`
* `dependency_audit`

### Known provider lanes

* `query`
* `job`

### Known permissions

* `project.read`
* `project.write`
* `runner.invoke`
* `support.bundle`
* `freecad.headless`
* `network.loopback`
* `settings.read`
* `settings.write`

### Known capabilities

* `commands`
* `event_hooks`
* `workflow.formatter`
* `workflow.import_organizer`
* `workflow.diagnostics`
* `workflow.test`
* `workflow.template`
* `workflow.packaging`
* `workflow.runtime_explainer`
* `workflow.freecad_helper`
* `workflow.dependency_audit`

## 2. Declarative command API

`contributes.commands[]` shape:

```json
{
  "id": "string",
  "title": "string",
  "menu_id": "shell.menu.tools",
  "shortcut": "Ctrl+Alt+P",
  "status_tip": "string",
  "tool_tip": "string",
  "message": "string",
  "runtime": true,
  "runtime_payload": {},
  "runtime_handler": "handle_command"
}
```

Rules:

* `id` and `title` are required.
* `runtime` defaults to `false`.
* `runtime: true` routes the command through the plugin host and requires
  `runtime.entrypoint`.
* `runtime: false` leaves execution entirely declarative inside the shell.
* Command contribution shape is validated when the manifest is parsed; invalid
  command entries fail plugin load instead of being skipped during activation.

## 3. Event hook API

`contributes.event_hooks[]` shape:

```json
{
  "event_type": "run_exit",
  "command_id": "acme.runtime.echo"
}
```

Supported `event_type` values:

* `run_start`
* `run_output`
* `run_exit`
* `project_opened`
* `project_open_failed`

Event hooks now deliver structured payloads derived from the shell event object when the
target command executes.

## 4. Workflow provider API

`contributes.workflow_providers[]` shape:

```json
{
  "id": "formatter",
  "kind": "formatter",
  "lane": "query",
  "title": "Acme Formatter",
  "priority": 100,
  "languages": ["python"],
  "file_extensions": [".py"],
  "query_handler": "handle_formatter_query",
  "capabilities": [],
  "permissions": []
}
```

Job-provider example:

```json
{
  "id": "pytest",
  "kind": "test",
  "lane": "job",
  "title": "Acme Pytest",
  "start_handler": "handle_pytest_job",
  "cancel_handler": "cancel_pytest_job"
}
```

Rules:

* workflow providers require `runtime.entrypoint`
* query providers require `query_handler`
* job providers require `start_handler`
* provider `capabilities` and `permissions` must be subsets of the plugin-level
  declarations

## 5. Runtime handler API

Runtime module entrypoint path is `runtime.entrypoint`.

### Command handlers

Command handlers use this signature:

```python
def handle_command(command_id, payload):
    ...
```

### Query provider handlers

Query-provider handlers use this signature:

```python
def handle_formatter_query(provider_key, request):
    ...
```

### Job provider handlers

Job-provider handlers use this signature:

```python
def handle_pytest_job(provider_key, request, emit_event, is_cancelled):
    ...
```

`emit_event(event_type, payload)` publishes streaming job updates.
`is_cancelled()` returns `True` when the shell requested cancellation.

Return values should be JSON-serializable. Query providers should return structured data
such as typed edits or diagnostics. Job providers should return final structured results.

## 6. Host IPC protocol

Transport:

* newline-delimited JSON over stdin/stdout

### Command request

```json
{
  "type": "command",
  "request_id": "uuid",
  "command_id": "acme.runtime.echo",
  "payload": {},
  "activation_event": "on_command:acme.runtime.echo"
}
```

### Query request

```json
{
  "type": "provider_query",
  "request_id": "uuid",
  "provider_key": "cbcs.python_tools:formatter",
  "request": {},
  "activation_event": "on_provider:formatter"
}
```

### Job start request

```json
{
  "type": "provider_job_start",
  "request_id": "uuid",
  "job_id": "uuid",
  "provider_key": "cbcs.pytest:pytest",
  "request": {}
}
```

### Job cancel request

```json
{
  "type": "provider_job_cancel",
  "request_id": "uuid",
  "job_id": "uuid"
}
```

### Unary response

```json
{
  "type": "response",
  "request_id": "uuid",
  "ok": true,
  "result": {}
}
```

### Job event

```json
{
  "type": "job_event",
  "job_id": "uuid",
  "provider_key": "cbcs.pytest:pytest",
  "event_type": "job_progress",
  "payload": {}
}
```

### Job terminal messages

```json
{
  "type": "job_result",
  "job_id": "uuid",
  "provider_key": "cbcs.pytest:pytest",
  "result": {}
}
```

```json
{
  "type": "job_error",
  "job_id": "uuid",
  "provider_key": "cbcs.pytest:pytest",
  "error": "string"
}
```

### Host control messages

* `{"type":"ping"}`
* `{"type":"reload"}`

### Host lifecycle messages

* `{"type":"ready","command_count":N,"provider_count":N}`
* `{"type":"reloaded","command_count":N,"provider_count":N}`

## 7. Project plugin policy API

Project-scoped plugin policy lives at `cbcs/plugins.json`.

Schema:

```json
{
  "schema_version": 1,
  "enabled_plugins": ["cbcs.python_tools"],
  "disabled_plugins": [],
  "pinned_versions": {
    "cbcs.python_tools": "1.0.0"
  },
  "preferred_providers": {
    "formatter:python": "cbcs.python_tools:formatter",
    "test": "cbcs.pytest:pytest"
  }
}
```

Provider preference keys use:

* `<kind>`
* `<kind>:<language>`

Examples:

* `formatter`
* `formatter:python`
* `diagnostics:python`

## 8. Compatibility and activation

Compatibility checks:

* `api_version` exact match with editor plugin API version
* optional app/API min-max constraints

Activation gates:

* compatible manifest
* plugin enabled in global registry
* project policy does not disable or pin away the plugin
* safe mode is disabled
* runtime trust is satisfied for installed runtime plugins
* activation event matches the invoked command/provider path when activation events are
  declared

## 9. Failure, safety, and quarantine semantics

* runtime command failures increment plugin failure count
* repeated failures can disable the plugin automatically
* bundled plugins participate in the same host model but are treated as product-owned
  trusted code
* manual enable clears failure count and last error
* phase-1 workflow plugins must remain pure Python
* plugins must not rely on hidden directories or unrestricted subprocess assumptions
