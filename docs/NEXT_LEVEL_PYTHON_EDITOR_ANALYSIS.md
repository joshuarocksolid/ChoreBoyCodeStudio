# ChoreBoy Code Studio: Next-Level Python Editor Analysis

Date: 2026-03-24

## Purpose

This document analyzes what ChoreBoy Code Studio is still missing to become a genuinely great Python editor for ChoreBoy users.

The goal is not "become VS Code on ChoreBoy." The goal is:

- be the best Python-first editor that actually fits ChoreBoy's runtime and UX constraints
- preserve the product's strongest advantage: deep alignment with `docs/DISCOVERY.md`
- avoid spending months cloning features that matter less than trust, clarity, and runtime fit

This analysis is based on:

- product/runtime docs: `docs/PRD.md`, `docs/DISCOVERY.md`, `docs/ARCHITECTURE.md`, `docs/TASKS.md`
- current implementation samples from `app/`
- current user-request backlog in `docs/USER_REQUESTS_TODO.md`
- official editor docs for [VS Code Python](https://code.visualstudio.com/docs/languages/python), [PyCharm](https://www.jetbrains.com/pycharm/features/), [Thonny](https://thonny.org/), [Spyder](https://spyder-ide.github.io/website-spyder/), and [Zed](https://zed.dev/docs/ai/overview)

## Executive Summary

The good news: ChoreBoy Code Studio is already much more than a simple editor. It already has a separate runner process, project templates, tree-sitter highlighting, a Python REPL, debugger wiring, plugin infrastructure, support bundles, packaging, per-project settings, and ChoreBoy-specific runtime probes. That is a serious foundation.

The hard truth: many of the current "IDE" features are homegrown and shallow compared with the mature semantics and workflow polish of top Python editors. The product is strongest in runtime fit, packaging, and ChoreBoy-native workflows. It is weakest in the exact places expert Python users decide whether an editor is trustworthy:

- semantic code intelligence
- safe refactoring
- dependency/environment workflow
- Python-aware formatting and imports
- visual runtime inspection

If we want to take the editor to the next level, the main work is not adding more isolated commands. The main work is making Python workflows feel trustworthy, teachable, and repeatable under ChoreBoy's constraints.

## Strategic Thesis

Code Studio should not chase feature parity with every desktop IDE. It should become:

- the most dependable Python editor for a locked-down, no-terminal, offline-first environment
- the easiest place for a ChoreBoy user to create, run, debug, package, and support a Python project
- a tool that feels safer and more self-explanatory than general-purpose editors because the environment is more constrained

That means the next level is not mostly about breadth. It is about depth in five areas:

1. trusted Python semantics
2. trusted project/runtime workflow
3. trusted debugging and testing
4. trusted recovery and supportability
5. trusted product maintainability

## Current Position

## What Code Studio Already Does Well

- Strong process model. `app/run/run_service.py`, `app/run/process_supervisor.py`, and runner boot paths implement the right editor-vs-runner separation.
- Strong ChoreBoy fit. `app/bootstrap/capability_probe.py`, project metadata under `cbcs/`, support bundles, packaging, and runtime-aware templates are exactly the right product instincts.
- Strong editing base. `app/editors/code_editor_widget.py` already supports breakpoints, diagnostics overlays, completion plumbing, search highlights, and adaptive large-file behavior.
- Strong customization surface. Settings, theme tokens, lint profiles, per-project overrides, and plugin manager UI are more mature than many internal tools ever reach.
- Strong extensibility direction. Plugin discovery, install/uninstall, trust, safe mode, runtime host isolation, and packaging are already real.
- Strong evidence of product seriousness. The codebase and docs show a real release mindset, not just an experiment.

## Where the Current Product Still Feels Second-Tier

- Python intelligence is broad but mostly heuristic.
- Refactors are present but not safe enough for larger real-world projects.
- Formatting is not yet a real Python formatting story.
- The dependency story is still weak for a no-terminal environment.
- The debugger exists, but the debugging experience is not yet rich enough.
- Testing exists, but it is not yet a first-class editor workflow.
- Large shell modules suggest product velocity will eventually slow under their own weight.

## Benchmark Comparison

## What Other Editors Do Better

| Editor | What it does especially well | What it does better than Code Studio today | What Code Studio already does better for ChoreBoy |
|---|---|---|---|
| VS Code + Python | Broad ecosystem, interpreter selection, linting/testing/debugging integration, strong IntelliSense | Better semantic completions, better testing UX, better formatter/linter ecosystem, better environment UX | Better ChoreBoy/runtime fit, better appliance-style packaging, better built-in awareness of AppRun and support-bundle workflows |
| PyCharm | Deep Python semantics, safe refactors, inspections, visual debugger, profiler | Better rename/find-references safety, better navigation confidence, better debugger UX, stronger "trust" for large Python projects | Lighter product direction and far better alignment with locked-down ChoreBoy distribution |
| Thonny | Beginner-first Python UX, step-by-step debugging, variables visibility, package GUI | Better learnability, better "what just happened?" feedback for new Python users, simpler mental model | Better project-first structure, better multi-file/product packaging direction, better long-term extensibility |
| Spyder | Console-heavy scientific workflow, variable explorer, integrated runtime inspection | Better REPL introspection, better variable inspection, better profiling and interactive execution feel | Better packaging, better support bundle model, better product direction for deployed ChoreBoy tools |
| Zed | Modern speed, collaboration, AI-assisted editing | Better editing feel, better AI-assisted workflows, stronger "modern editor" perception | Better offline/runtime specificity for ChoreBoy and less dependence on online/cloud assumptions |

## Competitive Readout

- Against lightweight editors like Thonny, Code Studio is already more ambitious and structurally stronger.
- Against serious Python editors like PyCharm and VS Code, Code Studio is still behind in semantic trust and workflow polish.
- Against modern editors like Zed, Code Studio is behind in speed perception and AI integration, but those are not the most urgent gaps for ChoreBoy.
- The best product opportunity is not "out-feature PyCharm." It is "out-fit PyCharm for ChoreBoy while borrowing the right parts of its trust model."

## Hard Truths

## 1. The product already has many IDE features, but too many of them are thinner than they look

Examples:

- `app/intelligence/reference_service.py` finds references by token scanning and AST definition lookup, not by a deeper semantic model.
- `app/intelligence/refactor_service.py` applies rename edits directly from those hits, which is useful but not yet strong enough to be treated as universally safe.
- `app/intelligence/navigation_service.py`, `hover_service.py`, and `signature_service.py` are sensible, but still closer to "clever local analysis" than "trusted Python language intelligence."

This is the single biggest product gap.

## 2. The formatting story is currently not credible enough

`app/editors/formatting_service.py` only trims trailing whitespace and ensures a final newline. That is fine as a helper, but it is not what users mean by "format file" or "format on save" in a Python editor.

If this remains as-is, the product will continue to feel custom and incomplete.

## 3. The ChoreBoy dependency workflow is still under-productized

This is arguably the most important ChoreBoy-specific gap.

Users do not have a normal terminal. They cannot casually create venvs, run `pip install`, or recover from dependency mistakes using shell muscle memory. A Python editor on ChoreBoy has to productize dependency handling in the GUI or through a very explicit import/vendor flow.

Today, the editor has better packaging than most tools, but not yet a complete "how do I add and trust a library?" workflow.

## 4. The debugging experience is functional, not yet confidence-building

PDB-based debugging is meaningful progress, but top-tier Python editors provide:

- richer call stack navigation
- watch expressions
- variable exploration
- exception visibility
- clearer current-frame feedback
- more discoverable debug/test loops

For ChoreBoy, this matters even more because users lack external tools.

## 5. Maintainability is becoming a real product risk

`app/shell/main_window.py` is very large and imports almost every major subsystem. The architecture is directionally good, but the shell still acts as a gravity well.

That does not just hurt code elegance. It slows every future improvement that needs shell wiring, increases regression risk, and makes the editor harder to evolve confidently.

## 6. Tooling hygiene still has rough edges

- `pyrightconfig.json` targets Python 3.11 even though `docs/DISCOVERY.md` makes Python 3.9 the production truth.
- `AGENTS.md` documents a known failing test.

These are not the biggest user-facing problems, but they are warning signs: the product will not feel top-tier if its own engineering confidence is fuzzy.

## Priority Matrix

The table below is sorted by importance first, then by practical leverage for ChoreBoy.

Difficulty labels:

- `S` = small
- `M` = medium
- `L` = large
- `XL` = very large / architectural

| Rank | Improvement | Importance | Difficulty | Why it matters | Recommended benchmark to learn from |
|---|---|---:|---:|---|---|
| 1 | Trusted Python semantics and navigation | Critical | XL | This is the biggest gap between "feature-rich" and "serious Python editor." Completion, definition, references, rename, hover, and import resolution need to be more trustworthy. | PyCharm, VS Code Python |
| 2 | ChoreBoy-native dependency and environment workflow | Critical | XL | Users lack a terminal. If adding libraries is painful or mysterious, the editor ceiling stays low no matter how many editor features ship. | VS Code environment UX, Thonny package UX |
| 3 | Real Python formatting and import management | Critical | M | Current formatting is too shallow. A great Python editor needs a real formatter and import organizer story. | VS Code Python, PyCharm, Thonny plugins |
| 4 | First-class testing workflow | High | M | A strong Python editor should make `pytest` discovery, run, rerun, and failure navigation obvious. | VS Code Python, PyCharm |
| 5 | Better debugger and runtime inspection | High | L | Debugging is already present but not yet rich enough for confident troubleshooting without external tools. | PyCharm, Spyder, Thonny |
| 6 | Safer refactors with preview, rollback, and confidence cues | High | L | Rename/import updates should feel reviewable and reversible, not opaque. | PyCharm |
| 7 | Local history, diffs, and recovery UX | High | M | ChoreBoy users need safety nets more than Git power features. Local history may matter more than full Git integration. | VS Code local history patterns, JetBrains local history |
| 8 | Architecture decomposition and engineering hygiene | High | M | Future feature work will slow down unless shell complexity is reduced and runtime/tooling truth is aligned. | Internal product health benchmark |
| 9 | Better onboarding and "explain the runtime" UX | High | S-M | Thonny is a reminder that clarity beats raw feature count for many Python users. | Thonny |
| 10 | Packaging/distribution polish for real deployed tools | Medium | M | This is a unique differentiator for ChoreBoy and should become a signature strength. | Internal differentiation, not direct parity |
| 11 | Stronger plugin ecosystem around Python workflows | Medium | L | Infrastructure is present, but the value is limited until high-value workflow plugins exist. | VS Code ecosystem, Spyder plugins |
| 12 | AI-assisted workflows with offline/local constraints | Low | XL | This can be valuable later, but it is not the next bottleneck. | Zed, Cursor, JetBrains AI |

## Detailed Recommendations

## 1. Trusted Python Semantics and Navigation

Importance: Critical
Difficulty: XL

### Why this matters

This is the largest capability gap versus PyCharm and VS Code.

Code Studio already has:

- completion via `app/intelligence/completion_service.py`
- navigation via `app/intelligence/navigation_service.py`
- hover via `app/intelligence/hover_service.py`
- signature help via `app/intelligence/signature_service.py`
- references via `app/intelligence/reference_service.py`
- rename via `app/intelligence/refactor_service.py`

That is impressive coverage. But most of it is still built from AST parsing, token scans, and project caches. That works for small-to-medium scripts. It becomes risky as projects grow, import graphs get deeper, symbols shadow each other, or Python's dynamic behavior shows up.

### What "next level" looks like

- deeper symbol resolution across modules
- more trustworthy completion ordering
- better import-aware and scope-aware rename
- clearer confidence levels when the engine is unsure
- stronger hover/signature data for user-defined and imported symbols
- fewer false-positive references

### Best implementation direction for ChoreBoy

Because ChoreBoy cannot depend on Node or arbitrary sidecar binaries inside AppRun, the best path is likely pure-Python, in-process intelligence:

- short-term: evaluate `jedi` for completion, definition, signatures, and doc resolution
- short-term: evaluate `LibCST` or `rope` for safer rename/import-aware refactors
- medium-term: keep the current symbol index for fast project scans, but use a smarter semantic engine for final resolution
- always: preserve graceful fallback when a library cannot fully resolve dynamic code

### Hard recommendation

Do not keep stacking more features onto the current heuristic layer until the semantic core improves. That will widen the "looks smart, acts risky" gap.

## 2. ChoreBoy-Native Dependency and Environment Workflow

Importance: Critical
Difficulty: XL

### Why this matters

This is the most ChoreBoy-specific missing piece.

Normal Python editors rely on terminals, venvs, `pip`, Conda, or shell access. ChoreBoy users do not have that. That means Code Studio has to own the entire dependency story much more explicitly.

### What is missing

- a UI for adding a package from local wheel/zip/folder
- validation for Python 3.9 compatibility
- validation for compiled-extension feasibility under ChoreBoy's `noexec` and AppArmor constraints
- clear feedback about whether a package is:
  - pure Python and safe
  - compiled but supported through memfd loader patterns
  - unsupported on ChoreBoy
- a stable place to manage project-local vendored packages
- better guidance for how `vendor/` is used at runtime

### What "next level" looks like

- "Add Dependency..." wizard
- project dependency manifest in `cbcs/`
- compatibility audit before run/package
- curated dependency bundles for common safe libraries
- warnings when a user attempts to import something that is not packaged into the project

### Why this matters more than generic IDE features

On ChoreBoy, dependency friction can kill a project before semantic completion ever matters.

## 3. Real Python Formatting and Import Management

Importance: Critical
Difficulty: M

### Why this matters

Today, formatting is effectively whitespace cleanup. That is a helper, not a Python formatter.

### What to add

- ship a real Python formatter, ideally pure-Python and vendorable
- provide format file and format-on-save that users can trust
- add import sorting and grouping
- show formatter status clearly in settings and the UI
- make "format failed" errors understandable

### Best candidates

- `black` for predictable formatting
- `isort` for imports

### Important product principle

If the editor says "format on save," it must perform a recognizable Python formatting action. Otherwise the product will feel misleading.

## 4. First-Class Testing Workflow

Importance: High
Difficulty: M

### Why this matters

A strong Python editor is not just about editing and running one file. It is about tightening the edit-test-debug loop.

### What already exists

- `pytest` runtime path exists
- test-running helpers already exist

### What is missing

- visible test explorer
- file/class/test discovery UI
- run current test
- rerun failed tests
- test result navigation back into editor
- coverage summary
- debug this test

### Why this is especially important on ChoreBoy

Because users do not have a terminal, the editor must own the testing workflow rather than assume command-line literacy.

## 5. Better Debugger and Runtime Inspection

Importance: High
Difficulty: L

### Why this matters

Code Studio already deserves credit for shipping debugger wiring. But from a user point of view, the next level is not just stepping. It is inspectability.

### What to learn from competitors

- PyCharm: strong call stack, variable inspection, watches, exception context
- Spyder: strong live variable exploration
- Thonny: strong step clarity for understanding code behavior

### What to add

- stronger watch expressions
- better locals/globals presentation
- variable explorer pane for simple Python objects
- clearer exception pause behavior
- conditional breakpoints and hit conditions
- "debug current file" and "debug current test" flows that feel obvious

### ChoreBoy-specific opportunity

Because the environment is closed, an excellent in-app debugger is more valuable than on a normal desktop.

## 6. Safer Refactors With Preview and Rollback

Importance: High
Difficulty: L

### Why this matters

Current rename capability is a strong start, but users need confidence cues before they trust large-scale edits.

### What to add

- preview panel before applying rename/import updates
- confidence indicators when the engine is heuristic
- automatic rollback on partial failure
- per-file diff preview
- undo story that survives more than one editor session when needed

### Strategic value

Safe refactors are one of the clearest dividing lines between "text editor with extras" and "serious Python IDE."

## 7. Local History, Diffs, and Recovery UX

Importance: High
Difficulty: M

### Why this matters

Git integration is useful, but local history may be even more aligned with ChoreBoy users.

Users need easy ways to:

- see what changed
- restore yesterday's version
- compare autosave/recovery state with saved state
- recover from bad refactors or accidental file operations

### Why this should come before deep Git work

Git assumes mental models and tooling habits that many ChoreBoy users may not have. Local history gives most of the safety value with less conceptual overhead.

## 8. Architecture Decomposition and Engineering Hygiene

Importance: High
Difficulty: M

### Why this matters

The editor will not scale well if major workflows keep piling into `app/shell/main_window.py`.

### What to improve

- continue extracting workflow-specific controllers and coordinators
- keep `MainWindow` as composition root rather than logic hub
- split large UI-heavy modules like `settings_dialog.py`, `style_sheet.py`, and `code_editor_widget.py`
- align `pyrightconfig.json` with Python 3.9 reality or add an explicit 3.9 validation gate
- clear the documented failing test and restore a stronger green baseline

### Why this belongs in a product strategy doc

Because maintainability is now directly connected to how fast the product can ship next-level capabilities.

## 9. Better Onboarding and Runtime Explanation

Importance: High
Difficulty: S-M

### Why this matters

Thonny is a strong reminder that beginner trust often comes from explanation, not raw power.

Code Studio should explain:

- what runtime is being used
- why a package/import may fail
- when headless FreeCAD behavior differs
- what run configuration is active
- how to package/export a project
- how to recover from failures without a terminal

### Recommended UX additions

- guided first-run Python project walkthrough
- "why did this fail?" explanations tied to common ChoreBoy/runtime issues
- dependency compatibility tips before run/package
- better surfacing of run configs, default entry point, and active-file vs project run behavior

## 10. Packaging and Distribution Polish

Importance: Medium
Difficulty: M

### Why this matters

This is one area where Code Studio can beat general-purpose editors in a way that matters to ChoreBoy users.

### What to improve

- one-click package validation before export
- clearer install/upgrade story for packaged projects
- dependency audit inside packaging flow
- smoother relocatable path support
- better generated user-facing package metadata and docs

### Strategic value

The editor should make it unusually easy to turn a Python project into something a ChoreBoy dealer or power user can hand to someone else over USB.

## 11. Stronger Plugin Ecosystem Around Python Workflows

Importance: Medium
Difficulty: L

### Why this matters

The plugin substrate is real, but the highest-value plugin use cases should be closer to Python productivity:

- formatters
- linters
- project templates
- packaging helpers
- FreeCAD workflow helpers
- diagnostics/explainers

### Hard truth

Plugin infrastructure without killer workflow plugins is architecture without market pull.

## 12. AI-Assisted Workflows

Importance: Low
Difficulty: XL

### Why this matters

Modern editors increasingly treat AI as table stakes. Zed, VS Code, and JetBrains all push hard here.

### Why this is not a top priority yet

- ChoreBoy is offline-first / constrained
- the editor still has more urgent core-product gaps
- AI without trusted local context and workflow integration becomes surface glitter

### Recommended stance

Defer major AI investment until:

- semantics are stronger
- dependency workflow is productized
- testing/debugging workflows are first-class
- there is a credible offline or bring-your-own-model story

## Improvements by Difficulty

## Best High-Impact, Lower-Difficulty Wins

- ship real Python formatting and import sorting
- improve onboarding and runtime explanation
- align Python 3.9 tooling truth and clear known failing test debt
- make run/test/debug entry points more discoverable
- add local history and restore UX

## Best Medium-Difficulty Strategic Wins

- test explorer and better test result UX
- safer refactor preview and rollback
- packaging validation and dependency audit
- shell/controller decomposition
- better variable/watch inspector experience

## Best High-Difficulty, Transformative Bets

- stronger semantic engine for Python intelligence
- ChoreBoy-native dependency ingestion and compatibility management
- richer debugger with variable explorer and advanced breakpoints
- offline-capable AI workflow layer

## If We Only Do Five Things

If the goal is to meaningfully move the product toward "great Python editor for ChoreBoy users," the top five bets should be:

1. Replace or augment heuristic Python intelligence with a more trustworthy semantic layer.
2. Productize dependency management for ChoreBoy instead of assuming terminal skills.
3. Ship a real formatter/import organizer and stop treating whitespace cleanup as formatting.
4. Turn testing and debugging into first-class, highly discoverable workflows.
5. Reduce shell complexity and align engineering tooling with Python 3.9 production reality.

## What We Should Not Prioritize First

These may be useful eventually, but they are not the highest-leverage next-level work right now:

- broad multi-language parity beyond Python and core support files
- cloud-first AI features
- deep generic GitHub or remote-dev workflows
- notebook-first workflows
- large amounts of surface-area polish that do not improve trust or runtime success

## Recommended Product Direction

The strongest possible version of Code Studio is not a compromised clone of bigger editors.

It is:

- more trustworthy than lightweight Python editors
- more teachable than expert-heavy IDEs
- more deployable than general-purpose editors
- more aware of runtime constraints than any mainstream alternative

That means the winning roadmap is:

- borrow semantic trust from PyCharm and VS Code
- borrow clarity from Thonny
- borrow runtime inspection ideas from Spyder
- borrow modern workflow expectations, selectively, from Zed
- keep doubling down on packaging, support, and constrained-runtime fitness that only Code Studio can own

## Bottom Line

Code Studio is already closer to a real Python IDE than its name may undersell. But to reach the next tier, it needs less feature sprawl and more trust in the core Python workflow.

The biggest missing pieces are not more commands or more panes. They are:

- trustworthy Python semantics
- trustworthy dependency workflow
- trustworthy formatting/refactoring
- trustworthy debug/test loops
- trustworthy internal maintainability

If those five areas improve, Code Studio can become a genuinely excellent Python editor for ChoreBoy users without ever needing to become a generic desktop IDE.
