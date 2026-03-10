# Changelog

All notable changes to ChoreBoy Code Studio are documented in this file.

## [0.2] — 2026-03-09

### Packaging and Installation

- Add packaging script (`package.py`) and PySide2 GUI installer for ChoreBoy target systems.
- Add desktop entry launcher for the installer wizard.
- Switch distribution archive from tar.gz to password-protected zip.
- Reject excluded and invalid entrypoint paths during packaging.

### Editor Features

- Add auto-save setting with UI toggle and signal integration.
- Promote preview tabs to permanent tabs on first content edit.
- Implement system trash-compatible delete behavior for the project tree.
- Enhance syntax highlighting with dark/light theme-aware default palettes.
- Expand Treesitter token coverage for JavaScript, Python, and SQL (variables, properties, keywords, operators).
- Track document revisions in the Treesitter highlighter for more accurate line counting.

### Security Hardening

- Block plugin install path traversal inputs.
- Constrain plugin runtime entrypoint paths.
- Enforce runtime plugin trust verification at handler load.
- Harden plugin exporter archive path component validation.
- Validate project tree names and move edge cases.

### Performance

- Optimize run log append scalability for large output.
- Prune excluded directories during find-in-files walk.
- Optimize module completion no-match latency with indexed cache.
- Harden supervisor against stale exit races.
- Avoid runtime import probes during routine lint.

### Bug Fixes

- Fix Python console REPL output event handling.
- Fix plugin menu contribution registration.
- Fix pytest UI actions for AppRun runtime.
- Use shared non-native file dialog helpers across all dialogs.
- Reject shared temp root as importable project path.
- Scope active log path to the configured state root.
- Include active fallback app log in support bundles.
- Fix installer issues.

### Documentation

- Add complete user program manual with chapters, screenshots, and build pipeline.
- Add plugin authoring guide.
- Update DISCOVERY.md with SQLAlchemy 2.0.48 validation results and production library details.
- Add PostgreSQL `libpq.so` loading documentation (AppArmor constraints).
- Publish end-to-end smoke test report, performance audit report, and adversarial code audit.
- Add development environment setup documentation.

### Developer Experience

- Add pyright configuration and VSCode settings for Python analysis.
- Establish Cursor rules for documentation navigation, TDD workflow, testing strategy, Python 3.9 compatibility, UI theme compatibility, no-hidden-folders constraint, and hard-cutover refactor policy.
- Vendor directory excluded from git tracking with auto-population instructions.

## [0.1] — 2026-03-06

Initial release of ChoreBoy Code Studio.

- Project-first editor and runner for the FreeCAD AppRun runtime.
- Multi-file project management with templates (Qt app, utility script, headless tool).
- Integrated Python runner with subprocess lifecycle, stdout/stderr capture, and exit code reporting.
- Python debug runner with breakpoint support.
- Python REPL console.
- Syntax highlighting (Treesitter-based) for Python, JavaScript, SQL, and more.
- Code intelligence: completion, diagnostics, quick fixes, symbol indexing.
- Find-in-files and go-to-line navigation.
- Configurable editor settings (font, indentation, format-on-save, trailing whitespace).
- Global and per-project settings with layered override model.
- Light and dark theme support with system-follow mode.
- Customizable keybindings.
- Plugin system: install, trust, enable/disable, menu contributions, runtime hosting.
- Run history with persistent manifests and log files.
- Session persistence (open tabs, cursor positions, layout).
- Recent projects list.
- SQLite-backed state index.
- Support bundle export for diagnostics.
- Example project (CRUD showcase).
