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

Status legend: `planned` → `drafted` → `done`. `done` means the chapter section is
written and its facts were cross-checked against the authoritative source above
(screenshots are attached for the major dialogs/panels; not every command warrants its
own image).

**Coverage review (this pass):** every Run-menu item was verified against
`run_menu_builder.py`; the full shortcut table against `SHORTCUT_COMMANDS` plus the
fixed menu shortcuts in `*_menu_builder.py`; the Settings tabs/fields against
`settings_dialog*.py` (which corrected the Intelligence/Local-History "tab" mislabeling
and added per-tab screenshots). All enumerated user-facing surfaces below map to a
written, source-verified chapter section.

## File menu

| Feature | Chapter | Status |
| --- | --- | --- |
| New Project / New Project from Template | 050 | done |
| New Window | 050 | done |
| Open Project / Open Recent | 050 | done |
| Open File | 050 | done |
| Save / Save All / Auto Save | 070 | done |
| Quick Open | 080 | done |
| Recovery Center | 170 | done |
| Global History | 170 | done |
| Settings (General, Keybindings, Syntax Colors, Linter, Files tabs) | 220, 230 | done |
| Exit | 050 | done |

## Edit menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Undo / Redo | 070 | done |
| Find / Replace / Go To Line | 080 | done |
| Find in Files | 080 | done |
| Find References / Rename Symbol | 130 | done |
| Toggle Comment / Indent / Outdent | 070 | done |
| Paste & Re-indent Flat Python / Re-indent Selection | 070 | done |
| Go To Definition / Signature Help / Hover Info | 130 | done |
| Analyze Imports | 150 | done |
| Go to Symbol in File | 080 | done |
| Set Language Mode / Clear Language Override / Inspect Token | 070, 260 | done |

## Run menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Run Active File / Run Project | 090 | done |
| Run With Arguments / Run Configurations | 090 | done |
| Stop / Restart | 090 | done |
| Debug Active File / Debug Project | 110 | done |
| Continue / Pause / Step Over / Into / Out | 110 | done |
| Toggle Breakpoint / Remove All Breakpoints / Exception Stops | 110 | done |
| Rerun Last Debug Target | 110 | done |
| Run/Debug pytest (project/file/at cursor); Debug Failed | 160 | done |
| Start/Restart Python Console / Clear Console | 120 | done |
| Package Project | 200 | done |

## View menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Reset Layout | 040, 220 | done |
| Theme (System/Light/Dark/HC Light/HC Dark) | 240 | done |
| Zoom In / Out / Reset | 070 | done |
| Markdown Source / Preview / Split / Toggle | 100 | done |

## Tools menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Format Current File / Organize Imports | 140 | done |
| Lint Current File / Apply Safe Fixes | 150 | done |
| Plugin Manager | 190 | done |
| Dependency Inspector / Add Dependency | 180 | done |
| Rebuild Intelligence Cache / Refresh Runtime Modules | 130, 340 | done |
| Runtime Center | 340 | done |
| Project Health Check / Generate Support Bundle | 340 | done |

## Help menu

| Feature | Chapter | Status |
| --- | --- | --- |
| Getting Started / Onboarding | 020 | done |
| Keyboard Shortcuts | 250 | done |
| Load Example Project | 050 | done |
| About / Version / Logs | 340 | done |

## Panels & surfaces

| Feature | Chapter | Status |
| --- | --- | --- |
| Explorer / Search / Outline sidebar | 040, 060, 080 | done |
| Run Log / Problems / Debug / Python Console panels | 040, 090, 110, 120, 150 | done |
| Status bar (runtime, run target, project, cursor) | 040 | done |
| Test Explorer | 160 | done |
| Run/Debug toolbar | 040, 090 | done |

## File formats

| Feature | Chapter | Status |
| --- | --- | --- |
| `cbcs/project.json` | 050, 280 | done |
| `cbcs/settings.json` / global settings.json | 220, 280 | done |
| `cbcs/plugins.json` | 190, 280 | done |
| `cbcs/dependencies.json` | 180, 280 | done |
| `cbcs/package.json` / package manifest/report | 200, 280 | done |
| Run manifest / run logs | 090, 280 | done |

## Plugin authoring

| Feature | Chapter | Status |
| --- | --- | --- |
| Manifest, contributions, lifecycle | 300, 310 | done |
| Runtime plugins, workflow providers, IPC | 320 | done |
| API reference, compatibility, distribution | 330 | done |
