# Changelog

## 0.3.0

- Added XLSX export action (`export_xlsx`) with Apache POI runtime dependencies.
- Expanded `info` action metadata to include parameters, fields, and query details.
- Added `Report.info()` metadata API.
- Added optional pre-fill parameter validation with `validate_params=True`.
- Added subreport convenience support through `subreport_dir` injection.
- Added compound `fill_and_export` Java action and `Report.export_all()` Python API.
- Added performance profiling harness and release hardening documentation.

## 0.2.0

- Added new Java bridge actions for HTML, CSV, XLS, text, and XML export.
- Added JSON and CSV data source fill actions.
- Added Python exporter APIs: `export_html`, `export_csv`, `export_xls`, `export_text`, `export_xml`.
- Added matching `Report` methods for all new export formats.
- Extended `print_report` with printer selection, copy count, collation, duplex, and dialog control options.
- Added `ConnectionPool` helper for named JDBC credential storage.
- Added API reference and JRXML authoring guide.

## 0.1.0

- Added standalone `jasper_bridge` package structure with public API exports.
- Added full exception hierarchy with optional Java stacktrace propagation.
- Added JNI JVM lifecycle manager with lazy boot, attach/reuse, classpath assembly, and Java main invocation.
- Added unified `JasperBridge.java` command entrypoint and compiled `JasperBridge.class`.
- Added typed parameter wrappers and serialization for strings, numbers, booleans, bytes, images, and date/time types.
- Added compiler, filler, and exporter modules for JRXML compile, fill, PDF export, and PNG page export.
- Added `Report` facade with compile/fill/export/preview/print workflows and convenience helpers.
- Added Qt preview and printing integrations for rendered page images.
- Added required JasperReports/JDBC runtime jars under `jasper_bridge/lib/`.
- Added initial user-facing usage documentation.
