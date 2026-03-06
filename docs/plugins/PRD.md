# ChoreBoy Code Studio — Plugin Platform PRD

## 1. Goal

Ship a modern plugin platform that lets advanced users extend Code Studio without bloating the core editor experience.

## 2. Confirmed product decisions

1. v1 includes runtime code plugins.
2. Publisher signing is not required in v1.
3. Per-project plugin pinning and overrides ship in phase 2.

## 3. Platform model

Plugin platform has two extension types:

* Declarative contributions
* Runtime code plugins

Runtime plugin code runs in a dedicated plugin host process. Editor process remains isolated from plugin runtime failures.

## 4. Distribution and install model

* Offline-first package install from local folder/zip
* Filesystem-based plugin registry and logs under visible global state directories
* Explicit install validation before activation

## 5. Manifest contract

Each plugin provides `plugin.json` with:

* `id`, `name`, `version`
* `api_version`
* `engine_constraints`
* `activation_events`
* `capabilities`
* `contributes`
* runtime entrypoint metadata for runtime plugins

## 6. Lifecycle

1. Discover
2. Parse and validate manifest
3. Compatibility check
4. Install/enable
5. Activate on event
6. Disable/uninstall
7. Quarantine after repeated failures

## 7. Safety model

* Permission/trust prompt for runtime plugins
* Safe mode startup with all plugins disabled
* Failure quarantine and explicit re-enable flow
* Actionable per-plugin logs and diagnostics

## 8. Share workflow

* Installed plugins can be exported as local `.cbcs-plugin.zip` bundles.
* Export/import remains filesystem-first for USB transfer workflows.

## 9. Phase plan

## Phase H00 (completed): Pre-plugin stabilization

* Settings service centralization
* Runtime command/action registration seam
* Shared host process manager
* Typed shell event contracts
* `cbcs/` visibility in project tree

## Phase H01: Manifest + discovery/index

* Implement manifest schema and parser
* Add compatibility index and diagnostics

## Phase H02: Installer + registry

* Install/uninstall/enable/disable/update
* Atomic registry persistence

## Phase H03: Plugin Manager UX

* Plugin list/details panel
* Enable/disable/install/remove controls

## Phase H04: Declarative contributions

* Menu/command/keybinding/event-hook contribution points
* Validation and deterministic load behavior

## Phase H05: Runtime plugin host + IPC

* Dedicated host process
* Structured request/response/event protocol
* Activation event routing

## Phase H06: Safety controls

* Safe mode
* Crash quarantine
* Recovery workflows

## Phase H07: Docs + author contracts

* Authoring guide
* API reference
* Versioning and compatibility policy

## 10. Acceptance coverage

Plugin platform acceptance is tracked in:

* AT-37 install flow
* AT-38 runtime isolation
* AT-39 enable/disable lifecycle
* AT-40 safe mode + quarantine
* AT-41 declarative contributions
* AT-42 compatibility enforcement
