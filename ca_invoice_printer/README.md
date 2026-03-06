# CA Invoice Printer Demo

CA Invoice Printer is a desktop demo app for `jasper_bridge`.
It is both:
- a practical invoice preview/print tool for Classic Accounting data
- a feature coverage app used to confirm `jasper_bridge` is working end-to-end

## What this project is

This app connects to a PostgreSQL Classic Accounting database, lets you pick invoices, and generates JasperReports output with a Qt UI.

The app now has three tabs:
- **Invoices**: JDBC invoice workflow (connect, search, preview, print, export)
- **Standalone Reports**: no-DB report testing for JSON/CSV/empty data sources and typed parameters
- **System**: runtime diagnostics for JVM and classpath

## What it demonstrates

The demo exercises most `jasper_bridge` capabilities:
- report compile, fill, preview, print
- print options (copies, collate, duplex)
- export formats (PDF, HTML, CSV, XLS, XLSX, text, XML, PNG in batch export)
- data sources (JDBC, JSON, CSV, empty)
- typed params (`ImageParam`, `DateParam`, `TimeParam`, `DateTimeParam`)
- `validate_params=True` flows
- batch export with `export_all`
- report metadata via `info()`
- JVM diagnostics (`status`, `java_version`, `classpath`)

## How to run

From the repository root:

```bash
/opt/freecad/AppRun -c "import os,runpy,sys;root=os.path.abspath('.');sys.path.insert(0,root);runpy.run_path(os.path.join(root,'ca_invoice_printer','main.py'), run_name='__main__')"
```

## Requirements

- FreeCAD AppRun runtime with PySide2 available
- `jasper_bridge` Java dependencies under `jasper_bridge/lib/`
- PostgreSQL Classic Accounting database (for the **Invoices** tab)
- JRXML templates in `ca_invoice_printer/reports/`

## Project layout

- `main.py` - app window and tab container
- `invoice_tab.py` - database invoice workflow UI
- `standalone_tab.py` - standalone report testing UI
- `system_tab.py` - JVM and classpath diagnostics
- `printer.py` - invoice fill/preview/print/export helpers
- `db.py` - PostgreSQL query helpers
- `reports/CustomerInvoice.jrxml` - classic invoice template
- `reports/demo_params.jrxml` - standalone typed-parameter demo template
- `reports/sample_data.json` and `reports/sample_data.csv` - sample data source files
