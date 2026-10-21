# Form Builder: end-to-end delivery plan

Owner: Joshua Aguilar. Orchestrator: Claude (main session). Started 2026-10-21.
Integration branch: `feat/form-builder` (from `main` at `54c3a14`). Merging to `main` is Joshua's call.

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
| Try mode | SQLite runs on a scratch copy. PostgreSQL writes, then rolls back |
| Locale | US English by default, with a per-project setting |
| Users | A real mix of programmers and non-programmers, so the point-and-click formula builder ships with logic level 3 |
| Speed | Open a 300-widget form ≤ 150 ms; each edit ≤ 16 ms; save ≤ 50 ms; ≤ 30 MB extra. Re-checked on the ChoreBoy VM |

## 2. Operating model

### Roles

- **Claude (orchestrator):** owns this plan, writes every brief, reviews every diff, reruns every verification, merges PRs into `feat/form-builder`, keeps the roadmap artifact current, and keeps workspaces and leases clean.
- **Grok (heavy lifting):** implements code (UI included), writes tests, builds harnesses and does research gathering. It runs in local worktrees, lab-host lanes or Cursor Cloud, through `~/.claude/skills/grok/scripts/grok-run`.
- **Opus (only where it matters):**
  - *Design specs:* writes the interaction and visual spec before UI-heavy work packages.
  - *UX sign-off gate:* every UI-facing PR is reviewed from screenshots, interaction-test traces and a launched build, and returns APPROVE, or CHANGES with a concrete list.
  - *Logic soundness gate:* every PR that carries logic (document model, commands, writer, generator, expression language, rules, data layer) gets a correctness review. That covers invariants, edge cases, determinism, SQL safety and failure modes.
  - *Rescue:* if Grok fails the same gate twice, Opus may implement the narrow hard part.

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
6. Opus gate where it applies (UX and/or logic).
7. Milestone gates add: a run on the ChoreBoy VM (FreeCAD 1.1) and on the Linux lab host, a full screenshot tour, and an update to the parity ledger.

### Parity ledger

