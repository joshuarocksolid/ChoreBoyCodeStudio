# Form Builder: end-to-end delivery plan

Owner: Joshua Aguilar. Orchestrator: Claude (main session). Started 2026-10-21.
Integration branch: `feat/form-builder` (from `main` at `54c3a14`). Merging to `main` is Joshua's call.
Revision 1 (2026-10-21): folds in the Opus soundness review (5 critical and 11 important findings).

This plan delivers the complete, polished CBCS visual form builder: a Qt Designer–parity editor inside ChoreBoy Code Studio that saves standard `.ui` files, generates `ui_<name>.py`, supports four levels of logic stored inside the `.ui`, and has a best-in-class, very fast UX. It runs only on PySide6 / FreeCAD 1.1.

## 1. Vision and fixed decisions

These were decided with Joshua between 2026-10-20 and 2026-10-21. They are not reopened without new evidence.

| Topic | Decision |
| --- | --- |
| File | Standard Qt 6 `.ui` is the only source of truth for layout and logic |
| Parity | Full Qt Designer parity: every item in `research/R3_designer_parity_checklist.md` (330 items) |
| Runtime | Our own in-process generator writes `ui_<name>.py` on every save. The user's `<name>_window.py` calls `self.ui.setupUi(self)` |
| Logic | Levels 1–4 per `LOGIC_DESIGN.md`: connections, call your code, no-code rules, data binding. Levels 3–4 are stored as dynamic properties and expanded to plain Python |
| Qt | PySide6 only. On PySide2 runtimes the feature is hidden, and `.ui` opens as XML text as it does today |
| Designer | Not embedded. Its source is a behavior reference only, never copied (MIT clean room) |
| AI | The product has no AI features |
| UX direction | Start screen → Workbench (Outline + live canvas + inspector with Properties / Behavior / Data). Plain-word sizing. The 25 ranked pains in `research/P_user_pain_points.md` are requirements |
| Connections | Managed by CBCS: named connections in project settings, a generated `cbcs_connections.py`, passwords never in the project |
| Try mode | SQLite runs on a scratch copy. PostgreSQL writes, then rolls back (Joshua's choice, which overrides the read-only default in `LOGIC_DESIGN.md` §0/§2.10). Rollback does not undo sequence advances, `NOTIFY` or other side effects that escape the transaction, so Try mode shows a banner, sets a statement timeout and lock timeout, warns about those effects, and keeps "Would run" (read-only) as a per-connection option |
| Locale | US English by default, with a per-project setting |
| Users | A real mix of programmers and non-programmers, so the point-and-click formula builder ships with logic level 3 |
| Speed | Open a 300-widget form ≤ 150 ms; each edit ≤ 16 ms; save ≤ 50 ms; ≤ 30 MB extra per open form (and ≤ 60 MB with 3 forms open). The primary metric is process CPU time, plus wall time on an idle machine (load < 2), with warmup, n = 15 and p95 reported. Re-checked on the ChoreBoy VM and on a CPU-capped profile matching ChoreBoy hardware |
| Generated code | `ui_<name>.py` imports from `PySide6` directly (the same shape as `uic`), never the FreeCAD `PySide` shim. FreeCAD `Gui::` widgets use a guarded `FreeCADGui` import with a Qt base-class fallback. Generated code is Python 3.9-parseable |
| Generation scope | Generation runs only for forms that belong to a CBCS project (under `forms/`, or adopted with "Adopt this form"). A `.ui` file outside a project (e.g. FreeCAD workbench files, or forms an app loads with `QUiLoader`) is edited without writing `ui_*.py` beside it |
| Translations | Every translation attribute is preserved and editable, and `retranslateUi` is generated. `.ts`/lupdate/lrelease tooling is out of scope (not in FreeCAD bundles). That's a won't-do recorded in the ledger |
| Cloud | Cursor Cloud is the primary place Grok lanes run. The repo carries a cloud environment with FreeCAD 1.0 (PySide2) and FreeCAD 1.1 (PySide6, Python 3.11, Qt 6 uic/rcc) |

## 2. Operating model

### Roles

- **Claude (orchestrator):** owns this plan, writes every brief, reviews every diff, reruns every verification, merges PRs into `feat/form-builder`, keeps the roadmap artifact current, and keeps workspaces and leases clean.
- **Grok (heavy lifting):** implements code (UI included), writes tests, builds harnesses and does research gathering. It runs in local worktrees, lab-host lanes or Cursor Cloud, through `~/.claude/skills/grok/scripts/grok-run`.
- **Opus (only where it matters):**
  - *Design specs:* writes the interaction and visual spec before UI-heavy work packages.
  - *UX sign-off gate:* every UI-facing PR is reviewed from screenshots, interaction-test traces and a launched build, and returns APPROVE, or CHANGES with a concrete list.
  - *Logic soundness gate:* every PR that carries logic (document model, commands, writer, generator, expression language, rules, data layer) gets a correctness review. That covers invariants, edge cases, determinism, SQL safety and failure modes.
  - *Rescue:* if Grok fails the same gate twice, Opus may implement the narrow hard part. A rescue PR is gated by a fresh Opus instance, not its author.

### Bounded fix loop

- A CHANGES verdict is a closed, numbered list. A re-review checks only those items, plus a regression check on the new diff. A new finding must cite a spec clause or a failing test.
- Round 3 goes to Opus rescue. Round 4 descopes the item to a follow-up WP, recorded in the ledger.

### Work package sizing

- One subsystem per WP, and about 1,500 net lines or fewer. Anything larger is split before the brief is written.
- Each WP owns a disjoint set of directories. Shared registries (command catalog, widget catalog, property-editor registry, tab-content providers) are changed only by their seam WP, or through registration files that each WP adds without editing shared ones.

### Work package lifecycle

```
brief (Claude) → [spec (Opus) if UI-heavy] → implement (Grok, sub-branch fb/<wp-id>)
  → self-checks (Grok) → review + rerun gates (Claude) → Opus gate(s) → fix loop
  → PR into feat/form-builder → merge (Claude) → roadmap update
```

- Sub-branches are `fb/<wp-id>-<slug>`, cut from the current `feat/form-builder`. Each lane gets its own registered worktree (`agent-workspace create-worktree`), or a lab or cloud lane.
- PRs target `feat/form-builder`. They use squash merges, with a body written using the `pr` skill.
- Two lanes never touch the same files at once. Section 5 shows which work packages can run in parallel.

### Quality gates (every PR)

1. Tests: pure-model tests (no Qt), offscreen Qt tests, and interaction tests that drive real mouse and keyboard events.
2. Oracles:
   - `QUiLoader` loads every saved file into the same widget tree.
   - Our `ui_*.py` and `uic -g python` build identical widget trees.
   - The corpus round-trip stays at 100%.
   - Determinism: save, then save again, gives identical bytes.
3. The speed budget script stays within budget, with the machine load recorded.
4. `npx pyright` is clean for the feature package, the CBCS fast shard has no regressions, and the dune checks pass (feature map, handles, file roles, install count).
5. Code style: Python 3.9 syntax in all feature code (repo rule; the feature itself loads only on PySide6) and PySide6 APIs only. Generated user code is also 3.9-compatible.
6. Opus gate where it applies (UX and/or logic), using the checklists in section 2a.
7. Milestone gates add: a run on the ChoreBoy VM (FreeCAD 1.1) and on the Linux lab host, a full screenshot tour, and an update to the parity ledger.
8. Python 3.9 is checked mechanically: `ast.parse(feature_version=(3, 9))` runs over the feature package and over all generated output, and pyright uses `pythonVersion 3.9` for the feature.
9. Determinism holds across machines: the double-save test runs on macOS and Linux, under the `C` and `de_DE` locales. Float and decimal formatting are pinned.
10. Interaction tests inject drag state through the controller seam, because `QDrag.exec` blocks offscreen. Each milestone also runs a real-drag smoke test on xcb on the lab host.
11. Accessibility is checked on every UI PR: accessible names, visible focus, and a keyboard-only path.
12. The user manual page for a feature is written in the same milestone as the feature. M9.6 only consolidates.

### Parity ledger

- `docs/form_builder/parity.json` is the source of truth for all 330 R3 items, the 25 pains and the logic features. `docs/form_builder/PARITY.md` is generated from it.
- Status and proving test are filled in automatically from `@pytest.mark.parity("R3-145")` and `@pytest.mark.pain("P-3")` markers by `tools/form_builder_parity.py`. Hand-written text is limited to won't-do reasons. So PRs never conflict on the ledger.
- "Done" requires a marked, passing test. "Won't-do" requires a reason that Opus has approved. The target is zero won't-do outside items that are meaningless for Python, such as C++-only export macros, and even those are preserved on round-trip.

### Autonomy and reporting

- Fully autonomous. Claude asks Joshua only when truly blocked, for example when every Cursor account is exhausted (exit 3) or a product decision is outside the fixed decisions above.
- The roadmap artifact shows milestone status, the ledger percentage, speed numbers and the latest screenshots. Each milestone's end is announced in the session with a short report.

### Hygiene

- Every worktree is registered with owner, purpose, base and cleanup condition, and retired once its PR merges.
- Every database or container created for tests gets a lease (`local-dev-data` skill). Test temp folders are deleted.
- Grok views are closed after review. Lab lanes are cleaned with `lab-clean`.
- `main` is merged into `feat/form-builder` at each milestone start, so the drift stays small.

## 2a. Opus gate checklists

### O-UX gate

**The PR must include:**
- Before and after screenshots in light, dark and high contrast, at 100% and 200% DPI.
- An interaction-test trace (event log plus final XML diff) for every new gesture.
- A keyboard-only script that completes the WP's tasks.
- A launched-build screenshot sequence from the lab Linux host.
- The `UX_SPEC.md` clause ids implemented.
- The parity and pain ids covered.
- Speed numbers for the edit path.

**The reviewer checks:**
1. Each spec clause matches; deviations are justified.
2. Nothing overlaps content: chips and badges never cover widgets, and focus is always visible.
3. No sticky modes; Esc always exits.
4. Every action can be undone in one step and is reflected in the outline and selection.
5. Error and empty states use plain-word copy.
6. Shortcuts don't collide with the shell table.
7. The canvas uses the runtime palette.
8. Accessible names are set and tab order is sane.
9. A non-programmer persona walkthrough finishes the task without docs.

Verdict: APPROVE, or CHANGES as a closed, numbered list.

### O-logic gate

**The PR must include:**
- The invariants for the touched modules.
- Property-based or fuzz output (seed, number of cases).
- Oracle results: `QUiLoader` tree equality, `uic` tree equality with the text diff, corpus percentage, and Designer-resave zero diff.
- Double-save byte identity on macOS and Linux.
- For logic and data: the conformance-suite delta, evaluator ≡ generated-code results, SQL listings with parameter binding, and SQLite plus PG 9.3 run logs.
- A failure-mode table (malformed input, newer format version, missing method, missing driver, lost connection).

**The reviewer checks:**
1. Invariants are enforced and tested, not just stated.
2. Every mutation goes through the command log; replay equals live, and undo-all equals the original.
3. Unknown nodes and unknown `cbcs*` keys are preserved.
4. No SQL value interpolation; identifiers are quoted; PostgreSQL 9.3 syntax only.
5. No user or custom-widget code runs in the editor process.
6. Generated code never swallows user exceptions and is 3.9-parseable.
7. Errors produce FB-coded diagnostics, and a logic error never blocks saving.
8. Sources of non-determinism are removed (dict order, floats, locale, time).
9. The code conforms to `CONTRACTS.md`.

Verdict: APPROVE, or CHANGES as a closed list.

## 3. Architecture (production)

```
app/features/form_builder/
  __init__.py              FeatureSpec: registers only when app.qt.qt_compat.IS_QT6
  engine/                  NO Qt imports
    ui4/                   typed ui4 document model, reader, deterministic writer,
                           unknown-node preservation, defaults table
    commands/              command log, every edit, undo/redo, grouping, replay
    query/                 selection, hit-test index contracts, layout math helpers
    codegen/               ui_<name>.py generator (uic-shaped), rcc → *_rc.py,
                           window-class template, logic expansion (L1–L4)
    logic/                 expression language (ast allowlist), typing, rule model,
                           validation, actions, data-binding model, SQL builders
    project/               form files, generated-file hashes, connections model
  qtside/                  PySide6 only
    realize/               model → live widgets, incremental patches
    canvas/                view, overlay painter, interaction controllers per layout kind
    inspector/             Properties / Behavior / Data tabs, property editors per type
    outline/, insert/, start/, dialogs/, theme/, icons/
    preview/               preview + Try mode in a separate AppRun process (IPC over stdio JSON)
  integration/             EditorTabFactory route, Problems, Run, packaging, settings,
                           shell theme tokens, handles
```

- **Shell seam (M2.0):** the editor surface plugs in through a generic tab-content provider registry in `platform.shell`. Markdown is moved onto that registry, which replaces today's hard-wired Markdown route. Feature specs get an `enabled()` predicate, and feature `install.py` modules must not import a Qt binding at module level. A dune rule enforces that, so loading `app.features` under PySide2 never imports PySide6.
- **Dirty state and text:** dirty state comes from the command log, and XML is serialized lazily (on save, local-history snapshot, the draft timer, or View XML), never on every edit. Edits made in View XML commit as one `ReplaceDocument` command when you switch back, and parse errors are shown without losing either version. Draft and local-history restore re-realize the form. Each tab has its own command log. Acceptance test AT-32 keeps passing.
- **Contracts (M1.0):** the engine and the Qt side talk only through `docs/form_builder/CONTRACTS.md` and typed stubs. That document defines node identity (stable ids), the document API, the change-event schema, the realize patch protocol, hit-test index invalidation, the selection model, diagnostic records (FB codes), the versioned preview IPC schema, and codegen entry points. The per-class defaults table is a committed JSON produced by a Qt-side dump script; a test checks it against the running Qt 6.8.x, and the engine itself stays Qt-free.
- **Preview process:** a child FreeCAD 1.1 `AppRun` started with `QProcess` (no shell; confirmed by the M0.7 probe). It reuses CBCS's existing child-supervision and framing code (`app/plugins/host_supervisor.py`, `rpc_protocol.py`, `app/runner/*`), with versioned messages, one warm pooled child shared by all open forms, tolerance for stdout noise, conftest reaping and crash-loop backoff. User and custom-widget code only ever runs there.
- **Generated files in the shell:** `ui_*.py`, `*_rc.py` and the logic expansion are excluded from Problems linting and auto-format, and open with a "generated, do not edit" banner.
- The spike branch `feat/form-builder-spike` is reference material. Its engine (model, xmlio, commands, generate, realize) is ported and hardened, not copied blindly. Its UI is redesigned from the Opus `DESIGN.md` plus the review findings.

## 4. Milestones and work packages

Legend: **G** = Grok implements; **O-spec** = Opus writes the spec; **O-UX** / **O-logic** = Opus sign-off gate; **VM** = ChoreBoy VM check.

### M0. Foundation (setup)

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M0.1 | Integration branch, worktree, and this plan; research docs committed under `docs/form_builder/` | Claude | Branch pushed and plan merged |
| M0.2 | Opus review of this plan for soundness, gaps and ordering | O-logic | Findings folded in |
| M0.3 | Test lanes: a `testing/run_form_builder_checks.py` that runs the feature tests on PySide6 (FreeCAD.app 1.1.3 python, and `~/opt/freecad` with `CBCS_QT_API=pyside6` for Python 3.9 syntax), plus oracles, speed and pyright | G | One command runs every gate and prints a summary |
| M0.4 | Corpus build-out: FreeCAD Mod `.ui` (67), Qt examples `.ui` from qtbase/qttools (BSD), PySide6 examples, the spike samples, hand-made edge forms (every container and property type, connections, resources, custom widgets) | G | ≥ 200 `.ui` files with a manifest and licence notes |
| M0.5 | Parity ledger (`parity.json` → generated `PARITY.md`) seeded from R3, the pains and the logic features, all mapped to work packages; markers-based status tool | G + Claude | Ledger exists and has been reviewed |
| M0.6 | Roadmap artifact (milestone tracker) | Claude | Published |
| M0.4b | Designer resave corpus: script Qt Designer (`Designer.app` from FreeCAD.app `lib/qt6/bin`) to open each corpus file, make a no-op edit and save. This gives us Designer's canonical serializer output, and shows how Designer handles `cbcs*` dynamic properties | G | Resaved set committed (licence permitting) with a manifest. Becomes the zero-diff oracle: a CBCS no-op save of a Designer-saved file has zero diff, or only diffs on an allowlist kept in the ledger |
| M0.7 | ChoreBoy FreeCAD 1.1.1 capability probe (`run-choreboy-probe`): spawning `AppRun` through `QProcess` with no shell, and its cold-start time; QtUiTools; uic/rcc present; `import FreeCADGui` in a child; pg8000/psycopg importable; Qt minor version; CPU, RAM, screen DPI | G + Claude | Results recorded in the plan as fixed facts. If no Postgres driver is importable, M8.1 vendors pure-Python pg8000 (+ scramp, asn1crypto) |
| M0.8 | Cloud environment: FreeCAD 1.1 + FreeCAD 1.0 runtimes, vendor bundles, Xvfb, env vars, and AGENTS.md cloud docs, all proven inside a Cursor Cloud VM | G (cloud) | PR merged. A fresh cloud VM runs every lane |
| M0.9 | UX spec v1 (moved forward from M3.0): written from the spike `DESIGN.md`, the spike screenshots, Joshua's "rough edges" feedback, the pains and delighters, and an Opus heuristic run of the spike build. Covers the shell integration (M2) and the canvas (M3) first; later sections are added before M4–M5 | O-spec | `docs/form_builder/UX_SPEC.md` approved. No O-UX gate runs without an approved spec section |

### M1. Engine (production)

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M1.0 | Architecture contracts (`CONTRACTS.md` + typed stub modules): stable node ids, document API, change events, realize patch protocol, hit-test index invalidation, selection model, diagnostics (FB codes), versioned preview IPC schema, codegen entry points, the defaults-table JSON + Qt dump script | O-spec, O-logic | Approved. Every M1–M3 WP implements against it |
| M1.1a | ui4 model, reader and writer: core schema (widgets, layouts, items, spacers, properties), unknown-node preservation, deterministic writer | G, O-logic | Corpus round-trip for core files. Double-save byte-identical |
| M1.1b | ui4 property values: every value type (font, palette, brush/gradient, icon sets, size policy, string list, translatable strings with comments, date/time, URL, locale…) | G, O-logic | Every value type round-trips |
| M1.1c | ui4 main window, actions, resources, custom widgets, connections, slots/signals, button groups, tab stops, form-level settings (R3 items 223–330 complete) | G, O-logic | Corpus round-trip 100%, plus the Designer-resave zero-diff oracle. Fuzzed and malformed `.ui` never crashes and gives a clear error |
| M1.1d | Writer ↔ Designer alignment: implement CONTRACTS Appendix E and drive `test_designer_resave_diff.py` to zero outside the allowlist, then make it a hard oracle gate | G, O-logic | Zero non-allowlisted bytes against all 209 Designer resaves; allowlist reviewed by Opus |
| M1.2 | Command log: the full command catalog (insert, delete, move, reparent, wrap, unwrap, morph, break layout, set property, z-order, container pages, actions, connections, tab order, buddies, promotion, resources), grouping, merge of rapid property edits, undo/redo, replay determinism. Z-order is rebuilt from the real child list (pain 24) | G, O-logic | Property-based tests (random command sequences: replay equals live, undo-all equals original) |
| M1.3 | Generator: `uic`-shaped Python for everything M1.1 reads, including resources (an rcc-equivalent `*_rc.py`), promoted classes, i18n/`retranslateUi`, connections, buddies, tab order, button groups, actions, main-window parts, and the uic-flag equivalents (R3 322–330). Guarded `FreeCADGui` import | G, O-logic | Every corpus file: our module and `uic`'s build identical trees, with the text diff reported. The 6 known spike failures fixed. Generated modules run under FreeCAD 1.1 `AppRun` on the VM. Generation speed stays in budget on big forms (pain 23) |
| M1.4 | Project layer: forms belong to a project (`forms/`, or "Adopt this form"), generated-file hashes (detect hand edits to `ui_*.py`), window-class creation, naming rules, rename and move of a form (window class and references updated), completion of widget names (pain 15) | G | Tests cover create-once, hand-edit detection, adopt, rename/move, and Jedi completing `self.ui.okButton`, with the old name gone after a rename |
| M1.5 | Speed harness: big forms of 300, 600 and 1000 widgets; CPU and idle-wall metrics, warmup, n = 15, p95; per-form and 3-form memory; runs on the Mac, on the VM and on a CPU-capped profile matching the M0.7 hardware | G | Budgets asserted, with load recorded |

### M2. CBCS integration shell

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M2.0 | Shell seam: a generic tab-content provider registry in `platform.shell`, Markdown moved onto it, `FeatureSpec.enabled()`, a dune rule forbidding module-level Qt imports in feature `install.py`, and a test that importing `app.features` under PySide2 never imports PySide6. Also proposed to `main` as its own small PR (Joshua merges), so the branch doesn't carry a shell fork | G, O-logic | Markdown is unchanged for users. Fast shard green on both bindings. Dune green |
| M2.1 | Feature package and registration (PySide6 only, through `enabled()`), dune owner, handles, file roles | G | Dune checks green. Under PySide2, `.ui` opens as text with a hint |
| M2.2 | Editor tab: `.ui` opens the visual editor with a View XML toggle (one `ReplaceDocument` command on switching back). Dirty state from the command log; lazy XML; per-tab command log; save, local history and draft restore that re-realize the form; close prompts; autosave and crash recovery; external file change with a three-way choice when the form is dirty. Covers R3 13–16 (new/open/save/close) | G, O-UX + O-logic | AT-32 still passes. New acceptance tests added |
| M2.3 | Problems integration (FB codes), settings keys, shell theme tokens (light, dark, high contrast), keyboard shortcuts that don't collide with F5/F6/Ctrl+R, generated files excluded from linting/format and opened with a banner | G, O-UX | Shortcut table test. Theme switch keeps the canvas in the runtime palette |
| M2.4 | Run and packaging: F5 on a form runs its project entry. The packager includes `ui_*.py`, `*_rc.py` and generated connections, and flags stale generated files. New-project template "Qt app with a form". Migration guide plus an "Adopt this form" flow for apps that load `.ui` with `QUiLoader`/`loadUi` (example_projects, SmokeQtApp). Importing code-built UI is a won't-do | G | Packaging fixture test. The template project runs on the VM |
| M2.5 | Preview process (pain 11), built on CBCS's existing supervisor and framing code: versioned messages, one warm pooled child shared by all open forms, crash-loop backoff. Custom widgets load there. A crash becomes a Problems row | G, O-logic | Kill/raise fixtures leave the editor alive. Cold and warm start timed. **VM** |

### M3. Canvas and layout editing excellence

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M3.0 | UX spec: canvas sections confirmed (written in M0.9) | O-spec | Canvas sections of `UX_SPEC.md` approved |
| M3.1a | Realizer: `FormSession`, the selection model, model → live widgets with O(changed) patches for every container kind and main-window chrome, runtime palette isolation, and the `app.qt` immediate-delete helper (CONTRACTS §3.7, §5, §6). Added 2026-10-22: no earlier row owned the realizer | G, O-logic | Patch equals rebuild across random commands with undo/redo; zero fallbacks for the standard set; no user code imported; build ≤ 90 ms and patch ≤ 8 ms at 300w |
| M3.1 | Canvas core: view, zoom, overlay painter, hit-test index, selection model (single, multi, rubber band, parent, siblings), hover, chips that never cover content (fixes the name-chip overlap), move/resize and grid snap, Tab selects next object, in-place text edit, broken-layout marker (R3 17–22, 30–31, 34) | G, O-UX | Interaction tests. Speed holds |
| M3.1b | Inspector framework: the Properties/Behavior/Data tab shell, the property-editor registry, changed markers, reset and multi-select plumbing, and the object inspector (R3 28–29) | G, O-UX | Registry API used by M3.6 and M4.3 without edits to shared files |
| M3.2 | Drop and move engine for every layout kind: box, grid (cells, spans, insert row/column), form (label/field), splitter, stacked/tab pages, and bare containers. Auto-layout on first drop, next drop fills the next cell | G, O-UX | Per-kind interaction tests. Pains 1, 4 and 21 |
| M3.3 | Layout operations: wrap, unwrap, morph layout, morph widget, break layout (confirmed, keeps sizes), adjust size, simplify grid, spacers, gaps, margins, stretch, splitter handles on the canvas (pain 19), size constraints | G, O-UX | R3 35–56 ledger rows done. Pains 5, 14 and 19 |
| M3.4 | Clipboard and duplication: copy, cut, paste into a layout at an index (pain 3), cross-form paste, Alt-drag clone, duplicate, scratch pad | G, O-UX | R3 23–27, 32–33 done |
| M3.5 | Outline: keyboard editing (Tab nest, Shift+Tab, Alt+arrows, `/` insert, F2 rename keeping focus), drag reparent, page reorder, references shown before delete | G, O-UX | Pains 20 and 25. A keyboard-only test script passes |
| M3.6 | Sizing panel: Hug/Fill/Fixed, share, min/max, "why is it this size?", font-size and DPI preview (pain 12), two-widths view | G, O-UX | Pain 2 tests. The "why" text is verified against the real widget |
| M3.7 | Opus heuristic and keyboard-only review of M3 as a whole | O-UX | APPROVE |

### M4. Widgets, containers and properties

Spec: `UX_SPEC.md` §13.1 (version 2, M4.0). Refined 2026-10-28: the property editors split into four lanes, a small seam lane goes first for the inspector popover and the context menu, and the review closes the milestone. R3 113–119 move to M5.1 and R3 123 to M5.4 (their editing surfaces are built there; UX §13.1.7).

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M4.0 | UX spec for M4 (§13.1 v2), lane split and first-wave briefs | O-spec | Spec branch merged |
| M4.0s | Seams: the row popover shell and popover sessions, `commit(value, session)` and session-scoped undo merging, the wheel rule, the Pages group slot in the inspector, the context-menu contributor registry (`integration/menu_ext/`) | G, O-logic | UX-TOK-005, PED-002 … 005, CONT-020 pass their tests; later lanes register without editing shared files |
| M4.1 | Widget catalog and Insert: one catalog (friendly names everywhere), categories, glyphs, search with synonyms and ranking, Recently used, icon and list views, quick insert on the same search, window kinds and the Wizard New form card, FreeCAD and Your widgets categories | G, O-UX | R3 57–109, 111, 112, 120, 133 done. K9 passes |
| M4.2 | Containers and pages: page commands (insert before and after, delete, move, start page) from canvas, outline and menu; shown page vs start page; scroll area, MDI, dock sides, wizard; group box and frame rows; stand-ins for OpenGL and Qt Quick | G, O-UX + O-logic | R3 110, 121, 122, 124–132 done. K10 passes |
| M4.3a | Property editors, scalars: bool, numbers, enum, flags, char, size/point/rect, size policy, key sequence, date and time, locale | G, O-UX + O-logic | R3 151–154, 158, 166–169, 171 done. Pain 18. K11 passes |
| M4.3b | Property editors: font, colour, brush and gradient, palette, cursor | G, O-UX + O-logic | R3 159–163 done. K13 passes |
| M4.3c | Property editors: pictures and icon sets (resource-aware), picture brushes | G, O-UX | R3 164–165 done. K15 passes |
| M4.3d | Text, translations and the Properties tab: text and multi-line popover, Translation disclosure, rich text, string lists and the shared list editor, C strings, URLs, custom (dynamic) properties, attributes in All properties, sort A–Z | G, O-UX + O-logic | R3 148–150, 155–157, 170, 172 done. K12 passes |
| M4.4 | Item editors (combo, list, tree, table; columns and rows) and the inspector Pages group | G, O-UX + O-logic | R3 173 done. K14 passes |
| M4.5 | Review of M4 as a whole: heuristic, keyboard-only (K9–K15 together) and the persona walkthrough (UX §12.6); speed rows for UX-M4-007 in the harness; fix lanes as needed | O-UX + G | APPROVE. Ledger: every M4 row done |

#### M4 lanes

Paths are relative to `app/features/form_builder/` unless they start with `tests/`, `tools/` or `docs/`. A lane owns the files it creates and the files listed. Two lanes never edit the same file; when a lane needs a change in a file it does not own, it writes a strict `xfail` repro in its own test file and reports it. `engine/codegen/**` is M4.2's in wave 1; any other lane that finds a generator bug reports it with a repro. `tests/form_builder/perf/harness.py` is M4.5's.

| Lane | Owns | Must not touch | Closes |
| --- | --- | --- | --- |
| M4.0s | `qtside/inspector/api.py`, `qtside/inspector/_properties.py` (commit and session plumbing, the Pages group slot only), `qtside/inspector/_services.py`, new `qtside/inspector/editors/_popover.py`, `qtside/theme/chrome.py` (the `fb.*` tokens of UX-TOK-005), new `integration/menu_ext/`, `integration/context_menu.py`, `integration/surface.py` (the context-menu hook only) | every other inspector, canvas and insert file | no R3 rows (enables PED, CONT-019, CONT-020) |
| M4.1 | new `qtside/insert/catalog/` (Qt-free data), `qtside/insert/*.py` (pane, search, recent, tiles), `qtside/icons/**`, `qtside/canvas/core/palette.py`, the friendly-name tables in `qtside/inspector/words.py`, `qtside/canvas/core/words.py` and `qtside/outline/friendly.py` (delegate to the catalog), `integration/workbench.py` (the `InsertPane` move and the quick-insert list only), `integration/new_form.py`, `qtside/start/**`, new `integration/insert_memory.py`, `dune.yaml` (a file role for the Qt-free catalog) | `qtside/canvas/**` except `core/palette.py` and `core/words.py`, `qtside/realize/**`, `engine/**` | R3 57–109, 111, 112, 120, 133 (57 rows) |
| M4.2 | `engine/commands/catalog_ext/drop.py`, new `engine/commands/catalog_ext/pages.py`, `engine/commands/planning.py` (page helpers), new `engine/query/pages.py`, `engine/query/drop_target.py`, `engine/shell_commands.py`, `engine/codegen/**` (container fixes), `qtside/canvas/**` except `core/palette.py` and `core/words.py`, `qtside/realize/**`, `qtside/theme/overlay.py` (the `ov.*` tokens of UX-TOK-005), `integration/canvas.py`, new `integration/menu_ext/pages.py` (after M4.0s), new `qtside/inspector/editors/rows_containers.py` | `integration/workbench.py`, `qtside/insert/**`, any other inspector file | R3 110, 121, 122, 124–132 (12 rows) |
| M4.3a | `qtside/inspector/editors/scalars.py`, `choices.py`, `geometry.py`, new `editors/numbers.py`, `editors/flags.py`, `editors/dates.py`, `editors/locale.py`, `editors/keys.py`, `editors/_enum_words.py` (names are the lane's choice; new modules only register overrides) | `api.py`, `_properties.py`, `model.py`, `visual.py`, `raw.py`, every M4.3d module | R3 151–154, 158, 166–169, 171 (10 rows), pain 18 |
| M4.3d | `qtside/inspector/_properties.py`, `model.py`, `api.py` (after M4.0s), `pane.py`, `_services.py` (after M4.0s), new `editors/text.py`, `editors/_translation.py`, `editors/_list_editor.py`, `editors/stringlist.py`, `editors/url.py`, `editors/custom_props.py` | the M4.3a modules, `visual.py`, `raw.py`'s registrations | R3 148–150, 155–157, 170, 172 (8 rows) |
| M4.3b | `qtside/inspector/editors/visual.py`, new `editors/_color_picker.py`, `editors/brush.py`, `editors/palette.py`, `editors/cursor.py`, new `integration/editor_memory.py` (recent colours) | `choices.py` (its cursor editor stays as the baseline), `_properties.py`, `model.py` | R3 159–163 (5 rows) |
| M4.3c | new `qtside/inspector/editors/images.py`, `editors/_picture_picker.py`, `qtside/realize/props.py` (pictures from `.qrc` on disk), a read-only `.qrc` reader under `engine/project/` | `engine/codegen/resources.py` (report gaps), `_properties.py` | R3 164, 165 (2 rows) |
| M4.4 | new `qtside/items/` (item editor), new `qtside/inspector/editors/pages_list.py` (Pages group body), `engine/commands/catalog.py` (`SetItems` merge key only) and `planning.set_items`, `qtside/canvas/core/text.py` and the canvas Enter and double-click routing for item widgets, `qtside/realize/api.py` (`_item_texts` for trees), new `integration/menu_ext/items.py` | `_list_editor.py` (reuse; changes go back to M4.3d's owner through the orchestrator) | R3 173 (1 row) |
| M4.5 | `tests/form_builder/perf/harness.py` (M4 rows), `tests/form_builder/qtside/test_m4_keyboard_scripts.py` (K9–K15 run together), review repros | product files only through fix lanes | ledger audit: 95 M4 rows |

**Order and dependencies.**

1. Wave 1 starts at once with three lanes: **M4.0s**, **M4.1**, **M4.2**. M4.2 builds its engine, canvas and outline parts first and adds `integration/menu_ext/pages.py` after M4.0s merges.
2. When M4.0s merges: **M4.3a** and **M4.3d** start (both need the popover and sessions).
3. Wave 2, as lanes free up: **M4.3b** (after M4.0s), **M4.3c** (after M4.0s and M4.2, which owns `qtside/realize/**` in wave 1), **M4.4** (after M4.2 and M4.3d: it needs the canvas and the list editor).
4. **M4.5** after every lane has merged.

Merge order inside a wave follows readiness; a lane rebases on `feat/form-builder` before its gate. Expected size: M4.0s ~500 net lines; M4.1, M4.2, M4.3d ~1,500 each; M4.3a, M4.3b ~1,200; M4.3c, M4.4 ~1,000.

**Review gates.** Each lane's PR lists the UX clause ids it implements and runs its K script. O-UX gates every lane (screenshots per UX §12.2 "M4 states", light, dark and both high contrast themes, 100% and 200%, the inspector states also at 236 px). O-logic gates M4.0s (session undo, merge tokens, registry order), M4.2 (page commands, start page, dock area attributes, generated code for wizards), M4.3a (pain 18 and value round-trips), M4.3b (palette and gradient serialization and determinism), M4.3d (translation attributes, dynamic properties in generated code, rich-text determinism) and M4.4 (`SetItems` merge and replay). One Opus gate runs at a time; M4.0s's gate goes first because two lanes wait on it.

### M5. Main windows, resources, styling, custom widgets, templates

Spec: `UX_SPEC.md` §13.2 (version 3, M5.0), with the M5 states, K16–K23, checks and persona in §12. Refined 2026-10-29: a seam lane goes first (form-menu contributors, workbench slots, form-inspector groups, canvas overlay layers, project settings), R3 222 moves from M5.6 to M5.5b (UX §13.2.1 D20), button groups are built in M5.1 although CONTRACTS lists `SetButtonGroup` under M5.6 (D25), and the P-9 test is amended (D3). The review closes the milestone.

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M5.0 | UX spec for M5 (§13.2 v3), lane split and first-wave briefs | O-spec | Spec branch merged |
| M5.0s | Seams: form-menu contributor registry (`integration/form_menu_ext/`), three workbench slots (a left-pane section, a drawer under the canvas, a split beside it) with Alt+5 and the short-height tabs, a form-inspector group slot, a canvas overlay-layer registry (`qtside/canvas/layers/`), lane key registration (`integration/keys_ext/`), a Problems fix-button registry (`integration/problem_fixes/`), discovery of `engine/diagnostic_codes/` modules, project settings access for `form_builder.*` keys, and the project file index (`.qrc` and `.py` files, mtime cached) | G, O-logic | UX-M5-010 passes; a dummy contributor of each kind registers from a new file without editing a shared one; KEY-001 covers `keys_ext` keys |
| M5.1 | Main window: blank template parts, add and remove parts, "Type here" menus, submenus and toolbars with the keyboard grammar and the reuse list, drags, the Actions section, action, menu, toolbar and status bar inspectors, central area rules, refusals, widget actions, action and button groups (pain 17) | G, O-UX + O-logic | R3 113–119 and 134–144 done (18 rows). P-17. K16 passes |
| M5.2 | Resources: the project-wide picture picker, Add picture with automatic `forms/resources.qrc`, file drops, the resource editor tab, raw-path problems and fix, the form's pictures files, `*_rc.py` on `.qrc` save (pain 9) | G, O-UX + O-logic | R3 174–175 done. P-9 (amended test). K17 passes |
| M5.3 | Style: the style sheet drawer with live apply, the two-layer check, selector matches on the canvas, Insert helpers, curated Text colour and Background rows, the Appearance order, the form's Look group (pain 8) | G, O-UX + O-logic | R3 176 done. P-8. K18 passes |
| M5.4 | Your own classes: the "Use my own class" popover with the `ast` check, storage and demote, the project registry and Insert's Your widgets, canvas drawing and stand-ins, real class in Preview with trial construction, the security note (pain 7) | G, O-UX + O-logic | R3 123 and 194–198 done (6 rows). P-7. K19 passes |
| M5.5a | Preview options (style, screens), Save image, Print, View Python code | G, O-UX | R3 177–181 done (5 rows). K20 passes |
| M5.5b | Form settings in the form inspector (Code, Translation, Free placement), legacy defaults, the grid step on the canvas | G, O-UX + O-logic | R3 185–193 and 222 done (10 rows). K21 passes |
| M5.5c | Save as template, template storage and use, Start v2 with Your templates first, the new built-in, Settings > Form designer | G, O-UX + O-logic | R3 182–184 done. K22 passes |
| M5.6 | One editing mode: tab-order and buddies overlays finished (UX-OVL-001 … 008) with keyboard paths, the tab order list, the buddy drop-down, Form designer keys page, the Designer key mapping, F1 help card (pain 13) | G, O-UX + O-logic | R3 1, 8–12, 199–221 done (29 rows). P-13, P-20. K23 passes |
| M5.R | Review of M5 as a whole: heuristic, keyboard-only (K16–K23 together) and the persona walkthrough (UX §12.6); speed rows for UX-M5-009 in the harness; fix lanes as needed | O-UX + G | APPROVE. Ledger: every M5 row done (74 R3 rows, P-7, P-8, P-9, P-13, P-17, P-20) |

#### M5 lanes

Paths are relative to `app/features/form_builder/` unless they start with `tests/`, `tools/` or `docs/`. A lane owns the files it creates and the files listed. Two lanes never edit the same file at the same time; when a lane needs a change in a file it does not own, it writes a strict `xfail` repro in its own test file and reports it. New context-menu rows go in `integration/menu_ext/`, new Form menu items in `integration/form_menu_ext/`, new keys in `integration/keys_ext/`, Problems fix buttons in `integration/problem_fixes/`, new canvas layers in `qtside/canvas/layers/`, new FB codes in a new module under `engine/diagnostic_codes/`, new commands in `engine/commands/catalog_ext/`, new inspector rows in new `qtside/inspector/editors/rows_*.py` modules: each lane adds its own file there and edits no shared one. Each lane's tests are new files `tests/form_builder/**/test_m5_<lane>_*.py`. `tests/form_builder/perf/harness.py` is M5.R's.

| Lane | Owns | Must not touch | Closes |
| --- | --- | --- | --- |
| M5.0s | `integration/form_menu.py` (the contributor hook only), new `integration/form_menu_ext/__init__.py`, `integration/workbench.py` (the three slots, Alt+5 and the short-height tabs only), `qtside/inspector/_properties.py` (the form-group slot only), `qtside/canvas/paint.py` and `qtside/canvas/core/overlay.py` (the layer hook only), new `qtside/canvas/layers/__init__.py`, new `integration/keys_ext/__init__.py`, new `integration/problem_fixes/__init__.py`, `engine/diagnostic_codes/__init__.py` (module discovery), `integration/problems_bridge.py` (a fix-button registry keyed by FB code), new `integration/project_settings.py`, new `engine/project/project_files.py` | every other file | no R3 rows (enables every M5 lane) |
| M5.1 | new `engine/commands/catalog_ext/actions.py` and `main_window.py`, new `engine/query/actions.py`, `engine/codegen/emit.py` (menus, toolbars, groups), `engine/project/templates.py` (blank Main window), `qtside/canvas/**` except `paint.py`, `core/overlay.py`, `core/snap.py` and other lanes' `layers/*.py`, `qtside/realize/**`, new `qtside/actions/**`, `qtside/insert/catalog/windows.py` and `qtside/insert/catalog/search.py` (main-window part rows), `integration/surface.py` (Enter routing into menu editing, refusal sentences), new `qtside/inspector/editors/rows_actions.py`, new `qtside/inspector/editors/form_button_groups.py` (through the form-group slot), new `integration/menu_ext/main_window.py`, `integration/form_menu_ext/main_window.py`, `integration/keys_ext/main_window.py`, new `engine/diagnostic_codes/fb03x_main.py` (FB036, FB037), `qtside/theme/overlay.py` (`ov.type_here`, `ov.menu_drop`) | `integration/workbench.py`, `engine/codegen/resources.py`, `qtside/preview/**`, any other inspector file | R3 113–119, 134–144 (18 rows), P-17 |
| M5.2 | new `engine/project/qrc_write.py`, `engine/project/pictures.py`, `engine/project/save.py` (`*_rc.py` on `.qrc` save), `engine/project/packaging.py` (raw paths), `engine/codegen/resources.py`, `qtside/inspector/editors/_picture_picker.py` and `editors/images.py`, new `qtside/resources/**` (resource editor tab), new `integration/qrc_provider.py`, `integration/provider.py` (one registration line), new `integration/problem_fixes/resources.py` (fix buttons for FB031, FB032), new `qtside/inspector/editors/form_files.py` (Files group through the slot), new `engine/diagnostic_codes/fb03x_resources.py` | `engine/codegen/emit.py`, `qtside/canvas/**` (file drops on the canvas go through a drop-handler hook M5.1 exposes; until then they are a strict xfail), `qtside/realize/**` | R3 174, 175 (2 rows), P-9 |
| M5.3 | new `engine/style/**` (Qt-free tokenizer, checker, selector matcher), new `qtside/style/**` (drawer, Qt probe), new `qtside/canvas/layers/style_matches.py`, new `qtside/inspector/editors/rows_style.py` (Style sheet, Text colour, Background, Appearance order, the form's Look group), `qtside/inspector/editors/font.py` (the colour swatch in the summary), new `integration/menu_ext/style.py`, `integration/form_menu_ext/style.py`, new `integration/problem_fixes/style.py`, new `engine/diagnostic_codes/fb03x_style.py` (FB033, FB034), `qtside/theme/overlay.py` (`ov.style_match`, after M5.1 merges, else report) | `qtside/realize/**` (sheets already apply as authored; gaps are reported to M5.1), `qtside/canvas/**` except its layer, `_properties.py` | R3 176 (1 row), P-8 |
| M5.4 | new `engine/commands/catalog_ext/promote.py`, new `engine/project/custom_widgets.py` (registry, `ast` resolver), `engine/codegen/emit.py` (own-class imports, after M5.1), `qtside/realize/**` and `qtside/realize/stand_in.py` (after M5.1), `qtside/insert/**` (Your widgets from the registry, after M5.1), `qtside/preview/child/modules.py` (trial construction), new `qtside/dialogs/promote.py`, new `integration/menu_ext/promote.py`, new `integration/preview_notice.py`, new `integration/problem_fixes/custom.py`, new `engine/diagnostic_codes/fb03x_custom.py` (FB035) | `qtside/preview/pool.py`, `child/session.py`, `child/main.py`, `engine/ipc/**` (M5.5a's) | R3 123, 194–198 (6 rows), P-7 |
| M5.5a | `qtside/preview/pool.py`, `qtside/preview/launch.py`, `qtside/preview/child/session.py`, `child/main.py`, `child/materialize.py`, `engine/ipc/protocol.py` (optional `set_appearance` fields only, no version bump), new `qtside/code_view/**`, new `integration/image_export.py`, `integration/workbench.py` (the Aa menu, after M5.6 merges), `integration/form_menu_ext/preview.py`, `integration/keys_ext/preview.py`, `integration/memory.py` (screen profiles per user) | `child/modules.py` (M5.4's), `engine/codegen/**` | R3 177–181 (5 rows) |
| M5.5b | new `qtside/inspector/editors/form_settings.py` (Code, Translation, Free placement groups through the slot), new `engine/commands/catalog_ext/form_fields.py` (`SetFormField`, the grid in `designerdata`), `qtside/canvas/core/snap.py` (the grid step), `integration/form_menu_ext/form_settings.py` | `engine/ui4/**` (writer gaps are reported with a repro), every other canvas file | R3 185–193, 222 (10 rows) |
| M5.5c | `qtside/start/**`, `engine/project/templates.py` (after M5.1), new `engine/project/user_templates.py`, `integration/new_form.py`, new `qtside/dialogs/save_template.py`, `integration/form_menu_ext/templates.py`, new `integration/settings_page.py` (Settings > Form designer, through the shell's settings-page registration; a missing seam is reported) | `engine/project/qrc_write.py` (use it, don't change it), `qtside/insert/**` | R3 182–184 (3 rows) |
| M5.6 | `qtside/canvas/**` (after M5.1) except `core/snap.py` and other lanes' `layers/*.py`, new `qtside/canvas/layers/tab_order.py` and `buddies.py`, `integration/surface.py` (F7, F8, F1, banners; after M5.1), `integration/workbench.py` (overlay toggles; before M5.5a), new `engine/commands/catalog_ext/tab_order.py` (`SetTabStops`, `SetBuddy`), new `qtside/inspector/editors/tab_order_list.py` and `editors/buddy.py`, new `qtside/keys_page/**`, new `integration/widget_help.py`, `integration/keys_ext/modes.py`, `integration/form_menu_ext/modes.py`, `engine/shell_commands.py` | `qtside/realize/**`, `qtside/insert/**` | R3 1, 8–12, 199–221 (29 rows), P-13, P-20 |
| M5.R | `tests/form_builder/perf/harness.py` (M5 rows), `tests/form_builder/qtside/test_m5_keyboard_scripts.py` (K16–K23 together), review repros | product files only through fix lanes | ledger audit: 74 M5 rows |

**Order and dependencies.**

1. Wave 0: **M5.0s** alone in product files. In parallel, the Qt-free engine parts that only create new files may start: M5.2's `qrc_write.py`, M5.3's `engine/style/**`, M5.4's `custom_widgets.py`. They merge with their lane, not before.
2. Wave 1, when M5.0s merges: **M5.1**, **M5.2**, **M5.3** (three lanes). M5.1 owns `qtside/canvas/**`, `qtside/realize/**`, `qtside/insert/**`, `integration/surface.py`, `engine/codegen/emit.py` and `engine/project/templates.py` in this wave; M5.3 draws only through its own layer file.
3. Wave 2, as lanes free up: **M5.4** (after M5.1: realize, Insert, emit), **M5.6** (after M5.1: canvas, surface), **M5.5b** (after M5.0s; it can join wave 1 if a lane slot is free, since it touches only its own files and `core/snap.py`).
4. Wave 3: **M5.5a** (after M5.4 and M5.6: it takes `integration/workbench.py` last and shares the preview child with M5.4's file), **M5.5c** (after M5.1 and M5.2: templates and picture copying).
5. **M5.R** after every lane has merged.

Merge order inside a wave follows readiness; a lane rebases on `feat/form-builder` before its gate. Expected size: M5.0s ~600 net lines; M5.1 ~1,500 (split M5.1a canvas and menus / M5.1b Actions section and groups if the brief passes 1,500); M5.2, M5.3, M5.4, M5.6 ~1,200–1,500 each; M5.5a ~1,000; M5.5b ~700; M5.5c ~1,000.

**Review gates.** Each lane's PR lists the UX clause ids it implements, runs its K script and reports its UX-M5-009 rows. O-UX gates every lane (screenshots per UX §12.2 "M5 states", light, dark and both high contrast themes, 100% and 200%, inspector states also at 236 px). O-logic gates M5.0s (registry order and discovery, atomic project-settings writes), M5.1 (action reference removal, menu and toolbar order in generated code against uic, group membership without reordering), M5.2 (`.qrc` determinism, copy rules, `*_rc.py` against rcc, nothing outside the project is read), M5.3 (the check agrees with Qt's parser, selector matching against Qt's own styling), M5.4 (CONTRACTS §10.4 import rule, trial construction, header round-trip), M5.5b (form-field round-trips), M5.5c (template copy, rename and picture merge) and M5.6 (tab-stop splicing, buddy writes). One Opus gate runs at a time; M5.0s's goes first because every lane waits on it. Each milestone gate also runs the §16.3 facts on the ChoreBoy VM.

**Done when, per lane** (in addition to the table's rows and the PLAN §2 gates): every clause the lane names passes its evidence codes; its K script passes with no mouse event; its ledger rows are done with marked, passing tests; its UX-M5-009 rows are inside budget with machine load recorded; every on-screen sentence it added is in UX §13.2.10; and its manual page is written (PLAN §2 gate 12).

### M6. Logic levels 1–2

Spec: `UX_SPEC.md` §13.3 (version 4, M6.0), with the M6 states, K24–K26, checks and personas in §12; contracts in `CONTRACTS.md` §15 (logic storage) and §16 (handlers and the window file); the changes to `LOGIC_DESIGN.md` are listed at its end. Refined 2026-10-29: a seam lane goes first; M6.1 splits into an engine lane (a), the Events list (b) and the canvas (c); M6.2 splits into a Qt-free code lane (a) and its UI (b); a review closes the milestone. Rule intents, conditions, form events, Shift+F12 and method rename wait for M7 (UX §13.3.9).

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M6.0 | UX spec for M6 (§13.3 v4), CONTRACTS §15–16, lane split and first-wave briefs | O-spec | Spec branch merged |
| M6.0s | Seams: Behavior tab section registry, canvas double-click contributors, overlay kind registry with a link gesture, the code bridge, the handler service protocol, `WindowFacts` stubs, the expanders and intents packages, `Method.params`, Problems routing to code lines | G, O-logic | A dummy contributor of each kind registers from a new file without editing a shared one; the M3 Behavior list still works through the new host |
| M6.0b | Logic storage layer: the codec and canonical JSON, schema v1 with the `slot` and `call` verbs, the version marker, unknown keys kept, FB401–FB403 and FB405 declared, read-only logic (FB402), rename, paste and delete participants including formula tokens, `SetLogic` on the codec (`LOGIC_DESIGN.md` §2.13, §6; CONTRACTS §15) | G, O-logic | Round-trip, fuzz, rename and paste tests; undo covers logic edits |
| M6.1a | Events engine: `SetEventSteps` and `MergeEventStorage` with the storage choice and minimal diff, signal compatibility, the events catalog (common and default events, words), the M6 intents, the step-list expander (CONTRACTS §15.6) | G, O-logic | Storage invariant and expander tests pass; runtime calls match list order |
| M6.1b | Events list UI: the Behavior Events section, From other widgets, All events on this form, the event and step pickers, Alt+B and Ctrl+Shift+E, FB404 Merge | G, O-UX + O-logic | R3 3–5 done. Pain 16. K24 passes |
| M6.1c | Canvas: logic badges, arrows, Show all connections, the Connections overlay (F4) with drag and keyboard links | G, O-UX | R3 2 done. K25 passes |
| M6.2a | Code engine: the safe window-file reader, the window class finder, handler naming, line-boundary stub planning and unplanning, the FB2xx checks (`LOGIC_DESIGN.md` §3.2–3.6; CONTRACTS §16.1, 16.2, 16.5) | G, O-logic | Every check has a fixture and its clean twin. Pain 22 |
| M6.2b | Call your code UI: double-click and "Write code for…", the method page, stub insertion and undo through the code bridge, go to code (F12), Problems fixes, Your methods, Connect methods by name, F5 save prompt, Preview stand-ins | G, O-UX + O-logic | R3 6, 7 done. Pain 6. K26 passes. **VM** (UX §16.4) |
| M6.R | Review of M6 as a whole: heuristic, keyboard-only (K24–K26 together) and the two persona walkthroughs (UX §12.6); speed rows for UX-M6-003 in the harness; fix lanes as needed | O-UX + G | APPROVE. Ledger: every M6 row done (6 R3 rows, P-6, P-16, P-22, 11 logic features) |

#### M6 lanes

Paths are relative to `app/features/form_builder/` unless they start with `tests/`, `tools/` or `docs/`. A lane owns the files it creates and the files listed. Two lanes never edit the same file at the same time; when a lane needs a change in a file it does not own, it writes a strict `xfail` repro in its own test file and reports it. New context-menu rows go in `integration/menu_ext/`, Form menu items in `integration/form_menu_ext/`, keys in `integration/keys_ext/`, Problems fix buttons in `integration/problem_fixes/`, canvas layers in `qtside/canvas/layers/`, FB codes in a new module under `engine/diagnostic_codes/`, commands in `engine/commands/catalog_ext/`, participants in `engine/commands/participants/`, Behavior sections in `qtside/inspector/behavior_ext/`, double-click contributors in `integration/activate_ext/`, overlay kinds in `integration/overlay_ext/`, intents in `engine/logic/intents/`, expanders in `engine/codegen/expanders/`: each lane adds its own file there and edits no shared one. Each lane's tests are new files `tests/form_builder/**/test_m6_<lane>_*.py`; the M6 fixture project is `tests/form_builder/fixtures/m6/` (UX §12.3), created by M6.0s and extended by lanes in their own subfolders. `tests/form_builder/perf/harness.py` is M6.R's.

| Lane | Owns | Must not touch | Closes |
| --- | --- | --- | --- |
| M6.0s | `qtside/inspector/_behavior.py` (becomes the section host; the M3 list moves into `behavior_ext/_legacy_connections.py` until M6.1b withdraws it), new `qtside/inspector/behavior_ext/__init__.py`, `qtside/canvas/core/gesture.py` and `qtside/canvas/core/words.py` (the double-click hook and its hover words only), new `integration/activate_ext/__init__.py`, `integration/overlays.py` (the kind registry and the generic link gesture only; Tab order and Buddies keep their code), new `integration/overlay_ext/__init__.py`, new `integration/code_bridge.py`, new `integration/handlers.py`, new `engine/project/window_facts.py` (frozen dataclasses only), new `engine/codegen/expanders/__init__.py`, new `engine/logic/intents/__init__.py`, `engine/codegen/logic_hooks.py` and `engine/codegen/emit.py` (`Method.params` and its rendering only), `integration/problems_bridge.py` and `engine/diagnostics.py` (optional `code_path` and `code_line` in the location and detail; double-click opens code when set), new `tests/form_builder/fixtures/m6/`. Also edited at the gate's say-so, hooks only: `qtside/canvas/controller.py` (passes `host.activation_claim` into `World.claims`, runs `Activate` through `host.activate_node`), `integration/surface.py` (`code_bridge`, `activation_claim`, `activate_node`, overlay toggles, a code-only Problems row opens code) and `integration/workbench.py` (`FormToolbar.overlay_toggles` from `overlay_ext`); later lanes add contributors and never edit these hooks | every other file | no R3 rows (enables every M6 lane) |
| M6.0b | `engine/logic/storage.py`, new `engine/logic/codec.py`, new `engine/logic/refs.py`, new `engine/commands/participants/logic_targets.py`, `logic_formulas.py`, `logic_labels.py`, `engine/commands/planning.py` (`set_logic`, `_sync_logic_marker`, the FB402 guards, the fragment version rule only), `engine/commands/catalog.py` (`SetLogic`'s fields and docstring only), `engine/ui4/document.py` (`logic_version` only), `engine/session.py` (`logic_read_only` only), `engine/clipboard.py` (the fragment version attribute), new `engine/diagnostic_codes/fb4xx_logic.py` | `engine/ui4/reader.py`, `writer.py` (report gaps with a repro), `engine/codegen/**`, any `qtside/` or `integration/` file | L-logic-storage, L-logic-references |
| M6.1a | new `engine/logic/events.py` (event model over connections, lists and by-name methods), `engine/logic/compat.py`, `engine/logic/events_catalog.py`, new `engine/logic/intents/m6.py`, new `engine/commands/catalog_ext/events.py` (`SetEventSteps`, `MergeEventStorage`), `engine/commands/catalog.py` (`AddConnection`, `EditConnection`, `MoveConnection` semantics only, after M6.0b), new `engine/codegen/expanders/steps.py`, new `engine/diagnostic_codes/fb40x_events.py` (FB404, FB405 producers) | `engine/logic/codec.py` (use its API; until M6.0b merges, code to CONTRACTS §15.5 and merge after it), `engine/codegen/emit.py`, any `qtside/` or `integration/` file | L-runtime-connect |
| M6.1b | new `qtside/inspector/behavior_ext/events.py`, `from_others.py`, `form_events.py`, new `qtside/pickers/**` (event picker, step picker, target and slot pages, method page shell), `qtside/inspector/model.py` (`BehaviorView` and friends), `qtside/inspector/pane.py` (Alt+B focus and the count badge only), delete `behavior_ext/_legacy_connections.py`, new `integration/keys_ext/behavior.py` (Alt+B, Ctrl+Shift+E, the list keys), new `integration/form_menu_ext/events.py`, new `integration/menu_ext/events.py`, new `integration/problem_fixes/events.py` (Merge, Open as text) | `qtside/canvas/**`, `integration/overlays.py`, `integration/surface.py`, the method page's code actions (they call `integration/handlers.py`) | R3 3, 4, 5; P-16; L-events-list, L-signal-slot-picker |
| M6.1c | new `qtside/canvas/layers/logic_badges.py` and `connections.py`, new `integration/overlay_ext/connections.py` (banner, toggle, link handler opening the M6.1b pickers), `integration/keys_ext/modes.py` (F4 now toggles the overlay; Ctrl+Shift+L), new `integration/form_menu_ext/connections.py`, `qtside/theme/overlay.py` (`ov.connect`, `ov.connect_faint`, `ov.code`, `ov.logic_badge`) | `qtside/canvas/core/**`, `paint.py`, every inspector file, `integration/surface.py` | R3 2; L-canvas-overlay |
| M6.2a | new `engine/project/window_file.py`, new `engine/project/handler_names.py`, new `engine/project/handler_checks.py`, `engine/codegen/window_template.py` (`plan_stub`, `plan_unstub`, the docstring), new `engine/diagnostic_codes/fb2xx_code.py` (FB201–FB213) | `engine/project/custom_widgets.py` (reuse `_read_regular` through a small public helper the lane adds in its own module, or report), `engine/codegen/emit.py`, any `qtside/` or `integration/` file | L-handler-naming, L-signature-checks, L-connect-slots-by-name; P-22 |
| M6.2b | new `integration/handlers_code.py` (the method gesture, undo pairing, go to code), new `integration/activate_ext/handlers.py` (double-click), new `integration/handler_checks_bridge.py` (runs the checks on the D12 triggers, inherited names from the stock Qt class), new `qtside/inspector/behavior_ext/your_methods.py`, `qtside/pickers/method_page.py` (after M6.1b), `qtside/inspector/editors/form_settings.py` (Connect methods by name), new `integration/keys_ext/code.py` (F12), new `integration/menu_ext/code.py`, new `integration/problem_fixes/code.py`, `integration/run_action.py` (the F5 prompt), `qtside/preview/child/materialize.py` and `engine/ipc/protocol.py` (`form_methods`, optional field), `integration/preview_control.py` (the would-call status) | `engine/project/window_file.py` and the other M6.2a modules (report), `qtside/canvas/**`, `engine/codegen/emit.py` | R3 6, 7; P-6; L-stub-and-jump, L-design-time-errors |
| M6.R | `tests/form_builder/perf/harness.py` (M6 rows), `tests/form_builder/qtside/test_m6_keyboard_scripts.py` (K24–K26 together), review repros | product files only through fix lanes | ledger audit: every M6 row |

**Order and dependencies.**

1. Wave 1 starts at once with four lanes: **M6.0s** (the only lane in shared product files), **M6.0b**, **M6.1a** and **M6.2a** (Qt-free, new files plus the engine files listed). M6.1a codes against CONTRACTS §15.5 and rebases on M6.0b before its gate; M6.0b's gate goes first.
2. Wave 2, when M6.0s and M6.1a have merged: **M6.1b** and **M6.1c** in parallel. M6.1c's link handler opens M6.1b's pickers; until M6.1b merges it uses a strict xfail for that one test and a temporary picker stub in its own file.
3. Wave 3, when M6.1b and M6.2a have merged: **M6.2b**.
4. **M6.R** after every lane has merged.

Merge order inside a wave follows readiness; a lane rebases on `feat/form-builder` before its gate. Expected size: M6.0s ~700 net lines; M6.0b ~1,300; M6.1a ~1,200; M6.1b ~1,500 (split M6.1b1 Events section / M6.1b2 pickers if the brief passes 1,500); M6.1c ~1,000; M6.2a ~1,200; M6.2b ~1,400.

**Review gates.** Each lane's PR lists the UX clause ids it implements, runs its K script (M6.1b K24, M6.1c K25, M6.2b K26) and reports its UX-M6-003 rows. **O-logic** gates M6.0s (registry order and discovery, the code bridge never writes outside the project and keeps the tab's undo, the double-click hook leaves Enter alone), M6.0b (canonical text both ways, fuzz, marker truth table, unknown keys kept, FB402 write-back byte identity, participants touch only NAME tokens, replay and undo-all), M6.1a (the storage invariant over random sequences, minimal diff and hints kept, overload choice, generated step code against PySide6 at run time, 3.9-parseable), M6.1b (every gesture is one `SetEventSteps` entry; Esc leaves bytes and the stack unchanged), M6.2a (no import, the pre-scan crash set under the Python 3.9 AppRun lane, the insertion fixture set, every FB2xx with a clean twin, naming over the corpus) and M6.2b (the method gesture's order and rollback, undo and redo against edited and unedited stubs, the tab-saved rule, Preview stand-ins never import the window file). **O-UX** gates M6.1b, M6.1c and M6.2b (screenshots per UX §12.2 "M6 states", light, dark and both high contrast themes, 100% and 200%, inspector states also at 236 px; the K script with no mouse event). One Opus gate runs at a time; M6.0s's goes first because every UI lane waits on it, then M6.0b's because M6.1a rebases on it. M6.2b also runs the UX §16.4 facts on the ChoreBoy VM.

**Done when, per lane** (in addition to the table's rows and the PLAN §2 gates): every clause the lane names passes its evidence codes; its K script passes with no mouse event; its ledger rows are done with marked, passing tests; its UX-M6-003 rows are inside budget with machine load recorded; every on-screen sentence it added is in UX §13.3.8; every FB code it emits is declared in its own `diagnostic_codes` module; and its manual page is written (PLAN §2 gate 12: `manual/events.md` by M6.1b, `manual/your-code.md` by M6.2b).

### M7. Logic level 3 (formulas, rules, checks, Try mode)

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M7.1 | Expression language: an ast-allowlist parser, the type system (Text, Whole, Number, Money/Decimal, Date…), blank semantics, the function library, Excel-habit quick fixes, and error messages | G, O-logic | Spec conformance suite (hundreds of cases) and fuzzing. Generated Python matches the evaluator |
| M7.2 | Rules: enabled, visible and read-only when; value and default; re-checked at startup and after each record load. Repair references and two-places merge for forms edited in Qt Designer (§6.5) | G, O-logic | Scenarios 1–2 from `LOGIC_DESIGN.md` pass end to end |
| M7.3 | Checks and formats: required, ranges, length, patterns, presets, cross-field, inline error labels, and run-time timing; shipped-app error behavior and "Open rule" links on traceback frames (§2.11) | G, O-logic + O-UX | Scenario 3 passes |
| M7.4 | Action vocabulary: message, confirm, open form, close/accept/reject, clear, set value, focus, enable/disable, switch page, run your method | G, O-logic | Scenario 4 passes |
| M7.5 | Point-and-click condition and value builder (ships with typed formulas) | G, O-UX | Opus heuristic review approves it for non-programmers |
| M7.6 | Try mode: run the real generated code in the preview process with a stand-in window class | G, O-UX + O-logic | **VM** |
| M7.7 | Persona walkthroughs (instead of human tests): Opus plays a non-programmer shop owner and a Qt developer through the logic scenarios, recording step counts and confusion points | O-UX | Findings fixed or ledgered |
| M7.8 | Logic panel and search: the form-wide Logic outline, Ctrl+Shift+F, a "Forms logic" group in project Find, and "Read as text" (§2.8) | G, O-UX | Search finds every rule and handler |

### M8. Logic level 4 (data)

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M8.0 | Data UX spec refresh: the Data panel, connections manager screen, navigation toolbar and list screens | O-spec | Approved |
| M8.1 | Connections manager: project settings screen, Test button, generated `cbcs_connections.py`, password policies (ask, remember on this machine, none), `on_connect` hook, and driver probing (`cb_psycopg`, `psycopg`, `pg8000`; vendors pure-Python pg8000 + scramp + asn1crypto if the M0.7 probe finds no driver) | G, O-logic + O-UX | Tests against SQLite and a leased Postgres 9.3 container. **VM** |
| M8.2 | Form data source and field bindings: the key-list loading model, one record at a time, dirty tracking, close guard, conflict detection, PostgreSQL 9.3-safe SQL | G, O-logic | Scenarios 5–6 pass on SQLite and PostgreSQL 9.3 |
| M8.3a | Lookups (foreign key → combo) | G, O-UX + O-logic | Scenario 5 on SQLite and PG 9.3 |
| M8.3b | Master-detail line items | G, O-UX + O-logic | Scenario 6 on SQLite and PG 9.3 |
| M8.3c | List and search screens | G, O-UX + O-logic | Tests on both databases |
| M8.3d | Form-from-table producing bound forms (SQLite and Postgres) | G, O-UX + O-logic | Invoice end-to-end demo on the VM |
| M8.4 | Try mode for data: SQLite on a scratch copy; Postgres write then roll back, with a banner, statement and lock timeouts, side-effect warning (sequences, NOTIFY), and a per-connection read-only "Would run" option | G, O-logic | Tests prove the rollback and that the user's data is unchanged |
| M8.5 | Eject to code: turns the data layer into plain user-owned methods, and documents the `self.ui.cbcs_*` API | G, O-logic | The ejected form behaves identically, proven by a test |
| M8.6 | Schema helper process and the `cbcs/schema/*.json` cache (§5.1, §2.6) | G, O-logic | Schema refresh works offline and is cached |

### M9. Hardening and polish

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M9.1 | Parity audit: every ledger row done (or approved won't-do) with a test. Gap-closing sprints as needed | G + Claude | Ledger 100% |
| M9.2 | Robustness: fuzzed `.ui`, huge forms (1000+ widgets), long sessions (memory), multi-form projects (cross-form open-form actions, rename/move of forms) | G, O-logic | All pass |
| M9.3 | Accessibility and keyboard-only operation of every feature, high contrast, high DPI on Qt 6, screen-reader names | G, O-UX | Keyboard-only script covers every feature |
| M9.4 | Speed on the ChoreBoy VM and the lab Linux host. Optimise where needed | G | Budgets met on the VM. **VM** |
| M9.5 | Visual polish pass: a full screenshot tour in light, dark and high-contrast; micro-interactions; empty states; copy | O-spec + G, O-UX | Opus final UX APPROVE |
| M9.6 | Docs: user manual pages (`docs/manual*`), keyboard reference, README, CHANGELOG, acceptance tests | G, O-UX (copy) | Docs reviewed |
| M9.7 | Final logic soundness audit across the engine, generator, expression language, rules and data layer | O-logic | APPROVE |

**M9.4 known misses carried from M3 (accepted at M3.7; budgets unchanged).** Real MainWindow, 1400×900, 1000-widget reference form, CPU p50 at load 30–50 on the Mac. These are the `edit total surface`, `edit layout spacing` and `paste surface` rows in `tests/form_builder/perf/harness.py`. Over budget they report the verdict `known miss` (named in every speed report, budget unchanged) instead of `fail`, so the perf gate stays meaningful for every other row. Only these three points may carry that verdict (`KNOWN_M94_POINTS`); M9.4 removes it.

- Edit layout spacing: ~22–33 ms against 16 ms. Qt's own relayout of the 394-row form layout costs ~5–6 ms. The rest is the hit-index refresh, which re-measures ~400 items (it has to: every item moves), plus a whole-page repaint of the proxied form.
- Paste: ~50–65 ms against 16 ms, ~50 ms with the inspector hidden. Undoing it costs ~60 ms. The cost is the realize patch (reconciling a 394-row form layout), a full hit-index walk after any structural change (~5–7 ms), a full rebuild of the overlay's static layer on insert (~7 ms), and the row shift in the engine. The row shift is already one bubble per parent for the forward edit, and for undo and redo since M3.7a.
- Edit label text was ~20 ms CPU at load 30 when M3.7a closed. The rescue did not reach 16. A text edit on a QLabel in the form layout invalidates the whole proxied page (the scene reports the full page rect) although no widget moves. Bisecting it showed that only the realizer's property patch is needed; a raw `setText` on the same widget does not do it. Nothing found yet.
- Leads:
  1. A cached page or a region paint layer, so overlay and caption changes never re-render the proxied form.
  2. An O(changed) static overlay layer on insert and delete.
  3. A structural refresh of the hit index that only re-measures the changed container. Today any insert, delete or move takes the full walk, the only path proven equal to a rebuild by the structural fuzz in `tests/form_builder/qtside/test_hit_index_incremental_repro.py`.
  4. A cheaper realize patch for long form layouts.
  5. The whole-page invalidation after a QLabel text patch.
  6. The shell's draft autosave, which serializes the whole form to XML (~20–40 ms) and sometimes lands inside an edit.

### M10. Release candidate

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M10.1 | Merge the latest `main`, rerun every gate, and do a full end-to-end run on the VM: build three real apps (data entry, list + detail, main window with menus) from scratch with the builder, package them, install them, and run them | Claude + G | All green, with a recorded demo |
| M10.2 | Open the final PR `feat/form-builder` → `main` for Joshua to merge. Retire the spike branch and its worktree after preserving lessons. Clean up all lanes and leases | Claude | PR open, workspace audit clean |

## 5. Parallelism

- M0.3–M0.9 run in parallel: the local Mac lane, lab lanes and cloud lanes. M0.9 (Opus UX spec) and M1.0 (Opus contracts) are written while Grok builds the M0 tooling.
- M1.0 must be approved before any other M1 code merges. Then M1.1a lands first. M1.1b, M1.1c and M1.2 follow in parallel, then M1.3, M1.4 and M1.5.
- M2.0 (shell seam) can start right after M1.0, because it doesn't depend on the engine. M2.1–M2.4 follow, and M2.5 is a separate lane once the IPC contract is approved.
- M3.1a lands first, then M3.1 and M3.1b. M3.2–M3.6 then split by directory into 2–3 lanes.
- M4 runs in two waves (see "M4 lanes"): M4.0s, M4.1 and M4.2 at once; M4.3a and M4.3d once M4.0s merges; then M4.3b, M4.3c and M4.4. Editors register through the M3.1b registry and context-menu rows through `integration/menu_ext/`, so lanes never edit each other's files.
- M5 runs in waves (see "M5 lanes"): M5.0s first; then M5.1, M5.2 and M5.3; then M5.4, M5.6 and M5.5b; then M5.5a and M5.5c. New Form menu items, context-menu rows, keys, canvas layers, FB codes, commands and inspector rows register from each lane's own files, so lanes never edit each other's files.
- M6.0, M6.0b and M7.1 (the pure language, no UI) can start during M5. Inside M6, M6.0s, M6.0b, M6.1a and M6.2a run together (PLAN M6 lanes).
- M8.1 can start during M7.
- M9 is mostly parallel.

**Capacity:** Cursor Cloud is the default home for Grok lanes once M0.8 lands, so lanes are limited by Cursor accounts rather than machines. The Mac allows one local lane (workspace policy), used for Mac-only checks. The lab host is for VM work and Linux checks. One Opus gate runs at a time, and there's no hard cap on cloud lanes beyond file-disjointness and the review bandwidth.

## 6. Verification matrix

| Level | Where | When |
| --- | --- | --- |
| Pure model, codegen and language tests | Mac, FreeCAD.app 1.1.3 python, plus `~/opt/freecad` with PySide6 (Python 3.9 syntax) | Every PR |
| Offscreen Qt and interaction tests | Mac | Every PR |
| Oracles (`QUiLoader`, `uic`, corpus) | Mac | Every PR |
| Linux run | Lab host with the FreeCAD 1.1.x AppImage | Every milestone |
| Real appliance | ChoreBoy VM (FreeCAD 1.1.1) via `run-choreboy-app` | M2.5, M7.6, M8.1, M8.3, M9.4, M10.1 |
| UX | Opus gate: screenshots, interaction traces, a launched build | Every UI PR, plus milestone tours |

## 7. Risks

| Risk | Mitigation |
| --- | --- |
| Cursor accounts exhausted | `grok-run` rotates accounts. On exit 3, stop and ask Joshua to add an account |
| `main` drift and conflicts | Merge `main` at every milestone start; keep the feature self-contained |
| Linux and macOS Qt differences | A lab Linux run every milestone, and the VM at key points |
| Grok output quality on UI | Opus spec first, an Opus gate before merge, and Opus rescue after two failed gates |
| Clean-room licence | Briefs forbid copying Qt source. Reviews spot-check for translated code |
| Scope creep in logic | `LOGIC_DESIGN.md` §8 limits: no general-purpose language, no node graphs |
| Speed regressions | Budget gate on every PR, plus VM speed at milestones |
| PySide2 users | The feature is hidden and `.ui` text editing still works. Release waits for FreeCAD 1.1 on ChoreBoy |

## 8. Definition of done

- All 330 parity items done with tests, or approved won't-do (expected near zero).
- All 25 ranked pains solved, with their tests from `research/P_user_pain_points.md`.
- Logic levels 1–4 per `LOGIC_DESIGN.md`, including the six scenarios on SQLite and PostgreSQL 9.3.
- Speed budgets met on the Mac and the ChoreBoy VM.
- Opus final APPROVE on UX and on logic soundness.
- User docs complete. Three real apps built, packaged and run on the VM.
- PR to `main` open for Joshua, with every workspace and lease cleaned up.

## Appendix A. ChoreBoy runtime facts (M0.7 probe, 2026-10-21)

Probed on the ChoreBoyExp VM (FreeCAD 1.1.1) with `cb_probes/harness/probes/fb_m07_probe` (branch `probes/fb-m07`). These are fixed facts for design decisions.

| Fact | Value | Consequence |
| --- | --- | --- |
| Runtime | Python 3.11.14, Qt/PySide6 6.8.3, Linux 6.1, glibc 2.31 | Matches the Mac's FreeCAD.app 1.1.3 |
| Hardware (VM) | 2 vCPU (i7-10750H host), 4 GB RAM; screen 1680×1050, 96 logical dpi, dpr 1.0 | Real ChoreBoy specs vary; the VM is the reference low end |
| Raw Qt cost | Building 300 widgets and showing them: 137–274 ms warm (Mac: about 92 ms real display, 14 ms offscreen). One widget edit with repaint: 18–23 ms. Pure Python: about 4–10× slower than the Mac | Absolute budgets apply on the Mac. On ChoreBoy the budget is **overhead-relative**: opening a form costs at most 1.5× the raw Qt build of the same widgets, and an edit costs at most 1.5× a raw widget update plus repaint (target ≤ 2 frames) |
| `AppRun` | An ELF binary, not a shell script. `QProcess.start("/opt/freecad/AppRun", ["-c", code])` works without a shell. Bare start-and-exit: about 0.11 s | The preview child is spawned directly |
| `-c` length | Fails ("File name too long") somewhere between 200 and 400 characters | The child launches through a short `runpy.run_path` stub (139 characters) |
| Preview child cold start | Python + PySide6 + 150 widgets: 2.9–3.0 s offscreen, 3.9 s on the real display | One warm, pooled preview child is required. Spawn it at form open, in the background |
| stdin/stdout JSON | Works both ways | The IPC can use the existing framed stdio protocol |
| `uic` / `rcc` | Present under `/opt/freecad/usr/lib/qt6`, but exec is **denied** (execve EACCES) | The in-process generator is mandatory. `uic` is only a dev-machine oracle |
| FreeCADGui | Imports in an `AppRun -c` child, but `UiLoader` is absent there. Available in-process in GUI FreeCAD | Generated code needs a guarded `FreeCADGui.UiLoader` with a Qt base-class fallback |
| Postgres drivers | `pg8000`, `psycopg`, `scramp` and `asn1crypto` ship in `/opt/freecad`. No `psycopg2` or `cb_psycopg` | No vendoring needed. Driver probe order: psycopg, then pg8000 |
| SQLite | 3.51.1 | |
| `QFileSystemWatcher`, `QLocalServer` | Both work | External-change detection and local IPC are available |
| Home folder | Dotfiles directly in `~` cannot be written; the job dir is writable | Machine-local secrets ("remember on this machine") go under CBCS's existing state directory, which the probe must confirm is writable before M8.1 |
| Still to probe | The default app style, palette and font; window-manager-reserved Alt/function keys; the state-dir write check | Added to the next probe run (UX_SPEC §16.2) |
