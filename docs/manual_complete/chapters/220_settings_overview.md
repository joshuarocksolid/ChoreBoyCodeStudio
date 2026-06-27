# Settings Overview: Scopes & Layering

ChoreBoy Code Studio keeps your preferences in a Settings dialog with two **scopes** —
global and project. This chapter explains how the two scopes combine, where settings are
stored, and how to tell when a project is overriding a global default.

## Opening Settings

Choose **File > Settings...**. The dialog has a scope toggle at the top (**Global** /
**Project**) and a row of tabs.

![The Settings dialog, General tab, in Global scope](../screenshots/230_settings_general.png)

## Global vs project scope

- **Global** settings apply to every project by default. They are stored in
  `~/choreboy_code_studio_state/settings.json`.
- **Project** settings override the global defaults for one project only. They are stored
  in that project's `cbcs/settings.json`.

The **Project** scope is only available when a project is open.

## How settings layer

Effective settings are resolved in three layers, each overriding the one before:

1. **Built-in defaults** (shipped with the application).
2. **Global settings** (`~/choreboy_code_studio_state/settings.json`).
3. **Project overrides** (`<project>/cbcs/settings.json`).

So a value you set at project scope wins over your global value, which wins over the
built-in default.

## What can be overridden per project

Only a defined set of sections can be set per project — the ones that genuinely make
sense to vary by project:

- **Editor** (indentation, save behavior, preview tabs, and similar)
- **Intelligence** (completion, diagnostics, highlighting)
- **Linter** (enable/disable, provider, rule overrides)
- **Files** (exclude patterns)
- **Output** (auto-open panels)
- **Local History** (retention and exclusions)

Other settings are **global-only** because they describe your machine or you, not a
project:

- **Theme** and dark-chrome palette
- **Syntax Colors**
- **Keybindings**
- window layout, last opened project, and the import-update policy

> [!NOTE] When you switch the Settings dialog to **Project** scope, the global-only tabs
> (Keybindings, Syntax Colors) are hidden, because those cannot be set per project.

## The project-override indicator

When a project has its own settings, the status bar shows **(project overrides)** next to
the project name. This is your at-a-glance signal that the project is not using pure
global defaults.

## Resetting project overrides

In **Project** scope, controls that override a global value offer a **Reset to Global**
option. Resetting removes the project override so the global value applies again, and the
status-bar indicator clears once all overrides are removed.

## Saving and applying

Click **Save** to apply your changes. Many settings — such as theme, keybindings, and
syntax colors — apply immediately, without restarting the application.

## Where to go next

- See every individual setting in "Every settings tab & field".
- Customize colors and high-contrast modes in "Themes in depth".
- Change keyboard shortcuts in "Keyboard shortcuts".
