# ChoreBoy Code Studio: Next-Level Python Editor Audit

Date: 2026-03-25

## Purpose

This document is no longer just a forward-looking wishlist. It is a current-state audit of how far ChoreBoy Code Studio has already moved toward becoming a great Python editor for ChoreBoy users, what is still missing, and what should happen next.

The goal is still not "become VS Code on ChoreBoy." The goal is:

- be the best Python-first editor that actually fits ChoreBoy's runtime and UX constraints
- preserve the product's strongest advantage: deep alignment with `docs/DISCOVERY.md`
- prioritize user trust, clarity, and supportability over feature-count theater
- make the next roadmap decisions from first principles rather than from stale assumptions

This audit is based on:

- product/runtime docs: `docs/PRD.md`, `docs/DISCOVERY.md`, `docs/ARCHITECTURE.md`, `docs/TASKS.md`
- current implementation under `app/`, `bundled_plugins/`, and the packaging flows
- current user-request backlog in `docs/USER_REQUESTS_TODO.md`
- competitor framing from VS Code Python, PyCharm, Thonny, Spyder, and Zed

## Audit Status Legend

- `done` - the core recommendation is materially delivered; remaining work is mostly polish or follow-on scope
- `substantial_partial` - there is real shipped product value, but trust, discoverability, or workflow depth is still incomplete
- `early_partial` - enabling infrastructure exists, but the user-facing workflow is still thin or incomplete
- `not_started` - no meaningful product slice has landed yet

## Executive Summary

The previous version of this document was directionally right, but it now understates the current product. Code Studio is no longer "promising scaffolding plus a lot of homegrown features." It already has a separate runner process, real packaging/export flows, runtime explanation surfaces, local history and recovery, Python formatting/import management, pytest execution, debugger surfaces, provider-based plugins, and ChoreBoy-specific validation paths.

That is the good news. The hard part is that the remaining gaps are now more subtle and more important. The next tier will not come from adding more isolated commands or more architecture layers. It will come from making the core Python workflow more trustworthy and more obvious for a user who has no terminal, no package-manager muscle memory, and no fallback IDE.

From a first-principles standpoint, the product now needs to shift from "build more substrate" to "finish the workflows that decide whether people trust the editor." The highest-leverage bets are:

- a terminal-free dependency lifecycle
- deeper semantic trust and clearer confidence signaling
- a first-class test/debug loop
- stronger onboarding and runtime/dependency explanation
- continued shell, backlog, and documentation alignment

Packaging and plugin infrastructure should now be treated as strengths to polish, not as the main missing foundations. AI-assisted workflows should remain explicitly deferred until the core Python workflows are stronger.

## Strategic Thesis

Code Studio should not chase broad parity with desktop IDEs. It should become:

- the most dependable Python editor for a locked-down, no-terminal, offline-first environment
- the easiest place for a ChoreBoy user to create, add dependencies to, run, test, debug, package, and support a Python project
- a tool that is more honest about confidence and constraints than mainstream editors because ChoreBoy users need supportable behavior more than magic

That means the next level is not mostly about breadth anymore. It is about depth in five areas:

1. terminal-free dependency workflow
2. semantic trust and reviewable edits
3. discoverable run, test, and debug loops
4. runtime explanation, recovery, and supportability
5. maintainable internals and truthful docs/backlog state

## Current Position

## What Code Studio Already Does Well

- Strong process model. `app/run/run_service.py`, `app/run/process_supervisor.py`, and the runner boot path already implement the right editor-vs-runner separation.
- Strong ChoreBoy fit. `app/bootstrap/capability_probe.py`, visible `cbcs/` metadata, support bundles, project packaging, and runtime-aware templates remain exactly the right product instincts.
- Strong editor base. Tree-sitter highlighting, breakpoint gutters, adaptive large-file behavior, preview tabs, project tree actions, run-current-file, and per-project settings are real product features, not stubs.
- Strong safety model. Local history, draft recovery, restore-to-buffer flows, packaging validation, and structured runtime explanations reduce the damage from mistakes in a no-terminal environment.
- Strong workflow infrastructure. Provider-based plugins, bundled workflow plugins, packaging wizard flows, dependency audit, and runtime-center surfaces are already beyond what many editor products ever reach.
- Strong evidence of seriousness. The codebase, tests, packaging contract, and manual docs all show a release-minded product rather than a prototype.

