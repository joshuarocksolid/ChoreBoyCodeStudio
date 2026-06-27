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
| New Project / New Project from Template | 050 | drafted |
| New Window | 050 | drafted |
| Open Project / Open Recent | 050 | drafted |
| Open File | 050 | drafted |
| Save / Save All / Auto Save | 070 | drafted |
| Quick Open | 080 | drafted |
| Recovery Center | 170 | drafted |
| Global History | 170 | drafted |
| Settings | 220, 230 | drafted |
| Exit | 050 | drafted |

## Edit menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Undo / Redo | 070 | drafted |
| Find / Replace / Go To Line | 080 | drafted |
| Find in Files | 080 | drafted |
| Find References / Rename Symbol | 130 | drafted |
| Toggle Comment / Indent / Outdent | 070 | drafted |
| Paste & Re-indent Flat Python / Re-indent Selection | 070 | drafted |
| Go To Definition / Signature Help / Hover Info | 130 | drafted |
| Analyze Imports | 150 | drafted |
| Go to Symbol in File | 080 | drafted |
| Set Language Mode / Clear Language Override / Inspect Token | 070, 260 | drafted |

## Run menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Run Active File / Run Project | 090 | drafted |
| Run With Arguments / Run Configurations | 090 | drafted |
| Stop / Restart | 090 | drafted |
| Debug Active File / Debug Project | 110 | drafted |
| Continue / Pause / Step Over / Into / Out | 110 | drafted |
| Toggle Breakpoint / Remove All Breakpoints / Exception Stops | 110 | drafted |
| Rerun Last Debug Target | 110 | drafted |
| Run/Debug pytest (project/file/at cursor); Debug Failed | 160 | drafted |
| Start/Restart Python Console / Clear Console | 120 | drafted |
| Package Project | 200 | drafted |

## View menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Reset Layout | 040, 220 | drafted |
| Theme (System/Light/Dark/HC Light/HC Dark) | 240 | drafted |
| Zoom In / Out / Reset | 070 | drafted |
| Markdown Source / Preview / Split / Toggle | 100 | drafted |

## Tools menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Format Current File / Organize Imports | 140 | drafted |
| Lint Current File / Apply Safe Fixes | 150 | drafted |
| Plugin Manager | 190 | drafted |
| Dependency Inspector / Add Dependency | 180 | drafted |
| Rebuild Intelligence Cache / Refresh Runtime Modules | 130, 340 | drafted |
| Runtime Center | 340 | drafted |
| Project Health Check / Generate Support Bundle | 340 | drafted |

## Help menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Getting Started / Onboarding | 020 | drafted |
| Keyboard Shortcuts | 250 | drafted |
| Load Example Project | 050 | drafted |
| About / Version / Logs | 340 | drafted |

## Panels & surfaces

| Feature | Chapter | Status |
| --- | --- | --- |
| Explorer / Search / Outline sidebar | 040, 060, 080 | drafted |
| Run Log / Problems / Debug / Python Console panels | 040, 090, 110, 120, 150 | drafted |
| Status bar (runtime, run target, project, cursor) | 040 | drafted |
| Test Explorer | 160 | drafted |
| Run/Debug toolbar | 040, 090 | drafted |

## File formats

| Feature | Chapter | Status |
| --- | --- | --- |
| `cbcs/project.json` | 050, 280 | drafted |
| `cbcs/settings.json` / global settings.json | 220, 280 | drafted |
| `cbcs/plugins.json` | 190, 280 | drafted |
| `cbcs/dependencies.json` | 180, 280 | drafted |
| `cbcs/package.json` / package manifest/report | 200, 280 | drafted |
| Run manifest / run logs | 090, 280 | drafted |

## Plugin authoring

| Feature | Chapter | Status |
| --- | --- | --- |
| Manifest, contributions, lifecycle | 300, 310 | drafted |
| Runtime plugins, workflow providers, IPC | 320 | drafted |
| API reference, compatibility, distribution | 330 | drafted |
