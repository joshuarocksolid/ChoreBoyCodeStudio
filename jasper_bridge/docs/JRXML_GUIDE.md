# JRXML Guide for ChoreBoy

## Runtime model

- Jasper execution runs through the in-process JVM bridge (`jasper_bridge`).
- Reports are compiled/fill/exported from Python using JSON commands.
- Keep report assets in your project folder for folder-copy portability.

## File organization

Recommended layout:

```text
my_project/
  jasper_bridge/
  reports/
    invoice.jrxml
    subreports/
  assets/
    logo.png
```

Use absolute or project-relative paths from Python code.

## Parameters

Declare parameters in JRXML with stable names and matching Java-compatible types.

Python values are mapped as:

- `str` -> `java.lang.String`
- `int` -> `java.lang.Long`
- `float` -> `java.lang.Double`
- `bool` -> `java.lang.Boolean`
- `bytes` -> `byte[]`
- `ImageParam` -> `java.awt.Image`
- `DateParam` -> `java.sql.Date`
- `TimeParam` -> `java.sql.Time`
- `DateTimeParam` -> `java.sql.Timestamp`

## Data source strategies

### Empty data source

Use for static forms and single-page templates.

```python
report.fill(params={"TITLE": "Invoice"})
```

### JDBC data source

Use for query-backed reports.

```python
report.fill(
    jdbc="jdbc:postgresql://localhost:5432/classicaccounting",
    user="postgres",
    password="true",
)
```

### JSON data source

```python
report.fill(json_file="data/invoice.json", select_expression="records")
```

### CSV data source

```python
report.fill(csv_file="data/invoice.csv")
```

## Export targets

- PDF for distribution
- PNG for page rendering/preview pipelines
- HTML/CSV/XLS/XML/TEXT for integration and diagnostics

Use overwrite control when writing into persistent output folders.

## Page and rendering guidance

- Use predictable page sizes in JRXML (`A4`, `Letter`, or explicit dimensions).
- Keep image sizes reasonable; prefer `ImageParam(path=...)` over large in-memory image bytes.
- For text exports, tune `page_width` and `page_height` to your target output format.

## SQL guidance

- Keep queries compatible with PostgreSQL 9.3.x constraints in ChoreBoy deployments.
- Bind user-provided data through report parameters instead of string-concatenating SQL.
- Prefer explicit field aliases so JRXML field mappings remain stable.

## Diagnostics

- Enable `logging.getLogger("jasper_bridge").setLevel(logging.DEBUG)` while integrating reports.
- Java exceptions are returned as structured errors with stacktraces.
- If export fails with missing fill state, ensure `fill()` ran first in the same process.

## Subreport workflows

Use `subreport_dir` when your master report expects a `SUBREPORT_DIR` parameter:

```python
report.fill(
    jdbc="jdbc:postgresql://localhost:5432/classicaccounting",
    user="postgres",
    password="true",
    subreport_dir="reports/subreports",
)
```

`jasper_bridge` will auto-inject `SUBREPORT_DIR` when it is not already present in `params`.

## Parameter validation mode

Use `validate_params=True` to validate required report parameters and declared Java types before fill:

```python
report.fill(params={"TITLE": "Invoice"}, validate_params=True)
```

Use `report.info()` to inspect metadata returned from Jasper, including parameters, fields, and query text.

## Common pitfalls

- Missing jar files in `jasper_bridge/lib/`
- Wrong JDBC credentials or unreachable host
- Parameter name mismatch between JRXML and Python dict keys
- Calling export/preview/print before fill