## Where the Current Product Still Feels Second-Tier

- Dependency handling is still too manual for a locked-down environment.
- Semantic intelligence is materially better than the old audit described, but it still does not feel "PyCharm-trustworthy" on harder Python cases.
- Refactors and debugging have real foundations, but the review and inspectability experience is not yet rich enough.
- Testing power exists, but it is not yet surfaced as an obvious first-class workflow.
- Documentation and backlog state no longer fully reflect shipped reality, which can misdirect future work.
- Plugin infrastructure is ahead of the actual third-party ecosystem it is supposed to enable.

## Audit Scorecard

| # | Area | Status | Audit snapshot |
|---|---|---|---|
| 1 | Trusted Python semantics and navigation | `substantial_partial` | `SemanticSession`, `SemanticFacade`, Jedi-backed read-only semantics, and Rope-backed rename planning are already shipped; the remaining gap is trust, proof, and UX clarity. |
| 2 | ChoreBoy-native dependency and environment workflow | `early_partial` | Vendoring, dependency audit, import explanation, and packaging validation exist; adding and managing dependencies is still too manual. |
| 3 | Real Python formatting and import management | `substantial_partial` | Black/isort adapters, `pyproject.toml` resolution, organize-imports, and save-time formatting are real; the remaining work is readiness UX and structural import-management follow-through. |
| 4 | First-class testing workflow | `substantial_partial` | Project/current-file pytest runs and failure-to-Problems integration exist, including debug-current-test; there is still no test explorer, rerun-failed flow, or coverage UX. |
| 5 | Better debugger and runtime inspection | `substantial_partial` | The debug panel already has stack, threads, variables, watches, and breakpoint controls; reliability and inspectability still need to deepen. |
| 6 | Safer refactors with preview and rollback | `substantial_partial` | Semantic rename preview/apply, rollback-on-write-failure, and local history recording exist; the review surface and confidence cues are still too thin. |
| 7 | Local history, diffs, and recovery UX | `substantial_partial` | Draft recovery, per-file history, global restore, deleted-file recovery, and retention controls are already a real differentiator. |
| 8 | Architecture decomposition and engineering hygiene | `substantial_partial` | Controller/session extraction, editor module splitting, and 3.9 tooling truth have improved materially; `MainWindow` size and doc/backlog drift are still real risks. |
| 9 | Better onboarding and runtime explanation | `substantial_partial` | Welcome checklist, Runtime Center, project health, preflight, and contextual explainers are shipped; guided flow and dependency-centric onboarding can improve. |
| 10 | Packaging and distribution polish | `substantial_partial` | Packaging is now one of the strongest current areas, with validation, wizard flows, and installable/portable profiles; relocatability and upgrade polish remain. |
| 11 | Stronger plugin ecosystem around Python workflows | `early_partial` | The platform is real and bundled providers exist, but the broader ecosystem is still mostly first-party. |
| 12 | AI-assisted workflows | `not_started` | There is no dedicated AI workflow layer yet, which is acceptable given higher-priority gaps. |

## Benchmark Comparison

## What Other Editors Still Do Better

| Editor | What it still does especially well | What it still does better than Code Studio today | What Code Studio now does especially well for ChoreBoy |
|---|---|---|---|
| VS Code + Python | Broad ecosystem, interpreter/env workflows, test explorer, polished IntelliSense | Better dependency/environment UX, better testing UX, deeper ecosystem reach | Better ChoreBoy/runtime fit, better packaging, better support-bundle and runtime-explanation workflows |
| PyCharm | Deep Python semantics, safe refactors, visual debugger, inspections | Better semantic confidence, better refactor review UX, better debugger trust | Lighter product direction, better fit for locked-down distribution, better appliance-style support flows |
| Thonny | Beginner-first Python UX, step clarity, package GUI | Better onboarding clarity and easier package mental model | Better project-first structure, better packaging/export direction, better long-run extensibility |
| Spyder | Runtime inspection, console-heavy workflows, variable exploration | Better live runtime inspection and object exploration | Better packaging, better project packaging/support story, better constrained-runtime awareness |
| Zed | Modern editing feel, AI assistance, perceived speed | Better modern-editor perception and AI story | Better offline/runtime specificity and less dependence on cloud assumptions |

