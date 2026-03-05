# jasper_bridge Library PRD

## 1. Product Goal

`jasper_bridge` is a standalone Python library that lets ChoreBoy users compile, fill, export, preview, and print JasperReports from their Python projects. It wraps the JNI-based Java integration validated in the `jasper_probe/` phase into a clean, versioned API.

Users import it like any other library:

```python
from jasper_bridge import Report, ImageParam

report = Report("invoices/invoice.jrxml")
report.fill(jdbc="jdbc:postgresql://localhost:5432/classicaccounting",
            user="postgres", password="true",
            params={
                "CompNameAddr": "Acme Corp\n123 Main St\nSpringfield, IL 62701",
                "CompLogo": ImageParam("/path/to/logo.png"),
                "TransID": 12345,
            })
report.export_pdf("output/invoice.pdf")
report.preview()
report.print()
```

The library is **standalone** -- it has no dependency on ChoreBoy Code Studio and can be imported into any Python project running under the FreeCAD AppRun runtime.

---

## 2. Constraints

These are non-negotiable and inherited from the ChoreBoy environment. Every slice must respect them.

| Constraint | Detail |
|---|---|
| Python version | 3.9.2 (FreeCAD AppRun runtime). No 3.10+ features. |
| No pip/internet | Library distributed as a folder copy, not a package. |
| Java binary execution blocked | Mandatory access control prevents running `java`/`javac` binaries. |
| JVM loaded via ctypes + JNI | `libjvm.so` from JDK 14.0.1 loaded in-process. |
| One JVM per process | Created once at first use, reused for process lifetime. |
| PySide2 5.15 available | For Qt print preview and printing integration. |
| JasperReports 6.7.0 | JARs shipped with the library in `lib/`. |
| PostgreSQL 9.3.6 via JDBC | `postgresql-42.2.2.jar` for database-driven reports. |
| JVM SIGSEGV handler | QApplication must be initialized before QFont usage when JVM is loaded. |
| No hidden folders | All library paths must use visible (non-dot-prefixed) names. |

---

## 3. Architecture Overview

```
User's Python script
  from jasper_bridge import Report
         |
         v
jasper_bridge (Python layer)
  compiler.py   filler.py   exporter.py   preview.py   printing.py
         \          |           /
          v         v          v
      jvm.py (JVM lifecycle + JNI calls)
              |
              v
      java/JasperBridge.class (single Java entry point)
              |
              v
      lib/ (JasperReports JARs + JDBC driver)
```

### Communication protocol

Python sends commands to Java via `call_java_main("JasperBridge", [json_string])`. The Java side parses the JSON command, performs the requested action, and prints a single JSON response line to stdout. The JNI fd-pipe mechanism captures this stdout output and returns it to Python.

**Request format:** `JasperBridge.main(String[] args)` where `args[0]` is a JSON command string with an `"action"` field.

**Response format (success):**

```json
{"status": "ok", "action": "compile", "jasper_path": "/path/to/output.jasper", "size": 22439}
```

**Response format (error):**

```json
{"status": "error", "action": "compile", "error_type": "net.sf.jasperreports.engine.JRException", "error_message": "...", "stacktrace": "..."}
```

---

## 4. Library Structure (Target)

```
jasper_bridge/
    __init__.py
    _version.py
    errors.py
    jvm.py
    params.py
    compiler.py
    filler.py
    exporter.py
    report.py
    preview.py
    printing.py
    connections.py          (v0.2)
    java/
        JasperBridge.java
        JasperBridge.class
    lib/
        jasperreports-6.7.0.jar
        itext-2.1.7.js6.jar
        groovy-all-2.4.12.jar
        ecj-4.4.2.jar
        postgresql-42.2.2.jar
        commons-beanutils-1.9.3.jar
        commons-collections-3.2.2.jar
        commons-digester-2.1.jar
        commons-logging-1.1.1.jar
        castor-core-1.3.3.jar
        castor-xml-1.3.3.jar
        jackson-annotations-2.9.5.jar
        jackson-core-2.9.5.jar
        jackson-databind-2.9.5.jar
    docs/
        PRD.md
        USAGE.md
        API.md              (v0.2)
        JRXML_GUIDE.md      (v0.2)
        CHANGELOG.md
```

---

## 5. Public API Reference

This section defines the complete public API so that each implementation slice has a concrete target.

### 5.1 Error hierarchy (`errors.py`)

```python
class JasperBridgeError(Exception): ...    # base for all library errors
class JVMError(JasperBridgeError): ...     # JVM failed to start or crashed
class CompileError(JasperBridgeError): ... # JRXML compilation failed
class FillError(JasperBridgeError): ...    # report filling failed
class ExportError(JasperBridgeError): ...  # export to format failed
class DataSourceError(FillError): ...      # JDBC/JSON/CSV connection or parsing failed
class ParameterError(FillError): ...       # missing or invalid report parameter
class PrintError(JasperBridgeError): ...   # printing failed
```

### 5.2 Typed parameters (`params.py`)

```python
class ImageParam:
    def __init__(self, path: str = None, *, data: bytes = None): ...

class DateParam:
    def __init__(self, year: int, month: int, day: int): ...

class TimeParam:
    def __init__(self, hour: int, minute: int, second: int): ...

class DateTimeParam:
    def __init__(self, year: int, month: int, day: int,
                 hour: int, minute: int, second: int): ...
```

**Type mapping (Python to Java via JSON):**

| Python type | JSON `type` field | JSON `value` field | Java type |
|---|---|---|---|
| `str` | `"string"` | `"..."` | `String` |
| `int` | `"long"` | `N` | `Long` |
| `float` | `"double"` | `N.N` | `Double` |
| `bool` | `"boolean"` | `true`/`false` | `Boolean` |
| `bytes` | `"bytes"` | `"<base64>"` | `byte[]` |
| `ImageParam(path=...)` | `"image_path"` | `"/path/to/file"` | `BufferedImage` |
| `ImageParam(data=...)` | `"image_bytes"` | `"<base64>"` | `BufferedImage` |
| `DateParam(y,m,d)` | `"date"` | `"2026-03-05"` | `java.sql.Date` |
| `TimeParam(h,m,s)` | `"time"` | `"14:30:00"` | `java.sql.Time` |
| `DateTimeParam(...)` | `"datetime"` | `"2026-03-05T14:30:00"` | `java.sql.Timestamp` |

