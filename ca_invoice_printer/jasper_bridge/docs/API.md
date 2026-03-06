# jasper_bridge API Reference

## Top-level exports

```python
from jasper_bridge import (
    Report,
    ImageParam,
    IntegerParam,
    DateParam,
    TimeParam,
    DateTimeParam,
    ConnectionPool,
    compile_jrxml,
    quick_pdf,
    preview_pdf,
    jvm,
)
```

## Errors

- `JasperBridgeError`
- `JVMError`
- `CompileError`
- `FillError`
- `DataSourceError`
- `ParameterError`
- `ExportError`
- `PrintError`

Java-originated failures can include `java_stacktrace`.

## Parameter wrappers

- `ImageParam(path=None, *, data=None)`
- `IntegerParam(value)`
- `DateParam(year, month, day)`
- `TimeParam(hour, minute, second)`
- `DateTimeParam(year, month, day, hour, minute, second)`

## Compiler API

- `compile_jrxml(jrxml_path: str, output_path: str = None) -> str`

## Report class

### Constructor

- `Report(jrxml_path: str)`

### Lifecycle

- `compile(output: str = None) -> str`
- `fill(params=None, jdbc=None, user=None, password=None, json_file=None, select_expression=None, csv_file=None) -> dict`
  - v0.3 additions: `subreport_dir=None`, `validate_params=False`

### Exports

- `export_pdf(path: str, overwrite: bool = True) -> str`
- `export_png(path: str, zoom: float = 1.0, overwrite: bool = True) -> list[str]`
- `export_html(path: str, overwrite: bool = True) -> str`
- `export_csv(path: str, overwrite: bool = True) -> str`
- `export_xls(path: str, overwrite: bool = True) -> str`
- `export_text(path: str, page_width: int = 120, page_height: int = 60, overwrite: bool = True) -> str`
- `export_xml(path: str, overwrite: bool = True) -> str`
- `export_xlsx(path: str, overwrite: bool = True) -> str`

### Preview and print

- `preview(title: str = "Report Preview") -> None`
- `print(title: str = "Print Report", printer=None, copies=1, collate=False, duplex=False, show_dialog=True) -> bool`
- `info(refresh: bool = False) -> dict`
- `export_all(exports: list[dict], ..., validate_params=False) -> dict`

### Properties

- `is_compiled: bool`
- `is_filled: bool`
- `page_count: int`

## Convenience functions

- `quick_pdf(jrxml_path: str, output_path: str, **fill_kwargs) -> str`
- `preview_pdf(pdf_path: str) -> None`

## Connection pool

`ConnectionPool` stores named JDBC credentials for convenience:

- `add(connection_id, jdbc, user, password)`
- `remove(connection_id)`
- `has(connection_id)`
- `get(connection_id) -> dict`
- `list_ids() -> list[str]`
- `clear()`

Use with `Report.fill(**pool.get("name"))`.

### Batch export spec format

Each entry in `exports` for `export_all` uses:

```python
{"format": "pdf", "output_path": "out/report.pdf"}
{"format": "png", "output_dir": "out/pages", "zoom": 2.0}
{"format": "xlsx", "output_path": "out/report.xlsx"}
{"format": "text", "output_path": "out/report.txt", "page_width": 120, "page_height": 60}
```

## JVM module

- `jvm.ensure_jvm(lib_root: str = None) -> tuple`
- `jvm.call_java_main(env_ptr, class_name: str, args: list[str]) -> str`
- `jvm.status() -> str`
- `jvm.java_version() -> str`
- `jvm.classpath() -> list[str]`