## Competitive Readout

- Against lightweight editors like Thonny, Code Studio is now materially ahead in project structure, packaging, runtime explanation, and safety tooling.
- Against serious Python editors like PyCharm and VS Code, Code Studio is still behind in semantic trust, dependency UX, and test/debug discoverability.
- Against modern editors like Zed, Code Studio is still behind in AI and "modern editor" perception, but those are not the bottlenecks that most limit ChoreBoy users today.
- The best product opportunity is still not "out-feature PyCharm." It is "out-fit mainstream editors for ChoreBoy while borrowing their trust model where it matters."

## Hard Truths

## 1. The old audit now understates the product

The previous version correctly identified the strategic gaps, but several specific claims are now stale. Code Studio already has real semantics infrastructure, real Python formatting/import tooling, real pytest hooks, real debugger surfaces, real local history, and real packaging/runtime explanation flows. The next roadmap should start from what has landed, not from what used to be missing.

## 2. The semantic trust gap is still real, but it is no longer a "token scan only" story

The product now has `SemanticSession`, `SemanticFacade`, Jedi-backed read-only semantics, and Rope-backed rename planning. The remaining problem is that advanced users still need stronger proof, broader fixture coverage, clearer confidence signaling, and better review surfaces. The gap moved from "absence of engines" to "how much users can trust the result."

## 3. The formatting story is now credible for Python

The old claim that formatting was only whitespace cleanup is no longer true for Python. Black and isort are already integrated, project-local `pyproject.toml` settings are resolved, and format/organize-imports can run through provider workflows. The remaining work is readiness UX, failure clarity, and keeping structural import edits separate from simple style tooling.

## 4. Dependency lifecycle is now the biggest uniquely ChoreBoy gap

This is still the least productized critical workflow. Code Studio can already audit dependencies and explain missing imports, but users still lack a terminal-free "add, inspect, trust, remove, and package this dependency" loop. In a no-terminal appliance, that matters more than many classic IDE features.

## 5. Packaging and plugins are ahead of the rest of the product

That is a good problem to have. Packaging, validation, provider-based plugins, bundled workflow plugins, and supportability seams are already stronger than many editor products ever reach. The risk is that the team keeps building more substrate instead of finishing the user-facing workflows that most need it.

## 6. Maintainability risk is now partly a truth-management problem

`app/shell/main_window.py` is still large, but file size is no longer the only maintainability issue. Some docs and backlog phases still describe already-shipped work as future work. If architecture docs, analysis docs, and tasks drift from reality, the product can waste time solving the wrong problems.

## 7. There is already more workflow power than the UI makes obvious

Project/current-file test runs, debug-current-test, runtime explanations, local history restore, organize-imports, package validation, and provider provenance already exist. The next win is not just adding more commands. It is making the current power easier to discover, easier to trust, and easier to learn.

## Priority Matrix

The ranking below is sorted by next strategic leverage for the product, not by which areas are least implemented.

