# AGENTS.md

## 1. Purpose

This repository contains **ChoreBoy Code Studio**, a Qt-based project editor and runner for constrained ChoreBoy systems.

The project exists to provide a **project-first Python development experience** inside the ChoreBoy environment using the **FreeCAD AppRun runtime** rather than a normal system Python installation.

This file tells coding agents how to work safely and effectively in this repo.

---

## 2. Read These Files First

Before making any non-trivial change, read these canonical docs in this order:

1. `docs/PRD.md`
2. `docs/DISCOVERY.md`
3. `docs/ARCHITECTURE.md`
4. `docs/ACCEPTANCE_TESTS.md`
5. `docs/TASKS.md`

If a task affects system structure, runtime boundaries, or project layout, re-read `docs/ARCHITECTURE.md` before editing code.

---

## 3. Canonical Ownership of Docs

Use these files as the source of truth:

- `docs/PRD.md` = what the product must do
- `docs/DISCOVERY.md` = what the environment supports and restricts
- `docs/ARCHITECTURE.md` = how the system is structured
- `docs/ACCEPTANCE_TESTS.md` = how success is validated
- `docs/TASKS.md` = implementation slices and backlog
- `AGENTS.md` = instructions for agents working in this repo

Do not duplicate large parts of those docs into code comments or new markdown files without a reason.

---

## 4. Hard Constraints

These constraints are non-negotiable unless the docs are explicitly updated:

1. Users are on a **locked-down ChoreBoy system**.
2. The main runtime is **FreeCAD AppRun** at `/opt/freecad/AppRun`.
3. The available Python environment is **not** a normal system Python setup.
4. The FreeCAD runtime on **ChoreBoy production** ships **Python 3.9.2**. The **Cursor Cloud** development environment ships **Python 3.11** in the same FreeCAD AppRun. All code must be compatible with **Python 3.9** (no 3.10+ features). See `docs/DISCOVERY.md` section 1A and `.cursor/rules/python39_compatibility.mdc`.
5. `PySide2` is available in the FreeCAD runtime.
6. `import FreeCAD` works for headless/backend operations.
7. Some FreeCAD features that depend on GUI modules do **not** work in console mode.
8. `subprocess` is allowed and is a core primitive.
9. `SQLite` is available and should be preferred for lightweight local persistence.
10. Pure-Python vendored dependencies are acceptable; system package assumptions are not.

Do not introduce architecture that depends on:
- apt installs
- pip installs on the target machine
- internet access
- background services that are not already part of the supported runtime
- heavy external tooling unless explicitly approved in docs

---

## 5. Core Architectural Rules

### 5.1 Never run user project code in the editor process
All user code must run in a **separate runner process**.

### 5.2 Respect the editor/runner boundary
If a change affects launching, execution, logging, output capture, or crash handling, review the runner architecture first.

### 5.3 Filesystem-first design
Projects must remain ordinary folders on disk. Prefer transparent file-based storage over opaque internal state.

### 5.4 Project metadata must stay human-readable
Canonical project metadata belongs in project files such as `cbcs/project.json`, not hidden in a database.

### 5.5 Use SQLite only for caches, indexes, or optional acceleration
Do not move the project’s primary identity or project metadata into SQLite.

### 5.6 Prefer explicit contracts
Prefer:
- JSON manifests
- explicit file paths
- explicit exit codes
- explicit logs
- explicit config

Avoid hidden coupling, magic globals, and fragile bootstrapping.

### 5.7 Optimize for supportability
When choosing between cleverness and diagnosability, choose diagnosability.

---

## 6. Workflow Rules for Agents

### 6.1 Plan first for non-trivial work
For any task beyond a small local edit:
- summarize the task
- identify the files that will change
- describe the intended approach
- note risks or open questions
- then implement

Do not jump straight into broad multi-file edits without a plan.

### 6.2 Work in thin vertical slices
Prefer one complete, testable slice over scattered partial implementation across many subsystems.

Good examples:
- open project → edit file → save
- create run manifest → launch runner → capture stdout
- show traceback → write run log → expose log path

Avoid “build the whole app at once” behavior.

### 6.3 Keep changes scoped
Touch the minimum number of files needed for the task.

