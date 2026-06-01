# 7) Settings and Customization

Use Settings to make Code Studio fit your workflow.

Open with `File > Settings...`.

![Figure 11 — File menu path to Settings](../screenshots/manual_11_settings_dialog.png)

## Global vs project scope

The scope selector controls where changes are saved:

- **Global**: applies to all projects for this user/machine.
- **Project**: applies only to current project (`cbcs/settings.json`).

Project scope is useful when sharing consistent behavior with others.

## Theme and view options

Use `View > Theme` to switch:

- System
- Light
- Dark
- High Contrast Light
- High Contrast Dark

High Contrast modes target stronger body-text contrast and wider focus rings for users who need WCAG AAA readability. They are optional; most users can stay on System, Light, or Dark.

Use `View > Zoom In/Out/Reset` for text readability.

## Keybindings

In Settings, **Keybindings** tab lets you:

- search commands,
- change shortcuts,
- detect conflicts,
- reset to defaults.

## Syntax colors

Use **Syntax Colors** tab to customize token colors.
Four scopes are available: Light, Dark, High Contrast Light, and High Contrast Dark. Overrides persist independently under `syntax_colors.*` in settings.

## Linter controls

In **Linter** tab you can:

- enable or disable linting,
- choose lint provider,
- tune rule severities,
- override rules for a project.

## Recommended starter setup

For most hobby users:

1. Keep theme on System or Dark (or High Contrast if you need stronger contrast).
2. Keep linting enabled.
3. Use default shortcuts first, then customize only what you use daily.
4. Use project scope only for settings that truly belong to that project.