| Rank | Improvement | Current status | Importance | Difficulty | Why it matters now | Recommended benchmark to learn from |
|---|---|---|---:|---:|---|---|
| 1 | ChoreBoy-native dependency and environment workflow | `early_partial` | Critical | XL | Without a terminal-free dependency lifecycle, project complexity hits a ceiling quickly on ChoreBoy. | VS Code environment UX, Thonny package UX |
| 2 | Trusted Python semantics and navigation | `substantial_partial` | Critical | XL | The semantics layer is real, but trust and confidence still decide whether expert users rely on the editor. | PyCharm, VS Code Python |
| 3 | First-class testing workflow | `substantial_partial` | High | M | No-terminal users need a visible, repeatable test loop, not just command-like test actions. | VS Code Python, PyCharm |
| 4 | Better debugger and runtime inspection | `substantial_partial` | High | L | Debug foundations exist, but the inspectability and reliability bar is higher in a closed environment with no external tools. | PyCharm, Spyder, Thonny |
| 5 | Better onboarding and runtime explanation | `substantial_partial` | High | M | Explanation is part of the product in a constrained runtime, especially around imports, run targets, and packaging. | Thonny |
| 6 | Architecture decomposition and engineering hygiene | `substantial_partial` | High | M | Future velocity now depends on keeping shell ownership, docs, backlog, and validation truth aligned. | Internal product health benchmark |
| 7 | Safer refactors with preview, rollback, and confidence cues | `substantial_partial` | High | M-L | Rename exists, but larger projects still need a richer review/apply story before the feature feels truly safe. | PyCharm |
| 8 | Real Python formatting and import management | `substantial_partial` | Medium | M | The base contract is now shipped; remaining work is polish, clarity, and structural follow-on alignment. | VS Code Python, PyCharm |
| 9 | Local history, diffs, and recovery UX | `substantial_partial` | Medium | M | This is already a signature strength; the next work is polish and discoverability, not another storage rewrite. | JetBrains local history, VS Code patterns |
| 10 | Packaging and distribution polish | `substantial_partial` | Medium | M | Packaging is already differentiated; the remaining work is upgrade, relocatability, and handoff polish. | Internal differentiation |
| 11 | Stronger plugin ecosystem around Python workflows | `early_partial` | Medium | L | The platform is ready enough; the next value comes from better providers and examples, not more plugin plumbing. | VS Code ecosystem, Spyder plugins |
| 12 | AI-assisted workflows with offline/local constraints | `not_started` | Low | XL | This is worth revisiting later, but it is not the next bottleneck for ChoreBoy users. | Zed, Cursor, JetBrains AI |

## Detailed Recommendations

## 1. Trusted Python Semantics and Navigation

Importance: Critical  
Audit status: `substantial_partial`

### Why this matters

This is still one of the clearest gaps versus PyCharm and VS Code. It is also the area where the old audit is most stale: Code Studio already moved beyond pure token/AST heuristics.

### Progress so far

- `app/intelligence/semantic_session.py` and `app/intelligence/semantic_worker.py` already give the editor a serialized semantic lane rather than ad-hoc background calls.
- `app/intelligence/semantic_facade.py` already routes read-only semantics through `app/intelligence/jedi_engine.py`.
- `app/intelligence/refactor_engine.py` already gives rename planning a Rope-backed lane.
- `app/intelligence/completion_service.py` already distinguishes semantic and approximate results rather than pretending everything is equally trustworthy.
- Unit, integration, and runtime-parity tests already exist around semantic navigation and engine behavior.

### What is still missing

- Broader trust on harder Python cases such as deeper import graphs, shadowing, partially broken buffers, and more dynamic code.
- Better user-visible confidence signaling in the UI, not just metadata traveling through the backend.
- Clearer handling of ambiguous or degraded results so the editor is honest when it is approximating.
- A richer multi-file review surface for semantic operations such as rename.

### Recommended next steps

- Treat Jedi and Rope as the current semantic foundation, not as future evaluation candidates.
- Expand fixture-heavy tests around the hardest Python cases before adding more semantic features.
- Make confidence visible in editor UX for completion, hover, references, and rename.
- Keep tree-sitter and SQLite as acceleration layers rather than semantic truth.
- If the current engine stack eventually hits a hard ceiling, replace it behind the existing facade instead of widening the heuristic layer.

## 2. ChoreBoy-Native Dependency and Environment Workflow

Importance: Critical  
Audit status: `early_partial`

### Why this matters

This remains the most important ChoreBoy-specific gap. A no-terminal product cannot assume that users will manage `vendor/` manually forever.

### Progress so far

