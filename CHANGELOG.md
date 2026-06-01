# Changelog

All notable user-facing changes to ChoreBoy Code Studio are documented here.

Release tags: `v0.1`, `v0.2`.

## [Unreleased]

### Documentation

- Documentation consistency remediation: unified test checkpoints, PRD shortcuts, four-theme manual coverage, and missing doc index files.

## [0.2] - 2026-03-09

Tag: `v0.2`

### Added

- Test Explorer activity with discovery, run one/all, rerun failed, and navigate-to-test.
- Run configurations UI with named configs, default argv, and status-bar active-config indicator.
- Welcome / runtime onboarding flows and Runtime Center.
- High Contrast Light and High Contrast Dark theme modes with per-scope syntax color overrides.
- Markdown preview, split view, and toggle shortcuts for `.md` files.
- Local history and draft recovery workflows.

### Changed

- Shell/runner integration hardening for preflight, stop/restart, and theme-safe panels.
- Fast test shard (~30 s agent loop) with `slow` marker for subprocess/debug tests.

## [0.1] - Initial MVP

Tag: `v0.1`

### Added

- Editor + separate runner process architecture.
- Project open/edit/save, run log, problems panel, and basic debug support.
- Project templates (Qt app, headless tool, utility script).
- Plugin platform foundation and bundled workflow plugins.
- Visible project metadata (`cbcs/`) and global state (`choreboy_code_studio_state/`).
