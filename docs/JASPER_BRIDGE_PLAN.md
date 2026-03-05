# jasper_bridge Library Plan

## 1. What this is

A standalone Python library that lets ChoreBoy Code Studio users generate, fill, export, and print JasperReports from their Python projects. It wraps the JNI-based Java integration discovered in the jasper_probe phase into a clean, versioned, documented API.

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
report.preview()   # opens Qt print preview
report.print()     # opens Qt print dialog
```

## 2. Why a separate library

- **Reusable across projects.** Users can import it into any Python project on ChoreBoy, not just inside ChoreBoy Code Studio.
- **Versioned independently.** The library has its own release cycle, separate from the IDE.
- **Testable in isolation.** The library can be tested without the full IDE running.
- **Clean dependency boundary.** ChoreBoy Code Studio does not need to know about JasperReports internals.

## 3. Constraints

These are inherited from the ChoreBoy environment (see `docs/DISCOVERY.md`):

- Python 3.9.2 (FreeCAD AppRun runtime)
- No pip, no internet, no system package installs
- Java binary execution blocked by mandatory access control
- JVM loaded in-process via ctypes + JNI (`libjvm.so` from JDK 14.0.1)
- One JVM per process (created once, reused for lifetime)
- PySide2 5.15 available for Qt integration
- JasperReports 6.7.0 JARs shipped with the library
- PostgreSQL 9.3.6 reachable via JDBC (postgresql-42.2.2.jar)
- JVM installs SIGSEGV handler; QApplication must be initialized before QFont usage

## 4. Architecture overview

```
┌─────────────────────────────────────────────┐
│  User's Python script                       │
│  from jasper_bridge import Report           │
└───────────┬─────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────┐
│  jasper_bridge (Python)                     │
│  ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │ compiler │ │ filler   │ │ exporter    │ │
│  └────┬─────┘ └────┬─────┘ └──────┬──────┘ │
│       │            │              │         │
│  ┌────▼────────────▼──────────────▼──────┐  │
│  │  jvm.py (JVM lifecycle + JNI calls)   │  │
│  └────────────────┬──────────────────────┘  │
│                   │                         │
│  ┌────────────────▼──────────────────────┐  │
│  │  java/JasperBridge.class              │  │
│  │  (single Java entry point)            │  │
│  └────────────────┬──────────────────────┘  │
│                   │                         │
│  ┌────────────────▼──────────────────────┐  │
│  │  lib/ (JasperReports JARs)            │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### Communication protocol

Python → Java communication uses `call_java_main(class, args)` with structured JSON output from the Java side. This replaces the pipe-delimited `TAG|detail` format used in probes with proper JSON, enabling richer return values and structured error reporting.

**Request:** `JasperBridge.main(String[] args)` where `args[0]` is a JSON command string.

**Response:** Java prints a single JSON line to stdout, captured by the JNI helper's fd-pipe mechanism.

Example flow:

```
Python: call_java_main("JasperBridge", ['{"action":"compile","jrxml":"/path/to/report.jrxml","output":"/path/to/report.jasper"}'])
Java:   {"status":"ok","jasper_path":"/path/to/report.jasper","size":22439}
```

This design keeps the JNI layer thin (just `main(String[])` invocation and stdout capture) while giving the Java side full flexibility to return structured results.

## 5. Library structure

```
jasper_bridge/
├── __init__.py              # version, public API re-exports
├── report.py                # Report class (main user-facing API)
├── params.py                # typed parameter wrappers (ImageParam, DateParam, etc.)
├── compiler.py              # compile_jrxml() → .jasper
├── filler.py                # fill_report() with various data sources
├── exporter.py              # export to PDF, PNG, HTML, CSV, XML, XLS, text
├── preview.py               # Qt QPrintPreviewDialog integration
├── printing.py              # Qt QPrinter / QPrintDialog direct printing
├── connections.py           # connection pool / reuse (v0.2)
├── jvm.py                   # JVM lifecycle (from jni_helper.py, refined)
├── errors.py                # Exception hierarchy
├── _version.py              # __version__ = "0.1.0"
├── java/
│   ├── JasperBridge.java    # single comprehensive Java entry point
│   └── JasperBridge.class   # pre-compiled (Java 8 bytecode target)
├── lib/
│   ├── jasperreports-6.7.0.jar
│   ├── itext-2.1.7.js6.jar
│   ├── groovy-all-2.4.12.jar
│   ├── ecj-4.4.2.jar
│   ├── postgresql-42.2.2.jar
│   ├── commons-beanutils-1.9.3.jar
│   ├── commons-collections-3.2.2.jar
│   ├── commons-digester-2.1.jar
│   ├── commons-logging-1.1.1.jar
│   ├── castor-core-1.3.3.jar
│   ├── castor-xml-1.3.3.jar
│   ├── jackson-annotations-2.9.5.jar
│   ├── jackson-core-2.9.5.jar
│   └── jackson-databind-2.9.5.jar
└── docs/
    ├── USAGE.md             # user-facing documentation
    ├── API.md               # API reference
    ├── JRXML_GUIDE.md       # guide to writing JRXML for ChoreBoy
    └── CHANGELOG.md         # version history
```