- `vendor/README.md` and the vendored runtime/tooling loaders already define an approved dependency path.
- `app/packaging/dependency_audit.py` already inspects imports, flags native-extension risk, and surfaces subprocess assumptions before export.
- `app/intelligence/diagnostics_service.py` and `app/support/runtime_explainer.py` already explain unresolved imports and common runtime failures in user-facing language.
- Packaging validation already knows how to warn about missing, vendored, runtime, and native dependency classes.

### What is still missing

- No `Add Dependency...` GUI workflow.
- No first-class project dependency manifest in `cbcs/` for third-party libraries.
- No guided ingest flow for local wheels, zip files, or vendored folders.
- No clear lifecycle for update, remove, inspect, or re-audit.
- No simple, visible classification of "pure Python and safe", "native but supported through approved loader patterns", or "unsupported on ChoreBoy".

### Recommended next steps

- Make this the next major product workflow investment.
- Introduce a project-local dependency manifest under `cbcs/` so vendoring decisions become inspectable, supportable, and packageable.
- Build a terminal-free dependency wizard for local wheel/zip/folder ingestion plus curated safe bundles.
- Reuse existing dependency-audit and runtime-explainer work instead of inventing a second compatibility layer.
- Keep the workflow deterministic and visible; do not hide dependency magic in implicit caches or hidden paths.

## 3. Real Python Formatting and Import Management

Importance: Medium  
Audit status: `substantial_partial`

### Why this matters

The product can now credibly say it supports real Python formatting. The challenge is to make that reliability obvious and keep the boundaries clean.

### Progress so far

- `app/python_tools/black_adapter.py` already provides Black-backed formatting.
- `app/python_tools/isort_adapter.py` already provides import organization.
- `app/python_tools/config.py` already resolves project-local `pyproject.toml` settings.
- Save-time and manual format/import actions are already wired through workflow providers.
- Runtime readiness probing for Python tooling already exists.

### What is still missing

- Better user-facing readiness and troubleshooting surfaces when tooling is unavailable or misconfigured.
- Clearer product messaging that distinguishes Python formatting from generic text hygiene.
- Stronger follow-through between style-oriented import organization and later semantic import rewrites.
- Continued doc/backlog cleanup so this area is no longer described as "whitespace cleanup only."

### Recommended next steps

- Keep Black and isort as the phase-1 contract. Do not reopen the formatter decision unless a hard runtime problem appears.
- Improve status and settings surfaces so users can tell whether Python tooling is ready and whether project-local config was found.
- Keep structural import edits in the semantic/refactor lane rather than loading more intelligence into organize-imports.
- Prefer polish and clarity over adding yet another style system.

## 4. First-Class Testing Workflow

Importance: High  
Audit status: `substantial_partial`

### Why this matters

A serious Python editor is not just an edit/run tool. On ChoreBoy, the editor must own the test loop because users cannot fall back to a shell.

### Progress so far

- `app/run/test_runner_service.py` already launches pytest through the correct runtime and parses failures into `ProblemEntry` results.
- `app/shell/menus.py` and `app/shell/main_window.py` already expose Run Project Tests, Run Current File Tests, and Debug Current Test flows.
- Pytest failures already flow back into the Problems surface.
- Workflow-provider integration already exists for pytest.

### What is still missing

- No test explorer or collection tree.
- No caret-level "run current test" targeting; current targeting is file-scoped.
- No rerun-failed-only workflow.
- No coverage surface.
- No dedicated test result UI beyond console plus Problems.

### Recommended next steps

- Build a test explorer on top of the current pytest service rather than rewriting the runtime path.
- Add discovery for file/class/test nodes and rerun-failed flows.
- Make current test, current file, and project test scopes obvious and easy to pick.
- Keep debug-current-test tightly integrated with the test surface.
- Treat coverage as a follow-on once discovery and rerun loops are solid.

## 5. Better Debugger and Runtime Inspection

Importance: High  
Audit status: `substantial_partial`

### Why this matters

Debugger progress is already meaningful, but the next tier is inspectability and confidence, not just stepping.

### Progress so far

