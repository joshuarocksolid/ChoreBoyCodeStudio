# Diagnostics and support

Project Health Check reports actionable problems. Support Bundle zips logs and runtime state for USB handoff. Application log is always written and openable from Help.

Owns AT-22, AT-23, AT-79.

## Sub-features

- `health-check` **Tools → Project Health Check** lists structure / runner issues (AT-22).
- `support-bundle` **Tools → Generate Support Bundle** writes `cbcs_support_YYYYMMDD_HHMMSS.zip` (AT-23).
- `support-runtime` bundle includes a runtime explanation snapshot (AT-79).
- `app-log` **Help → Open Application Log** / **Open Log Folder**.
- `startup-explain` Runtime Center explains failed capability checks (shared with [launch-runtime.md](./launch-runtime.md)).

## How to get to it (user POV)

- **Tools → Project Health Check / Generate Support Bundle / Runtime Center...**.
- **Help → Open Application Log / Open Log Folder**.
- Click `#shell.startupStatusLabel`.

## Driving it with control-cbcs

Preconditions:

- Doctor passed.
- A project open for health check (or prove the disabled/empty state on welcome).

- **Health.** `control-cbcs trigger "$SID" shell.action.tools.projectHealthCheck`. A dialog or report lists checks. Shot `health-check`.
- **Bundle.** `control-cbcs trigger "$SID" shell.action.tools.generateSupportBundle`. Choose a path under the disposable tree. Zip exists. Copy it to Mac artifacts. Unzip listing includes `app.log` and a health/runtime JSON.
- **App log.** Confirm `$HOME/choreboy_code_studio_state/logs/app.log` exists and contains a startup line. Copy the tail into artifacts.
- **Proof.** Bundle zip (or its listing) plus the health-check shot.

## Gotchas

- Bundle destination dialog is native. Point it at the run tree.
- Log fallback is `/tmp/choreboy_code_studio/logs/app.log` if HOME state is unwritable — that would mean isolation failed.
- Plugin state in the bundle is required when plugins are installed (AT-88); see [plugins.md](./plugins.md).
