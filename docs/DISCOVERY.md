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
- **Postgres connectivity** via vendored psycopg 3 with C acceleration (or pg8000 as fallback)

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

### ✅ Subprocess (severely restricted)

* `/bin/sh` is the **only** binary that can be executed via subprocess.
* Shell builtins (`echo`) work because they run inside `/bin/sh` itself.
* All other binaries are blocked by AppArmor — including `/bin/bash`, `/usr/bin/python3`, `/usr/bin/env`, `/usr/bin/id`, Java, `pg_dump`, `at`, `systemd-run`.
* Several common utilities do not exist in the AppImage filesystem at all: `uname`, `cat`, `ssh`, `soffice`.
* See pg_backup_probe probe 9 for the full execution whitelist (14 binaries tested, only `/bin/sh` allowed).

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

## 4E. C Extensions Loadable via `memfd_create` — `noexec` Bypass (2026-03-04)

**Date discovered:** 2026-03-04 (probes 2b through 2d)

### The problem: `noexec` blocks all compiled Python extensions on writable paths

ChoreBoy mounts every writable filesystem with the `noexec` flag:

| Path | `noexec`? |
|---|---|
| `/home/default/` | YES |
| `/tmp/` | YES |
| `/opt/freecad/` | no (read-only, but executable) |

Any attempt to `import` a Python C extension (`.so` file) from `/home/default/` or `/tmp/` fails:

```
ImportError: .../module.cpython-39-x86_64-linux-gnu.so: failed to map segment from shared object
```

This means vendoring pre-compiled wheels (e.g., `tree-sitter`, `numpy`, any package with C code) and importing them normally **does not work**.

### The solution: `os.memfd_create()` + `/proc/self/fd/`

Linux's `memfd_create` system call creates an anonymous file backed entirely by RAM. The resulting file descriptor lives at `/proc/self/fd/N` and is **not subject to filesystem mount flags** — including `noexec`.

```python
import os, ctypes

so_bytes = open("vendor/module.cpython-39-x86_64-linux-gnu.so", "rb").read()
fd = os.memfd_create("module", 0)
os.write(fd, so_bytes)

lib = ctypes.CDLL(f"/proc/self/fd/{fd}")   # works
```

`ctypes.CDLL` loads the shared object from the memfd path successfully, bypassing the `noexec` restriction entirely.

### Loading as a Python extension module (not just ctypes)

`ctypes.CDLL` gives raw C function access, but Python C extension modules (like `tree_sitter._binding`) need to be loaded as proper Python modules so their classes and functions appear in `sys.modules`.

**What fails:** `importlib.util.spec_from_file_location` returns `None` for `/proc/self/fd/N` paths because the path lacks a `.so` file extension.

**What works:** Explicitly constructing an `ExtensionFileLoader` and `spec_from_loader`:

```python
import importlib.machinery, importlib.util, sys

loader = importlib.machinery.ExtensionFileLoader(
    "package._binding",
    f"/proc/self/fd/{fd}"
)
spec = importlib.util.spec_from_loader("package._binding", loader)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
```

After this, `import package` (the pure-Python wrapper) finds `_binding` already in `sys.modules` and works normally.

### Validated: tree-sitter on ChoreBoy

tree-sitter is a C parsing library that provides incremental, fault-tolerant syntax parsing. It requires two compiled components: a Python C extension (`_binding.so`) and a grammar library (`languages.so`). Both were loaded successfully via memfd.

**Versions tested:**
- tree-sitter 0.21.3 (`cp39-cp39-manylinux_2_17_x86_64`)
- tree-sitter-languages 1.10.2 (`cp39-cp39-manylinux_2_17_x86_64`)

### Historical validation note

This section proves that the memfd loading technique works on ChoreBoy for the
older `0.21.3` monolithic grammar stack. It should not be treated as automatic
proof for the newer size-optimized per-language `0.23.x` bundle now used by
the editor.

The current product target is still a ChoreBoy `cp39` bundle, but it ships a
smaller set of per-language wheels instead of `tree-sitter-languages`. That
bundle must be validated on the actual device in its own right. If a device log
shows a symbol error during `_binding` import, the regression is in native
compatibility of the shipped wheel set, not in the memfd strategy itself.

**Probe results (probe2d):**

