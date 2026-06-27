# Every Settings Tab & Field

This chapter documents every setting in the Settings dialog, organized by tab, with its
default value and whether it can be overridden per project. Open Settings with
**File > Settings...**.

> [!NOTE] "Project-overridable" means the setting can differ per project. Settings marked
> global-only describe your machine or account and apply everywhere.

## General tab

The General tab (project-overridable sections plus the global-only Appearance group)
collects appearance, output, and editor behavior.

![The General settings tab](../screenshots/230_settings_general.png)

### Appearance (global-only)

| Setting | Default | Description |
| --- | --- | --- |
| Theme | System | The color theme: System, Light, Dark, High Contrast Light, High Contrast Dark. |
| UI font weight | Normal | Weight of interface text: Normal, Medium, or Bold. |
| Dark chrome palette | Standard (blue-tinted dark) | In Dark mode, choose Standard or Neutral gray dark. |

### Output (project-overridable)

| Setting | Default | Description |
| --- | --- | --- |
| Auto-open Run Log on run output | On | Switch to the Run Log when a run produces output. |
| Auto-open Problems on run failure | On | Switch to the Problems panel when a run fails. |

### Editor (project-overridable)

| Setting | Default | Description |
| --- | --- | --- |
| Tab width | 4 | Display width of a tab character. |
| Font family | monospace | Editor font. |
| Font size | 10 | Editor font size. |
| Indent style | spaces | Insert spaces or tabs when indenting. |
| Indent size | 4 | Number of spaces per indent level. |
| Detect indentation from file | On | Match the opened file's existing indentation. |
| Format on save | Off | Run Black when saving a Python file. |
| Organize imports on save | Off | Sort imports when saving a Python file. |
| Trim trailing whitespace on save | On | Remove trailing spaces on save. |
| Insert final newline on save | On | Ensure the file ends with a newline. |
| Enable preview tabs | On | Single-click opens a temporary preview tab. |
| Auto save | Off | Save changes automatically. |
| Exit behavior | Ask | On exit with unsaved changes: ask, or keep unsaved for next launch. |
| Hover tooltip enabled | Off | Show documentation tooltips on hover. |
| Auto re-indent flat-Python paste | Off | Automatically fix indentation of pasted flat Python (high-confidence cases). |

## Intelligence tab (project-overridable)

Controls code intelligence and syntax-highlighting performance.

| Setting | Default | Description |
| --- | --- | --- |
| Enable completion | On | Offer code completion. |
| Auto-trigger completion | Off | Show completions automatically while typing. |
| Completion minimum characters | 2 | Characters typed before auto-completion triggers. |
| Enable diagnostics | On | Show linting/analysis problems. |
| Real-time diagnostics | On | Update problems as you type. |
| Enable quick fixes | On | Offer automatic fixes for problems. |
| Require preview for multi-file fixes | On | Preview before applying fixes that touch several files. |
| Cache enabled | On | Use the symbol index cache for speed. |
| Incremental indexing | On | Update the symbol index incrementally. |
| Metrics logging enabled | On | Log intelligence performance metrics. |
| Force full reindex on open | Off | Rebuild the whole index when a project opens. |
| Highlighting adaptive mode | normal | Highlighting detail level for large files. |
| Reduced-highlighting threshold | 250,000 chars | File size at which highlighting is reduced. |
| Lexical-only threshold | 600,000 chars | File size at which only basic highlighting is used. |

## Linter tab (project-overridable)

| Setting | Default | Description |
| --- | --- | --- |
| Enable Python linting | On | Turn linting on or off. When off, provider and rule controls are disabled. |
| Provider | Default (built-in) | Choose the lint backend: Default (built-in) or Pyflakes. |
| Rule overrides | (none) | Enable/disable individual rules and set their severity. |

Rule overrides let you, for example, disable an "unused import" rule (such as `PY220`)
or change a rule's severity to a warning. In project scope, each override offers
**Reset to Global**. See "Linting & the Problems panel" for the rule catalog.

## Files tab (project-overridable)

| Setting | Default | Description |
| --- | --- | --- |
| Exclude patterns | (project-dependent) | Glob patterns for files/folders hidden from the Explorer (for example, `vendor`, `__pycache__`, `*.sqlite3`). |

## Keybindings tab (global-only)

Lists every command with its current shortcut, grouped by category (File, Edit, Run,
View, Tools). Click a shortcut to record a new key combination. Conflicts are detected
and must be resolved. See "Keyboard shortcuts" for the full default table.

## Syntax Colors tab (global-only)

Customize the color of each syntax token. A scope dropdown offers four independent
palettes:

- **Light Theme**
- **Dark Theme**
- **High Contrast Light**
- **High Contrast Dark**

Overrides in one scope do not affect the others. See "Themes in depth".

## Local History (project-overridable)

Controls how much Local History is kept. See "Local History & recovery".

| Setting | Default | Description |
| --- | --- | --- |
| Max checkpoints per file | 50 | How many saved revisions to keep per file. |
| Retention days | 30 | How long to keep history entries. |
| Max tracked file size | 1,000,000 bytes | Files larger than this are not tracked. |
| Exclude patterns | (none) | Files matching these patterns are not tracked. |

## Where settings are stored

- Global: `~/choreboy_code_studio_state/settings.json`
- Project: `<project>/cbcs/settings.json`

Both are plain JSON. The exact keys are listed in Part V, "File & folder reference".
