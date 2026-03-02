# ChoreBoy Discovery: Running Standalone Qt (PySide2) Apps via FreeCAD AppRun

**Date discovered:** 2026-02-28  
**Environment:** Classic ChoreBoy V6 (VM), LibrePy Editor 1.9.2  
**Primary breakthrough:** We can launch real standalone Qt windows (PySide2) on ChoreBoy by executing Python inside FreeCAD’s packaged runtime using `/opt/freecad/AppRun -c ...`.

---

## 1. Executive Summary

We discovered a reliable way to run **full Qt (PySide2) applications** on the ChoreBoy system without depending on LibreOffice UI widgets (PyBrex) and without running the full FreeCAD GUI.

The approach is:

1. Use LibrePy (inside LibreOffice) as a **launcher** (or any Python context that can call subprocess).
2. Spawn FreeCAD’s `AppRun` in console mode:
   - `'/opt/freecad/AppRun', '-c', 'exec(open(".../main.py").read())'`
3. The executed script can:
   - `import PySide2` and create a `QApplication()`
   - show windows and run a Qt event loop
   - log to disk
   - `import FreeCAD` for headless backend work (geometry/document creation)
4. The launched app can be detached so it survives LibreOffice closing:
   - `subprocess.Popen(..., start_new_session=True)`

This effectively creates a new “application platform” for ChoreBoy:
- **Qt UI frontend**
- **FreeCAD headless backend engine**
- **SQLite local persistence**
- Optional: **Postgres connectivity** via vendored pure-Python driver (pg8000), if needed.

---

## 2. Why This Matters

### LibreOffice / LibrePy limitations (current pain)
- PyBrex and LibreOffice UI tooling have limitations: awkward layouting, limited docs, and debugging is painful.
- LibrePy is powerful for scripting, but not ideal for building rich native UIs.

### Qt via FreeCAD solves the biggest issues
- Qt is a mature UI framework with enormous documentation and patterns.
- PySide2 provides a professional UI stack (menus, dialogs, layouts, docking, etc.).
- FreeCAD already ships PySide2 and its own Python runtime; we reuse what exists on the machine.

---

## 3. Core Mechanism (How It Works)

### Key runtime: FreeCAD embedded Python
ChoreBoy includes FreeCAD, which ships:
- `/opt/freecad/AppRun`
- embedded Python runtime
- PySide2
- FreeCAD libraries accessible via `import FreeCAD`

We run Python code inside that runtime by calling:

```python
subprocess.Popen(
    ['/opt/freecad/AppRun', '-c', 'exec(open("/home/default/myapp/main.py").read())'],
    start_new_session=True
)
```

### Why `start_new_session=True` matters

This detaches the spawned process from LibreOffice/LibrePy so the Qt app can remain alive even if LibreOffice closes.

---

## 4. Confirmed Capability Matrix

These probes were run and verified on ChoreBoy:

### ✅ Python Runtime / Paths

* `sys.version`: **3.9.2**
* `sys.executable`: `/opt/freecad/usr/bin/FreeCAD`
* `sys.path` includes `/home/default/myapp` and FreeCAD Mod directories

### ✅ Filesystem Write

* Can write to `/home/default/myapp/logs/*`
* Logging to `logs/app.log` works

### ✅ SQLite

* Can create and write SQLite database:

  * `/home/default/myapp/logs/probe.sqlite3`
* Insert/select worked

### ✅ Subprocess

* Can run shell commands:

  * `echo`, `uname`, etc.

### ✅ Qt UI Designer Loading

* `PySide2.QtUiTools` is available
* Confirmed working with a real `.ui` file (`myapp/ui/probe.ui`)
* Proven workflow:

  * design `.ui` files on a normal machine
  * copy to ChoreBoy
  * load at runtime on ChoreBoy via `QtUiTools.QUiLoader`

### ✅ FreeCAD Headless Backend

* `import FreeCAD` works in the launched script
* Can create a document and save:

  * `/home/default/myapp/logs/probe_box.FCStd`

### ✅ FreeCAD Export (Partial)

* STL export worked:

  * `/home/default/myapp/logs/probe_box.stl`
* STEP and SVG export attempts failed because they relied on GUI-only modules:

  * Error: `Cannot load Gui module in console application.`

**Implication:** Some export formats require headless-safe export paths (e.g., Part module export) or running FreeCAD with GUI.

### ✅ Postgres Reachability (Network)

* `localhost:5432` TCP connectivity works (port reachable)

### ❌ Postgres Python Drivers (Not Present)

* `psycopg2` / `psycopg` not installed in FreeCAD runtime
* `psql` not available on PATH

**Implication:** Direct Postgres requires vendoring a pure-Python client (recommended: pg8000) or implementing a bridge.