## 6. Public API design

### 6.1 Report class (primary interface)

```python
from jasper_bridge import Report, ImageParam, DateParam

report = Report("/path/to/report.jrxml")

report.compile()
report.compile(output="/path/to/report.jasper")

# Typed parameters: primitives are auto-inferred, use wrappers for images/dates
report.fill(params={
    "TITLE": "Monthly Report",               # str → java.lang.String
    "RECORD_COUNT": 42,                       # int → java.lang.Long
    "TAX_RATE": 0.075,                        # float → java.lang.Double
    "SHOW_FOOTER": True,                      # bool → java.lang.Boolean
    "INVOICE_DATE": DateParam(2026, 3, 5),    # → java.sql.Date
    "LOGO": ImageParam("/path/to/logo.png"),  # → java.awt.Image (from file)
})
report.fill(jdbc="jdbc:postgresql://localhost:5432/mydb",
            user="postgres", password="true",
            params={"DEPARTMENT": "Sales"})
report.fill(json_file="/path/to/data.json", select_expression="records")
report.fill(csv_file="/path/to/data.csv")

# All export methods accept overwrite=True (default) to replace existing files.
# Pass overwrite=False to raise FileExistsError if the output already exists.
report.export_pdf("/path/to/output.pdf")
report.export_pdf("/path/to/output.pdf", overwrite=False)
report.export_png("/path/to/output/", zoom=2.0)
report.export_html("/path/to/output.html")
report.export_csv("/path/to/output.csv")
report.export_xls("/path/to/output.xls")
report.export_xml("/path/to/output.xml")
report.export_text("/path/to/output.txt")

report.preview()
report.preview(title="Invoice Preview")

# Direct printing via Qt QPrinter / QPrintDialog
report.print()
report.print(printer="Xerox_6515", copies=2, show_dialog=False)
report.print(printer="Xerox_6515", duplex=True, collate=True)

report.page_count
report.is_compiled
report.is_filled
```

### 6.2 Convenience functions

```python
from jasper_bridge import compile_jrxml, quick_pdf, preview_pdf

compile_jrxml("report.jrxml", "report.jasper")

quick_pdf("report.jrxml", "output.pdf",
          jdbc="jdbc:postgresql://localhost:5432/mydb",
          user="postgres", password="true")

preview_pdf("existing_report.pdf")
```

### 6.3 JVM management (advanced)

```python
from jasper_bridge import jvm

jvm.status()       # "running" | "not_started"
jvm.java_version() # "14.0.1"
jvm.classpath()    # list of JAR paths
```

### 6.4 Error hierarchy

```python
from jasper_bridge.errors import (
    JasperBridgeError,       # base
    JVMError,                # JVM failed to start or crashed
    CompileError,            # JRXML compilation failed
    FillError,               # report filling failed
    ExportError,             # export to format failed
    DataSourceError,         # JDBC/JSON/CSV connection or parsing failed
    ParameterError,          # missing or invalid report parameter
    PrintError,              # printing failed (no printers, dialog cancelled)
)
```

### 6.5 Parameter types

JasperReports parameters are strongly typed Java objects. Passing a `Long` parameter as a `String` causes a fill-time `ClassCastException`. The library provides automatic type inference for Python primitives and explicit wrapper classes for types that cannot be inferred.

