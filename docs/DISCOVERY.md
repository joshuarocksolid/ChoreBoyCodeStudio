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
   - `'/opt/freecad/AppRun', '-c', 'import os,runpy,sys; ...; runpy.run_path(".../main.py", run_name="__main__")'`
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

## 1A. Hard Constraint: Python 3.9

The FreeCAD AppRun runtime on ChoreBoy ships **Python 3.9.2**. This is the only Python available to applications launched through AppRun.

**All application code, vendored libraries, and test code must be compatible with Python 3.9.**

Key implications:

- Do not use `match`/`case` (3.10+), `ExceptionGroup` (3.11+), `type` aliases (3.12+), or other post-3.9 features.
- Built-in generic annotations (`list[int]`, `dict[str, int]`) are available (PEP 585 landed in 3.9).
- Before vendoring a dependency, verify it supports Python 3.9.
- See `.cursor/rules/python39_compatibility.mdc` for the full syntax reference.

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
    [
        '/opt/freecad/AppRun',
        '-c',
        "import os,runpy,sys;root='/home/default/myapp';"
        "sys.path.insert(0,root) if root not in sys.path else None;"
        "os.chdir(root);runpy.run_path('/home/default/myapp/main.py', run_name='__main__')",
    ],
    start_new_session=True
)
```

### Why `start_new_session=True` matters

This detaches the spawned process from LibreOffice/LibrePy so the Qt app can remain alive even if LibreOffice closes.

---

## 3A. New Discovery: Launching Qt Apps via `.desktop` Files (No LibrePy Launcher)

We confirmed the ChoreBoy desktop environment can launch our Qt apps directly using a `.desktop` application shortcut.

### Why this matters

- Removes the need for `launcher.py` and LibrePy as a “bootstrap”.
- Users can launch apps like any normal desktop app (icon, menu entry, etc.).
- Makes distribution/UX much cleaner (copy folder + install shortcut).

### Recommended pattern

1. Rename `main.py` to `main.py` and treat it as the single entrypoint.
2. Create a `.desktop` file whose `Exec=` runs FreeCAD’s runtime and uses deterministic bootstrap:
   - normalize `sys.path`
   - set `cwd`
   - launch with `runpy.run_path(...)`

### Example `.desktop` (MyApp)

```ini
[Desktop Entry]
Type=Application
Version=1.0
Name=MyApp
Comment=Launch MyApp (Qt via FreeCAD AppRun)
#Icon=/home/default/myapp/icon.png
Terminal=false
Categories=Utility;

