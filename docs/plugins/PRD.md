# ChoreBoy Code Studio — Plugin Platform PRD

## 1. Goal

Ship a provider-based plugin platform that makes Python workflows extensible without
turning Code Studio into an unconstrained desktop-IDE extension host.

The platform must preserve ChoreBoy’s core reliability constraints:

* the editor Qt process never imports third-party plugin code
* plugin workflow code runs through the isolated plugin host
* project files remain the source of truth
* workflow plugins return structured results rather than mutating editor state directly

## 2. Product decisions

1. v1 keeps declarative commands and runtime commands, but Python workflow extensibility
   moves to typed workflow providers.
2. Phase-1 external workflow plugins are pure-Python and AppRun-safe only.
3. Bundled first-party workflow plugins are the compatibility canary for the public API.
4. `cbcs/plugins.json` is the project-scoped source of truth for plugin pins, overrides,
   and preferred workflow providers.
5. Semantic-engine and debugger-engine providers remain core-owned until their separate
   contracts stabilize.
6. Publisher signing is still deferred; trust remains explicit and local.

## 3. Platform model

The platform now has three extension surfaces:

* Declarative contributions
* Runtime commands
* Workflow providers

Workflow providers are typed integrations for editor-owned surfaces such as formatting,
diagnostics, test execution, templates, packaging, runtime explanation, FreeCAD helper
jobs, and dependency audit flows.

The shell owns:

* menus, status, and visual affordances
* editor buffer application
* diagnostics rendering
* test and packaging UX
* project pinning and provider preference selection

Plugins own:

* workflow computation
* structured result generation
* long-running job progress events

## 4. Distribution and install model

Distribution remains offline-first:

* local folder or `.cbcs-plugin.zip` install
* explicit manifest validation
* install-time audits before activation
* filesystem-based registry and trust state under visible global paths

Bundled plugins live under visible repo path `bundled_plugins/` and are discovered
alongside installed plugins when the shell/runtime asks for bundled providers.

## 5. Manifest contract

Every plugin still provides `plugin.json`, but the v2 contract now includes:

* `id`, `name`, `version`
* `api_version`
* `runtime.entrypoint`
* `activation_events`
* `capabilities`
* `permissions`
* `engine_constraints`
* `contributes.commands`
* `contributes.event_hooks`
* `contributes.workflow_providers`

Workflow providers declare:

* `id`
* `kind`
* `lane` (`query` or `job`)
* `title`
* optional `priority`
* optional language/file-extension targeting
* `query_handler` for query providers
* `start_handler` and optional `cancel_handler` for job providers

## 6. Project pinning and provider selection

`cbcs/plugins.json` stores project-scoped workflow policy:

* explicitly enabled plugins
* explicitly disabled plugins
* pinned versions by plugin id
* preferred providers by workflow kind and optional language key

This keeps plugin reproducibility visible, shareable, and filesystem-first.

## 7. Lifecycle

1. Discover installed plugins
2. Optionally merge bundled plugins
3. Parse and validate manifest
4. Run compatibility and install-time audits
5. Load project plugin policy from `cbcs/plugins.json`
6. Build workflow provider catalog
7. Activate only on matching command/provider/event usage
8. Quarantine or disable after repeated failures

## 8. Runtime and IPC model

The isolated host now exposes two provider lanes:

* Query lane for fast structured requests such as formatters, diagnostics, template
  metadata, and runtime explainers
* Job lane for long-running work such as pytest runs, packaging, dependency audit, and
  FreeCAD helpers

Job providers communicate through streaming messages:

* `provider_job_start`
* `job_event`
* `job_result`
* `job_error`
* `provider_job_cancel`

## 9. Safety model

Safety rules are stricter for workflow plugins than for legacy commands:

* runtime trust remains explicit for installed runtime plugins
* bundled first-party plugins are treated as trusted product code
* safe mode disables all plugin activation
* repeated runtime failures still trigger quarantine
* workflow plugins must not write hidden paths or rely on hidden metadata directories
* phase-1 external workflow plugins must remain pure Python
* plugin install validation should flag unsupported subprocess assumptions and forbidden
  output-path conventions early

## 10. Rollout plan

### Phase H00-H07 (completed foundation)

Completed plugin foundation remains valid:

* manifest/discovery
* installer/registry
* Plugin Manager
* declarative contributions
* isolated runtime host
* safe mode + quarantine
* baseline plugin docs

### Workflow-provider expansion

The Python workflow ecosystem now rolls out through ten slices:

1. Contract and backlog cutover
2. Manifest v2 and project pinning
3. Workflow provider catalog and broker
4. IPC v2 with query/job lanes
5. Core workflow adapters behind provider contracts
6. Diagnostics and Python tooling provider cutover
7. Bundled reference plugins
8. UI/settings/support integration
9. Safety and performance gates
10. Validation, SDK, and compatibility hardening

## 11. Acceptance coverage

Plugin platform acceptance is now tracked across both the original lifecycle tests and
the workflow-provider expansion:

* `AT-37` install flow
* `AT-38` runtime isolation
* `AT-39` enable/disable lifecycle
* `AT-40` safe mode + quarantine
* `AT-41` declarative contributions
* `AT-42` compatibility enforcement
* `AT-85` provider selection and provenance
* `AT-86` project plugin pinning and overrides
* `AT-87` streaming workflow jobs
* `AT-88` plugin/provider visibility in support bundles
* `AT-89` pure-Python compatibility gating