### 6.4 Avoid speculative abstraction
Do not add plugin systems, generic frameworks, or future-proofing layers unless the current task clearly requires them.

### 6.5 Preserve user-visible behavior unless the task explicitly changes it
Do not silently rename concepts, move files, or alter workflow assumptions without updating docs.

---

## 7. Editing Rules

### 7.1 Prefer small modules
New code should be placed in the subsystem that owns it rather than in oversized utility files.

### 7.2 Avoid hidden side effects at import time
Modules should be safe to import. Heavy work belongs in explicit functions or boot paths.

### 7.3 Keep bootstrapping deterministic
Startup code must normalize:
- app root
- project root
- working directory
- log destination
- `sys.path` behavior

Do not rely on accidental current working directory behavior.

### 7.4 Make errors actionable
When surfacing failures:
- preserve traceback
- preserve logs
- provide clear messages
- keep the editor alive when possible

### 7.5 Comment only where helpful
Do not add obvious comments. Add comments where they explain:
- ChoreBoy-specific constraints
- AppRun-specific behavior
- editor/runner contracts
- non-obvious safety decisions

---

## 8. Validation Rules

A task is not complete just because code was written.

Before declaring work done, validate as much as the task allows.

### 8.1 Minimum validation expectation
At minimum:
- confirm imports are coherent
- confirm edited files are internally consistent
- confirm obvious references and paths line up
- check for broken architecture assumptions

### 8.2 If the task affects execution flow
Validate the relevant run path, such as:
- run manifest creation
- runner launch
- stdout/stderr capture
- traceback handling
- stop/terminate behavior
- log file writing

### 8.3 If the task affects project structure or persistence
Validate:
- project loading
- metadata read/write
- path handling
- recovery from missing files or partial state

### 8.4 If validation could not be completed
State clearly:
- what was validated
- what was not validated
- what remains uncertain

Do not claim success beyond what was actually checked.

---

## 9. Documentation Update Rules

Update docs when the implementation changes the contract.

### Update `docs/ARCHITECTURE.md` if you change:
- process boundaries
- module boundaries
- project layout
- persistence strategy
- runner contract
- logging/error model
- template model

### Update `docs/PRD.md` if you change:
- user-facing goals
- scope
- workflows
- major product behavior

### Update `docs/ACCEPTANCE_TESTS.md` if you change:
- what counts as MVP completion
- validation steps
- expected behaviors

### Update `docs/TASKS.md` if you:
- complete a task
- split a task
- discover a new implementation dependency
- change recommended sequencing

---

## 10. Preferred Task Shape

When implementing, prefer tasks shaped like this:

- one clear objective
- a small set of files
- one subsystem boundary at a time
- a clear validation step
- a short completion summary

Good:
- “Add run manifest model and JSON serialization.”
- “Implement process supervisor for runner launch and stop.”
- “Add per-run log path generation and log file creation.”

Bad:
- “Build the whole IDE.”
- “Refactor the app for future plugins.”
- “Generalize everything.”

---

## 11. Forbidden Assumptions

Do not assume any of the following unless the docs explicitly say so:

- a normal desktop Python installation
- pip availability on the target system
- GUI-capable FreeCAD export paths in console mode
- internet access
- Git availability
- package managers
- OS-level developer tools
- unrestricted write access outside the intended app/project locations

---

## 12. Preferred Decision Biases

When multiple valid approaches exist, prefer the option that is:

1. more compatible with ChoreBoy constraints
2. easier to understand from reading the repo
3. easier for another agent to continue later
4. easier to validate
5. easier to support in the field

In practice, this usually means preferring:
- explicit manifests over implicit state
- plain JSON over custom formats
- stable file paths over discovery magic
- isolated runner processes over shared-process shortcuts
- simple, inspectable data flow over clever abstractions

---

## 13. How to Report Completed Work

When finishing a non-trivial task, summarize:

1. what changed
2. which files changed
3. how it fits the architecture
4. what was validated
5. any follow-up work or uncertainty

Keep the summary concrete.

---

## 14. First-Slice Priority

If work order is ambiguous, bias toward improving the core MVP slice:

1. open project
2. open/edit file
3. save file
4. run in separate runner process
5. capture stdout/stderr
6. show traceback
7. write per-run log
8. stop run safely