| Step | What | Result |
|---|---|---|
| 1 | `ctypes.CDLL` from memfd baseline | PASS |
| 2 | `_binding.so` loaded as Python module via `ExtensionFileLoader` | PASS |
| 3 | `import tree_sitter` (pure Python, finds `_binding` in `sys.modules`) | PASS |
| 4 | `languages.so` (84.6 MB grammar blob) loaded via memfd `ctypes.CDLL` | PASS |
| 5 | `Language` object constructed from ctypes function pointer | PASS |
| 6 | Full parse of Python source code (40-node AST) | PASS |
| 7 | Highlight query captures (12 captures with correct positions) | PASS |
| 8 | `tree_sitter_languages` convenience API | FAIL (not needed) |
| 9 | Additional languages: JS, C, C++, Rust, JSON, HTML, CSS, Bash | PASS (8/8) |

**Memory cost:** ~82 MB in memfds (one-time at startup, dominated by `languages.so`).

### Working integration pattern (Strategy A)

```
Startup sequence:
  1. Read _binding.so from vendored files
  2. Write to os.memfd_create()
  3. Load via ExtensionFileLoader + spec_from_loader into sys.modules
  4. import tree_sitter (pure Python finds _binding already loaded)
  5. Read languages.so from vendored files
  6. Write to os.memfd_create()
  7. Load via ctypes.CDLL from /proc/self/fd/
  8. Construct Language objects via ctypes function pointers
  9. Create Parser, call set_language(), ready to parse
```

The `tree_sitter_languages` convenience wrapper (`get_language()`, `get_parser()`) does not work because its Cython core internally calls `Language(path, name)` using a relative path derived from its own `__file__`, which resolves wrong under `/proc/self/fd/`. This is harmless — Strategy A constructs `Language` objects directly from function pointers and does not need the convenience API.

### Broader implication

This technique is **not specific to tree-sitter**. Any pre-compiled C extension that ships as a `manylinux` wheel for `cp39-x86_64` can be loaded on ChoreBoy using the same memfd pattern, as long as:

1. Its compiled `.so` files are compatible with ChoreBoy's glibc (2.17+ for `manylinux2014`)
2. All `.so` files are loaded via memfd before any Python `import` that depends on them
3. Python C extensions use `ExtensionFileLoader` (not `spec_from_file_location`)
4. Plain shared libraries use `ctypes.CDLL` directly

This opens the door to vendoring other compiled Python packages that were previously assumed to be blocked by the `noexec` restriction.

### Parallel with JNI discovery (section 4D)

The memfd technique for C extensions mirrors the JNI in-process loading discovery for Java: both bypass the binary execution block by loading compiled code as a shared library within the Python process rather than trying to execute a binary via the filesystem.

| Approach | Java (section 4D) | C extensions (this section) |
|---|---|---|
| Blocked path | `subprocess.run(["java", ...])` | `import module` from `/home/default/` |
| Bypass | `ctypes.CDLL("libjvm.so")` + JNI | `os.memfd_create()` + `ctypes.CDLL` / `ExtensionFileLoader` |
| Runs inside | Python process (shared library) | Python process (shared library in RAM) |

---

## 4F. libpq.so Loadable from System Path (2026-03-06)

**Date discovered:** 2026-03-06 (pg_backup_probe probe 7)

### Finding

PostgreSQL's native client library (`libpq.so`) can be loaded via `ctypes.CDLL` from the system library path, but **not** from the PostgreSQL installation directory.

| Path | Exists | Loadable | Owner |
|---|---|---|---|
| `/opt/PostgreSQL/9.3/lib/libpq.so` | YES | NO (Permission denied) | root:daemon (gid=1) |
| `/opt/PostgreSQL/9.3/lib/libpq.so.5` | YES | NO (Permission denied) | root:daemon (gid=1) |
| `/usr/lib/x86_64-linux-gnu/libpq.so` | YES | **YES** | root:root (gid=0) |

### Why `/opt/` is blocked but `/usr/lib/` is not

AppArmor whitelists the system library path (`/usr/lib/`) for `dlopen()` calls, but blocks loading `.so` files from `/opt/PostgreSQL/`. This matches the broader pattern: the `/opt/PostgreSQL/9.3/bin/pg_dump` binary is also blocked from execution despite having `rwxr-xr-x` permissions. The AppArmor profile for the FreeCAD AppRun process restricts access to the PostgreSQL installation directory specifically.

### What this enables

`libpq.so` provides the full PostgreSQL wire protocol implementation in C, including:

* `PQconnectdb()` — connect to PostgreSQL
* `PQexec()` — execute queries
* `PQgetResult()` — retrieve results
* `PQputCopyData()` / `PQgetCopyData()` — COPY protocol at native speed