Each parameter is serialized as `{"name": "...", "type": "...", "value": ...}` in the JSON command array sent to JasperBridge.java.

A `serialize_params(params_dict)` function converts a user-provided `dict[str, Any]` into the JSON-ready list of typed parameter objects, performing automatic type inference for Python primitives.

### 5.3 JVM lifecycle (`jvm.py`)

```python
def ensure_jvm(lib_root: str = None) -> tuple:
    """Boot JVM or attach to existing one. Returns (jvm_ptr, env_ptr)."""

def call_java_main(env_ptr, class_name: str, args: list[str]) -> str:
    """Invoke class.main(String[]) and return captured stdout."""

def status() -> str:
    """Return 'running' or 'not_started'."""

def java_version() -> str:
    """Return JDK version string (e.g. '14.0.1')."""

def classpath() -> list[str]:
    """Return list of JAR paths on the JVM classpath."""
```

### 5.4 Compiler (`compiler.py`)

```python
def compile_jrxml(jrxml_path: str, output_path: str = None) -> str:
    """Compile JRXML to .jasper. Returns the output path."""
```

### 5.5 Filler (`filler.py`)

```python
def fill_report(jrxml_or_jasper: str,
                params: dict = None,
                jdbc: str = None,
                user: str = None,
                password: str = None,
                json_file: str = None,        # v0.2
                select_expression: str = None, # v0.2
                csv_file: str = None,          # v0.2
                ) -> dict:
    """Fill a report and return the Java response dict (includes page_count)."""
```

### 5.6 Exporter (`exporter.py`)

```python
def export_pdf(output_path: str, overwrite: bool = True) -> str:
    """Export the currently-filled report to PDF. Returns output path."""

def export_png(output_dir: str, zoom: float = 1.0, overwrite: bool = True) -> list[str]:
    """Export pages as PNGs. Returns list of page image paths."""
```

### 5.7 Report class (`report.py`)

```python
class Report:
    def __init__(self, jrxml_path: str): ...

    def compile(self, output: str = None) -> str: ...
    def fill(self, params: dict = None, jdbc: str = None,
             user: str = None, password: str = None, **kwargs) -> None: ...
    def export_pdf(self, path: str, overwrite: bool = True) -> str: ...
    def export_png(self, path: str, zoom: float = 1.0, overwrite: bool = True) -> list[str]: ...
    def preview(self, title: str = "Report Preview") -> None: ...
    def print(self, **kwargs) -> bool: ...

    @property
    def page_count(self) -> int: ...
    @property
    def is_compiled(self) -> bool: ...
    @property
    def is_filled(self) -> bool: ...
```

### 5.8 Convenience functions (re-exported from `__init__.py`)

```python
def compile_jrxml(jrxml_path: str, output_path: str = None) -> str: ...
def quick_pdf(jrxml_path: str, output_path: str, **fill_kwargs) -> str: ...
def preview_pdf(pdf_path: str) -> None: ...
```

### 5.9 Preview (`preview.py`)

```python
def preview(page_images: list[str], title: str = "Report Preview") -> None:
    """Show page PNGs in a QPrintPreviewDialog."""
```

### 5.10 Printing (`printing.py`)

```python
def print_report(page_images: list[str], title: str = "Print Report") -> bool:
    """Open QPrintDialog and print pages. Returns True if printed."""
```

---

## 6. Java-Side Contract: JasperBridge.java

### 6.1 Supported actions (v0.1)

| Action | Key JSON fields | Response fields |
|---|---|---|
| `compile` | `jrxml`, `output` (optional) | `jasper_path`, `size` |
| `fill_empty` | `jrxml_or_jasper`, `params` (optional) | `page_count` |
| `fill_jdbc` | `jrxml_or_jasper`, `jdbc_url`, `user`, `pass`, `params` (optional) | `page_count` |
| `export_pdf` | `output_path` | `output_path`, `size` |
| `export_png` | `output_dir`, `zoom` (optional, default 1.0) | `pages` (list of paths), `count` |
| `info` | `jrxml_or_jasper` | `name`, `page_width`, `page_height`, `parameters` |

### 6.2 State management

JasperBridge holds two static fields:

- `lastReport` (`JasperReport`) -- the most recently compiled report
- `lastPrint` (`JasperPrint`) -- the most recently filled report

This allows fill-once, export-many workflows. Export actions operate on `lastPrint`. Fill actions update both fields.

### 6.3 Compile-on-demand

Fill actions accept `.jrxml` or `.jasper` paths. If `.jrxml` is provided, it is compiled in memory before filling.

### 6.4 Typed parameter deserialization

The `params` field is a JSON array of `{"name", "type", "value"}` objects. JasperBridge iterates the array and constructs Java objects matching the type mapping in section 5.2. Uses Jackson (shipped in JasperReports JARs) for JSON parsing.

### 6.5 Error reporting

On error, JasperBridge catches the exception and prints:

```json
{"status": "error", "action": "...", "error_type": "fully.qualified.ClassName", "error_message": "...", "stacktrace": "..."}
```

Diagnostic output goes to stderr (not stdout). The fd-pipe mechanism only captures stdout.

### 6.6 Compilation target

JasperBridge.java must be compiled with `-source 8 -target 8` to ensure bytecode compatibility with both JDK 8 and JDK 14. This uses `javac` on the development machine (not on ChoreBoy, where `javac` is blocked). The `.class` file ships with the library.

---

## 7. Logging Contract

