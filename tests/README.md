# Test Layout

This directory is intentionally scaffolded before implementation code lands.

- `unit/` holds fast tests for pure business logic and small contracts.
- `integration/` holds cross-module tests for process, filesystem, and protocol behavior.
- `runtime_parity/` holds tests that require the FreeCAD AppRun runtime on a dev machine.

No executable tests are added yet by design. Real tests begin when implementation starts.