---

## 5. Postgres Strategy (Deep Dive)

### What we know

* Network connection to `localhost:5432` works
* No default Postgres Python drivers exist inside the FreeCAD AppRun runtime:

  * `psycopg2` / `psycopg` not installed
  * `psql` not available on PATH

### Decision: **Use vendored `pg8000` (pure Python) for Postgres**

We will standardize on **`pg8000` vendored into `myapp/vendor/`** as the Postgres connector for ChoreBoy Qt apps running via FreeCAD AppRun.

**Why this is the best fit for ChoreBoy:**

* **Works in the locked FreeCAD AppRun runtime** (no system installs required)
* **Pure Python** (no compiled wheels / no libpq dependency)
* **Simple deployment**: ship as part of the app folder
* **Good performance** for typical CRUD workloads, especially when we reuse connections and batch work

### Benchmark result (confirmed)

We ran an in-app micro-benchmark using `pg8000`:

* Queries: **2000** (`select 1` loop in a single transaction)
* Total time: **0.1223 seconds**
* Throughput: **~16,347 queries/sec**
* Avg time/query: **~0.061 ms**

**Interpretation:** Driver overhead is very low in this environment; `pg8000` is not a bottleneck for normal application workloads.

### How to vendor `pg8000`

On a normal Linux machine:

```bash
mkdir -p myapp/vendor
python3 -m pip install --target myapp/vendor pg8000
```

Copy the entire `myapp/` folder to ChoreBoy.

In code:

```python
import sys
sys.path.insert(0, "/home/default/myapp/vendor")

import pg8000.native

conn = pg8000.native.Connection(
    user="postgres",
    password="true",
    host="localhost",
    database="postgres",
    port=5432,
)

print(conn.run("select version()"))
```

### Operational notes (for max performance)

* Prefer **one connection per worker/thread** (or a small pool) rather than reconnecting frequently.
* Wrap multiple statements in a **transaction** to reduce round trips.
* Batch inserts/updates when possible.

### Fallback options (only if required later)

1. **SQLite locally + periodic sync/export**
2. **Local bridge service** (HTTP/IPC) that uses a faster native driver outside AppRun (e.g., psycopg3/asyncpg)
3. If `psql` becomes available later, call it via subprocess

## 6. FreeCAD Export Strategy (Headless vs GUI)

### Current finding

GUI-based exporters (ImportGui) fail under console mode:

* “Cannot load Gui module in console application.”

### Next tests

* Use headless export paths:

  * Part module: `shape.exportStep(...)` (candidate)
* If necessary, run a FreeCAD GUI session for export-only actions

---

## 7. Recommended Project Template

Standard folder:

```
myapp/
  main.py
  launcher.py
  vendor/          # optional (pg8000 etc)
  logs/
  app/
    __init__.py
    backend.py
    main_window.py
```

Key ideas:

* `launcher.py`: spawns AppRun detached
* `main.py`: bootstraps sys.path, logging, crash window, launches Qt
* `backend.py`: contains all probes and backend actions
* `main_window.py`: Qt UI that triggers probes and displays output

---

## 8. Minimal Launcher Snippet (LibrePy Console)

```python
import subprocess
subprocess.Popen(
    ['/opt/freecad/AppRun', '-c', 'exec(open("/home/default/myapp/main.py").read())'],
    start_new_session=True
)
```

---

## 9. Debugging Model

Because debugging tools are limited, we use:

1. A log file in `logs/app.log`
2. A crash popup that shows full traceback (Qt window)

This avoids “silent failures” and makes iterative development realistic.

---

## 10. Next Steps Checklist (Priority Order)

### FreeCAD Exports

* [ ] Attempt STEP export without GUI dependencies (Part-based)
* [ ] Decide if GUI mode is required for certain exporters

### UI Builder Workflow

* [x] Create a `.ui` file on dev machine (Qt Designer)
* [x] Copy to ChoreBoy and load using `QtUiTools.QUiLoader`

### Threading / Responsiveness

* [ ] Add a long-running FreeCAD operation and ensure UI stays responsive (QThread)

### Choose first real app

Once Postgres + export limits are known, select a first production target:

* Qt tool + SQLite config
* FreeCAD-backed generator tool (geometry + STL output)
* Mini IDE / Runner for ChoreBoy Qt scripts

---

## 11. Bottom Line

We have confirmed a new capability on ChoreBoy:

> **We can build real standalone Qt apps in Python, launched via FreeCAD AppRun, with FreeCAD usable as a headless backend engine.**

This is a major upgrade over LibreOffice-only UI approaches and likely becomes the preferred path for complex apps on ChoreBoy going forward.

```