```python
from jasper_bridge import ImageParam, DateParam, TimeParam, DateTimeParam

params = {
    "TITLE": "Invoice",                           # str → String
    "RECORD_COUNT": 42,                            # int → Long
    "TAX_RATE": 0.075,                             # float → Double
    "SHOW_FOOTER": True,                           # bool → Boolean
    "RAW_DATA": b"\x89PNG...",                     # bytes → byte[]
    "LOGO": ImageParam("/path/to/logo.png"),       # file path → BufferedImage
    "STAMP": ImageParam(data=raw_bytes),           # raw bytes → BufferedImage
    "INVOICE_DATE": DateParam(2026, 3, 5),         # → java.sql.Date
    "START_TIME": TimeParam(14, 30, 0),            # → java.sql.Time
    "CREATED_AT": DateTimeParam(2026, 3, 5, 14, 30, 0),  # → java.sql.Timestamp
}
```

**Type mapping:**

| Python type | JSON encoding | Java type |
|---|---|---|
| `str` | `{"type":"string","value":"..."}` | `String` |
| `int` | `{"type":"long","value":N}` | `Long` |
| `float` | `{"type":"double","value":N}` | `Double` |
| `bool` | `{"type":"boolean","value":true}` | `Boolean` |
| `bytes` | `{"type":"bytes","value":"<base64>"}` | `byte[]` |
| `ImageParam(path)` | `{"type":"image_path","value":"/path/to/file"}` | `BufferedImage` |
| `ImageParam(data=b"...")` | `{"type":"image_bytes","value":"<base64>"}` | `BufferedImage` |
| `DateParam(y,m,d)` | `{"type":"date","value":"2026-03-05"}` | `java.sql.Date` |
| `TimeParam(h,m,s)` | `{"type":"time","value":"14:30:00"}` | `java.sql.Time` |
| `DateTimeParam(...)` | `{"type":"datetime","value":"2026-03-05T14:30:00"}` | `java.sql.Timestamp` |

The `params` dict is serialized to a JSON array of `{"name": "...", "type": "...", "value": ...}` objects in the command payload sent to `JasperBridge.java`. The Java side iterates this array, constructs the appropriate Java object for each entry, and places them in the `HashMap<String, Object>` passed to `JasperFillManager`.

### 6.6 Connection management (v0.2)

For scripts that fill multiple reports against the same database, an optional connection pool avoids repeating JDBC credentials on every `fill()` call. Connections are registered by ID and referenced at fill time.

```python
from jasper_bridge import ConnectionPool

pool = ConnectionPool()
pool.add("main_db", "jdbc:postgresql://localhost:5432/mydb",
         user="postgres", password="true")

report1.fill(connection="main_db", params={...})
report2.fill(connection="main_db", params={...})
```

The pool is Python-side only. Each `fill()` call still passes the full JDBC URL and credentials to `JasperBridge.java` — the pool is a convenience wrapper, not a persistent Java-side connection. This avoids complexity around JDBC connection lifecycle management across JNI.

## 7. Java-side design: JasperBridge.java

A single Java class that handles all JasperReports operations. It receives a JSON command via `main(String[])` and prints a JSON response to stdout.

### Supported actions

| Action | Description | Key inputs |
|---|---|---|
| `compile` | Compile JRXML to .jasper | `jrxml`, `output` |
| `fill_empty` | Fill with JREmptyDataSource | `jrxml_or_jasper`, `params` |
| `fill_jdbc` | Fill with JDBC data source | `jrxml_or_jasper`, `jdbc_url`, `user`, `pass`, `params` |
| `fill_json` | Fill with JsonDataSource | `jrxml_or_jasper`, `json_file`, `select_expr`, `params` |
| `fill_csv` | Fill with JRCsvDataSource | `jrxml_or_jasper`, `csv_file`, `params` |
| `export_pdf` | Export filled report to PDF | `output_path` |
| `export_png` | Export filled report to PNG pages | `output_dir`, `zoom` |
| `export_html` | Export filled report to HTML | `output_path` |
| `export_csv` | Export filled report to CSV | `output_path` |
| `export_xls` | Export filled report to XLS | `output_path` |
| `export_xml` | Export filled report to XML | `output_path` |
| `export_text` | Export filled report to plain text | `output_path`, `page_width`, `page_height` |
| `fill_and_export` | Combined fill + export (atomic) | all fill args + all export args |
| `info` | Return report metadata | `jrxml_or_jasper` |

All fill actions accept a `params` array containing typed parameter objects (see section 6.5 for the type mapping). Each parameter is a JSON object with `name`, `type`, and `value` fields. The Java side deserializes each parameter into the correct Java type before placing it in the `HashMap<String, Object>` passed to `JasperFillManager`.

