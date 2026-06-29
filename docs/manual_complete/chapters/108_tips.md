# Tips & Efficient Workflows

This chapter collects habits and shortcuts that make day-to-day work faster. None of it is
required, but these patterns help you get the most from ChoreBoy Code Studio.

## Work keyboard-first

Most common actions have a shortcut. Internalizing a handful pays off quickly:

- `Ctrl+P` to open any file by name — usually faster than clicking through the tree.
- `Ctrl+S` after every meaningful change (and consider format-on-save).
- `F5` / `Shift+F5` to run; `Shift+F2` to stop.
- `F12` to jump to a definition; `Shift+F12` to find uses; `F2` to rename.
- `Ctrl+Shift+F` to search the whole project; `Ctrl+G` to jump to a line.

You can change any of these in **Settings > Keybindings** (see "Keyboard shortcuts").

## Master preview tabs

Single-click opens a file in a temporary **preview** tab that the next preview replaces.
This keeps your tab bar clean while you browse. When you actually want to keep a file,
double-click it or just start editing — it becomes permanent. If you prefer every open to
be permanent, turn off preview tabs in **Settings > Editor**.

## Keep the Problems panel clean

Fix what the linter flags before you run. A clean Problems panel means the next failure in
the panel is almost certainly from your run, not pre-existing noise. Real-time diagnostics
make this nearly free.

## Use the console as a scratchpad

Before adding a tricky expression to a file, try it in the **Python Console**. You get
instant feedback, can inspect live objects with completion, and never touch your files
until you are happy with the result.

## Save run setups you repeat

If you keep typing the same arguments, save them as a named **Run Configuration** and
select it from the status-bar run-target indicator. Then `Shift+F5` always uses the right
arguments, working directory, and environment.

## Let the tools format for you

Turn on **Format on save** and **Organize imports on save** in **Settings > Editor**. You
stop thinking about formatting entirely, and your code stays consistent — while save
reliability is preserved even if a transform fails.

## Trust Local History

Because every save creates a checkpoint and unsaved work is drafted automatically, you can
experiment freely. If a change goes wrong, restore an earlier version from **Local
History**; if you deleted a file, recover it from **Global History**.

## Two projects at once

Use **File > New Window** (`Ctrl+Shift+N`) to open a second project side by side — handy
for copying code between projects or comparing approaches.

## Tune highlighting for big files

If you work with very large files, the editor already reduces highlighting detail past
size thresholds to stay responsive. You can adjust those thresholds in **Settings >
Intelligence** if you want more or less detail.

## When something is confusing, ask the app

The application explains itself:

- The **status bar** shows runtime readiness, run state, and your cursor position.
- **Tools > Runtime Center** explains runtime and project health in plain language.
- **Help > Getting Started** and **Help > Keyboard Shortcuts** are always available.

## Back up to USB

Projects are plain folders. Copy them to a USB drive regularly, or zip them. Power
interruptions happen; your projects are your files.

## Where to go next

- The full shortcut list is in "Keyboard shortcuts".
- Short step-by-step recipes are in "Common Task Recipes".
