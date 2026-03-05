# Performance Profiling

## Scope

This document defines the profiling workflow for v0.3 fill/export performance.

## Profiling harness

Use:

```bash
python3 jasper_bridge/tools/profile_fill_export.py \
  --jrxml jasper_probe/test_reports/hello_static.jrxml \
  --output-dir /tmp/jasper_bridge_profile \
  --iterations 5 \
  --zoom 2.0
```

For JDBC-backed profiling:

```bash
python3 jasper_bridge/tools/profile_fill_export.py \
  --jrxml jasper_probe/test_reports/simple_query.jrxml \
  --output-dir /tmp/jasper_bridge_profile_jdbc \
  --iterations 5 \
  --zoom 2.0 \
  --jdbc jdbc:postgresql://localhost:5432/classicaccounting \
  --user postgres \
  --password true
```

## Captured metrics

- average fill time
- average PDF export time
- average PNG export time
- average page count
- per-run timing breakdown

## Analysis checklist

1. Compare empty-data-source and JDBC timings.
2. Compare zoom levels for PNG export impact.
3. Track JVM cold start vs repeated run behavior.
4. Track impact of parameter payload size, especially base64 images.

## Current execution status

The profiling harness is implemented and ready for runtime execution. Profiling runs were not executed in this pass because test/acceptance execution was explicitly disabled for the session.