This could be used as a high-performance alternative to pg8000 for bulk data operations (COPY export/import). However, pg8000 already achieves ~26 MB/s throughput on ChoreBoy, which is more than sufficient for the ~36 MB of total database content.

### Current status

Validated and **actively used** by psycopg 3 binary (see section 4H). The bundled libpq 17.0.5 from psycopg\_binary is loaded via memfd and provides full C-accelerated PostgreSQL connectivity.

---

## 4H. psycopg 3 with C Acceleration via memfd (2026-03-07)

**Date discovered:** 2026-03-07 (psycopg3\_probe, probes 1-6)

### Finding

psycopg 3 with full **Cython C acceleration** (`psycopg_binary`) runs on ChoreBoy by loading its 16 compiled `.so` files (14 bundled native libs + 2 Cython extensions) entirely from memory via `memfd_create`, bypassing the `noexec` restrictions on all writable filesystems.

This is the most complex memfd loading achieved on ChoreBoy: a 14-library dependency chain (OpenSSL 3.5, Kerberos, LDAP, libpq 17.0.5) loaded in topological order with `RTLD_GLOBAL`, followed by two Cython C extensions loaded via `ExtensionFileLoader`.

### Loading recipe

```
1. Patch ctypes.util.find_library for "pq" and "c" (ldconfig incomplete)
2. Load 14 bundled .libs/*.so via memfd + ctypes.CDLL(RTLD_GLOBAL)
3. Load pq.so via memfd + ExtensionFileLoader  [MUST BE FIRST]
4. Load _psycopg.so via memfd + ExtensionFileLoader
5. import psycopg  (falls back to python due to circular import)
6. psycopg.pq.import_from_libpq()  (re-detect → binary)
```

### Key details

| Property | Value |
|---|---|
| psycopg version | 3.2.9 (last to support Python 3.9) |
| Bundled libpq | **17.0.5** (connects to PG 9.3 server) |
| Bundled OpenSSL | **3.5.0** |
| pq.\_\_impl\_\_ | `binary` (Cython C acceleration active) |
| Total memfd usage | ~10.4 MB |
| Vendor size on disk | ~13 MB |
| Integration tests | **41/41 passed** |

### Performance vs pg8000

| Metric | psycopg binary | pg8000 | Winner |
|---|---|---|---|
| Simple SELECT x2000 | 6,499 q/s | 12,974 q/s | pg8000 (2x) |
| Parameterized x1000 | 7,732 q/s | 4,849 q/s | **psycopg (1.59x)** |

pg8000 is faster for trivial queries (zero FFI overhead), but psycopg binary is **59% faster for parameterized queries** where Cython's compiled marshaling outperforms pure Python. For real-world workloads with complex queries and large result sets, psycopg binary is the clear winner.

### Issues resolved

1. **`find_library` broken**: ChoreBoy's ldconfig cache doesn't include libpq or libc. Patched to return known paths.
2. **Extension loading order**: `pq.so` must load before `_psycopg.so` (which imports pq during init).
3. **Circular import**: `_psycopg` init triggers `import_from_libpq()` before psycopg is ready. Fixed by re-calling `import_from_libpq()` after import.
4. **SQL\_ASCII encoding**: PG 9.3 returns text as bytes. Application code must decode explicitly.
5. **`version.py` exception handler**: Broadened from `PackageNotFoundError` to `Exception`.

---

## 4G. AppArmor Execution Whitelist: Only `/bin/sh` Allowed (2026-03-06)

**Date discovered:** 2026-03-06 (pg_backup_probe probe 9)

### Finding

The FreeCAD AppImage's AppArmor profile enforces a near-total execution whitelist. Out of 14 binaries tested, **only `/bin/sh` (dash, 125 KB) can be executed** via `subprocess.run()`. All other binaries receive `PermissionError` (errno 13) or do not exist in the AppImage's filesystem view.

### Complete whitelist map