`docs/form_builder/PARITY.md` tracks all 330 R3 items. Each row has an id, a status (todo / doing / done / won't-do), the work package, and the test(s) that prove it. "Done" requires a named test. "Won't-do" requires a written reason that Opus has approved. The target is zero won't-do outside items that are meaningless for Python, such as C++-only export macros. Even those are preserved on round-trip.

### Autonomy and reporting

- Fully autonomous. Claude asks Joshua only when truly blocked, for example when every Cursor account is exhausted (exit 3) or a product decision is outside the fixed decisions above.
- The roadmap artifact shows milestone status, the ledger percentage, speed numbers and the latest screenshots. Each milestone's end is announced in the session with a short report.

### Hygiene

- Every worktree is registered with owner, purpose, base and cleanup condition, and retired once its PR merges.
- Every database or container created for tests gets a lease (`local-dev-data` skill). Test temp folders are deleted.
- Grok views are closed after review. Lab lanes are cleaned with `lab-clean`.
- `main` is merged into `feat/form-builder` at each milestone start, so the drift stays small.

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

- The editor surface plugs into `EditorTabFactory`, the same way Markdown does. It writes the `.ui` text into `EditorTabState.current_content`, so dirty state, save and local history keep working. A "View XML" toggle keeps acceptance test AT-32 passing.
- The preview and Try-mode process is a child `/opt/freecad/AppRun` started with `QProcess`. It's allowed on FreeCAD 1.1.1 ChoreBoy, where `/bin/sh` is denied. User and custom-widget code only ever runs there.
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
| M0.5 | `PARITY.md` ledger seeded from R3, with all items "todo" and mapped to work packages | G + Claude | Ledger exists and has been reviewed |
| M0.6 | Roadmap artifact (milestone tracker) | Claude | Published |

### M1. Engine (production)

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M1.1 | ui4 model, reader and writer covering every element and attribute in the ui4 schema (R3 items 223–321). Unknown-node preservation, deterministic writer, defaults table per class from QMetaObject | G, O-logic | Corpus round-trip 100% (`QUiLoader` tree equal plus byte-stable second save). Fuzzed and malformed `.ui` never crashes; it gives a clear error instead |
| M1.2 | Command log: the full command catalog (insert, delete, move, reparent, wrap, unwrap, morph, break layout, set property, z-order, container pages, actions, connections, tab order, buddies, promotion, resources), grouping, merge of rapid property edits, undo/redo, replay determinism | G, O-logic | Property-based tests (random command sequences: replay equals live, undo-all equals original) |
| M1.3 | Generator: `uic`-shaped Python for everything M1.1 reads, including resources (an rcc-equivalent `*_rc.py`), promoted classes, i18n/`retranslateUi`, connections, buddies, tab order, button groups, actions, and main-window parts | G, O-logic | Every corpus file: our module and `uic`'s build identical trees. Text diff reported. Fixes the 6 known failures from the spike |
| M1.4 | Project layer: generated-file hashes (detect hand edits to `ui_*.py`), window-class creation, naming rules, file layout under `forms/` | G | Tests cover create-once, hand-edit detection and rename |
| M1.5 | Speed harness wired into gates (big forms of 300, 600 and 1000 widgets) | G | Budgets asserted on process time and wall time, with load recorded |

### M2. CBCS integration shell

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M2.1 | Feature package and registration (PySide6 only), dune owner, handles, file roles | G | Dune checks green. Under PySide2, `.ui` opens as text with a hint |
| M2.2 | Editor tab: `.ui` opens the visual editor, with a View XML toggle. Dirty, save, local history, close prompts, and external file-change reload | G, O-UX | AT-32 still passes. New acceptance tests added |
| M2.3 | Problems integration, settings keys, shell theme tokens (light, dark, high contrast), keyboard shortcuts that don't collide with F5/F6/Ctrl+R | G, O-UX | Shortcut table test. Theme switch keeps the canvas in the runtime palette |
| M2.4 | Run and packaging: F5 on a form runs its project entry. The packager includes `ui_*.py`, `*_rc.py` and generated connections, and flags stale generated files. New-project template "Qt app with a form" | G | Packaging fixture test. The template project runs on the VM |
| M2.5 | Preview process (pain 11): AppRun child over `QProcess` with JSON IPC. Custom widgets load there. A crash turns into a Problems row | G, O-logic | Kill/raise fixtures leave the editor alive. **VM** |

### M3. Canvas and layout editing excellence

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M3.0 | UX spec v2 from the spike `DESIGN.md`, Joshua's "rough edges", pains, delighters, and a heuristic review of the spike build (Opus launches and drives it) | O-spec | `docs/form_builder/UX_SPEC.md` approved |
| M3.1 | Canvas core: view, zoom, overlay painter, hit-test index, selection model (single, multi, rubber band, parent, siblings), hover, chips that never cover content (fixes the name-chip overlap) | G, O-UX | Interaction tests. Speed holds |
| M3.2 | Drop and move engine for every layout kind: box, grid (cells, spans, insert row/column), form (label/field), splitter, stacked/tab pages, and bare containers. Auto-layout on first drop, next drop fills the next cell | G, O-UX | Per-kind interaction tests. Pains 1, 4 and 21 |
| M3.3 | Layout operations: wrap, unwrap, morph layout, morph widget, break layout (confirmed, keeps sizes), adjust size, simplify grid, spacers, gaps, margins, stretch, splitter handles on the canvas (pain 19), size constraints | G, O-UX | R3 35–56 ledger rows done. Pains 5, 14 and 19 |
| M3.4 | Clipboard and duplication: copy, cut, paste into a layout at an index (pain 3), cross-form paste, Alt-drag clone, duplicate, scratch pad | G, O-UX | R3 23–27 done |
| M3.5 | Outline: keyboard editing (Tab nest, Shift+Tab, Alt+arrows, `/` insert, F2 rename keeping focus), drag reparent, page reorder, references shown before delete | G, O-UX | Pains 20 and 25. A keyboard-only test script passes |
| M3.6 | Sizing panel: Hug/Fill/Fixed, share, min/max, "why is it this size?", font-size and DPI preview (pain 12), two-widths view | G, O-UX | Pain 2 tests. The "why" text is verified against the real widget |
| M3.7 | Opus heuristic and keyboard-only review of M3 as a whole | O-UX | APPROVE |

### M4. Widgets, containers and properties

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M4.1 | Widget catalog: all 54 widget-box entries and the classes outside the default box (incl. `QWizard`), with drawn icons, search and categories | G, O-UX | R3 57–123 done |
| M4.2 | Containers: tab, stacked and toolbox pages; scroll area; MDI; dock widgets; wizard pages; group box; frame. Page operations from canvas, outline and inspector | G, O-UX | R3 124–133 done |
| M4.3 | Property editors for every type: bool, numbers, enum, flags, string (translatable with comment and disambiguation), string list, char, font, color, brush/gradient, palette, cursor, pixmap, icon set, size/point/rect, size policy, key sequence, date/time, URL and locale. Changed markers, reset, multi-select, search, and the dynamic properties UI | G, O-UX + O-logic | R3 145–171 done. Pain 18 |
| M4.4 | Item editors: list, tree, table and combo items; columns and rows | G, O-UX | R3 172–173 done |

### M5. Main windows, resources, styling, custom widgets, templates

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M5.1 | Main window: inline "Type here" menus and submenus, toolbars, status bar, dock areas, action editor, dragging actions onto menus and toolbars (pain 17), action and button groups | G, O-UX | R3 134–144 done |
| M5.2 | Resources: `.qrc` browser and editor, icon pickers that accept only resources (pain 9), `*_rc.py` generation | G, O-UX | R3 174–175 done |
| M5.3 | Style: theme roles, plus a style sheet editor with syntax check, a resource picker and selector-match highlighting (pain 8) | G, O-UX | R3 176 done |
| M5.4 | Custom widgets: promotion dialog using Python module paths, sized stand-ins, real class in preview, a custom widget registry, and a security note | G, O-UX + O-logic | R3 194–198 done. Pain 7 |
| M5.5 | Preview in styles and device profiles, save image, View Code, form settings (layout default, functions, includes, export macro, translation options), templates (built-in plus save-as-template), Start screen v2 including form-from-table upgrades | G, O-UX | R3 177–193 done |
| M5.6 | Editing modes and shortcuts parity: buddy and tab order (the list dialog too), the full keyboard index, grid settings | G, O-UX | R3 1, 8–12, 199–222 done |

### M6. Logic levels 1–2

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M6.0 | Logic UX spec refresh: the Behavior tab, Events list and canvas overlay, from `LOGIC_DESIGN.md` §2–3 | O-spec | Approved |
| M6.1 | Events list. Native `<connections>` for plain connections, and step lists for multi-step or conditional events. Friendly signal/slot picker (curated plus full list). Canvas arrows | G, O-UX + O-logic | R3 2–7 done. Pain 16 |
| M6.2 | Call your code: handler naming, double-click stub insertion (once, and undo removes an empty stub), jump to code, signature and `@Slot` checks by parsing `<name>_window.py`, and `connectSlotsByName` checks (pain 22). Problems integration | G, O-logic | Tests cover every check. Pain 6 |

### M7. Logic level 3 (formulas, rules, checks, Try mode)

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M7.1 | Expression language: an ast-allowlist parser, the type system (Text, Whole, Number, Money/Decimal, Date…), blank semantics, the function library, Excel-habit quick fixes, and error messages | G, O-logic | Spec conformance suite (hundreds of cases) and fuzzing. Generated Python matches the evaluator |
| M7.2 | Rules: enabled, visible and read-only when; value and default; re-checked at startup and after each record load | G, O-logic | Scenarios 1–2 from `LOGIC_DESIGN.md` pass end to end |
| M7.3 | Checks and formats: required, ranges, length, patterns, presets, cross-field, inline error labels, and run-time timing | G, O-logic + O-UX | Scenario 3 passes |
| M7.4 | Action vocabulary: message, confirm, open form, close/accept/reject, clear, set value, focus, enable/disable, switch page, run your method | G, O-logic | Scenario 4 passes |
| M7.5 | Point-and-click condition and value builder (ships with typed formulas) | G, O-UX | Opus heuristic review approves it for non-programmers |
| M7.6 | Try mode: run the real generated code in the preview process with a stand-in window class | G, O-UX + O-logic | **VM** |

### M8. Logic level 4 (data)

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M8.0 | Data UX spec refresh: the Data panel, connections manager screen, navigation toolbar and list screens | O-spec | Approved |
| M8.1 | Connections manager: project settings screen, Test button, generated `cbcs_connections.py`, password policies (ask, remember on this machine, none), `on_connect` hook, and driver probing (`cb_psycopg`, `psycopg`, `pg8000`) | G, O-logic + O-UX | Tests against SQLite and a leased Postgres 9.3 container. **VM** |
| M8.2 | Form data source and field bindings: the key-list loading model, one record at a time, dirty tracking, close guard, conflict detection, PostgreSQL 9.3-safe SQL | G, O-logic | Scenarios 5–6 pass on SQLite and PostgreSQL 9.3 |
| M8.3 | Lookups (foreign key → combo), master-detail line items, list and search screens, and form-from-table producing bound forms (SQLite and Postgres) | G, O-UX + O-logic | Invoice end-to-end demo on the VM |
| M8.4 | Try mode for data: SQLite on a scratch copy; Postgres write then roll back, with a banner, statement timeout and lock warning | G, O-logic | Tests prove the rollback and that the user's database is unchanged |
| M8.5 | Eject to code: turns the data layer into plain user-owned methods, and documents the `self.ui.cbcs_*` API | G, O-logic | The ejected form behaves identically, proven by a test |

### M9. Hardening and polish

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M9.1 | Parity audit: every ledger row done (or approved won't-do) with a test. Gap-closing sprints as needed | G + Claude | Ledger 100% |
| M9.2 | Robustness: fuzzed `.ui`, huge forms (1000+ widgets), long sessions (memory), crash recovery and autosave, external edits in Qt Designer coming back ("Repair references") | G, O-logic | All pass |
| M9.3 | Accessibility and keyboard-only operation of every feature, high contrast, high DPI on Qt 6, screen-reader names | G, O-UX | Keyboard-only script covers every feature |
| M9.4 | Speed on the ChoreBoy VM and the lab Linux host. Optimise where needed | G | Budgets met on the VM. **VM** |
| M9.5 | Visual polish pass: a full screenshot tour in light, dark and high-contrast; micro-interactions; empty states; copy | O-spec + G, O-UX | Opus final UX APPROVE |
| M9.6 | Docs: user manual pages (`docs/manual*`), keyboard reference, README, CHANGELOG, acceptance tests | G, O-UX (copy) | Docs reviewed |
| M9.7 | Final logic soundness audit across the engine, generator, expression language, rules and data layer | O-logic | APPROVE |

### M10. Release candidate

| WP | Work | Who | Done when |
| --- | --- | --- | --- |
| M10.1 | Merge the latest `main`, rerun every gate, and do a full end-to-end run on the VM: build three real apps (data entry, list + detail, main window with menus) from scratch with the builder, package them, install them, and run them | Claude + G | All green, with a recorded demo |
| M10.2 | Open the final PR `feat/form-builder` → `main` for Joshua to merge. Retire the spike branch and its worktree after preserving lessons. Clean up all lanes and leases | Claude | PR open, workspace audit clean |

## 5. Parallelism

- M0.3, M0.4 and M0.5 run in parallel.
- M1.1 must land first. Then M1.2 and M1.3 run in parallel, followed by M1.4 and M1.5.
- M2 starts once the M1.1/M1.2 APIs are stable. M2.1–M2.4 and M2.5 are separate lanes.
- M3.0 (Opus spec) runs during M1–M2. M3.1 lands first; M3.2–M3.6 then split by file area into 2–3 lanes.
- M4.1, M4.2, M4.3 and M4.4 run in parallel, since they touch separate files (catalog, containers, editors).
- M5.1–M5.6 run as 2–3 parallel lanes.
- M6.0 runs during M5. M7.1 (pure language) can start during M5 because it has no UI.
- M8.1 can start during M7.
- M9 is mostly parallel.

The limits are about 3 concurrent Grok lanes plus 1 Opus gate at a time, the free Cursor accounts, and lab load.

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
