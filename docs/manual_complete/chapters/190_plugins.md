# Using Plugins

ChoreBoy Code Studio can be extended with **plugins**. This chapter covers using and
managing plugins. If you want to *write* a plugin, see Part VI, "Extending ChoreBoy Code
Studio".

## What plugins do

Plugins add capabilities to the editor. They can:

- contribute commands, menu items, and keyboard shortcuts;
- provide **workflow providers** — the engines behind features such as formatting,
  import organizing, diagnostics, testing, templates, packaging, and dependency audits.

Several first-party plugins are **bundled** with the application and enabled by default.
They power built-in features rather than adding loose menu commands.

## The Plugin Manager

Open it with **Tools > Plugin Manager...**.

![The Plugin Manager listing bundled plugins and controls](../screenshots/190_plugin_manager.png)

The table lists every plugin with these columns:

| Column | Meaning |
| --- | --- |
| **Plugin** | The plugin's id. |
| **Version** | Installed version. |
| **Source** | `bundled`, `installed`, or `builtin`. |
| **Enabled** | Whether the plugin is active globally. |
| **Project** | Project-specific enable/disable state, if any. |
| **Providers** | Which workflow provider kinds the plugin offers. |
| **Permissions** | Capabilities the plugin requested (for example, `project.read`). |
| **Compatibility** | Whether the plugin is compatible with this app version. |
| **Path** | Where the plugin is installed. |

## Installing a plugin from a local package

Because ChoreBoy is offline, plugins are installed from local files:

1. In the Plugin Manager, click **Install...**.
2. Select a plugin package (a `.cbcs-plugin.zip`) or a plugin folder.
3. The plugin's manifest is validated before installation.

If the package is incompatible or violates the safety rules (for example, it bundles
compiled extensions or assumes hidden paths), installation is blocked with an actionable
explanation.

## Enabling, disabling, and removing

Select a plugin and use the buttons along the bottom of the Plugin Manager:

| Button | Effect |
| --- | --- |
| **Enable** / **Disable** | Turn the plugin on or off globally. |
| **Enable In Project** / **Disable In Project** | Override the plugin's state for the current project only. |
| **Pin To Project** / **Clear Pin** | Lock the project to a specific plugin version. |
| **Prefer Provider** / **Clear Preference** | Choose which plugin handles a workflow kind for this project. |
| **Uninstall** | Remove an installed plugin. |
| **Export...** | Export a plugin package. |

Enabled/disabled state and project pins persist across restarts. Project-specific choices
are saved in the project's `cbcs/plugins.json`.

## Safe mode

If a plugin misbehaves, you can recover:

- Tick **Safe mode (disable all plugins)** at the bottom of the Plugin Manager to start
  without any plugins active.
- The application also **quarantines** a plugin automatically if it fails repeatedly,
  disabling it so the editor stays stable. You can re-enable it explicitly after fixing
  the problem.

> [!IMPORTANT] Runtime plugin code runs in a **separate plugin-host process**, not inside
> the editor. A crash in a plugin therefore cannot take down the editor — it is isolated,
> just like your running programs.

## Workflow providers

Many core features are delivered through workflow providers, which lets plugins extend
or replace them cleanly. When a workflow runs (for example, formatting or running tests),
the application shows which provider handled it. Use **Prefer Provider** to choose a
specific provider for a workflow kind in a project.

## A worked example: disable a plugin for one project

Suppose a workflow plugin behaves differently than you want in one project, but you still
want it elsewhere:

1. Open **Tools > Plugin Manager...** with that project open.
2. Select the plugin and click **Disable In Project** (not the global **Disable**).
3. The choice is saved in the project's `cbcs/plugins.json`, so it persists for that
   project only and travels with it.

To pin a project to a specific plugin version, use **Pin To Project**; to choose which
provider handles a workflow kind, use **Prefer Provider**.

## Recovering from a bad plugin

If the editor becomes unstable after installing a plugin:

1. Restart and use **Safe mode (disable all plugins)** in the Plugin Manager to get a
   clean editor.
2. Disable or uninstall the offending plugin.
3. Re-enable other plugins.

The application also auto-quarantines a plugin that fails repeatedly, so it disables
itself before it can disrupt your work. You re-enable it explicitly after fixing the
cause.

## How bundled features relate to plugins

Several core capabilities — formatting, import organizing, diagnostics, testing,
templates, packaging, dependency audit, runtime explainers, FreeCAD helpers — are
delivered by bundled workflow-provider plugins. That is why the Plugin Manager lists them.
You normally leave these enabled; the architecture simply lets them be replaced or
extended cleanly.

## Where to go next

- Write your own plugin in Part VI, "Plugin platform concepts" and the chapters that
  follow.
- See plugin-related diagnostics in support bundles in "Diagnostics & support tools".
