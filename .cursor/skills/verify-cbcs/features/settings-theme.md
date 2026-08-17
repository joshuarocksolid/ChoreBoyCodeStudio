# Settings and theme

Settings edits global or project scope. Theme can be System, Light, Dark, High Contrast Light, or High Contrast Dark. Keybindings, syntax colors, linter rules, and file excludes persist.

Owns AT-34, AT-35, AT-43, AT-THEME-HIGH-CONTRAST, AT-THEME-NEUTRAL-DARK, smoke M5.

## Sub-features

- `settings-open` **File → Settings...** opens `#shell.settingsDialog`.
- `settings-scope` Global vs Project; status bar shows `(project overrides)` when they differ (AT-43).
- `settings-keybindings` search / edit / conflict / Reset All (AT-34).
- `settings-syntax` per-token colors persist for Light and Dark (AT-35).
- `settings-linter` provider and rule table (AT-36, shared with [format-lint-intelligence.md](./format-lint-intelligence.md)).
- `theme-four` View → Theme cycles Light, Dark, HC Light, HC Dark. All four must stay readable (welcome, explorer, settings, runtime dialogs).
- `theme-neutral-dark` optional neutral gray dark chrome (AT-THEME-NEUTRAL-DARK).

## How to get to it (user POV)

- **File → Settings...**.
- **View → Theme ▶** System / Light / Dark / High Contrast Light / High Contrast Dark.
- Settings tabs: General, Keybindings, Syntax Colors, Linter, Files.

## Driving it with control-cbcs

Preconditions:

- Doctor passed.
- Disposable HOME so settings writes do not touch the human profile.

- **Open settings.** `control-cbcs trigger "$SID" shell.action.file.settings`. `#shell.settingsDialog` is modal. Shot `settings-general`.
- **Scope.** `#shell.settingsDialog.scopeSegmented` can select Project only when a project is open. Change an editor setting at project scope. `#shell.projectStatusLabel` includes `(project overrides)`. Guest `<project>/cbcs/settings.json` has the key. Global `$HOME/choreboy_code_studio_state/settings.json` does not (or differs).
- **Theme Light.** `control-cbcs trigger "$SID" shell.action.view.theme.light`. Shot `theme-light` of welcome or editor.
- **Theme Dark.** `control-cbcs trigger "$SID" shell.action.view.theme.dark`. Shot `theme-dark`.
- **Theme HC Light.** `control-cbcs trigger "$SID" shell.action.view.theme.high_contrast_light`. Shot `theme-hc-light`. Editor/panel background is white; text stays readable.
- **Theme HC Dark.** `control-cbcs trigger "$SID" shell.action.view.theme.high_contrast_dark`. Shot `theme-hc-dark`. Background is black.
- **Keybinding.** Settings → Keybindings. Change a command; close; trigger the new shortcut (or reopen and read the table). `$HOME/choreboy_code_studio_state/settings.json` contains the override.
- **Proof.** Four theme shots with the window title visible, plus copied `settings.json` files.

## Gotchas

- Close the settings dialog before asserting live theme on the main window — some controls apply immediately, some on close. Re-read the visible chrome.
- System theme follows the guest desktop; do not use it as the four-theme proof.
- Neutral dark is opt-in under Appearance, not a fifth View → Theme item.
- OS high-contrast auto-detect is out of scope.