All modules log through Python's `logging` module under the `jasper_bridge` logger hierarchy. No custom log files or handlers.

| Logger | Level | Content |
|---|---|---|
| `jasper_bridge.jvm` | INFO | JVM boot, attach, classpath |
| `jasper_bridge.jvm` | DEBUG | JNI function calls, fd-pipe capture |
| `jasper_bridge.compiler` | INFO | Compile start/finish, output path, file size |
| `jasper_bridge.filler` | INFO | Fill mode, data source, parameter count, page count, timing |
| `jasper_bridge.filler` | DEBUG | Serialized JSON command (image data truncated) |
| `jasper_bridge.exporter` | INFO | Export format, output path, file size, timing |
| `jasper_bridge.preview` | DEBUG | Page image loading, dialog lifecycle |
| `jasper_bridge.printing` | INFO | Printer name, copies, dialog result |
| `jasper_bridge` | ERROR | All errors with full context and Java stacktrace |

---

## 8. Known Risks

| Risk | Mitigation |
|---|---|
| JVM SIGSEGV handler conflicts with Qt | Initialize QApplication before any JVM code uses Qt fonts |
| One JVM per process (classpath frozen at boot) | Include all JARs at boot; document limitation |
| JasperReports reflective-access warnings on Java 14 | Cosmetic only; suppress with `--add-opens` flags if possible |
| Large reports (1000+ pages) fill slowly | Document as known limitation |
| Large image params via base64 | Prefer `image_path` type; warn in docs about base64 overhead > 1MB |
| Printer not available on ChoreBoy | Raise `PrintError` with discoverable printer list; preview as fallback |

---

## 9. Phase 1 Implementation Slices (v0.1.0)

**Goal:** Users can compile, fill (empty + JDBC) with typed parameters including images, export (PDF + PNG), preview, and print reports.

### Slice dependency graph

```
Slice 1 (Skeleton + Errors)
    |           \
    v            v
Slice 2         Slice 4
(JVM)           (Params)
    |               |
    v               |
Slice 3             |
(Java)              |
    |    \          |
    v     v         v
Slice 5  Slice 6 <--+
(Compiler) (Filler)
    |        |
    v        v
    Slice 7
    (Exporter)
    |    |    \
    v    v     v
  S8   S9    S10
(Report)(Preview)(Print)
    |    |     |
    v    v     v
    Slice 11
    (JARs + Logging)
        |
        v
    Slice 12
    (Docs + E2E)
```

---

### Slice 1: Library Skeleton and Error Hierarchy

**Objective:** Create the importable library package with version info and exception classes.

**Files to create:**

| File | Contents |
|---|---|
| `jasper_bridge/__init__.py` | Version import from `_version`, public API re-exports (initially just errors and version). Docstring describing the library. |
| `jasper_bridge/_version.py` | Single assignment: `__version__ = "0.1.0"` |
| `jasper_bridge/errors.py` | Full exception hierarchy: `JasperBridgeError`, `JVMError`, `CompileError`, `FillError`, `ExportError`, `DataSourceError` (subclass of `FillError`), `ParameterError` (subclass of `FillError`), `PrintError`. Each class should accept a `message` and optionally a `java_stacktrace` for Java-originated errors. |

**Dependencies:** None (first slice).

**Validation:**

- `from jasper_bridge import __version__` returns `"0.1.0"`
- `from jasper_bridge.errors import JasperBridgeError, JVMError, CompileError, FillError, ExportError, DataSourceError, ParameterError, PrintError` succeeds
- `issubclass(DataSourceError, FillError)` is `True`
- `issubclass(ParameterError, FillError)` is `True`
- All exceptions are instantiable with a message string
- All exceptions accept an optional `java_stacktrace` keyword argument

---

### Slice 2: JVM Lifecycle (`jvm.py`)

**Objective:** Port `jasper_probe/jni_helper.py` into a production-quality JVM lifecycle module. This is the foundation layer that all Java interactions depend on.

**Source material:** `jasper_probe/jni_helper.py` -- the validated JNI helper that boots the JVM, loads classes, and captures stdout via fd-pipe.

**File to create:** `jasper_bridge/jvm.py`

**What to port from `jni_helper.py`:**

- `libjvm.so` discovery (glob + `_discovered.json` fallback)
- `LD_LIBRARY_PATH` setup for JVM native dependencies
- ctypes structure definitions (`JavaVMInitArgs`, `JavaVMOption`, `JNIEnv` function table)
- JNI function index constants (FindClass, GetStaticMethodID, CallStaticVoidMethodA, NewStringUTF, NewObjectArray, SetObjectArrayElement, ExceptionOccurred, ExceptionDescribe, ExceptionClear, GetVersion)
- `JNI_CreateJavaVM` / `JNI_GetCreatedJavaVMs` logic (reuse existing JVM)
- Classpath construction: `jasper_bridge/java/` + `jasper_bridge/lib/*.jar`
- `call_java_main(env_ptr, class_name, args)` with fd-pipe stdout capture
- Thread safety: the fd-pipe mechanism redirects fd 1, which must be serialized

**Refinements over `jni_helper.py`:**

- Use `jasper_bridge/` paths instead of `jasper_probe/` paths for classpath
- Raise `JVMError` (from `errors.py`) instead of printing errors
- Add `status()`, `java_version()`, `classpath()` public functions
- Add logging under `jasper_bridge.jvm` logger
- Lazy initialization: JVM boots on first `ensure_jvm()` call, not at import time
- Module-level `_jvm_ptr` and `_env_ptr` state (set once, reused)
- `lib_root` auto-detection: defaults to `os.path.dirname(os.path.abspath(__file__))` (the `jasper_bridge/` directory)

**Public API:**