- `app/shell/debug_panel_widget.py` already provides threads, call stack, variables, watches, breakpoint listing, and debug output surfaces.
- `app/runner/debug_runner.py` already supports breakpoint conditions and hit conditions.
- Current file, project, and pytest-target debug entry points already exist in the shell.
- Manual docs and automated tests already cover meaningful debug behavior.

### What is still missing

- A more robust structured transport and engine story for long-run debug reliability.
- Better variable/object inspection and clearer bounded previews for complex data.
- Stronger exception visibility and failure messaging when the debug session itself degrades.
- A tighter pairing between test failures and debug follow-up.

### Recommended next steps

- Finish the structured debug transport and session-contract hardening already implied by the architecture docs.
- Improve locals, watches, and object previews before adding more raw debugger commands.
- Make failed test to debug this test a first-class loop.
- Keep the debugger heavily support-oriented because users do not have a terminal debugger as a fallback.

## 6. Safer Refactors With Preview and Rollback

Importance: High  
Audit status: `substantial_partial`

### Why this matters

Refactors are where users decide whether the editor is a text editor with extras or a serious Python tool. Code Studio already crossed the "extras" line, but not the "trust it everywhere" line.

### Progress so far

- `app/intelligence/refactor_engine.py` already plans rename changes through Rope and produces per-file preview patches.
- `app/intelligence/semantic_facade.py` already routes semantic rename through the trusted semantic lane.
- Rename apply already rolls back on write failure.
- Successful rename applies are already recorded into local history transactions.

### What is still missing

- A richer multi-file review surface than a confirm dialog with preview text.
- Clear user-visible confidence cues about what the engine proved versus what it could not prove.
- Better rollback/review UX than "apply and rely on undo/history if needed."
- Stronger alignment between rename, import rewrite, and future semantic refactor surfaces.

### Recommended next steps

- Build a dedicated refactor preview surface with grouped file patches and explicit confidence language.
- Keep local history as a safety net, but do not use it as a substitute for good preview UX.
- Treat import updates and semantic rename as part of one reviewable edit model over time.
- Avoid adding more ad-hoc code actions until the review/apply model is stronger.

## 7. Local History, Diffs, and Recovery UX

Importance: Medium  
Audit status: `substantial_partial`

### Why this matters

For ChoreBoy users, local history is often more valuable than deep Git integration. This area is already one of Code Studio's best product instincts.

### Progress so far

- `app/persistence/local_history_store.py` already provides SQLite-plus-blob local history storage with drafts and checkpoints.
- `app/shell/local_history_dialog.py` already gives draft recovery diff review and per-file local history compare/restore flows.
- `app/shell/history_restore_picker.py` already supports global history restore, including moved or deleted files.
- Settings, retention, and automated tests already exist for the local history system.

### What is still missing

- Better discoverability and product framing so users understand this as a core safety feature.
- Continued polish in support tooling and docs so shipped behavior is reflected accurately.
- Fewer stale backlog references that still read as if this work has not landed.

### Recommended next steps

- Treat local history as a signature product feature, not as hidden plumbing.
- Improve discoverability through help, recovery flows, and support surfaces rather than building a second storage rewrite.
- Keep polishing labels, restore cues, and documentation so users trust it before they need it.
- Do not over-prioritize new history substrate work ahead of dependency, semantics, and test/debug loops.

## 8. Architecture Decomposition and Engineering Hygiene

Importance: High  
Audit status: `substantial_partial`

### Why this matters

Long-run product quality now depends on keeping the editor's internal truth honest: code structure, docs, backlog, and runtime assumptions all need to line up.

### Progress so far

- `app/shell/main_window.py` is still large, but the product already extracted meaningful workflow ownership into controllers and coordinators such as `project_controller`, `run_session_controller`, `editor_workspace_controller`, and `editor_intelligence_controller`.
- `CodeEditorWidget`, settings dialog construction, and stylesheet builders have already been split into focused modules.
- `pyrightconfig.json` already targets Python 3.9 source compatibility.
- `AGENTS.md` already reflects a strong test baseline instead of documenting a failing suite.

### What is still missing

- `MainWindow` is still a very large integration point.
- Some UI-heavy modules remain large enough to slow change.
- Backlog and analysis docs still lag shipped implementation in several areas.
- The dual truth of Python 3.9 production and 3.11 cloud dev remains easy to drift from without discipline.

