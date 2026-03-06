# jasper_bridge Usage

## Installation

Copy the `jasper_bridge/` folder into your project root:

```text
my_project/
  jasper_bridge/
  main.py
  reports/
```

No pip install step is required.

## Quick start

```python
from jasper_bridge import Report

report = Report("jasper_probe/test_reports/hello_static.jrxml")
report.fill()
report.export_pdf("output/hello_static.pdf")
```

## JDBC fill

```python
from jasper_bridge import Report

report = Report("jasper_probe/test_reports/simple_query.jrxml")
report.fill(
    jdbc="jdbc:postgresql://localhost:5432/classicaccounting",
    user="postgres",
    password="true",
)
report.export_pdf("output/simple_query.pdf")
```

## Typed parameters

```python
from jasper_bridge import DateParam, ImageParam, Report

report = Report("reports/invoice.jrxml")
report.fill(
    params={
        "COMPANY_NAME": "Acme Corp",
        "LOGO": ImageParam("assets/logo.png"),
        "INVOICE_DATE": DateParam(2026, 3, 5),
        "TOTAL": 42.5,
        "PAID": False,
    }
)
report.export_pdf("output/invoice.pdf")
```

## Export formats

v0.1 supports:

- PDF via `report.export_pdf(path)`
- PNG pages via `report.export_png(output_dir, zoom=1.0)`

## Preview and print

```python
from jasper_bridge import Report

report = Report("jasper_probe/test_reports/hello_static.jrxml")
report.fill()
report.preview(title="Report Preview")
report.print(title="Print Report")
```

## JVM diagnostics

```python
from jasper_bridge import jvm

print(jvm.status())
print(jvm.java_version())
print(jvm.classpath())
```

## Error handling

```python
from jasper_bridge import CompileError, FillError, Report

try:
    report = Report("reports/example.jrxml")
    report.fill()
except CompileError as exc:
    print("Compile failed:", exc)
except FillError as exc:
    print("Fill failed:", exc)
```

## Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("jasper_bridge").setLevel(logging.DEBUG)
```

## Troubleshooting

- `JVMError` at startup:
  - confirm `libjvm.so` exists on the system
  - confirm required jars exist under `jasper_bridge/lib/`
- `DataSourceError` during JDBC fill:
  - verify connection URL, username, and password
  - verify PostgreSQL server reachability
- `ExportError` before export:
  - call `fill()` first so Java-side `lastPrint` state is populated

## License

`jasper_bridge` is licensed under the MIT License.
See `../LICENSE`.

Third-party dependency notices are listed in `../THIRD_PARTY_NOTICES.md`.