```python
def ensure_jvm(lib_root: str = None) -> tuple:
    """Boot JVM or attach to existing. Returns (jvm_ptr, env_ptr)."""

def call_java_main(env_ptr, class_name: str, args: list[str]) -> str:
    """Invoke class.main(String[]) via JNI. Returns captured stdout."""

def status() -> str:
    """Return 'running' or 'not_started'."""

def java_version() -> str:
    """Return the JDK version string."""

def classpath() -> list[str]:
    """Return the classpath entries used at JVM boot."""
```

**Dependencies:** Slice 1 (imports `JVMError` from `errors.py`).

**Validation:**

- `from jasper_bridge.jvm import ensure_jvm, call_java_main, status` succeeds
- `status()` returns `"not_started"` before any call
- On ChoreBoy: `ensure_jvm()` returns a valid `(jvm_ptr, env_ptr)` tuple
- On ChoreBoy: `status()` returns `"running"` after `ensure_jvm()`
- On ChoreBoy: `java_version()` returns `"14.0.1"`
- On ChoreBoy: `classpath()` returns a list containing paths ending in `.jar`
- When `libjvm.so` is not found, raises `JVMError` with descriptive message

---

### Slice 3: Java Entry Point (`JasperBridge.java`)

**Objective:** Write the single comprehensive Java class that replaces all probe-specific Java helpers (`HelloJava`, `JdbcProbe`, `JasperCompileProbe`, `JasperFillExport`) with a unified JSON command interface.

**Source material:** `jasper_probe/tools/` Java sources (patterns, imports, JasperReports API usage).

**Files to create:**

| File | Contents |
|---|---|
| `jasper_bridge/java/JasperBridge.java` | Full Java source implementing all v0.1 actions |
| `jasper_bridge/java/JasperBridge.class` | Pre-compiled bytecode (Java 8 target) |

**Java class design:**

```java
public class JasperBridge {
    private static JasperPrint lastPrint = null;
    private static JasperReport lastReport = null;

    public static void main(String[] args) { ... }

    // Action handlers
    private static void handleCompile(ObjectNode cmd) { ... }
    private static void handleFillEmpty(ObjectNode cmd) { ... }
    private static void handleFillJdbc(ObjectNode cmd) { ... }
    private static void handleExportPdf(ObjectNode cmd) { ... }
    private static void handleExportPng(ObjectNode cmd) { ... }
    private static void handleInfo(ObjectNode cmd) { ... }

    // Helpers
    private static HashMap<String, Object> deserializeParams(ArrayNode params) { ... }
    private static JasperReport loadOrCompile(String path) { ... }
    private static void respond(ObjectNode response) { ... }
    private static void respondError(String action, Exception e) { ... }
}
```

**v0.1 actions to implement:**

| Action | Handler | JasperReports API |
|---|---|---|
| `compile` | `handleCompile` | `JasperCompileManager.compileReportToFile(jrxml, output)` |
| `fill_empty` | `handleFillEmpty` | `JasperFillManager.fillReport(report, params, new JREmptyDataSource())` |
| `fill_jdbc` | `handleFillJdbc` | `DriverManager.getConnection(url, user, pass)` then `JasperFillManager.fillReport(report, params, conn)` |
| `export_pdf` | `handleExportPdf` | `JasperExportManager.exportReportToPdfFile(lastPrint, path)` |
| `export_png` | `handleExportPng` | `JRGraphics2DExporter` rendering each page to `BufferedImage`, saved via `ImageIO.write()` |
| `info` | `handleInfo` | Load report, read `getName()`, `getPageWidth()`, `getPageHeight()`, `getParameters()` |

**Typed parameter deserialization:** Implements the full type mapping table from section 5.2 (string, long, double, boolean, bytes, image_path, image_bytes, date, time, datetime).

**JSON library:** Jackson 2.9.5 (`ObjectMapper`, `ObjectNode`, `ArrayNode`) -- already available from the shipped JARs.

**Compilation:** Must be compiled on a development machine with JDK 8+ using:

```bash
javac -source 8 -target 8 -cp "lib/*" java/JasperBridge.java
```

The `.class` file is committed to the repository and ships with the library.