Exec=/opt/freecad/AppRun -c "import os,runpy,sys;root='/home/default/myapp';sys.path.insert(0,root) if root not in sys.path else None;os.chdir(root);runpy.run_path('/home/default/myapp/main.py', run_name='__main__')"
```

### Install locations

- Per-user launcher:
  - `~/.local/share/applications/myapp.desktop`
- Desktop icon:
  - `~/Desktop/myapp.desktop`

After placing the file, ensure it is marked executable (from a terminal or file manager).

### Notes

- If the system requires “trusting” desktop shortcuts, you may need to right-click the icon and choose “Allow Launching” the first time.
- If you want the app to keep working when moved, hardcode the absolute path (recommended on ChoreBoy).

---

## 4. Confirmed Capability Matrix

These probes were run and verified on ChoreBoy:

### ✅ Python Runtime / Paths

* `sys.version`: **3.9.2** (see [section 1A](#1a-hard-constraint-python-39) — all code must target 3.9)
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

### PostgreSQL Version

* **Version: 9.3.5** (confirmed via `server_version` parameter status)
* Released September 2013, **end-of-life November 2018**
* Django 4.2 requires PostgreSQL 12+; Django 2.2 requires 9.4+
* No Django version supports both Python 3.9 and PostgreSQL 9.3
* Raw pg8000 connectivity works (probe 6 confirmed)
* Django ORM over PostgreSQL is **blocked** until PG is upgraded

**Implication:** PostgreSQL-backed Django projects cannot run on ChoreBoy
with the current PG 9.3 installation. SQLite remains the only viable Django
database backend. For direct PostgreSQL access, use raw pg8000.

### ❌ Postgres Python Drivers (Not Present)

* `psycopg2` / `psycopg` not installed in FreeCAD runtime
* `psql` not available on PATH

**Implication:** Direct Postgres requires vendoring a pure-Python client (recommended: pg8000) or implementing a bridge.

---

## 4A. Hidden Folders Are Unreliable on ChoreBoy

**Date discovered:** 2026-03-02

### Finding

Hidden (dot-prefixed) directories such as `.cbcs/` or `.choreboy_code_studio/` are **not reliably usable** on the ChoreBoy locked-down environment. Observed problems include:

* The ChoreBoy file manager does not show hidden folders by default, making project metadata invisible to users.
* Permission and ACL behavior for dot-prefixed directories may differ from normal directories under ChoreBoy's security policies.
* Directory creation can silently fail or be denied for hidden paths that would succeed for visible equivalents.

### Evidence

Commit `f6c6b96` (2026-03-02) had to introduce a three-tier fallback chain for logging (primary path, temp path, stderr) because the hidden `.choreboy_code_studio/` global state directory was not always writable or accessible.

### Recommendation

All project metadata directories, app state directories, log directories, and cache directories should use **visible (non-dot-prefixed) names**:

* Use `cbcs/` instead of `.cbcs/` for per-project metadata.
* Use `choreboy_code_studio/` instead of `.choreboy_code_studio/` for global app state.

This keeps project internals inspectable by users and avoids ChoreBoy filesystem policy issues.

### Migration status

The migration is complete in current code:

* `PROJECT_META_DIRNAME = "cbcs"`
* `GLOBAL_STATE_DIRNAME = "choreboy_code_studio_state"`

in `app/core/constants.py`, so new project metadata and app state paths are visible (non-dot-prefixed).

---

## 4B. No Direct Terminal Access on ChoreBoy

**Date discovered:** 2026-03-05

### Finding

ChoreBoy does **not** provide users with a terminal emulator, shell prompt, or any direct command-line access. There is no way to open a bash/sh session, run ad-hoc commands, or invoke scripts from a terminal.

### What users *can* do

- **ChoreBoy Code Studio runner** — hit Run (F5) to execute the project's configured entry file through the FreeCAD AppRun runtime. Output appears in the Run Log panel.
- **ChoreBoy Code Studio Python Console** — an interactive Python REPL inside the editor, also running through the FreeCAD AppRun runtime. Arbitrary Python expressions and statements can be entered here.
- **LibrePy Console** — the Python console inside LibreOffice, which can spawn subprocesses (including FreeCAD AppRun).

### Implications

- Scripts that require terminal interaction (stdin prompts, interactive debuggers, curses UIs) will not work.
- All script execution must go through one of the three channels above.
- To run an arbitrary `.py` file that is not the project's configured entry, users must either:
  1. Change the project's `default_entry` in `cbcs/project.json` to point at the desired file.
  2. Use Run > Run With Configuration (when available) to select a different entry file.
  3. Use Run > Run Current File Tests for pytest targets.
  4. Execute the file from the Python Console REPL, e.g.:
     ```python
     import runpy; runpy.run_path("/home/default/myapp/script.py", run_name="__main__")
     ```
- Any feature that assumes shell access (e.g., "run this terminal command") must be redesigned to work through the runner or REPL.

---

## 4C. Additional Launch/Runtime Findings (2026-03-03)

### Confirmed blockers

1. **Python 3.9 runtime typing crash was a real startup blocker**
   - Crash signature:
     - `TypeError: unsupported operand type(s) for |: 'types.GenericAlias' and 'NoneType'`
   - Triggered by runtime-evaluated type alias expression in `syntax_registry.py`.
   - Any runtime-evaluated typing expression using `|` must remain Python 3.9-safe.

2. **“Silent” launch failures were often logging-channel mismatch**
   - Global home log path may be unwritable.
   - Fallback logs land under `/tmp/choreboy_code_studio/logs/app.log`.
   - Debug workflow must inspect active fallback log path, not only expected home path.

3. **Capability probe can report FreeCAD false negatives**
   - Subprocess probe attempting to execute `/opt/freecad/usr/bin/FreeCAD` may fail with `Permission denied`.
   - Treat this as probe-launch constraint, not definitive proof that in-process `import FreeCAD` is impossible.

### Launch contract refinement

Preferred launch style for ChoreBoy:
- avoid `exec(open(...).read())` boot patterns;
- use explicit bootstrap (`sys.path`, `cwd`) + `runpy.run_path`;
- route failures to known log path and/or stderr-visible channel.

---

## 4D. Java and JasperReports on ChoreBoy: Full Pipeline Validated (2026-03-05)

**Date discovered:** 2026-03-05 (probes 1B through 7)

### Installed JDKs

- **JDK 14.0.1** (Oracle) at `/usr/lib/jvm/jdk-14.0.1/` — primary target
- **OpenJDK 8** at `/usr/lib/jvm/java-8-openjdk-amd64/` — also present

### Binary execution is blocked

All Java binaries (`java`, `javac`, `jlink`, etc.) fail with `PermissionError` (errno 13) when called via `subprocess.run()` or `os.execve()`. This is true even for copies made to `/tmp`. Traditional file permissions show `rwxr-xr-x`, so this is enforced by mandatory access control (AppArmor/SELinux profile) rather than Unix permissions.

```
/usr/lib/jvm/jdk-14.0.1/bin/java  →  PermissionError (code -13)
/usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java  →  PermissionError (code -13)
cp to /tmp + execute  →  PermissionError (code -13)
```

### JNI in-process loading works

`libjvm.so` at `/usr/lib/jvm/jdk-14.0.1/lib/server/libjvm.so` loads successfully via `ctypes.CDLL()`. This bypasses the binary execution block entirely because the JVM runs as a shared library within the Python process — no `execve()` call is made.

### Full pipeline probe results

Every step of the JasperReports pipeline has been validated on ChoreBoy:

| Probe | Capability | Status | Detail |
|---|---|---|---|
| 1B | `ctypes.CDLL(libjvm.so)` | PASS | Library loads cleanly |
| 2 | `JNI_CreateJavaVM` | PASS | Returns 0, JNI version 10.0 |
| 2 | Stdlib class loading | PASS | `java/lang/String`, `java/lang/System` |
| 2 | User class loading | PASS | `HelloJava` loaded from classpath |
| 2 | Method execution + stdout capture | PASS | `HelloJava.main()` output captured via fd pipe |
| 3 | Shared JNI helper (`jni_helper.py`) | PASS | JVM reuse across probes via `JNI_GetCreatedJavaVMs` |
| 4 | JDBC PostgreSQL connectivity | PASS | Driver loaded, connected, 78 tables in `classicaccounting` |
| 5 | JasperReports JRXML compile | PASS | `hello_static.jrxml` → 22,439-byte `.jasper` |
| 6 | Report fill (empty datasource) | PASS | 1 page filled |
| 6 | PDF export | PASS | 1,646 bytes |
| 6 | PNG export (2x zoom) | PASS | 52,661 bytes (1224x1584 pixels) |
| 6 | Report fill (JDBC datasource) | PASS | Connected, 0 pages (expected: static report has no query) |
| 7 | PySide2 QPrintPreviewDialog | PASS | Displayed probe 6 PNG, user closed dialog |

### JVM details

- JNI version: 10.0 (JNI_VERSION_10 = 0x000a0000)
- Java version: 14.0.1
- Vendor: Oracle Corporation
- Platform: Linux amd64

### PostgreSQL details

- Server: PostgreSQL 9.3.6
- JDBC driver: `org.postgresql.Driver` (postgresql-42.2.2.jar)
- Database: `classicaccounting` (78 public tables)
- Authentication: `postgres` / password

### JasperReports details

- JasperReports 6.7.0 (from JasperReportManager-1.2.oxt)
- Groovy 2.4.12 (expression evaluator)
- ECJ 4.4.2 (Eclipse Compiler for Java, used by JasperReports internally)
- iText 2.1.7.js6 (PDF export)
- Java 14 reflective-access warnings are emitted but do not affect functionality

### JVM signal handler caveat

The JVM installs its own `SIGSEGV` handler (used internally for safepoint polling). If the host process crashes (e.g., Qt segfault), the JVM's handler intercepts the signal first, producing a JVM-style backtrace. This is cosmetic — the JVM did not cause the crash. Any code that uses both the in-process JVM and Qt must ensure `QApplication` is initialized before using `QFont` or other font-dependent APIs.

### Implications

- The full JRXML → compile → fill → PDF/PNG → Qt print preview pipeline works on ChoreBoy
- Any Java library can be called from Python via ctypes + JNI, bypassing the binary execution block
- This matches how LibreOffice calls Java internally (loads JVM as shared library)
- One JVM per process: once created, the JVM lives until process exit; reuse via `JNI_GetCreatedJavaVMs` + `AttachCurrentThread`
- `LD_LIBRARY_PATH` must be set before loading `libjvm.so` so that its native dependencies are found

### Required `LD_LIBRARY_PATH` entries

```
/usr/lib/jvm/jdk-14.0.1/lib/server
/usr/lib/jvm/jdk-14.0.1/lib
/usr/lib/jvm/jdk-14.0.1/lib/jli
```

---

## 5. Postgres Strategy (Deep Dive)

### What we know

* Network connection to `localhost:5432` works
* **PostgreSQL version is 9.3.5** (EOL November 2018)
* No default Postgres Python drivers exist inside the FreeCAD AppRun runtime:

  * `psycopg2` / `psycopg` not installed
  * `psql` not available on PATH

### Django + PostgreSQL limitation

No Django version supports both Python 3.9 and PostgreSQL 9.3:

* Django 2.0 was the last to support PG 9.3, but it only supports Python 3.4-3.7
* Django 2.2+ supports Python 3.9 but requires PG 9.4+
* Django 4.2 (our vendored version) requires PG 12+

**Result:** Django ORM cannot be used with PostgreSQL on ChoreBoy until PG is
upgraded. Django + SQLite remains fully functional (probes 1-5 confirmed).

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
  cbcs/
    project.json
    logs/
  app/
    __init__.py
    backend.py
    main_window.py
```

> **Note:** All metadata directories use visible (non-dot-prefixed) names. Hidden folders are unreliable on ChoreBoy (see section 4A).

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
    [
        '/opt/freecad/AppRun',
        '-c',
        "import os,runpy,sys;root='/home/default/myapp';"
        "sys.path.insert(0,root) if root not in sys.path else None;"
        "os.chdir(root);runpy.run_path('/home/default/myapp/main.py', run_name='__main__')",
    ],
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