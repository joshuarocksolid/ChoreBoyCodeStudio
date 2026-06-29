# Plugin Platform Concepts

ChoreBoy Code Studio can be extended with plugins. This part of the manual is for plugin
**authors**. This chapter introduces the concepts; the following chapters walk through
building, running, and distributing a plugin.

If you only want to *use* plugins, see "Using plugins" in Part III instead.

## What a plugin can contribute

A plugin is a folder containing a `plugin.json` manifest. Through that manifest (and an
optional runtime module) a plugin can provide:

- **Declarative commands** — menu items, shortcuts, and simple messages, defined entirely
  in the manifest.
- **Runtime commands** — commands backed by Python code that runs in a separate plugin
  host process.
- **Workflow providers** — the recommended pattern. These plug into editor-owned
  workflows such as formatting, import organizing, diagnostics, tests, templates,
  packaging, dependency audits, runtime explanation, and FreeCAD helpers.

> [!TIP] For Python-ecosystem work, prefer **workflow providers**. They integrate with
> editor-owned surfaces without letting plugin code mutate the editor process directly,
> which keeps everything safe and supportable.

## The three lanes of execution

| Pattern | Where it runs | Use it for |
| --- | --- | --- |
| Declarative command | No code; handled by the shell | Simple UI affordances and messages. |
| Runtime command | Plugin host process | Custom logic triggered by a command or event. |
| Workflow provider | Plugin host process, via query/job lanes | Structured workflows the editor drives. |

Workflow providers themselves use two lanes:

- **query** — fast, structured request/response (for example, "format this text").
- **job** — long-running, streaming work that emits progress events (for example,
  "run the test suite").

## Process isolation

Runtime plugin code never runs inside the editor process. It runs in a dedicated
**plugin host process** and communicates with the editor over an explicit IPC contract.
A crash or hang in a plugin therefore cannot take down the editor — the same isolation
principle used for running your programs.

The editor always remains responsible for:

- applying edits to files,
- rendering diagnostics,
- showing which provider handled a workflow (provenance),
- persisting project plugin policy in `cbcs/plugins.json`.

## Capabilities and permissions

A plugin declares what it needs:

- **capabilities** — the workflow kinds it offers (for example, `workflow.formatter`,
  `workflow.test`).
- **permissions** — what it is allowed to access (for example, `project.read`,
  `runner.invoke`).

The application validates these before activating a plugin.

## Lifecycle

A plugin moves through a deterministic lifecycle: **discover → validate → enable →
activate → disable**. Activation can be tied to specific **activation events** (for
example, `on_provider:formatter`) so a plugin only loads when it is actually needed.

## Compatibility and safety (phase 1)

The current plugin SDK intentionally requires:

- **pure Python only** — no native (compiled) extensions;
- **no hidden metadata directories** (such as `.cbcs`, `.pytest_cache`, `.ropeproject`);
- **no terminal or arbitrary-binary assumptions**;
- plugins **return structured results** for editor-applied edits rather than writing
  project files directly.

These are part of the SDK contract, not temporary limitations.

## When to choose each pattern

| You want to… | Use |
| --- | --- |
| Add a menu item that shows a message or triggers an existing command | Declarative command |
| Run custom logic on a command or editor event | Runtime command |
| Provide formatting, diagnostics, tests, templates, packaging, etc. | Workflow provider |
| Do fast, structured request/response work | Workflow provider, **query** lane |
| Do long-running work with progress | Workflow provider, **job** lane |

For most serious extensions — especially anything touching Python workflows — a
**workflow provider** is the right choice, because the editor stays in control of applying
edits and rendering results while your code supplies the logic.

## The editor↔plugin boundary

A useful mental model: your plugin is a **service** the editor calls, not a piece of the
editor. The editor sends a structured request (for example, "format this text, here is the
project root and file path"); your plugin returns a structured result; the editor decides
what to do with it (apply the edit, show the diagnostics, display provenance). This keeps
plugins safe, testable, and replaceable.

## Reference plugins

The best examples are the first-party plugins bundled with the application, visible in the
repository under `bundled_plugins/` — for example `cbcs.python_tools` (formatter),
`cbcs.pytest` (tests), `cbcs.python_diagnostics`, `cbcs.templates.standard`,
`cbcs.packaging_tools`, and `cbcs.runtime_explainers`. Study these before inventing a new
manifest shape.

## Where to go next

- Build a minimal plugin in "Authoring your first plugin".
- Add runtime logic and providers in "Runtime plugins & workflow providers".
- Look up exact fields in "Plugin API reference & distribution".
