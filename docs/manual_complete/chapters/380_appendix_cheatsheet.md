# Appendix A — Quick-Reference Cheat Sheet

A one-page summary of the most useful commands and shortcuts. For the complete list, see
"Keyboard shortcuts".

## Everyday loop

1. Open a file (`Ctrl+P`, type its name).
2. Edit.
3. Save (`Ctrl+S`).
4. Run (`F5` active file, `Shift+F5` project).
5. Read the **Run Log**; if it fails, read **Problems**.

## Most-used shortcuts

| Action | Shortcut |
| --- | --- |
| Quick Open | `Ctrl+P` |
| Save / Save All | `Ctrl+S` / `Ctrl+Shift+S` |
| Find / Replace | `Ctrl+F` / `Ctrl+H` |
| Find in Files | `Ctrl+Shift+F` |
| Go To Line | `Ctrl+G` |
| Go to Symbol in File | `Ctrl+R` |
| Go To Definition | `F12` |
| Find References | `Shift+F12` |
| Rename Symbol | `F2` |
| Toggle Comment | `Ctrl+/` |
| Run Active File / Run Project | `F5` / `Shift+F5` |
| Debug Active File / Debug Project | `Ctrl+F5` / `Ctrl+Shift+F5` |
| Stop / Restart | `Shift+F2` / `Ctrl+Shift+F2` |
| Toggle Breakpoint | `F9` |
| Step Over / Into / Out | `F10` / `F11` / `Shift+F11` |
| Run Project Tests | `Ctrl+Shift+T` |
| Restart Python Console | `` Ctrl+` `` |
| Zoom In / Out / Reset | `Ctrl+=` / `Ctrl+-` / `Ctrl+0` |
| Close Tab | `Ctrl+W` |

## Key menus

- **File** — projects, files, save, settings.
- **Run** — run, debug, test, console, package.
- **Tools** — format, lint, plugins, dependencies, diagnostics.
- **View** — theme, zoom, Markdown modes, Test Explorer.

## When something goes wrong

1. **Tools > Runtime Center** — what's healthy and what's not.
2. **Problems** panel + **Run Log** — the error and where it is.
3. **Tools > Project Health Check** — common project problems.
4. **Tools > Generate Support Bundle** — package logs to share.

## Recover work

- Unsaved after a crash → **File > Open Recovery Center...**
- An earlier saved version → right-click file > **Local History...**
- A deleted file → **File > Open Global History...**

## Code intelligence at a glance

| Want | Do |
| --- | --- |
| Jump to where something is defined | `F12` |
| See everywhere it is used | `Shift+F12` |
| Rename it everywhere (with preview) | `F2` |
| See its documentation | `Ctrl+Shift+I` |
| See a function's parameters | `Ctrl+Shift+Space` |
| Jump to a symbol in this file | `Ctrl+R` |

## Settings you will likely want on

- **Format on save** and **Organize imports on save** (Settings > Editor).
- A comfortable **Theme** (View > Theme) — High Contrast for maximum legibility.
- **Auto-trigger completion** if you like live suggestions (Settings > Intelligence).

## Where things are stored

| Thing | Location |
| --- | --- |
| Project metadata | `<project>/cbcs/project.json` |
| Per-project settings | `<project>/cbcs/settings.json` |
| Per-run logs | `<project>/cbcs/logs/` |
| Global settings & logs | `~/choreboy_code_studio_state/` |

## Remember

- Your program runs in a **separate process** — the editor stays safe.
- Projects are **plain folders** — back them up to USB.
- Runs are **headless** — run FreeCAD GUI macros inside FreeCAD.
- Saving creates a **Local History checkpoint** — experiment freely; you can restore.
- When stuck, open **Tools > Runtime Center**, then generate a **Support Bundle**.
