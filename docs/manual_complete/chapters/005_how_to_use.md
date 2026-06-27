# How to Use This Manual

This is the **Complete Edition** of the ChoreBoy Code Studio user manual. It documents
every feature of the application in detail, with screenshots, and is meant to be both a
learning guide for new users and a reference for experienced ones.

If you want a short, get-started-fast booklet instead, see the separate *Hobbyist
Edition*. This Complete Edition goes much deeper.

## Who this manual is for

- **Newcomers** who have never opened the application and want to build and run their
  first project.
- **Everyday users** who want reliable, step-by-step instructions for common tasks.
- **Power users** who want exact details: every menu command, setting, keyboard
  shortcut, file format, and limitation.
- **Plugin authors** who want to extend the application.

You do not need to read the manual front to back. Use the reading paths below.

## How the manual is organized

The manual is grouped into parts that move from simple to advanced:

- **Part I — Get Started.** What the application is, how to launch it, and a guided
  first project. Read this first if you are new.
- **Part II — Core Daily Workflows.** Opening projects, managing files, editing,
  searching, and running code.
- **Part III — Power Features.** Debugging, the Python Console, code intelligence,
  formatting, linting, testing, local history, dependencies, plugins, and packaging.
- **Part IV — Settings & Customization.** Every setting, theme, and keyboard shortcut.
- **Part V — Reference.** Exhaustive menu, panel, and file-format references, plus a
  plain-language explanation of how the application works.
- **Part VI — Extending.** Authoring your own plugins.
- **Part VII — Support.** Diagnostics, troubleshooting by symptom, an FAQ, and a glossary.

## Reading paths

| If you want to… | Start at |
| --- | --- |
| Build and run your first project | Part I, "Your first project in 10 minutes" |
| Understand the window and panels | Part I, "A tour of the window" |
| Do everyday editing and running | Part II |
| Debug, test, or use the Python Console | Part III |
| Change a setting, theme, or shortcut | Part IV |
| Look up an exact command or file format | Part V |
| Write a plugin | Part VI |
| Fix a problem | Part VII, "Troubleshooting by symptom" |

## Conventions used in this manual

- **Menu paths** look like `File > Open Project...`. Follow each menu in order.
- **Keyboard shortcuts** look like `Ctrl+S`, `F5`, or `Shift+F5`.
- **Filenames, paths, and code** appear in a monospaced font, for example
  `cbcs/project.json` or `default_entry`.
- **Buttons and controls** appear in bold the first time, for example click **Run**.

The manual uses four kinds of highlighted notes:

> [!TIP] A shortcut or a faster way to do something.

> [!IMPORTANT] Something you should not miss, to avoid mistakes or lost work.

> [!NOTE] Background information or a pointer to a related section.

> [!LIMITATION] A boundary of the product or the ChoreBoy runtime that shapes how a
> feature behaves.

## About the screenshots

Screenshots show the exact area of the window to look at, and each caption explains
what to notice. Screenshots are captured from the application running on a development
build of the ChoreBoy runtime.

> [!NOTE] Development-build screenshots are visually very close to the production
> ChoreBoy appliance. The window's outer title bar and borders are drawn by the host
> system and may look slightly different on your machine; the application's own
> layout, labels, and panels match.

## A note on the ChoreBoy environment

ChoreBoy Code Studio is designed to run inside a locked-down appliance where you cannot
install ordinary software, open a terminal, or reach the open internet. Many design
choices in the application — and several limitations noted throughout this manual —
exist because of that environment. Part V's "How it works" chapter explains the
reasoning in plain language.
