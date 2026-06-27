# File & Folder Reference

This chapter documents the files and folders ChoreBoy Code Studio creates, both inside
each project and in its global state directory. Everything is plain, visible, and
inspectable.

## Project layout

A project is an ordinary folder. ChoreBoy Code Studio adds a visible `cbcs/` folder for
metadata and logs:

```text
my_project/
  cbcs/
    project.json          # canonical project metadata
    settings.json         # per-project settings overrides (optional)
    plugins.json          # per-project plugin policy (optional)
    dependencies.json     # managed dependency manifest (optional)
    package.json          # packaging metadata (optional)
    logs/                 # per-run logs (run_YYYYMMDD_HHMMSS.log)
    runs/                 # run manifests
    cache/                # caches/indexes (safe to delete)
  vendor/                 # vendored third-party packages (optional)
  main.py                 # your code
  ...
```

> [!NOTE] The `cbcs/` name is deliberately visible (not dot-prefixed). Hidden folders are
> unreliable on ChoreBoy, so all project data stays in plain sight.

## `cbcs/project.json`

The project's identity and run defaults. Example:

```json
{
  "schema_version": 1,
  "project_id": "proj_a1b2c3d4e5f6",
  "name": "My Project",
  "default_entry": "main.py",
  "working_directory": ".",
  "template": "utility_script",
  "default_argv": [],
  "env_overrides": {},
  "run_configs": [],
  "project_notes": ""
}
```

| Field | Meaning |
| --- | --- |
| `schema_version` | Metadata format version. |
| `project_id` | Stable id used by Local History and other features. |
| `name` | Display name. |
| `default_entry` | File run by Run Project. |
| `working_directory` | Directory runs start in. |
| `template` | Template the project was created from. |
| `default_argv` | Default arguments for Run Project. |
| `env_overrides` | Environment variables for runs. |
| `run_configs` | Named run configurations. |
| `project_notes` | Free-form notes. |

## `cbcs/settings.json`

Per-project settings overrides. Same shape as global settings, but only project-
overridable sections are honored: `editor`, `intelligence`, `linter`, `file_excludes`,
`output`, `local_history`. Example:

```json
{
  "file_excludes": { "patterns": ["*.sqlite3", "__pycache__"] },
  "editor": { "tab_width": 4 }
}
```

### Example with a run configuration

```json
{
  "schema_version": 1,
  "project_id": "proj_a1b2c3d4e5f6",
  "name": "TaskTracker",
  "default_entry": "main.py",
  "working_directory": ".",
  "template": "qt_app",
  "default_argv": [],
  "env_overrides": {},
  "run_configs": [
    {
      "name": "Debug run",
      "entry": "main.py",
      "argv": ["--config", "/tmp/app.toml"],
      "working_directory": ".",
      "env": { "DEBUG": "1" }
    }
  ],
  "project_notes": ""
}
```

## `cbcs/plugins.json`

Per-project plugin policy: version pins, project enable/disable state, and preferred
workflow providers. Written when you make project-specific plugin choices in the Plugin
Manager.

Example:

```json
{
  "schema_version": 1,
  "disabled": ["acme.noisy_plugin"],
  "version_pins": { "acme.python_tools": "1.0.0" },
  "preferred_providers": {
    "formatter:python": "acme.python_tools:formatter"
  }
}
```

## `cbcs/dependencies.json`

The managed dependency manifest. Each entry records `name`, `version`, `source`
(`wheel`/`zip`/`folder`/`runtime`), `classification`
(`pure_python`/`native_extension`/`runtime`), `status` (`active`/`removed`), and
`added_at`. See "Managing dependencies".

## `cbcs/package.json`

Packaging metadata saved by the packaging wizard so future builds reuse your choices. The
exported package also contains `package_manifest.json` and `package_report.json` (in the
output folder, not the project). See "Packaging, sharing & installing".

### `cbcs/dependencies.json` example

```json
{
  "schema_version": 1,
  "dependencies": [
    {
      "name": "humanize",
      "version": "4.9.0",
      "source": "wheel",
      "classification": "pure_python",
      "status": "active",
      "added_at": "2026-06-27T12:00:00Z"
    }
  ]
}
```

## Run manifests and logs

Each run writes a JSON **run manifest** under `cbcs/runs/` describing exactly how the run
was launched (entry file, working directory, mode, arguments, environment, and log path).
The corresponding output is saved to `cbcs/logs/run_YYYYMMDD_HHMMSS.log`. Manifests make
runs reproducible and easy to support.

A run manifest looks like:

```json
{
  "manifest_version": 1,
  "run_id": "20260627_153500_001",
  "project_root": "/home/default/projects/TaskTracker",
  "entry_file": "main.py",
  "working_directory": "/home/default/projects/TaskTracker",
  "mode": "python_script",
  "argv": [],
  "env": {},
  "log_file": "/home/default/projects/TaskTracker/cbcs/logs/run_20260627_153500.log"
}
```

Run exit codes have defined meanings: `0` success, `1` user-code error, `2` runner
bootstrap/config error, `3` invalid manifest, `130` terminated by the user.

## Global state directory

Application-wide state lives in a single visible folder under your home directory:

```text
~/choreboy_code_studio_state/
  settings.json                 # global settings
  recent_projects.json          # recent projects list
  python_console_history.json   # console history
  logs/
    app.log                     # editor application log
  cache/                        # global caches
  history/                      # Local History (index + content blobs)
  trash/                        # recoverable deleted items
  crash_reports/                # crash logs
  plugins/                      # installed plugins, registry, trust, logs
  state.sqlite3                 # optional global state database
```

## Settings keys (reference)

Global and project settings are JSON. The top-level sections include `theme`,
`syntax_colors`, `keybindings`, `ui_layout`, `editor`, `intelligence`, `linter`,
`file_excludes`, `output`, `local_history`, `plugins`, `onboarding`, `run`, and
`last_project_path`. Every individual field, its default, and whether it is
project-overridable are documented in "Every settings tab & field".

## Where to go next

- Understand why this layout exists in "How it works".
- Edit project metadata safely via the UI (see "Projects: open, create, import").
