# Release Hardening Checklist

## Implementation completeness

- [x] v0.1 core API and Java bridge actions implemented
- [x] v0.2 export/data-source expansion implemented
- [x] v0.3 advanced API features implemented
- [x] Runtime jar set included in `jasper_bridge/lib/`
- [x] Java bridge compiled to `jasper_bridge/java/JasperBridge.class`

## API/doc consistency

- [x] `USAGE.md` updated
- [x] `API.md` updated
- [x] `JRXML_GUIDE.md` updated
- [x] `CHANGELOG.md` updated through 0.3.0
- [x] Performance workflow documented in `PERFORMANCE.md`

## Manual runtime validation lane

- [ ] End-to-end static report fill/export on target runtime
- [ ] End-to-end JDBC report fill/export on target runtime
- [ ] Preview dialog smoke run
- [ ] Print dialog smoke run
- [ ] New export format smoke run (HTML/CSV/XLS/XML/TEXT/XLSX)
- [ ] Batch export smoke run

Manual runtime validation was intentionally not executed in this implementation pass because test/acceptance execution was explicitly disabled for the session.
