# Installing & First Launch

This chapter covers how ChoreBoy Code Studio is started on the appliance, what you see
the first time it opens, and how to confirm the application is ready to use.

## How the application is launched

On a ChoreBoy appliance, ChoreBoy Code Studio is installed as a normal desktop
application. You start it the same way you start any other program on the machine —
from its desktop icon or application launcher. There is nothing to install from the
internet and no terminal commands to type.

> [!NOTE] ChoreBoy Code Studio runs inside the appliance's bundled Python runtime. That
> runtime is already present on every ChoreBoy machine, which is why no separate
> installation step is required.

## The welcome screen

The first time you open the application — or any time no project is open — you see the
**welcome screen**. From here you can:

- **New Project** — create a project from a template.
- **Open Project** — open an existing project folder.
- **Search projects...** — filter your list of recent projects.
- **Recent Projects** — reopen a project you used before (this list fills in over time).

> [!TIP] After you have opened a project once, ChoreBoy Code Studio can reopen it
> automatically the next time you launch. If that happens, you go straight to your
> project instead of the welcome screen. You can always return to onboarding help from
> the **Help** menu.

## Confirming the application is ready

When the application starts, it runs a quick **capability check** to confirm the runtime
is healthy. The result appears at the far left of the **status bar** along the bottom of
the window.

- **Runtime ready (8/8 checks)** means everything is working.
- **Runtime issues (N/8 checks)** means one or more checks did not pass. The application
  still opens, but some features may be limited.

The capability check confirms things such as:

- the bundled runtime launcher is available,
- the Qt user-interface library can be loaded,
- the application's settings and log folders can be written,
- a temporary working folder is available,
- syntax highlighting support loaded successfully.

> [!IMPORTANT] If the status bar reports runtime issues, open **Tools > Runtime Center**
> for a plain-language explanation of what failed and what to do. See the chapter
> "Diagnostics & support tools" for details.

## Getting started help

ChoreBoy Code Studio includes built-in onboarding help that stays available even after
the welcome screen is gone:

- **Help > Getting Started** opens an in-application guide to your first steps.
- **Tools > Runtime Center** explains the current runtime and project health.

These surfaces are designed so you never need a terminal or external documentation to
understand the state of the application.

## Where your settings and logs live

ChoreBoy Code Studio stores its own settings and logs in a single, visible folder under
your home directory named `choreboy_code_studio_state`. This includes:

- your editor preferences and theme,
- your list of recent projects,
- the application log (`logs/app.log`),
- Local History data for crash recovery.

You normally never need to touch these files, but it is reassuring to know they are
plain, visible files you can inspect or back up. See Part V, "File & folder reference",
for the complete layout.

## Where to go next

Continue with "Your first project in 10 minutes" to build and run something right away.