### Recommended next steps

- Keep `MainWindow` as a composition root, but continue pulling workflow ownership outward by reason to change.
- Treat docs/backlog sync as a real quality gate, not as optional cleanup.
- Prefer feature slices that update code, tests, architecture, and task status together.
- Keep Python 3.9 compatibility and validation gates explicit in every future feature phase.

## 9. Better Onboarding and Runtime Explanation

Importance: High  
Audit status: `substantial_partial`

### Why this matters

In a constrained runtime, explanation is not secondary polish. It is part of the core product.

### Progress so far

- `app/shell/welcome_widget.py` already includes a first-run checklist and onboarding actions.
- Runtime-center surfaces and structured explanation models already turn startup and project facts into user-facing guidance.
- `app/support/preflight.py` already catches obvious run/package issues before the expensive path starts.
- Project health, help docs, and support bundles already work together more than the old audit reflected.

### What is still missing

- A more guided end-to-end first-run story.
- Stronger surfacing of active run target and configuration state before execution.
- Dependency onboarding and dependency failure guidance tied directly into the learning flow.
- Continued wording cleanup so welcome, help, runtime center, and manual docs never drift.

### Recommended next steps

- Build onboarding around the real user journey: open or create project, add dependency, run, hit a failure, recover, package.
- Make active file vs project vs named configuration unmistakable before a run starts.
- Surface import and dependency explanations earlier, not only after a failure.
- Keep runtime explanation, onboarding, and support bundles driven by the same structured facts.

## 10. Packaging and Distribution Polish

Importance: Medium  
Audit status: `substantial_partial`

### Why this matters

Packaging is now one of the clearest areas where Code Studio can beat general-purpose editors for ChoreBoy users.

### Progress so far

- `app/packaging/validator.py`, `app/packaging/dependency_audit.py`, and related packaging modules already provide a strong manifest-driven validation path.
- The packaging wizard, installable default profile, portable profile, and product-package convergence are all real shipped work.
- Packaging already integrates dependency and preflight checks instead of treating export as a blind zip step.

### What is still missing

- Relocatable installation remains an open user-facing gap.
- Install/upgrade/move stories can still become clearer.
- Generated recipient-facing metadata and handoff UX can still improve.

### Recommended next steps

- Finish the relocatability audit and remove remaining path assumptions that unnecessarily anchor to one install location.
- Keep installable packaging as the default polished path and treat portable as a specialized mode.
- Make packaging output even better at explaining what was bundled, what was excluded, and how to install or upgrade safely.
- Avoid spending more time on packaging substrate unless it directly improves handoff or supportability.

## 11. Stronger Plugin Ecosystem Around Python Workflows

Importance: Medium  
Audit status: `early_partial`

### Why this matters

The plugin platform is no longer hypothetical. The question now is whether it will generate enough workflow value to justify its complexity.

### Progress so far

- `app/plugins/` already contains a real host, broker, catalog, manifest, project policy, and provenance model.
- Bundled first-party providers already cover formatting, diagnostics, pytest, templates, runtime explanation, packaging, FreeCAD helpers, and dependency audit.
- The Plugin Manager and support surfaces already expose provider provenance and policy state.

### What is still missing

- A richer external ecosystem.
- More "must-have" workflow plugins that feel distinct from core wrappers.
- Clear exemplars for third-party authors who want to build high-value Python productivity features.

### Recommended next steps

- Judge plugin work by user-facing workflow value, not by platform novelty.
- Focus ecosystem efforts on a small number of high-value lanes such as dependency management, coverage/test UX, FreeCAD helpers, richer diagnostics, and packaging aids.
- Produce exemplar plugins that feel like credible third-party offerings rather than only thin first-party wrappers.
- Keep safety, provenance, and compatibility bar high from the start.

## 12. AI-Assisted Workflows

Importance: Low  
Audit status: `not_started`

### Why this matters

AI will eventually matter to user expectations, but it is still not the bottleneck that most limits ChoreBoy Code Studio right now.