### Compile-on-demand

JasperBridge accepts either `.jrxml` or `.jasper` files. If a `.jrxml` is provided for filling, it compiles automatically (in memory). This matches JasperReports' `JasperFillManager.fillReport(JasperReport, ...)` pattern where the report object can be created from either format.

### Keeping the JasperPrint in memory

After filling, the Java side holds the `JasperPrint` object in a static field so that multiple export calls can be made without re-filling. This is important for the workflow where a user fills once and exports to multiple formats.

### JSON response format

```json
{
  "status": "ok",
  "action": "fill_jdbc",
  "page_count": 3,
  "details": { "fill_time_ms": 245, "query_rows": 42 }
}
```

```json
{
  "status": "error",
  "action": "fill_jdbc",
  "error_type": "java.sql.SQLException",
  "error_message": "Connection refused",
  "stacktrace": "..."
}
```

## 8. Export format capabilities

### Available with shipped JARs

| Format | Exporter class | JAR dependency | Status |
|---|---|---|---|
| PDF | `JRPdfExporter` | itext-2.1.7.js6.jar | Available |
| PNG (page images) | `JRGraphics2DExporter` + ImageIO | JDK built-in (AWT) | Available |
| HTML | `HtmlExporter` | JasperReports core | Available |
| CSV | `JRCsvExporter` | JasperReports core | Available |
| XLS | `JRXlsExporter` | JasperReports core | Available |
| XML | `JRXmlExporter` | JasperReports core | Available |
| Plain text | `JRTextExporter` | JasperReports core | Available |
| JSON metadata | `JsonMetadataExporter` | JasperReports core | Available |

### Not available (need additional JARs)

| Format | Required JARs | Notes |
|---|---|---|
| XLSX | Apache POI (poi-ooxml, poi-ooxml-schemas, xmlbeans) | Could add later |
| DOCX | Apache POI | Could add later |
| PPTX | Apache POI | Could add later |
| ODT | JasperReports ODF module | Could add later |
| RTF | JasperReports core (may work, needs testing) | Possible |

### Adding XLSX support later

XLSX is probably the most requested missing format. Adding it would require shipping 3 additional JARs (Apache POI ~8MB total). This is a realistic future enhancement but not required for v0.1.

## 9. Data source support

### v0.1 (ship these)

| Source | How it works |
|---|---|
| Empty | `JREmptyDataSource` — for static reports with no data |
| JDBC (PostgreSQL) | `DriverManager.getConnection()` with shipped postgresql-42.2.2.jar |
| Report parameters | `HashMap<String, Object>` passed at fill time |

### v0.2 (add later)

| Source | How it works |
|---|---|
| JSON file | `JsonDataSource(InputStream)` with optional select expression |
| CSV file | `JRCsvDataSource(File)` with column name mapping |

### Not planned

| Source | Why not |
|---|---|
| XML | Low demand on ChoreBoy, complex setup |
| JavaBean collections | Requires building Java objects, impractical via JNI |

## 10. Qt print preview and printing

### 10.1 Preview (preview.py)

The preview module provides `QPrintPreviewDialog` integration, rendering report pages as PNG images and displaying them in a native Qt dialog with zoom, pagination, and printing.

```python
def preview(page_images: list[str], title: str = "Report Preview"):
    """Show report page PNGs in a QPrintPreviewDialog."""
```

- Ensures QApplication exists (creates one if needed)
- Loads page PNG files as QPixmap
- Renders pages into QPrintPreviewDialog via `paintRequested` signal
- Scales pages to fit printer page rect while maintaining aspect ratio

### 10.2 Direct printing (printing.py)

The printing module provides direct-to-printer output via Qt's `QPrinter` and `QPrintDialog`. This mirrors the LO JasperReportManager's `setPrintAction(0)` / `setPrinter()` / `setShowDialog()` capabilities using Qt's native print infrastructure.

**v0.1 — basic printing with dialog:**

```python
def print_report(page_images: list[str], title: str = "Print Report"):
    """Open QPrintDialog and print report pages to the selected printer."""
```

- Opens `QPrintDialog` for printer selection
- Renders page PNGs to the selected printer via `QPainter`
- Returns `True` if printed, `False` if the dialog was cancelled

**v0.2 — advanced printer configuration:**