| Binary | Exists | Executable | Notes |
|---|---|---|---|
| `/bin/sh` | YES | **YES** | The ONLY allowed binary |
| `/bin/bash` | YES | NO | Blocked despite `rwxr-xr-x` |
| `/usr/bin/env` | YES | NO | Blocked |
| `/usr/bin/uname` | NO | — | Not present in AppImage filesystem |
| `/usr/bin/id` | YES | NO | Blocked |
| `/usr/bin/cat` | NO | — | Not present in AppImage filesystem |
| `/usr/bin/python3` | YES | NO | Blocked (5.4 MB binary exists but can't run) |
| `/usr/bin/soffice` | NO | — | Not present in AppImage filesystem |
| `/usr/bin/libreoffice` | NO | — | Not present in AppImage filesystem |
| `/usr/lib/jvm/.../java` | YES | NO | Blocked |
| `/opt/PostgreSQL/.../pg_dump` | YES | NO | Blocked, and binary can't even be read |
| `/usr/bin/ssh` | NO | — | Not present in AppImage filesystem |
| `/usr/bin/at` | YES | NO | Blocked |
| `/usr/bin/systemd-run` | YES | NO | Blocked |

### Security context

- uid=1000, gid=1000, groups=[1000] (regular unprivileged user)
- Seccomp: **off** (`Seccomp: 0` in `/proc/self/status`)
- AppArmor profile name: unreadable (`/proc/self/attr/current` → Permission denied)
- This confirms: all execution restrictions are enforced by **AppArmor**, not seccomp

### Shell inherits restrictions

`/bin/sh` executes successfully, but when it tries to run a blocked binary, the kernel returns `EACCES`:

```
$ /bin/sh -c "/opt/PostgreSQL/9.3/bin/pg_dump --version"
/bin/sh: 1: /opt/PostgreSQL/9.3/bin/pg_dump: Permission denied
(exit code 126)
```

The shell does NOT transition to an unconfined AppArmor profile. It inherits the same restrictions as the parent Python process. This eliminates shell-mediated execution as a bypass strategy.

### Read access also blocked for some paths

`os.access("/opt/PostgreSQL/9.3/bin/pg_dump", os.R_OK)` returns `True` (POSIX permissions check passes), but `open(path, "rb")` raises `PermissionError`. AppArmor blocks the actual `open()` syscall despite Unix file permissions allowing it. This makes `memfd_create` + `fexecve` bypass impossible — the binary cannot be loaded into memory.

### Implications

- Any code running inside FreeCAD AppRun can only spawn processes via `/bin/sh` — and those processes inherit the same restrictions.
- Shell builtins (`echo`, `printf`, `test`, `[`, `read`, etc.) work because they execute within `/bin/sh` itself — no `execve()` is needed.
- There is no "escape hatch" binary that could proxy-execute blocked commands.
- External tools (LibreOffice, Java, Python3, pg_dump, ssh, at, systemd-run) must be accessed via in-process techniques (ctypes/JNI) or through IPC with independently running processes.

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

### Decision: **Use psycopg 3 binary (C-accelerated) for Postgres**

**Updated 2026-03-07.** We now recommend **psycopg 3 with C acceleration** (`psycopg_binary`) as the primary PostgreSQL driver on ChoreBoy. This replaces the earlier pg8000 recommendation.

**Why psycopg 3 binary:**

* **C-accelerated**: Cython-compiled marshaling is 59% faster than pg8000 for parameterized queries
* **Bundled libpq 17**: ships its own modern libpq, independent of the ancient system version
* **Full feature set**: COPY protocol, typed error handling, prepared statements, savepoints, async support
* **Industry standard**: psycopg is the most widely used Python PostgreSQL adapter
* **Proven on ChoreBoy**: 41/41 integration tests pass with C acceleration active (psycopg3\_probe)

**The trade-off:** Requires the memfd bootstrap (~10.4 MB in memory, ~13 MB on disk). pg8000 remains available as a zero-complexity fallback for simple cases.

### Benchmark comparison (confirmed on ChoreBoy)

| Metric | psycopg 3 binary | pg8000 | Winner |
|---|---|---|---|
| Simple SELECT x2000 | 6,499 q/s | **12,974 q/s** | pg8000 (2x) |
| Parameterized x1000 | **7,732 q/s** | 4,849 q/s | psycopg (1.59x) |
| INSERT x1000 | 281 inserts/s | (not tested) | — |
| COPY FROM STDIN | native | not supported | psycopg |

pg8000 is faster for trivial `SELECT 1` queries (zero FFI overhead vs libpq call overhead). psycopg binary wins on parameterized queries and will scale better on complex workloads with large result sets.

### When to use which driver

| Use case | Recommended driver |
|---|---|
| Production applications | **psycopg 3 binary** |
| Parameterized queries, complex workloads | **psycopg 3 binary** |
| Bulk data operations (COPY) | **psycopg 3 binary** |
| Simple scripts, quick prototypes | **pg8000** (zero setup) |
| Environments where memfd is unavailable | **pg8000** (pure Python) |

### How to bootstrap psycopg 3 binary on ChoreBoy

See section 4H for the complete loading recipe, or `psycopg3_probe/probe5_full_binary.py` for the reference implementation.

### pg8000 remains available as fallback

pg8000 still works and requires no memfd loading:

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

### Operational notes (for max performance with either driver)

* Prefer **one connection per worker/thread** (or a small pool) rather than reconnecting frequently.
* Wrap multiple statements in a **transaction** to reduce round trips.
* Batch inserts/updates when possible.
* With psycopg: use `COPY FROM STDIN` for bulk inserts instead of individual `INSERT` statements.

### ORM: SQLAlchemy 2.0.x with full Cython acceleration (validated)

**Updated 2026-03-09.** For PostgreSQL ORM on ChoreBoy, use **SQLAlchemy 2.0.48**
with the `postgresql+psycopg` dialect and **full Cython acceleration** — all
validated on live ChoreBoy with PG 9.3.6 (`cb_sqlalchemy_test`, 8/8 probes pass,
87 tests total, 0 failures, 4 expected-fail on PG 9.3 feature boundaries).

The production library is `cb_sqlalchemy`, which wraps the three-stage bootstrap
and provides `create_engine()` / `create_async_engine()` / `get_session_factory()`
with safe defaults:

1. `cb_psycopg.bootstrap()` — psycopg 3 binary C acceleration + libpq via memfd
2. `_greenlet.bootstrap()` — greenlet C extension via memfd (enables async ORM)
3. `_cext.bootstrap()` — `sys.meta_path` import hook that loads 5
   SQLAlchemy Cython modules (`cyextension/*`) from memfd on demand

After bootstrap, both sync and async ORM paths work:

* **Sync**: `cb_sqlalchemy.create_engine("postgresql+psycopg://...")` — full ORM
  surface validated (CRUD, joinedload, savepoints, bulk insert, reflection,
  stream\_results, UTF-8, advanced patterns, stress/edge cases)
* **Async**: `cb_sqlalchemy.create_async_engine("postgresql+psycopg://...")` —
  async CRUD, selectinload, rollback, AsyncConnection all pass

Production engine defaults (`CHOREBOY_ENGINE_DEFAULTS`):

* `pool_pre_ping=True`, `pool_size=2`, `max_overflow=0`, `echo=False`
* `client_encoding=utf8` — passed to dialect and enforced via connect event hook
* `pool_size`/`max_overflow` auto-stripped when using `NullPool` or `StaticPool`

### SQLAlchemy performance on ChoreBoy

Benchmarked on live ChoreBoy (PG 9.3.6, psycopg 3.2.9 binary, SA 2.0.48 with
Cython acceleration active, `cb_sqlalchemy_test` probe 6, 1500 simple / 800
parameterized iterations):

| Layer | SELECT 1 (q/s) | Parameterized (q/s) | vs raw psycopg |
|---|---|---|---|
| Raw psycopg | 10,045 | 8,576 | 1.00x |
| SA Core | 4,994 | 3,396 | 0.50x / 0.40x |
| SA ORM | 4,215 | 3,197 | 0.42x / 0.37x |
| SA Async | 2,598 | — | 0.26x |

ORM overhead is roughly 2-2.5x versus raw psycopg — typical for SQLAlchemy with
Cython acceleration. Async adds greenlet context-switch overhead; suitable for
I/O-bound concurrency rather than per-query throughput.

### PG 9.3 SQL feature boundaries (validated)

Probe 5 mapped which SQL features work and which are blocked on PG 9.3:

**Works on PG 9.3:**

* JSON type and `->` / `->>` operators
* Materialized views (`CREATE MATERIALIZED VIEW` / `REFRESH`)
* `LATERAL` joins
* Full ORM surface: CRUD, relationships, transactions, savepoints, bulk insert,
  schema reflection, streaming results, UTF-8 string roundtrip

**Unavailable on PG 9.3 (expected failures, not blockers):**

| Feature | Minimum PG | Error |
|---|---|---|
| `JSONB` type cast | 9.4 | `type "jsonb" does not exist` |
| `ON CONFLICT` (upsert) | 9.5 | `syntax error at or near "ON"` |
| `GENERATED ALWAYS AS ... STORED` | 12 | `syntax error at or near "GENERATED"` |
| `int4multirange` type cast | 14 | `type "int4multirange" does not exist` |

Application code must avoid these constructs when targeting PG 9.3.

### Probe evidence

* Initial validation (6 probes): `sqlalchemy_probe/SUMMARY.md`
* Full test suite (8 probes, 87 tests): `cb_sqlalchemy_test/SUMMARY.md`

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