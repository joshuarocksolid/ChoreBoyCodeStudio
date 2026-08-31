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

- **Health.** A project must be open. `control-cbcs trigger "$SID" shell.action.tools.projectHealthCheck` starts a background check, then opens `#shell.runtimeCenterDialog` titled **Project Health Check**. Shot `health-check`. Close with `reject()`.
- **Bundle.** `control-cbcs trigger "$SID" shell.action.tools.generateSupportBundle`. There is no save picker. The zip is `cbcs_support_YYYYMMDD_HHMMSS.zip` in the **project root**. A `QMessageBox.information` then blocks the bridge. Dismiss with virsh `KEY_ENTER`. Copy the zip to Mac artifacts. Unzip listing includes `global_logs/app.log` and `diagnostics/` JSON.
- **App log.** Confirm `$HOME/choreboy_code_studio_state/logs/app.log` exists and contains a startup line. Copy the tail into artifacts.
- **Proof.** Bundle zip (or its listing) plus the health-check shot.

## Gotchas

- There is no bundle destination dialog. The zip lands in the project root.
- Log fallback is `/tmp/choreboy_code_studio/logs/app.log` if HOME state is unwritable — that would mean isolation failed.
- Plugin state in the bundle is required when plugins are installed (AT-88); see [plugins.md](./plugins.md).