```python
def print_report(page_images: list[str],
                 printer: str = None,
                 copies: int = 1,
                 collate: bool = True,
                 duplex: bool = False,
                 show_dialog: bool = True,
                 title: str = "Print Report"):
    """Print report pages with optional printer configuration."""
```

- `printer` — target a specific printer by name (skip dialog if `show_dialog=False`)
- `copies` — number of copies
- `collate` — collate multi-copy output
- `duplex` — enable duplex (double-sided) printing
- `show_dialog` — when `False` with a named `printer`, print silently without user interaction

Qt printer discovery uses `QPrinterInfo.availablePrinters()` to validate named printers. If the requested printer is not found, raise `PrintError`.

### 10.3 Standalone PDF preview

For users who have existing PDF files (not generated by JasperReports), provide a utility that renders PDF pages to images and shows them in the same preview dialog. This depends on whether a PDF-to-image renderer is available in the runtime (Poppler, or Java-based rendering).

## 11. Implementation phases

### Phase 1: Core library (v0.1.0)

**Goal:** Users can compile, fill (empty + JDBC) with typed parameters including images, export (PDF + PNG), preview, and print reports.

| Step | Task | Files |
|---|---|---|
| 1.1 | Create library skeleton with `__init__.py`, `_version.py`, `errors.py` | 3 files |
| 1.2 | Port and refine `jni_helper.py` → `jvm.py` | 1 file |
| 1.3 | Implement `params.py` with `ImageParam`, `DateParam`, `TimeParam`, `DateTimeParam` wrappers and type serialization logic | 1 file |
| 1.4 | Write `JasperBridge.java` with compile, fill_empty, fill_jdbc, export_pdf, export_png, info actions and typed parameter deserialization (string, long, double, boolean, bytes, image_path, image_bytes, date, time, datetime) | 1 file |
| 1.5 | Compile `JasperBridge.java` to .class (Java 8 bytecode) | build step |
| 1.6 | Implement `compiler.py` (compile JRXML) | 1 file |
| 1.7 | Implement `filler.py` (fill with empty + JDBC, serialize typed params to JSON) | 1 file |
| 1.8 | Implement `exporter.py` (PDF + PNG export with `overwrite` kwarg) | 1 file |
| 1.9 | Implement `report.py` (Report class combining above) | 1 file |
| 1.10 | Implement `preview.py` (Qt print preview) | 1 file |
| 1.11 | Implement `printing.py` (Qt print dialog — basic, with dialog) | 1 file |
| 1.12 | Add `logging` integration across all modules under `jasper_bridge` logger | all files |
| 1.13 | Copy JARs into `lib/` | file copy |
| 1.14 | Write `docs/USAGE.md` | 1 file |
| 1.15 | End-to-end test on ChoreBoy | manual |

### Phase 2: Additional exports, data sources, and printing (v0.2.0)

| Step | Task |
|---|---|
| 2.1 | Add HTML export to JasperBridge.java + exporter.py |
| 2.2 | Add CSV export |
| 2.3 | Add XLS export (`JRXlsExporter`, no extra JARs needed) |
| 2.4 | Add plain text export |
| 2.5 | Add JSON data source support to filler.py |
| 2.6 | Add CSV data source support |
| 2.7 | Add advanced printing options (named printer, silent print, copies, collate, duplex) to `printing.py` |
| 2.8 | Implement `connections.py` — `ConnectionPool` for JDBC connection reuse |
| 2.9 | Write API reference docs |
| 2.10 | Write JRXML authoring guide for ChoreBoy |

### Phase 3: Polish and extras (v0.3.0)

| Step | Task |
|---|---|
| 3.1 | Add XLSX export (ship Apache POI JARs) |
| 3.2 | Report metadata/info API (parameters, fields, page size) |
| 3.3 | Subreport support and testing |
| 3.4 | Report parameter validation (check required params before filling) |
| 3.5 | Batch export (fill once, export to multiple formats) |
| 3.6 | Performance profiling and optimization |

## 12. JasperBridge.java design detail

The Java entry point handles all operations through a single `main(String[])` method. This keeps the JNI interface simple (one class, one method) while supporting all operations.

### State management

```java
public class JasperBridge {
    private static JasperPrint lastPrint = null;
    private static JasperReport lastReport = null;

    public static void main(String[] args) {
        String json = args[0];
        JSONObject cmd = new JSONObject(json);
        String action = cmd.getString("action");

        switch (action) {
            case "compile": handleCompile(cmd); break;
            case "fill_empty": handleFillEmpty(cmd); break;
            case "fill_jdbc": handleFillJdbc(cmd); break;
            case "export_pdf": handleExportPdf(cmd); break;
            case "export_png": handleExportPng(cmd); break;
            // ...
        }
    }
}
```

