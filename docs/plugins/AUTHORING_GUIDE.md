# ChoreBoy Code Studio Plugin Authoring Guide

## 1. Plugin package structure

Each plugin installs as a normal folder containing `plugin.json`.

Example:

```text
my_plugin/
  plugin.json
  runtime.py
```

The installer accepts either:

* a plugin folder
* a `.zip` archive containing exactly one plugin root with `plugin.json`

## 2. Required manifest fields

`plugin.json` minimum:

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

Required keys:

* `id` (string)
* `name` (string)
* `version` (string)
* `api_version` (integer)

Optional keys:

* `runtime.entrypoint`
* `activation_events`
* `capabilities`
* `engine_constraints`
* `contributes`

## 3. Engine constraints

Optional compatibility gates:

```json
"engine_constraints": {
  "min_app_version": "0.1.0",
  "max_app_version": "0.9.0",
  "min_api_version": 1,
  "max_api_version": 1
}
```

If constraints are not satisfied, plugin remains installed but is not activated.

## 4. Declarative commands

Commands are declared under `contributes.commands`.

Example:

```json
"contributes": {
  "commands": [
    {
      "id": "acme.sample.hello",
      "title": "Acme: Hello",
      "menu_id": "shell.menu.tools",
      "message": "Hello from Acme plugin"
    }
  ]
}
```

Supported command fields:

* `id` (required)
* `title` (required)
* `menu_id` (default `shell.menu.tools`)
* `shortcut`
* `status_tip`
* `tool_tip`
* `message`
* `runtime` (boolean)
* `runtime_payload` (object)
* `runtime_handler` (string; runtime plugins)

## 5. Runtime plugins

Set `runtime.entrypoint` and mark command with `runtime: true`.

Example manifest:

```json
{
  "id": "acme.sample_runtime",
  "name": "Acme Runtime",
  "version": "1.0.0",
  "api_version": 1,
  "runtime": {
    "entrypoint": "runtime.py"
  },
  "contributes": {
    "commands": [
      {
        "id": "acme.runtime.echo",
        "title": "Acme: Runtime Echo",
        "runtime": true,
        "runtime_handler": "handle_command",
        "runtime_payload": {
          "text": "default"
        }
      }
    ]
  }
}
```

Example `runtime.py`:

```python
def handle_command(command_id, payload):
    text = payload.get("text", "")
    return {"echo": text, "command_id": command_id}
```

The runtime host calls handler as:

* `handle_command(command_id, payload)` preferred
* `handle_command(payload)` fallback

## 6. Event hooks

Event hooks trigger an existing command when an editor event occurs.

Example:

```json
"contributes": {
  "event_hooks": [
    {"event_type": "run_exit", "command_id": "acme.runtime.echo"}
  ]
}
```

Supported `event_type` values:

* `run_start`
* `run_output`
* `run_exit`
* `project_opened`
* `project_open_failed`

## 7. Safety behavior

* Safe mode disables all plugin activation.
* Runtime failures increment plugin failure count.
* Plugin auto-disables after repeated failures.
* Manual re-enable resets failure count.
