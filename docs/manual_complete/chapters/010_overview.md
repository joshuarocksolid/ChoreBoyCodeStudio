# What Is ChoreBoy Code Studio?

ChoreBoy Code Studio is a complete, project-first environment for writing, running, and
debugging Python applications directly on a ChoreBoy appliance. It gives you a modern
code editor, a safe way to run your programs, and a full set of developer tools — all
without installing anything extra on the machine.

This chapter explains what the application does, what makes it different, and the key
ideas you will see throughout the rest of the manual.

## What you can do with it

With ChoreBoy Code Studio you can:

- **Create projects** from ready-made templates, or open any folder of Python files.
- **Edit code** with syntax highlighting, code completion, and go-to-definition.
- **Run your programs** and watch their output live, without freezing the editor.
- **Debug** with breakpoints, step controls, and a variable inspector.
- **Find problems** with built-in linting and a Problems panel.
- **Run tests** through an integrated Test Explorer.
- **Recover lost work** with autosave drafts and a built-in Local History.
- **Format code** with Black and organize imports automatically.
- **Manage dependencies** by adding Python packages from local files.
- **Extend the editor** with plugins.
- **Package and share** finished projects so they can be installed on other appliances.

![A project open in ChoreBoy Code Studio, with the file tree, editor, and panels](../screenshots/040_window_tour.png)

## What it is not

ChoreBoy Code Studio is focused and deliberate about its scope:

- It is **not** a general-purpose desktop IDE with thousands of extensions. It ships a
  curated, reliable feature set tuned for the ChoreBoy environment.
- It does **not** require internet access, a terminal, or system-level installation.
- It does **not** run your code inside itself. Your programs always run in a separate
  process (explained below), so a crash in your code never takes down the editor.

## How it compares to what you may know

If you have used a desktop code editor before, ChoreBoy Code Studio will feel familiar: a
file tree, tabbed editor, run/debug controls, a problems list, and an integrated terminal-
*style* output panel. The differences come from the ChoreBoy environment:

- There is **no terminal** — running, testing, and the Python Console all happen through
  buttons and panels instead of typed commands.
- There is **no internet and no package installer** — dependencies are added from local
  files into the project's `vendor/` folder.
- Your programs run through **FreeCAD's bundled Python**, which is why `import FreeCAD`
  works and why some FreeCAD GUI operations are unavailable in a normal run.

Everything in this manual is designed around those realities, so you get a real
development experience without fighting the environment.

## Who should read which part

- **Brand new?** Read Part I in order, then keep Part VII's troubleshooting handy.
- **Comfortable coder, new to this app?** Skim Part I's window tour, then use Part II and
  III as needed and Part V as a reference.
- **Power user?** Jump to Part IV (settings/shortcuts) and Part V (menu, file, and panel
  references).
- **Building extensions?** Go straight to Part VI (plugin authoring).

## The big idea: the editor and your program are separate

The single most important concept in ChoreBoy Code Studio is that **the editor and your
running program are two different processes.**

- The **editor** is the window you work in: the file tree, tabs, menus, and panels.
- The **runner** is a separate process that the editor starts whenever you press Run.
  Your program executes there.

This separation gives you three big benefits:

1. **Safety.** If your program crashes, hangs, or loops forever, the editor stays alive
   and responsive. You never lose the editor because of a bug in your code.
2. **Clear output.** Everything your program prints is captured cleanly and shown in the
   **Run Log** panel.
3. **Control.** You can stop a runaway program at any time with a single **Stop** command.

> [!NOTE] You will see this editor-vs-runner model reflected throughout the manual,
> especially in the chapters on running code (Chapter "Running code") and debugging
> (Chapter "Debugging"). A plain-language explanation of how it works internally is in
> Part V, "How it works".

## Projects are just folders

A ChoreBoy Code Studio project is an ordinary folder on disk. There is no hidden
database and no proprietary format. The project keeps a small, visible `cbcs/` folder
for its settings, but everything else is your own files.

Because a project is just a folder, you can:

- copy it to a USB drive,
- zip it up and share it,
- inspect every file with the file manager,
- back it up like any other folder.

> [!IMPORTANT] Always keep backups of your projects on a USB drive. Your projects are
> your files — treat them the way you would treat any important documents.

## An example: the project used in this manual

Most screenshots in this manual use a small example called **TaskTracker** — a simple
task-list application built with Python and the Qt user-interface toolkit. When you run
it, it opens its own window where you can add, edit, and delete tasks.

![The TaskTracker example application running in its own window](../screenshots/030_demo_app.png)

You can load this same example at any time from **Help > Load Example Project...** and
follow along.

## Where to go next

- New to the application? Continue with the next chapter, "Installing & first launch".
- Want to build something immediately? Jump to "Your first project in 10 minutes".
- Want to understand every part of the window? See "A tour of the window".