### Typed parameter deserialization

The `params` field in fill commands is a JSON array. Each element has `name`, `type`, and `value` fields. JasperBridge iterates the array and constructs the correct Java object for each entry:

```java
private static HashMap<String, Object> deserializeParams(ArrayNode params) {
    HashMap<String, Object> map = new HashMap<>();
    for (JsonNode p : params) {
        String name = p.get("name").asText();
        String type = p.get("type").asText();
        switch (type) {
            case "string":      map.put(name, p.get("value").asText()); break;
            case "long":        map.put(name, p.get("value").asLong()); break;
            case "double":      map.put(name, p.get("value").asDouble()); break;
            case "boolean":     map.put(name, p.get("value").asBoolean()); break;
            case "bytes":       map.put(name, Base64.getDecoder().decode(p.get("value").asText())); break;
            case "image_path":  map.put(name, ImageIO.read(new File(p.get("value").asText()))); break;
            case "image_bytes": map.put(name, ImageIO.read(new ByteArrayInputStream(
                                    Base64.getDecoder().decode(p.get("value").asText())))); break;
            case "date":        map.put(name, java.sql.Date.valueOf(p.get("value").asText())); break;
            case "time":        map.put(name, java.sql.Time.valueOf(p.get("value").asText())); break;
            case "datetime":    map.put(name, java.sql.Timestamp.valueOf(
                                    p.get("value").asText().replace("T", " "))); break;
        }
    }
    return map;
}
```

Image parameters use `javax.imageio.ImageIO` which is built into the JDK. The `image_path` type reads directly from disk; the `image_bytes` type decodes a base64 string into a `BufferedImage`. Both produce `java.awt.Image` objects compatible with JasperReports image parameters.

### JSON parsing without external deps

JasperReports ships Jackson JARs (jackson-core, jackson-databind, jackson-annotations 2.9.5) which we already include. JasperBridge can use Jackson for JSON parsing/generation, avoiding the need for additional libraries.

### Classpath at JVM boot

The JVM classpath is set once at boot time and includes:
- `jasper_bridge/java/` (JasperBridge.class)
- `jasper_bridge/lib/*.jar` (all JARs)

This means JasperBridge.class must be in the `java/` directory relative to the library root.

## 13. Versioning and distribution

### Version scheme

Semantic versioning: `MAJOR.MINOR.PATCH`

- `0.1.0` — initial release (compile, fill with typed params + images, PDF/PNG export, preview, basic print)
- `0.2.0` — additional exports (HTML, CSV, XLS, text), data sources (JSON, CSV), advanced printing, connection pool
- `0.3.0` — XLSX, subreports, metadata

### Distribution

The library is distributed as a folder (no pip, no wheel). Each project embeds its own copy of the `jasper_bridge/` directory alongside its source files.

```
/home/default/myproject/
├── jasper_bridge/          ← embedded library copy
├── main.py
└── reports/
    └── invoice.jrxml
```

Since the library lives inside the project folder, imports work without `sys.path` manipulation:

```python
from jasper_bridge import Report
```

## 14. Documentation plan

### docs/USAGE.md

Quick-start guide covering:
- Installation (copy folder)
- First report (hello world JRXML)
- Filling with database data
- Exporting to PDF
- Print preview
- Troubleshooting (JVM errors, classpath, JDBC)

### docs/API.md

Complete API reference for all public classes and functions with examples.

### docs/JRXML_GUIDE.md

Guide to writing JRXML report definitions for ChoreBoy:
- Page sizes (Letter, A4)
- Available fonts (DejaVu Sans, etc.)
- Parameters and fields
- SQL queries for CA database
- Grouping and sorting
- Conditional formatting
- Page headers/footers
- Subreports
- Common patterns (invoices, listings, summaries)

### docs/CHANGELOG.md

Version history with breaking changes, new features, and fixes.

## 15. Testing strategy

### Unit tests (dev machine)

- Test JSON command generation and response parsing
- Test Report class state machine (compile → fill → export)
- Test error handling and exception hierarchy
- Mock JVM calls for fast unit tests

### Integration tests (ChoreBoy)

