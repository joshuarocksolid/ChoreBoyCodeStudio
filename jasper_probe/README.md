# JasperReports ChoreBoy Probe Bundle

Self-contained test bundle to determine whether JasperReports can compile,
fill, export, and print CA reports on the ChoreBoy system via FreeCAD AppRun.

## What's included

| File/Dir | Purpose |
|---|---|
| `lib/` | JasperReports 6.7.0, Groovy, ECJ, iText, PostgreSQL JDBC driver, and dependencies |
| `tools/` | Pre-compiled Java helper classes (HelloJava, JdbcProbe, JasperCompileProbe, JasperFillExport) |
| `test_reports/` | Test JRXML files (hello_static.jrxml, simple_query.jrxml) |
| `probe1_java_runtime.py` | Is Java available on ChoreBoy? |
| `probe1b_java_deep_search.py` | Deep search: symlink chains, libjvm.so, permissions, ACLs |
| `probe2_jvm_bootstrap.py` | **JNI path:** Boot JVM in-process via ctypes (bypasses blocked java binary) |
| `jni_helper.py` | **Shared JNI module:** boots/reuses the JVM, provides `call_java_main()` |
| `probe3_jni_exec.py` | **JNI path:** Call HelloJava.main() via jni_helper (validates helper works) |
| `probe4_jni_jdbc.py` | **JNI path:** Call JdbcProbe.main() via jni_helper (PostgreSQL JDBC) |
| `probe5_jni_compile.py` | **JNI path:** Call JasperCompileProbe.main() via jni_helper (JRXML compile) |
| `probe6_jni_fill_export.py` | **JNI path:** Call JasperFillExport.main() via jni_helper (PDF + PNG export) |
| `probe7_qt_print.py` | Can Qt show print preview with report pages? |
| `probe2_jar_discovery.py` | *(Subprocess path, superseded)* find JasperReports JARs |
| `probe3_java_exec.py` | *(Subprocess path, superseded)* execute Java class via subprocess |
| `probe4_jdbc_connect.py` | *(Subprocess path, superseded)* JDBC via subprocess |
| `probe5_jasper_compile.py` | *(Subprocess path, superseded)* JRXML compile via subprocess |
| `probe6_jasper_fill_export.py` | *(Subprocess path, superseded)* fill+export via subprocess |

## How to run on ChoreBoy

### 1. Copy the bundle

Copy the entire `jasper_probe/` folder to ChoreBoy via USB, for example:

```
/home/default/jasper_probe/
```

### 2. Run probes in order

#### Option A: Via ChoreBoy Code Studio Run button

1. Open `jasper_probe/` as a project in ChoreBoy Code Studio
2. Select `probe1_java_runtime.py` in the file tree
3. Click **Run**
4. View results in the Console pane
5. Repeat for probe2 through probe7

#### Option B: Via Python Console

```python
import os, runpy
root = "/home/default/jasper_probe"
os.chdir(root)
runpy.run_path("probe1_java_runtime.py", run_name="__main__")
```

Change the filename to run each subsequent probe.

### 3. Probe sequence (ChoreBoy -- JNI path)

Probes 1, 1B, and 2 confirmed that java binary execution is blocked by
mandatory access control, but `libjvm.so` loads via ctypes and the JVM
boots in-process. All subsequent probes use the JNI path.

**Important:** If you previously ran `probe2_jvm_bootstrap.py` in this
REPL session (which calls `DestroyJavaVM`), restart the Python Console
first. The JNI probes (3-6) use `jni_helper.py` which never destroys the
JVM and reuses it across probes via `JNI_GetCreatedJavaVMs`.

```
Recommended run order:
1. Restart Python Console (clean JVM state)
2. probe3_jni_exec.py       -- validates jni_helper works
3. probe4_jni_jdbc.py        -- tests PostgreSQL JDBC
4. probe5_jni_compile.py     -- compiles JRXML to .jasper
5. probe6_jni_fill_export.py -- fills report, exports PDF + PNG
6. probe7_qt_print.py        -- Qt print preview (no JVM needed)
```

---

**Probe 3 -- Java execution via JNI (run first):**
```python
import os, runpy
os.chdir("/home/default/jasper_probe")
runpy.run_path("probe3_jni_exec.py", run_name="__main__")
```
Boots the JVM via `jni_helper` and calls `HelloJava.main()`. Validates
that the shared JNI module works before running heavier probes.

**Probe 4 -- JDBC connection via JNI:**
```python
runpy.run_path("probe4_jni_jdbc.py", run_name="__main__")
```
Calls `JdbcProbe.main(host, port, user, pass, db)` via JNI. Tests
PostgreSQL connectivity through JDBC.

**Probe 5 -- JRXML compile via JNI:**
```python
runpy.run_path("probe5_jni_compile.py", run_name="__main__")
```
Calls `JasperCompileProbe.main(jrxml, jasper)` via JNI. Compiles
hello_static.jrxml into a .jasper binary.

**Probe 6 -- Fill and export via JNI:**
```python
runpy.run_path("probe6_jni_fill_export.py", run_name="__main__")
```
Calls `JasperFillExport.main()` via JNI. Fills the report and exports to
PDF and PNG page images (both static and JDBC modes).

