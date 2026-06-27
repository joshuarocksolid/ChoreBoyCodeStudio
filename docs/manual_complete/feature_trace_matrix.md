# Feature Trace Matrix (Complete Edition Coverage)

This matrix maps every user-facing feature to the chapter(s) that document it. It is
the coverage checklist that guarantees the manual documents **every feature**. It is
seeded from the authoritative source surfaces and filled in as chapters are written.

Authoritative enumeration sources:

- Commands & menus: `app/shell/menus.py`, `app/shell/*_menu_builder.py`, `MenuCallbacks`.
- Shortcuts: `app/shell/shortcut_preferences.py` (`SHORTCUT_COMMANDS`).
- Settings: `app/shell/settings_dialog*.py`, `app/persistence/settings_store.py`.
- Behavior detail: `docs/ACCEPTANCE_TESTS.md`.
- File formats: `cbcs/*.json` schemas in `docs/ARCHITECTURE.md` §10/§13.

Status legend: `planned` → `drafted` → `done` (screenshot + reviewed).

## File menu

| Feature | Chapter | Status |
| --- | --- | --- |
| New Project / New Project from Template | 050 | planned |
| New Window | 050 | planned |
| Open Project / Open Recent | 050 | planned |
| Open File | 050 | planned |
| Save / Save All / Auto Save | 070 | planned |
| Quick Open | 080 | planned |
| Recovery Center | 170 | planned |
| Global History | 170 | planned |
| Settings | 220, 230 | planned |
| Exit | 050 | planned |

## Edit menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Undo / Redo | 070 | planned |
| Find / Replace / Go To Line | 080 | planned |
| Find in Files | 080 | planned |
| Find References / Rename Symbol | 130 | planned |
| Toggle Comment / Indent / Outdent | 070 | planned |
| Paste & Re-indent Flat Python / Re-indent Selection | 070 | planned |
| Go To Definition / Signature Help / Hover Info | 130 | planned |
| Analyze Imports | 150 | planned |
| Go to Symbol in File | 080 | planned |
| Set Language Mode / Clear Language Override / Inspect Token | 070, 260 | planned |

## Run menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Run Active File / Run Project | 090 | planned |
| Run With Arguments / Run Configurations | 090 | planned |
| Stop / Restart | 090 | planned |
| Debug Active File / Debug Project | 110 | planned |
| Continue / Pause / Step Over / Into / Out | 110 | planned |
| Toggle Breakpoint / Remove All Breakpoints / Exception Stops | 110 | planned |
| Rerun Last Debug Target | 110 | planned |
| Run/Debug pytest (project/file/at cursor); Debug Failed | 160 | planned |
| Start/Restart Python Console / Clear Console | 120 | planned |
| Package Project | 200 | planned |

## View menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Reset Layout | 040, 220 | planned |
| Theme (System/Light/Dark/HC Light/HC Dark) | 240 | planned |
| Zoom In / Out / Reset | 070 | planned |
| Markdown Source / Preview / Split / Toggle | 100 | planned |

## Tools menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Format Current File / Organize Imports | 140 | planned |
| Lint Current File / Apply Safe Fixes | 150 | planned |
| Plugin Manager | 190 | planned |
| Dependency Inspector / Add Dependency | 180 | planned |
| Rebuild Intelligence Cache / Refresh Runtime Modules | 130, 340 | planned |
| Runtime Center | 340 | planned |
| Project Health Check / Generate Support Bundle | 340 | planned |

## Help menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Getting Started / Onboarding | 020 | planned |
| Keyboard Shortcuts | 250 | planned |
| Load Example Project | 050 | planned |
| About / Version / Logs | 340 | planned |

## Panels & surfaces

| Feature | Chapter | Status |
| --- | --- | --- |
| Explorer / Search / Outline sidebar | 040, 060, 080 | planned |
| Run Log / Problems / Debug / Python Console panels | 040, 090, 110, 120, 150 | planned |
| Status bar (runtime, run target, project, cursor) | 040 | planned |
| Test Explorer | 160 | planned |
| Run/Debug toolbar | 040, 090 | planned |

## File formats

| Feature | Chapter | Status |
| --- | --- | --- |
| `cbcs/project.json` | 050, 280 | planned |
| `cbcs/settings.json` / global settings.json | 220, 280 | planned |
| `cbcs/plugins.json` | 190, 280 | planned |
| `cbcs/dependencies.json` | 180, 280 | planned |
| `cbcs/package.json` / package manifest/report | 200, 280 | planned |
| Run manifest / run logs | 090, 280 | planned |

## Plugin authoring

| Feature | Chapter | Status |
| --- | --- | --- |
| Manifest, contributions, lifecycle | 300, 310 | planned |
| Runtime plugins, workflow providers, IPC | 320 | planned |
| API reference, compatibility, distribution | 330 | planned |