### Progress so far

- None as a dedicated product workflow. Semantic intelligence is not the same thing as AI assistance.

### What is still missing

- A credible offline or bring-your-own-model story.
- Task-scoped context gathering and reviewable apply flows.
- Clear product boundaries around privacy, latency, and trust.

### Recommended next steps

- Keep this explicitly deferred for now.
- Revisit only after dependency lifecycle, semantic trust, and test/debug discoverability are materially stronger.
- If revisited later, start with reviewable, task-scoped assistance that respects offline and constrained-runtime realities.

## Improvements by Difficulty

## Best High-Impact, Lower-Difficulty Wins

- Make dependency readiness, runtime explanation, and active run-target clarity more visible using the surfaces that already exist.
- Build a test explorer and rerun-failed flow on top of the current pytest service.
- Give semantic rename and related refactors a better review surface instead of relying on dialog-only preview.
- Synchronize `docs/TASKS.md`, this audit, and manual/help copy with shipped capabilities so roadmap decisions start from truth.
- Keep local history discoverable enough that non-Git users learn it before they need emergency recovery.

## Best Medium-Difficulty Strategic Wins

- Add a `cbcs/` dependency manifest and an `Add Dependency...` wizard.
- Add file/class/test discovery plus rerun-failed and debug-failed-test flows.
- Finish structured debug transport and inspector hardening.
- Make onboarding and runtime explanation more explicitly dependency-aware and run-target-aware.
- Continue shell decomposition and validation-gate discipline so future feature work lands cleanly.

## Best High-Difficulty, Transformative Bets

- Productize the full dependency lifecycle for a no-terminal environment.
- Push semantic trust to the point where larger Python projects feel safe in the editor.
- Turn debug and test into one obvious, high-confidence workflow loop.
- Grow a real workflow-plugin ecosystem instead of only a plugin platform.
- Revisit AI only after the product has a stronger local trust model.

## If We Only Do Five Things

If the goal is to move the product meaningfully toward "great Python editor for ChoreBoy users," the top five bets should now be:

1. Productize dependency management instead of assuming manual vendoring skill.
2. Deepen the existing semantic stack and make confidence visible in the UI.
3. Build a first-class test explorer with rerun and debug follow-up loops.
4. Turn runtime, run-target, and dependency explanation into a guided workflow rather than scattered surfaces.
5. Keep shell decomposition, backlog truth, and docs/test alignment disciplined as each new feature lands.

## What We Should Not Prioritize First

These may still matter eventually, but they are not the highest-leverage next-level bets now:

- another packaging substrate rewrite
- more plugin plumbing without better workflow providers
- cloud-first or opaque AI features
- broad multi-language parity beyond Python and core support files
- deep GitHub, remote-dev, or terminal-centric workflows
- any feature plan that starts from stale backlog labels instead of current shipped state

## Recommended Product Direction

The strongest version of Code Studio is no longer a "light editor with ambitions." It is a focused Python workbench that is:

- more trustworthy than lightweight Python editors
- more teachable than expert-heavy IDEs
- more deployable than general-purpose editors
- more aware of runtime constraints than any mainstream alternative

The winning roadmap from here is:

- borrow semantic trust and review habits from PyCharm and VS Code
- borrow clarity and onboarding discipline from Thonny
- borrow runtime inspection ideas from Spyder
- keep treating packaging, supportability, and constrained-runtime fitness as core differentiators
- shift new investment toward the workflows that users touch directly, especially dependency, semantics, testing, debugging, and explanation

Packaging and plugin architecture should now serve this roadmap, not lead it.

## Bottom Line

Code Studio is already much closer to a serious Python editor than the previous version of this document gave it credit for. The product now has real depth in packaging, safety, runtime explanation, formatting, debugging, testing, and plugin infrastructure.

The next tier will come from finishing the workflows that most affect day-to-day trust: dependency lifecycle, semantic confidence, test/debug discoverability, onboarding clarity, and maintainable truth across code and docs.

If those areas improve, Code Studio can become not just a good Python editor for ChoreBoy, but the right one.
