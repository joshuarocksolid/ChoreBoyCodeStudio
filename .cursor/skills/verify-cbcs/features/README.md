# ChoreBoy Code Studio verification map

This directory is the maintained source for verifying user-facing behavior of the live Qt editor. Read this index, then the matching feature file, before driving.

Canon these files point at (do not duplicate): [docs/ACCEPTANCE_TESTS.md](../../../../docs/ACCEPTANCE_TESTS.md), [docs/SMOKE_WORKFLOW.md](../../../../docs/SMOKE_WORKFLOW.md).

## Baseline preconditions

- Launch with `control-cbcs launch --source` (or `--install` when the feature is packaging).
- Disposable `HOME` at `/home/default/cbcs-verify-<run-id>` (guest disk).
- `control-cbcs doctor "$SID"` must pass.
- Never drive an instance this run did not start.
- Start every recipe from this baseline unless the feature file says otherwise.

## Driving conventions

- Prefer `#shell.*` over `text:` over `class:[n]`. See [../references/handles.md](../references/handles.md).
- Treat commands as literal. Keep quoted names and flags unchanged.
- One action, then observe.
- Restore scratch files after a mutation. Do not remove proof artifacts.

## Proof

- Capture the user action and the resulting state.
- UI proof: screenshot (`control-cbcs shot`) plus a read/tree of the proving widget.
- Mutation proof: a second read of the stored value (guest file, `cbcs/`, settings).
- Record the feature id and entry point with every artifact.
- An unreachable path is reported with the command and the unmet precondition — not as verified via a different path.

## Feature entry contract

Each file: H1, one paragraph, then exactly four H2s in this order.

1. `Sub-features`
2. `How to get to it (user POV)`
3. `Driving it with control-cbcs`
4. `Gotchas`

## Features

- [Launch and runtime](./launch-runtime.md) — AT-01, AT-02, smoke M1
- [Welcome and onboarding](./welcome-onboarding.md) — AT-73, AT-74, AT-76, AT-77, AT-80, M2
- [Project open and create](./project-open-create.md) — AT-03, AT-04, AT-17, AT-19–21, AT-24, AT-33
- [Explorer and files](./explorer-files.md) — AT-05, AT-27, AT-28, AT-83
- [Editor, save, tabs](./editor-save-tabs.md) — AT-06–09, AT-44, drag-drop open
- [Markdown](./markdown.md) — AT-102, AT-103
- [Search and navigation](./search-navigation.md) — Find, Find in Files, Quick Open, Outline, Go To
- [Run](./run.md) — AT-10–16, AT-29, AT-75, AT-RUN-ARGS-*
- [Debug](./debug.md) — AT-30, AT-31, AT-59–64
- [Python console](./repl.md) — AT-26, console completion
- [Format, lint, intelligence](./format-lint-intelligence.md) — AT-32, AT-36, AT-45–58, editor completion
- [Test Explorer](./test-explorer.md) — AT-96–101, AT-62, M4
- [Settings and theme](./settings-theme.md) — AT-34, AT-35, AT-43, AT-THEME-*, M5
- [Plugins](./plugins.md) — AT-37–42, AT-85–89
- [Recovery and history](./recovery-history.md) — AT-18, AT-65–71
- [Dependencies](./dependencies.md) — AT-90–95
- [Packaging and installer](./packaging-installer.md) — AT-78, AT-81, AT-82, AT-84, AT-95, AT-104, AT-105
- [Shop-LAN state](./shop-lan-state.md) — opt-in shared state root; product default `/home/default/FreeCAD/choreboy_code_studio_state`
- [Diagnostics and support](./diagnostics-support.md) — AT-22, AT-23, AT-79
- [Layout and status](./layout-status.md) — AT-25, zoom, status chips
- [Flat-Python paste](./edit-flat-python-paste.md) — AT-EDIT-FLAT-PYTHON-PASTE

## Not in the product

Do not add files for: Git UI, Close Project, File → Zip / USB export, bottom Tasks tab, relocatable install, internet plugin marketplace.
