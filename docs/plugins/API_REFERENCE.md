# ChoreBoy Code Studio Plugin API Reference

## 1. Manifest API

File: `plugin.json`

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
  "engine_constraints": {
    "min_app_version": "string",
    "max_app_version": "string",
    "min_api_version": 1,
    "max_api_version": 1
  },
  "contributes": {
    "commands": [],
    "event_hooks": []
  }
}
```

## 2. Command contribution API

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

Notes:

* `id` and `title` are required.
* `runtime: true` routes command to runtime host.
* `runtime: false` uses declarative message handler in editor process.

## 3. Event hook API

`contributes.event_hooks[]` shape:

```json
{
  "event_type": "run_exit",
  "command_id": "acme.runtime.echo"
}
```

Supported `event_type`:

* `run_start`
* `run_output`
* `run_exit`
* `project_opened`
* `project_open_failed`

## 4. Runtime handler API

Runtime module entrypoint path is `runtime.entrypoint`.

Handler lookup:

* command-level `runtime_handler` value
* fallback `handle_command`

Accepted call signatures:

```python
def handle_command(command_id, payload):
    ...
```

or

```python
def handle_command(payload):
    ...
```

Return value:

* any JSON-serializable object is preferred
* scalar return values are wrapped by editor command flow when needed

## 5. Host IPC protocol

Transport:

* newline-delimited JSON over stdin/stdout

Request format:

```json
{
  "type": "command",
  "request_id": "uuid",
  "command_id": "acme.runtime.echo",
  "payload": {}
}
```

Success response:

```json
{
  "type": "response",
  "request_id": "uuid",
  "ok": true,
  "result": {}
}
```

Failure response:

```json
{
  "type": "response",
  "request_id": "uuid",
  "ok": false,
  "error": "string"
}
```

Host control messages:

* `{"type":"ping"}`
* `{"type":"reload"}`

Host events:

* `{"type":"ready","command_count":N}`
* `{"type":"reloaded","command_count":N}`

## 6. Compatibility and activation

Compatibility checks:

* `api_version` exact match with editor plugin API version
* optional app/API min-max constraints

Activation gates:

* plugin enabled in registry
* compatibility passes
* safe mode is disabled

## 7. Failure and quarantine semantics

* runtime command failure increments plugin failure count
* plugin auto-disables at configured threshold
* auto-disabled plugin remains installed
* manual enable resets failure count and clears last error
