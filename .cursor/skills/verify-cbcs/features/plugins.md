# Plugins

Plugin Manager installs from a local package, enables/disables, supports safe mode, pins a plugin to a project, and keeps a plugin-host crash from killing the editor.

Owns AT-37–42, AT-85–89.

## Sub-features

- `plugin-install` installs a local `.cbcs-plugin.zip`.
- `plugin-enable` enable/disable without reinstall.
- `plugin-safe-mode` disables all contributions.
- `plugin-quarantine` auto-disables after repeated host failures.
- `plugin-pin` pin / clear pin / project enable / prefer provider (AT-86).
- `plugin-compat` rejects incompatible API / runtime.
- `plugin-support` support bundle includes plugin/provider state (AT-88).

## How to get to it (user POV)

- **Tools → Plugin Manager...**.
- Project pin actions inside that dialog.

## Driving it with control-cbcs

Preconditions:

- Doctor passed.
- A known-good local plugin zip on the share (or bundled_plugins in the checkout).
- Disposable HOME so install state is throwaway.

- **Open manager.** `control-cbcs trigger "$SID" shell.action.tools.pluginManager`. The manager dialog is visible. Shot `plugin-manager`.
- **Install.** Choose the local package; confirm trust if prompted. The plugin appears with version, source, enabled.
- **Disable / enable.** Toggle enabled. Contributions disappear / return (menu item or template, depending on the plugin).
- **Safe mode.** Enable safe mode. Contributions stop. Disable safe mode; they return.
- **Pin.** With a project open, Pin To Project. `<project>/cbcs/` records the pin. Clear Pin removes it.
- **Isolation.** If you have a crashing plugin fixture, install it. Editor window stays up; plugin is quarantined / disabled. Shot `plugin-survived`.
- **Proof.** Shot of the manager row (version + enabled), plus copied `registry.json` from `$HOME/choreboy_code_studio_state/plugins/`.

## Gotchas

- There is no internet marketplace. Only local packages.
- Trust prompt is part of the user path — do not skip it via internals.
- Plugin host is a child process. `CBCS_DISABLE_BACKGROUND_RUNTIME` prevents this feature; do not set it here.
- Compatibility failures must be explicit in the UI, not a silent skip.