**Probe 7 -- Qt print preview (independent, best after probe 6):**
```python
runpy.run_path("probe7_qt_print.py", run_name="__main__")
```
Opens a QPrintPreviewDialog showing report page images.

---

#### Discovery probes (already completed, kept for reference)

**Probe 1 -- Java runtime:**
```python
runpy.run_path("probe1_java_runtime.py", run_name="__main__")
```
Finds the Java binary and tests subprocess execution. (Result: blocked)

**Probe 1B -- Java deep search:**
```python
runpy.run_path("probe1b_java_deep_search.py", run_name="__main__")
```
Symlink chains, libjvm.so search, permissions. (Result: libjvm.so works)

**Probe 2 -- JVM Bootstrap:**
```python
runpy.run_path("probe2_jvm_bootstrap.py", run_name="__main__")
```
Boots JVM via JNI_CreateJavaVM. (Result: full success, JNI version 10.0)

### 4. Check results

Each probe prints results to stdout and writes a `probeN_results.txt` file
in the `results/` directory. Probe 6 also generates PDF and PNG files there.

## Configuration

Probes 4 and 6 connect to the CA PostgreSQL database. Edit these values
at the top of each probe script if your credentials differ:

```python
PG_HOST = "localhost"
PG_PORT = "5432"
PG_USER = "postgres"
PG_PASSWORD = "true"
PG_DATABASE = "classicaccounting"
```

## Decision matrix

### Path A: Subprocess pipeline (probes 1 → 3)

| Probe 1 | Probe 3 | Verdict |
|---|---|---|
| PASS | PASS | Java subprocess works. Continue to probes 4-7. |
| PASS | FAIL | Java binary exists but execution is blocked. Switch to Path B. |
| FAIL | n/a | Java not available. Switch to Path B. |

### Path B: JNI pipeline (probes 1B → 2)

| Probe 1B libjvm.so | Probe 2 JNI_CreateJavaVM | Probe 2 HelloJava | Verdict |
|---|---|---|---|
| Loads | Returns 0 | Executes | **JNI path works. Rewrite probes 3-6 for JNI.** |
| Loads | Returns 0 | Fails | JVM boots, debug classpath/class loading |
| Loads | Returns negative | n/a | MAC blocks JVM creation. Pivot to pure-Python. |
| Not found | n/a | n/a | Java fully blocked. Pivot to pure-Python. |

### Full pipeline (probes 4-7, after Path A or B succeeds)

| Probe 4 | Probe 5 | Probe 6 | Probe 7 | Verdict |
|---|---|---|---|---|
| PASS | PASS | PASS | PASS | **Full Jasper-to-Qt-Print pipeline works. Ship it.** |
| PASS | PASS | PASS | FAIL | Java pipeline works, Qt print needs investigation |
| PASS | PASS | FAIL | any | Compile works but export fails -- check JARs |
| PASS | FAIL | any | any | JARs found but compile fails -- version issue |
| FAIL | any | any | any | Java runs but JDBC fails -- check creds/service |

If Path A (subprocess) works, the path forward is:
**Java subprocess for JasperReports + Qt QPrintPreviewDialog for viewing/printing.**

If Path B (JNI) works, the path forward is:
**In-process JVM via ctypes JNI for JasperReports + Qt QPrintPreviewDialog for viewing/printing.**

## What this proves

The key question from Reuben was two-fold:

1. "No JasperReports extension" -- We don't need the LibreOffice extension.
   JasperReports is a Java library. It can be called via subprocess (Path A)
   or loaded in-process via JNI (Path B). Path B is required on ChoreBoy
   because java binary execution is blocked by mandatory access control.

2. "No permission to launch external programs such as PDF viewer" --
   QPrintPreviewDialog is NOT an external program. It's a built-in PySide2
   widget that runs inside our already-running Qt application. It provides
   print preview, page navigation, and printing via the system print dialog.

## Shipped JARs

All JARs are from the existing JasperReportManager-1.2.oxt LibreOffice
extension (version 6.7.0 where available):

- jasperreports-6.7.0.jar (core)
- ecj-4.4.2.jar (Eclipse compiler for on-the-fly JRXML compilation)
- groovy-all-2.4.12.jar (Groovy for JRXML expressions)
- commons-beanutils, commons-collections, commons-digester, commons-logging
- itext-2.1.7.js6.jar (PDF export)
- postgresql-42.2.2.jar (JDBC driver)
- castor-core, castor-xml (XML binding)
- jackson-core, jackson-databind, jackson-annotations (JSON)

## Pre-compiled Java tools

The Java helper classes in `tools/` are compiled targeting Java 8 bytecode
for maximum compatibility. Source files (.java) are included for reference.

| Class | Purpose |
|---|---|
| HelloJava | Prints version info. Confirms Java subprocess works. |
| JdbcProbe | Connects to PostgreSQL via JDBC and runs test queries. |
| JasperCompileProbe | Compiles a JRXML to a .jasper binary. |
| JasperFillExport | Fills a report and exports to PDF and PNG page images. |