**Dependencies:** Slice 2 (the `.class` file must be loadable by `jvm.py`'s classpath).

**Validation:**

- On ChoreBoy: `call_java_main(env, "JasperBridge", ['{"action":"info","jrxml_or_jasper":"/path/to/hello_static.jrxml"}'])` returns valid JSON with `"status":"ok"`
- Compile action produces a `.jasper` file on disk
- Error action returns JSON with `"status":"error"` and populated `error_type`, `error_message`

---

### Slice 4: Typed Parameters (`params.py`)

**Objective:** Implement the parameter wrapper classes and the serialization function that converts a user-provided `dict` into the typed JSON array for JasperBridge.java.

**File to create:** `jasper_bridge/params.py`

**Classes:**

- `ImageParam(path=None, *, data=None)` -- exactly one of `path` or `data` must be provided. Raises `ParameterError` if neither or both are given. If `path` is given, validates the file exists.
- `DateParam(year, month, day)` -- stores components, serializes to `"YYYY-MM-DD"` string.
- `TimeParam(hour, minute, second)` -- stores components, serializes to `"HH:MM:SS"` string.
- `DateTimeParam(year, month, day, hour, minute, second)` -- stores components, serializes to `"YYYY-MM-DDTHH:MM:SS"` string.

**Serialization function:**

```python
def serialize_params(params: dict) -> list[dict]:
    """Convert {name: value} dict to [{"name": ..., "type": ..., "value": ...}] list."""
```

Type inference rules:
- `str` -> `{"type": "string", "value": "..."}`
- `int` -> `{"type": "long", "value": N}`
- `float` -> `{"type": "double", "value": N}`
- `bool` -> `{"type": "boolean", "value": true/false}` (check `bool` before `int` since `bool` is a subclass of `int`)
- `bytes` -> `{"type": "bytes", "value": "<base64>"}` (use `base64.b64encode().decode("ascii")`)
- `ImageParam` -> `"image_path"` or `"image_bytes"` depending on which was provided
- `DateParam` -> `"date"`
- `TimeParam` -> `"time"`
- `DateTimeParam` -> `"datetime"`
- Unrecognized types -> raise `ParameterError` with descriptive message

**Dependencies:** Slice 1 (imports `ParameterError` from `errors.py`).

**Validation:**

- `serialize_params({"TITLE": "Test"})` returns `[{"name": "TITLE", "type": "string", "value": "Test"}]`
- `serialize_params({"COUNT": 42})` returns `[{"name": "COUNT", "type": "long", "value": 42}]`
- `serialize_params({"RATE": 0.075})` returns `[{"name": "RATE", "type": "double", "value": 0.075}]`
- `serialize_params({"FLAG": True})` returns with `"type": "boolean"` (not `"long"`)
- `serialize_params({"LOGO": ImageParam("/path/to/logo.png")})` returns with `"type": "image_path"`
- `serialize_params({"DATE": DateParam(2026, 3, 5)})` returns with `"value": "2026-03-05"`
- `serialize_params({"X": object()})` raises `ParameterError`
- `ImageParam()` with no arguments raises `ParameterError`
- `ImageParam("/a", data=b"x")` with both arguments raises `ParameterError`

---

### Slice 5: Compiler (`compiler.py`)

**Objective:** Implement the JRXML compilation function that calls JasperBridge's `compile` action.

**File to create:** `jasper_bridge/compiler.py`

**Function:**

```python
def compile_jrxml(jrxml_path: str, output_path: str = None) -> str:
    """Compile a JRXML file to .jasper format.

    Args:
        jrxml_path: Absolute or relative path to the .jrxml file.
        output_path: Where to write the .jasper file. Defaults to same
                     directory and base name as jrxml_path with .jasper extension.

    Returns:
        The absolute path to the compiled .jasper file.

    Raises:
        FileNotFoundError: If jrxml_path does not exist.
        CompileError: If JasperReports compilation fails.
    """
```

**Implementation details:**

1. Resolve `jrxml_path` to absolute path
2. Verify the file exists (raise `FileNotFoundError` if not)
3. Compute default `output_path` if not provided (replace `.jrxml` with `.jasper`)
4. Build JSON command: `{"action": "compile", "jrxml": "<abs_path>", "output": "<abs_path>"}`
5. Call `jvm.ensure_jvm()` then `jvm.call_java_main(env, "JasperBridge", [json_str])`
6. Parse JSON response
7. If `status == "error"`, raise `CompileError` with `error_message` and `java_stacktrace=stacktrace`
8. Log compile result (output path, file size)
9. Return the output path

**Dependencies:** Slice 2 (`jvm.py`), Slice 3 (`JasperBridge.class`), Slice 1 (`CompileError`).

**Validation:**

- On ChoreBoy: `compile_jrxml("jasper_probe/test_reports/hello_static.jrxml")` produces a `.jasper` file
- Calling with a nonexistent path raises `FileNotFoundError`
- Calling with an invalid JRXML raises `CompileError` with a meaningful message

---

### Slice 6: Filler (`filler.py`)

**Objective:** Implement report filling with empty and JDBC data sources, including typed parameter serialization.

**File to create:** `jasper_bridge/filler.py`

**Function:**

```python
def fill_report(jrxml_or_jasper: str,
                params: dict = None,
                jdbc: str = None,
                user: str = None,
                password: str = None) -> dict:
    """Fill a report with data and parameters.

    Data source selection:
        - If jdbc/user/password are provided: JDBC data source (fill_jdbc action)
        - Otherwise: empty data source (fill_empty action)

    Args:
        jrxml_or_jasper: Path to .jrxml or .jasper file.
        params: Dict of report parameters {name: value}. Values can be
                Python primitives or typed wrappers (ImageParam, DateParam, etc.).
        jdbc: JDBC connection URL.
        user: Database username.
        password: Database password.

    Returns:
        Dict with response data including 'page_count'.

    Raises:
        FileNotFoundError: If the report file does not exist.
        FillError: If filling fails.
        DataSourceError: If the database connection fails.
        ParameterError: If parameter serialization fails.
    """
```

**Implementation details:**

1. Resolve path, verify file exists
2. Determine action: `"fill_jdbc"` if `jdbc` is provided, else `"fill_empty"`
3. Build JSON command with action, path, and optionally JDBC credentials
4. If `params` is provided, call `params.serialize_params(params)` and include as `"params"` array
5. Serialize the command dict to JSON string via `json.dumps()`
6. Call `jvm.ensure_jvm()` then `jvm.call_java_main()`
7. Parse JSON response
8. Map error types: `java.sql.SQLException` -> `DataSourceError`, others -> `FillError`
9. Log fill result (mode, page count, timing)
10. Return the parsed response dict

**Dependencies:** Slice 2 (`jvm.py`), Slice 3 (`JasperBridge.class`), Slice 4 (`serialize_params`), Slice 1 (`FillError`, `DataSourceError`, `ParameterError`).

**Validation:**

- On ChoreBoy: `fill_report("hello_static.jrxml")` returns dict with `page_count >= 1`
- On ChoreBoy: `fill_report("hello_static.jrxml", jdbc="jdbc:postgresql://localhost:5432/classicaccounting", user="postgres", password="true")` succeeds
- On ChoreBoy: `fill_report("hello_static.jrxml", params={"TITLE": "Test"})` passes parameters correctly
- Bad JDBC URL raises `DataSourceError`
- Nonexistent report file raises `FileNotFoundError`

---

### Slice 7: Exporter (`exporter.py`)

**Objective:** Implement PDF and PNG export functions that call JasperBridge's export actions on the currently-filled report.

**File to create:** `jasper_bridge/exporter.py`

**Functions:**

```python
def export_pdf(output_path: str, overwrite: bool = True) -> str:
    """Export the currently-filled report to PDF.

    Args:
        output_path: Where to write the PDF file.
        overwrite: If True (default), overwrite existing file.
                   If False, raise FileExistsError if file exists.

    Returns:
        Absolute path to the written PDF.

    Raises:
        FileExistsError: If overwrite=False and file exists.
        ExportError: If no report is currently filled, or export fails.
    """

def export_png(output_dir: str, zoom: float = 1.0, overwrite: bool = True) -> list[str]:
    """Export the currently-filled report pages as PNG images.

    Args:
        output_dir: Directory to write page images (created if needed).
        zoom: Zoom factor for rendering (1.0 = 72 DPI, 2.0 = 144 DPI).
        overwrite: If True (default), overwrite existing files.

    Returns:
        List of absolute paths to the written PNG files.

    Raises:
        ExportError: If no report is currently filled, or export fails.
    """
```

**Implementation details:**

1. Check overwrite policy (for PDF: check if file exists when `overwrite=False`)
2. Create output directory if needed (for PNG)
3. Build JSON command: `{"action": "export_pdf", "output_path": "..."}` or `{"action": "export_png", "output_dir": "...", "zoom": N}`
4. Call `jvm.call_java_main()` (JVM already running from prior fill)
5. Parse response; raise `ExportError` on failure
6. Log export result (format, path, file size, timing)
7. Return path(s)

**Dependencies:** Slice 2 (`jvm.py`), Slice 3 (`JasperBridge.class`), Slice 1 (`ExportError`). Logically requires a prior fill (Slice 6) to have populated `lastPrint` on the Java side.

**Validation:**

- On ChoreBoy: After filling, `export_pdf("/tmp/test.pdf")` writes a valid PDF
- On ChoreBoy: After filling, `export_png("/tmp/pages/", zoom=2.0)` writes PNG files
- `export_pdf("/tmp/test.pdf", overwrite=False)` raises `FileExistsError` if file exists
- Export without prior fill raises `ExportError`

---

### Slice 8: Report Class (`report.py`)

**Objective:** Implement the main user-facing `Report` class that composes compiler, filler, exporter, preview, and printing into a single coherent object.

**File to create:** `jasper_bridge/report.py`

**Class design:**

```python
class Report:
    def __init__(self, jrxml_path: str):
        # Store absolute path, initialize state flags

    def compile(self, output: str = None) -> str:
        # Delegates to compiler.compile_jrxml()
        # Updates is_compiled state

    def fill(self, params: dict = None, jdbc: str = None,
             user: str = None, password: str = None) -> None:
        # Delegates to filler.fill_report()
        # Auto-compiles if needed (compile-on-demand is handled Java-side)
        # Updates is_filled state, stores page_count

    def export_pdf(self, path: str, overwrite: bool = True) -> str:
        # Validates is_filled, delegates to exporter.export_pdf()

    def export_png(self, path: str, zoom: float = 1.0,
                   overwrite: bool = True) -> list[str]:
        # Validates is_filled, delegates to exporter.export_png()

    def preview(self, title: str = "Report Preview") -> None:
        # Exports to temp PNG dir if not already exported
        # Delegates to preview.preview()

    def print(self, **kwargs) -> bool:
        # Exports to temp PNG dir if not already exported
        # Delegates to printing.print_report()

    @property
    def page_count(self) -> int: ...

    @property
    def is_compiled(self) -> bool: ...

    @property
    def is_filled(self) -> bool: ...
```

**State machine:**

- `__init__` -> not compiled, not filled
- `compile()` -> compiled
- `fill()` -> filled (implicitly compiled via Java-side compile-on-demand)
- `export_*()` -> requires filled
- `preview()` / `print()` -> requires filled

Calling `export_*()` or `preview()` or `print()` on an unfilled report raises `ExportError("Report has not been filled. Call fill() first.")`.

**Convenience functions** (in `report.py` or `__init__.py`):

```python
def compile_jrxml(jrxml_path, output_path=None):
    return compiler.compile_jrxml(jrxml_path, output_path)

def quick_pdf(jrxml_path, output_path, **fill_kwargs):
    r = Report(jrxml_path)
    r.fill(**fill_kwargs)
    return r.export_pdf(output_path)
```

**Update `__init__.py`:** Re-export `Report`, `ImageParam`, `DateParam`, `TimeParam`, `DateTimeParam`, `compile_jrxml`, `quick_pdf`, `preview_pdf`, `jvm` module.

**Dependencies:** Slices 5, 6, 7 (compiler, filler, exporter), Slice 9 (preview), Slice 10 (printing). Preview and printing can be soft dependencies -- if not yet implemented, `preview()` and `print()` raise `NotImplementedError`.

**Validation:**

- `Report("hello_static.jrxml")` creates an instance with `is_compiled == False`, `is_filled == False`
- `report.fill()` sets `is_filled == True` and `page_count >= 1`
- `report.export_pdf("/tmp/test.pdf")` produces a file after fill
- `report.export_pdf(...)` before `fill()` raises `ExportError`
- `quick_pdf("hello_static.jrxml", "/tmp/quick.pdf")` produces a PDF in one call
- `from jasper_bridge import Report, ImageParam` works

---

### Slice 9: Qt Print Preview (`preview.py`)

**Objective:** Implement `QPrintPreviewDialog` integration that displays report pages rendered as PNG images.

**File to create:** `jasper_bridge/preview.py`

**Function:**

```python
def preview(page_images: list[str], title: str = "Report Preview") -> None:
    """Show report page PNGs in a QPrintPreviewDialog.

    Creates a QApplication if one does not exist. Loads page PNGs as QPixmap,
    renders them into the dialog via paintRequested signal, scaling pages to
    fit the printer page rect while maintaining aspect ratio.

    Args:
        page_images: List of absolute paths to page PNG files.
        title: Dialog window title.

    Raises:
        FileNotFoundError: If any page image path does not exist.
        PrintError: If QPixmap fails to load an image.
    """
```

**Implementation details (ported from `jasper_probe/probe7_qt_print.py`):**

1. Check/create `QApplication` instance (`QApplication.instance() or QApplication(sys.argv)`)
2. Load each page image path as `QPixmap`; validate all load successfully
3. Create `QPrinter(QPrinter.HighResolution)`
4. Create `QPrintPreviewDialog(printer)`
5. Connect `paintRequested` signal to a render function that:
   - Iterates pages
   - Creates `QPainter(printer)`
   - For each page: calculates scale to fit `printer.pageRect()` maintaining aspect ratio, draws the pixmap
   - Inserts `printer.newPage()` between pages
6. Set dialog title, exec dialog
7. If no QApplication event loop is running, call `dialog.exec_()`

**Dependencies:** Slice 1 (`PrintError`). PySide2 is a runtime dependency (available in FreeCAD AppRun).

**Validation:**

- On ChoreBoy: `preview(["/path/to/page_001.png"])` opens a `QPrintPreviewDialog` showing the image
- Multiple page images display with correct pagination
- Missing image path raises `FileNotFoundError`

---

### Slice 10: Qt Printing (`printing.py`)

**Objective:** Implement basic direct printing via Qt's `QPrintDialog`.

**File to create:** `jasper_bridge/printing.py`

**Function (v0.1 -- basic with dialog):**

```python
def print_report(page_images: list[str], title: str = "Print Report") -> bool:
    """Open QPrintDialog and print report pages to the selected printer.

    Creates a QApplication if one does not exist.

    Args:
        page_images: List of absolute paths to page PNG files.
        title: Print job title.

    Returns:
        True if the user accepted the dialog and printing completed.
        False if the user cancelled the dialog.

    Raises:
        FileNotFoundError: If any page image path does not exist.
        PrintError: If printing fails after dialog acceptance.
    """
```

**Implementation details:**

1. Check/create `QApplication` instance
2. Load page images as `QPixmap`
3. Create `QPrinter(QPrinter.HighResolution)`
4. Create `QPrintDialog(printer)`
5. Set document name to `title`
6. If `dialog.exec_() == QDialog.Accepted`:
   - Create `QPainter(printer)`
   - Render pages (same scaling logic as preview)
   - Return `True`
7. Else return `False`

**Dependencies:** Slice 1 (`PrintError`). PySide2 runtime dependency.

**Validation:**

- On ChoreBoy: `print_report(["/path/to/page.png"])` opens a print dialog
- Cancelling the dialog returns `False`
- Missing image path raises `FileNotFoundError`

---

### Slice 11: JARs and Logging Integration

**Objective:** Populate the `lib/` directory with all required JARs and add logging statements across all existing modules.

**Files to create/modify:**

| Action | Path |
|---|---|
| Create directory | `jasper_bridge/lib/` |
| Copy JARs | 14 JAR files from `jasper_probe/lib/` (on ChoreBoy) into `jasper_bridge/lib/` |
| Create directory | `jasper_bridge/java/` (if not already created in Slice 3) |
| Modify | `jasper_bridge/jvm.py` -- add logging statements under `jasper_bridge.jvm` |
| Modify | `jasper_bridge/compiler.py` -- add logging under `jasper_bridge.compiler` |
| Modify | `jasper_bridge/filler.py` -- add logging under `jasper_bridge.filler` |
| Modify | `jasper_bridge/exporter.py` -- add logging under `jasper_bridge.exporter` |
| Modify | `jasper_bridge/preview.py` -- add logging under `jasper_bridge.preview` |
| Modify | `jasper_bridge/printing.py` -- add logging under `jasper_bridge.printing` |

**JARs to include:**

```
jasperreports-6.7.0.jar
itext-2.1.7.js6.jar
groovy-all-2.4.12.jar
ecj-4.4.2.jar
postgresql-42.2.2.jar
commons-beanutils-1.9.3.jar
commons-collections-3.2.2.jar
commons-digester-2.1.jar
commons-logging-1.1.1.jar
castor-core-1.3.3.jar
castor-xml-1.3.3.jar
jackson-annotations-2.9.5.jar
jackson-core-2.9.5.jar
jackson-databind-2.9.5.jar
```

**Logging pattern for each module:**

```python
import logging
logger = logging.getLogger(__name__)
```

Then `logger.info(...)`, `logger.debug(...)`, `logger.error(...)` at the points defined in the logging contract (section 7 of this PRD).

**Dependencies:** Slices 2-10 (all modules must exist before adding logging).

**Validation:**

- `jasper_bridge/lib/` contains all 14 JARs
- Setting `logging.getLogger("jasper_bridge").setLevel(logging.DEBUG)` produces log output during compile/fill/export operations
- Each module uses `logging.getLogger(__name__)` (not a hardcoded logger name)

---

### Slice 12: Documentation and End-to-End Validation

**Objective:** Write user-facing documentation and perform complete end-to-end validation of the library.

**Files to create:**

| File | Contents |
|---|---|
| `jasper_bridge/docs/USAGE.md` | Quick-start guide: installation (copy folder), first report, filling with database data, exporting to PDF, print preview, troubleshooting |
| `jasper_bridge/docs/CHANGELOG.md` | Initial entry for v0.1.0 |

**USAGE.md outline:**

1. **Installation** -- copy `jasper_bridge/` folder into your project
2. **Quick start** -- compile, fill, export hello_static.jrxml
3. **Filling with database data** -- JDBC example with classicaccounting
4. **Typed parameters** -- ImageParam, DateParam examples
5. **Export formats** -- PDF, PNG (v0.1), note that more formats come in v0.2
6. **Print preview** -- `report.preview()` usage
7. **Printing** -- `report.print()` usage
8. **JVM management** -- `jvm.status()`, `jvm.java_version()`
9. **Error handling** -- exception hierarchy, catching errors
10. **Troubleshooting** -- common issues (JVM not found, JDBC connection refused, missing JARs)

**End-to-end validation script** (not shipped, used for testing):

```python
from jasper_bridge import Report

report = Report("jasper_probe/test_reports/hello_static.jrxml")
report.fill()
report.export_pdf("/tmp/jasper_bridge_test.pdf")
print(f"Pages: {report.page_count}")
print(f"PDF written: /tmp/jasper_bridge_test.pdf")
report.preview()
```

**Dependencies:** All prior slices.

**Validation:**

- The end-to-end script runs without errors on ChoreBoy
- `USAGE.md` accurately describes the API
- `CHANGELOG.md` has a v0.1.0 entry

---

## 10. Phase 2 Slices (v0.2.0)

**Goal:** Additional export formats, data sources, advanced printing, and connection pooling.

### Slice 2.1: HTML Export

Add `export_html` action to `JasperBridge.java` using `HtmlExporter`. Add `export_html()` to `exporter.py` and `Report` class. No extra JARs needed.

### Slice 2.2: CSV Export

Add `export_csv` action to `JasperBridge.java` using `JRCsvExporter`. Add `export_csv()` to `exporter.py` and `Report` class.

### Slice 2.3: XLS Export

Add `export_xls` action to `JasperBridge.java` using `JRXlsExporter`. Add `export_xls()` to `exporter.py` and `Report` class. No extra JARs needed.

### Slice 2.4: Plain Text Export

Add `export_text` action to `JasperBridge.java` using `JRTextExporter` with configurable `page_width` and `page_height`. Add `export_text()` to `exporter.py` and `Report` class.

### Slice 2.5: XML Export

Add `export_xml` action to `JasperBridge.java` using `JRXmlExporter`. Add `export_xml()` to `exporter.py` and `Report` class.

### Slice 2.6: JSON Data Source

Add `fill_json` action to `JasperBridge.java` using `JsonDataSource`. Add `json_file` and `select_expression` parameters to `filler.fill_report()` and `Report.fill()`.

### Slice 2.7: CSV Data Source

Add `fill_csv` action to `JasperBridge.java` using `JRCsvDataSource`. Add `csv_file` parameter to `filler.fill_report()` and `Report.fill()`.

### Slice 2.8: Advanced Printing

Extend `printing.print_report()` with `printer`, `copies`, `collate`, `duplex`, `show_dialog` parameters. Use `QPrinterInfo.availablePrinters()` for printer discovery. Raise `PrintError` if named printer not found.

### Slice 2.9: Connection Pool

Create `jasper_bridge/connections.py` with `ConnectionPool` class. Python-side convenience wrapper that stores JDBC credentials by ID. Each `fill()` call still passes full credentials to Java.

### Slice 2.10: API Reference and JRXML Guide

Write `jasper_bridge/docs/API.md` (complete API reference) and `jasper_bridge/docs/JRXML_GUIDE.md` (guide to writing JRXML for ChoreBoy, covering page sizes, fonts, parameters, SQL queries, grouping, common patterns).

---

## 11. Phase 3 Slices (v0.3.0)

**Goal:** Polish, advanced features, and performance.

### Slice 3.1: XLSX Export

Ship Apache POI JARs (~8MB: poi-ooxml, poi-ooxml-schemas, xmlbeans). Add `export_xlsx` action to `JasperBridge.java` using `JRXlsxExporter`. Add `export_xlsx()` to `exporter.py` and `Report` class.

### Slice 3.2: Report Metadata API

Extend `info` action to return full report metadata: declared parameters (name, type, default value), fields, page dimensions, query string. Expose via `Report.info()` property or method.

### Slice 3.3: Subreport Support

Test and document subreport workflows. Ensure classpath and parameter passing work correctly for reports that reference subreports.

### Slice 3.4: Parameter Validation

Before filling, optionally load report metadata and validate that all required parameters are provided and types match. Raise `ParameterError` with specific missing/mismatched parameter names.

### Slice 3.5: Batch Export

Add `fill_and_export` compound action to `JasperBridge.java` that performs fill + multiple exports in a single JNI call. Add `Report.export_all()` or similar convenience method.

### Slice 3.6: Performance Profiling

Profile fill and export operations for large reports (100+ pages). Identify bottlenecks in JNI call overhead, fd-pipe capture, and image rendering. Document performance characteristics and optimization recommendations.

---

## 12. Distribution Model

The library is distributed as a folder copy. Each user project embeds its own copy:

```
/home/default/myproject/
    jasper_bridge/          <- embedded library copy
    main.py
    reports/
        invoice.jrxml
```

Imports work without `sys.path` manipulation:

```python
from jasper_bridge import Report
```

No pip, no wheel, no setup.py. Users copy the folder.

---

## 13. Acceptance Criteria

The library is ready for user testing when all of the following work on ChoreBoy:

1. `from jasper_bridge import Report, ImageParam` succeeds
2. `Report("hello_static.jrxml").fill()` fills with empty data source
3. `report.export_pdf("output.pdf")` writes a valid PDF
4. `report.export_png("output/", zoom=2.0)` writes page PNGs
5. `report.preview()` opens a Qt print preview dialog showing pages
6. `report.print()` opens a Qt print dialog
7. `report.fill(jdbc="jdbc:postgresql://...", user="postgres", password="true")` fills from database
8. `report.fill(params={"LOGO": ImageParam("/path/to/logo.png"), "TransID": 12345})` passes typed parameters correctly
9. Errors produce clear messages with Java stacktraces where applicable
10. `import logging; logging.getLogger("jasper_bridge").setLevel(logging.DEBUG)` produces useful diagnostic output

---

## 14. Version History

| Version | Scope |
|---|---|
| 0.1.0 | Core: compile, fill (empty + JDBC), typed params, PDF/PNG export, preview, basic print |
| 0.2.0 | Additional exports (HTML, CSV, XLS, text, XML), data sources (JSON, CSV), advanced printing, connection pool |
| 0.3.0 | XLSX export, report metadata, subreports, parameter validation, batch export, performance |
