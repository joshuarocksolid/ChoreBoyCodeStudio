# ChoreBoy Code Studio — Test Strategy & Current Validation

## 1) Purpose

This document captures the **active** testing strategy and commands for the shipped implementation.

It aligns with:
- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/ACCEPTANCE_TESTS.md`
- `docs/TASKS.md`

## 2) Framework and markers

- Test runner: `pytest` (shipped inside the FreeCAD AppRun runtime)
- Markers (defined in `pyproject.toml`):
  - `unit`
  - `integration`
  - `runtime_parity`
  - `manual_acceptance`

## 3) Test layout

- `tests/unit/` — deterministic contract tests
- `tests/integration/` — multi-component filesystem/subprocess/runtime boundary tests
- `tests/runtime_parity/` — reserved for AppRun-specific checks where applicable

## 4) What is covered

Implemented coverage includes:

- bootstrap, logging, capability probe, path contracts
- project manifest/schema validation, project loading, and first-open metadata initialization for plain Python folders
- recent project persistence
- editor tab manager, dirty/save semantics, autosave store
- project tree model, quick-open ranking, find-in-files scanning
- run manifest schema, run id/log path generation
- process supervisor lifecycle and stop behavior
- runner bootstrap, execution context, traceback logging
- run orchestration end-to-end (manifest -> runner -> output -> log)
- diagnostics and support bundle generation
- built-in template discovery/materialization and generated-project execution
- responsiveness threshold checks (integration timing assertions)
- Designer subsystem end-to-end:
  - `.ui` routing to Designer surface
  - palette insertion, selection synchronization, typed properties
  - layout commands, reparenting, command-stack undo/redo
  - signals/slots, tab order, buddy interactions + serialization
  - resources/iconset/promote/custom-widget isolated preview checks
  - deterministic formatter, unknown-node preservation, component library flows
  - post-audit reliability/parity closure suites (DFIX/DGAP workstream), including:
    - insertion parent-resolution + undo consistency
    - isolated preview timeout/error diagnostics
    - layout-item attribute round-trip fidelity
    - focus-scoped F5/F6 shortcut arbitration
  - Designer validation + shell Problems parity

## 5) Core commands

Run full suite:

```bash
python3 run_tests.py -v
```

Run focused suites:

```bash
python3 run_tests.py -v tests/unit
python3 run_tests.py -v tests/integration
python3 run_tests.py -v tests/integration/performance
```

Run Designer-focused suites directly (fast signal while iterating on Designer):

```bash
.venv/bin/python -m pytest -q tests/unit/designer tests/integration/designer \
  tests/unit/shell/test_menus_designer_form.py \
  tests/unit/shell/test_menus_designer_mode.py \
  tests/unit/shell/test_shortcut_preferences.py \
  tests/unit/shell/test_status_bar.py
```

Run post-audit reliability/parity closure suites (recommended for D6+ slices):

```bash
python3 run_tests.py -v tests/unit/designer/canvas/test_form_canvas.py
python3 run_tests.py -v tests/unit/designer/io/test_ui_reader_writer.py
python3 run_tests.py -v tests/unit/designer/preview/test_preview_service.py
python3 run_tests.py -v tests/integration/designer/test_custom_widget_isolated_preview_runner.py
python3 run_tests.py -v tests/integration/designer/test_designer_preview_loader.py
python3 run_tests.py -v tests/integration/designer/test_open_ui_designer_surface.py
python3 run_tests.py -v tests/integration/designer/test_designer_save_roundtrip.py -k tranche_one_palette_widgets
python3 run_tests.py -v tests/integration/designer/test_designer_save_roundtrip.py -k tranche_two_palette_widgets
python3 run_tests.py -v tests/unit/shell/test_menus_designer_mode.py
python3 run_tests.py -v tests/unit/shell/test_shortcut_preferences.py
python3 run_tests.py -v tests/unit/shell/test_main_window_debug_routing.py -k designer_validation_issues
python3 run_tests.py -v tests/unit/designer/palette/test_widget_registry.py
python3 run_tests.py -v tests/unit/designer/canvas/test_drop_rules.py
python3 run_tests.py -v tests/unit/designer/properties/test_property_editor.py
python3 run_tests.py -v tests/unit/designer/properties/test_property_editor_panel.py
python3 run_tests.py -v tests/unit/designer/io/test_ui_reader_writer.py -k size_policy_and_size_constraints
python3 run_tests.py -v tests/unit/designer/properties/test_property_editor.py -k appearance
python3 run_tests.py -v tests/unit/designer/properties/test_property_editor_panel.py -k appearance
python3 run_tests.py -v tests/unit/designer/io/test_ui_reader_writer.py -k appearance_and_window_metadata
```

## 6) Manual acceptance validation

Manual acceptance is executed against `docs/ACCEPTANCE_TESTS.md`:

- MVP gate (`AT-01`, `AT-03`, `AT-24`, `AT-05`, `AT-06`, `AT-07`, `AT-08`, `AT-10`, `AT-11`, `AT-12`, `AT-14`, `AT-15`, `AT-16`) validated with GUI evidence.
- Extended checks (`AT-17`, `AT-19`, `AT-20`, `AT-21`, `AT-22`, `AT-23`) validated with GUI + artifact evidence.
- `AT-18` draft recovery is validated via integration simulation test (`tests/integration/persistence/test_autosave_recovery.py`) because force-kill GUI simulation is unsafe in this cloud session.

## 7) Notes for cloud environment

- Tests run through `/opt/freecad/AppRun` using real PySide2 — the same Qt binding used in production.
- `QT_QPA_PLATFORM=offscreen` is set by default in `run_tests.py` so tests do not require a display server.

## 8) Current baseline result

At latest validation checkpoint:

- `python3 run_tests.py -q` -> **150 passed** (no known test warnings)
- `.venv/bin/python -m pytest -q tests/unit/designer tests/integration/designer tests/unit/shell/test_menus_designer_form.py tests/unit/shell/test_menus_designer_mode.py tests/unit/shell/test_shortcut_preferences.py tests/unit/shell/test_status_bar.py` -> **142 passed** (Designer + shell command surface validation)