- Compile hello_static.jrxml
- Fill with empty data source, export PDF + PNG
- Fill with JDBC (classicaccounting), export PDF
- Preview rendered pages in Qt dialog
- Test error cases (missing JRXML, bad JDBC credentials, invalid parameters)

### Acceptance criteria

The library is ready when a user can write this script and it works:

```python
from jasper_bridge import Report, ImageParam

report = Report("invoice.jrxml")
report.fill(jdbc="jdbc:postgresql://localhost:5432/classicaccounting",
            user="postgres", password="true",
            params={
                "CompNameAddr": "Acme Corp\n123 Main St",
                "CompLogo": ImageParam("/path/to/logo.png"),
                "TransID": 12345,
            })
report.export_pdf("invoice.pdf")
report.preview()
report.print()
```

## 16. Logging

The library logs through Python's standard `logging` module under the `jasper_bridge` logger hierarchy. No custom log file API is needed — users configure logging with normal Python handlers.

```python
import logging
logging.getLogger("jasper_bridge").setLevel(logging.DEBUG)
```

### What gets logged

| Logger name | Level | Content |
|---|---|---|
| `jasper_bridge.jvm` | INFO | JVM boot, attach, classpath |
| `jasper_bridge.jvm` | DEBUG | JNI function calls, fd-pipe capture |
| `jasper_bridge.compiler` | INFO | Compile start/finish, output path, file size |
| `jasper_bridge.filler` | INFO | Fill mode, data source, parameter count, page count, timing |
| `jasper_bridge.filler` | DEBUG | Serialized JSON command (with image data truncated) |
| `jasper_bridge.exporter` | INFO | Export format, output path, file size, timing |
| `jasper_bridge.preview` | DEBUG | Page image loading, dialog lifecycle |
| `jasper_bridge.printing` | INFO | Printer name, copies, dialog result |
| `jasper_bridge` | ERROR | All errors with full context and Java stacktrace when available |

### Java-side diagnostic output

`JasperBridge.java` writes diagnostic output to stderr (not stdout, which is reserved for the JSON response). The JNI fd-pipe mechanism captures stdout for the JSON response; stderr flows through to the Python process's stderr and is captured by the `jasper_bridge.jvm` logger at DEBUG level when possible.

## 17. Known risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| JVM SIGSEGV handler conflicts with Qt | Process crash | Initialize QApplication before any JVM-loaded code uses Qt fonts |
| One JVM per process | Cannot change classpath after boot | Include all JARs at boot; document limitation |
| JasperReports reflective-access warnings (Java 14) | Noisy console output | Cosmetic only; suppress with `--add-opens` JVM flags if possible |
| Large reports (1000+ pages) fill slowly | Slow export | Document as known limitation; suggest pagination |
| PostgreSQL 9.3.6 query compatibility | Old SQL features only | Document which SQL features are available |
| JasperReports 6.7.0 is old | Missing newer features | Sufficient for current needs; upgrade path is to swap JARs |
| Large image params via base64 | Memory spike for big logos/photos | Prefer `image_path` type (Java reads file directly); warn in docs about base64 overhead for images > 1MB |
| Printer not available on ChoreBoy | `report.print()` fails silently | `PrintError` raised with discoverable printer list; preview always works as fallback |

## 18. Resolved questions

1. **Library name:** `jasper_bridge` — confirmed.

2. **Library location on ChoreBoy:** Each project embeds its own copy of the library. No shared location. This avoids coordinated updates and keeps projects self-contained.

3. **ChoreBoy Code Studio integration:** Not needed at this time. The library is a standalone import — no IDE menu items, project templates, or runner awareness required.

4. **JRXML editor support:** Out of scope for this plan. Syntax highlighting and validation for JRXML files is tracked separately in `docs/USER_REQUESTS_TODO.md`.

5. **Report designer:** Not needed. ChoreBoys typically have a visual report designer (Jaspersoft Studio) already installed. No need to reimplement one.

## 19. Recommended next steps

1. **Validate the database-driven path.** Run `simple_query.jrxml` through probe 6 to confirm JDBC-filled reports produce actual data pages. This hasn't been tested yet.

2. **Build JasperBridge.java.** The single Java entry point that replaces all probe helper classes.

3. **Implement Phase 1 (v0.1.0).** Following the steps in section 11.

4. **Ship to ChoreBoy for user testing.** Copy the library and a sample project to ChoreBoy, have a real user try it.