That path matters more than secondary enhancements.

---

## 15. When to Stop and Ask

Stop and ask for clarification if:
- the task conflicts with `docs/PRD.md`
- the task conflicts with `docs/ARCHITECTURE.md`
- the change would break the editor/runner boundary
- the change requires a new dependency model
- the task implies a product decision that is not documented

Do not silently make major product or architecture decisions that belong in the docs.

---

## 16. Bottom Line

Build this project as a **supportable, filesystem-first, AppRun-based Qt editor with a separate runner process**.

Keep implementation:
- explicit
- modular
- testable
- thin-sliced
- aligned with the docs

When in doubt, preserve the architecture and reduce complexity.

---

## Cursor Cloud specific instructions

### FreeCAD AppRun runtime

FreeCAD 1.0.2 is extracted to `/opt/freecad/` so that `/opt/freecad/AppRun` is available — matching the ChoreBoy production environment. This provides PySide2 5.15.15, FreeCAD 1.0.2 headless backend, and **Python 3.11** runtime. Both the application and the test suite run through AppRun.

**Note on Python version parity:** ChoreBoy production ships **Python 3.9.2**, while the Cursor Cloud FreeCAD AppRun ships **Python 3.11**. All code must remain compatible with **Python 3.9** (the production floor). The `.cursor/rules/python39_compatibility.mdc` rule enforces this. Vendored native `.so` files must be compiled for **cpython-311** to match the Cloud environment.

**Note on `os.memfd_create`:** The conda-forge Python 3.11 build in this AppRun does **not** expose `os.memfd_create`. The `app/treesitter/loader.py` already has a ctypes fallback that calls `libc.memfd_create` directly, which works.

### Environment setup (required before running tests or GUI)

1. **Install pytest into the FreeCAD Python** (not pre-installed):
```bash
/opt/freecad/usr/bin/python -c "
import subprocess, sys, os
result = subprocess.run(
    [sys.executable, '-m', 'pip', 'install', 'pytest>=9.0'],
    env={**os.environ, 'PYTHONHOME': '/opt/freecad/usr'}
)
raise SystemExit(result.returncode)
"
```

2. **Populate vendored dependencies** (not tracked in git):
```bash
# Download cp311 wheels (matching FreeCAD's Python 3.11)
pip download tree-sitter==0.21.3 --python-version 311 --abi cp311 \
  --platform manylinux_2_17_x86_64 --only-binary :all: --no-deps -d /tmp/wheels/
pip download tree-sitter-languages==1.10.2 --python-version 311 --abi cp311 \
  --platform manylinux_2_17_x86_64 --only-binary :all: --no-deps -d /tmp/wheels/

# Extract into vendor/ (pip --target won't install cross-platform wheels)
cd /tmp && mkdir -p extract_ts extract_tsl
cd /tmp/extract_ts && unzip -o /tmp/wheels/tree_sitter-0.21.3-cp311-*.whl
cd /tmp/extract_tsl && unzip -o /tmp/wheels/tree_sitter_languages-1.10.2-cp311-*.whl
cp -r /tmp/extract_ts/tree_sitter /workspace/vendor/tree_sitter
cp -r /tmp/extract_tsl/tree_sitter_languages /workspace/vendor/tree_sitter_languages

# Install pure-Python pyflakes
pip install pyflakes==3.4.0 --target=/workspace/vendor/ --no-deps
```

### Running tests

Tests run inside the FreeCAD AppRun Python with real PySide2 — no shims, no separate venv:
```
python3 run_tests.py -v
```
`run_tests.py` invokes pytest through `/opt/freecad/AppRun` and sets `QT_QPA_PLATFORM=offscreen` by default. Override the AppRun path with `CBCS_APPRUN` if needed. See `pyproject.toml` for marker definitions (`unit`, `integration`, `runtime_parity`, `manual_acceptance`).

### Launching the editor GUI

Use the dev launcher which boots `run_editor.py` through FreeCAD AppRun (ChoreBoy parity):
```
DISPLAY=:1 python3 dev_launch_editor.py --foreground
```
Status bar should show **"Startup: Runtime ready (6/6 checks)"** with all capabilities passing. Use `--dry-run` to inspect the generated command without launching.
