# Appendix D — Status & Run-State Reference

This appendix catalogs the states and messages you will see in the status bar and run
panels, so you can interpret the application at a glance.

## Startup / runtime readiness (status bar, far left)

| Message | Meaning | Action |
| --- | --- | --- |
| `Runtime ready (8/8 checks)` | All capability checks passed. | None — you are good to go. |
| `Runtime issues (N/8 checks)` | One or more checks failed. | Open **Tools > Runtime Center** for details. |

The capability checks cover: the runtime launcher, the Qt library, writable settings and
log folders, a writable temp folder, and syntax-highlighting support.

## Python tooling status (status bar)

| Message | Meaning |
| --- | --- |
| `Python: tools ready` | Formatting, linting, and intelligence tools loaded. |
| `pyproject` (appended) | A project `pyproject.toml` was detected and is in use. |

## Run state (status bar)

| State | Meaning |
| --- | --- |
| `Run: idle` | Nothing is running. |
| `Run: running` (green) | A program is executing; the **Stop** button is available. |
| `Run: finished` | The program exited successfully (exit code 0). |
| `Run: failed (code=N)` | The program exited with an error; the **Problems** panel opens. |
| `Run: terminated` | You stopped the run, or it was ended by a signal. |

## Project indicator (status bar)

| Display | Meaning |
| --- | --- |
| `Project: Name` | The open project's name. |
| `Project: Name (project overrides)` | The project has its own settings overriding global defaults. |

## Editor indicator (status bar, right)

Shows, in order: the active indentation (for example `Spaces: 4 (auto)`), the active file
name, the cursor position (`Ln 1, Col 1`), and the save state (`saved` or `modified`).

## Active run target (status bar, far right)

| Display | Meaning |
| --- | --- |
| `Default` | **Run Project** uses the project default entry and arguments. |
| `<name>` | A named run configuration is active and will be used by Run Project. |

Click it to switch configurations, open **Run With Arguments...**, or edit configurations.

## Run Log line prefixes

| Prefix | Source |
| --- | --- |
| `[system]` | The application's own run lifecycle messages (started, stopped, finished). |
| `[runner]` | The runner process reporting its run id, mode, and entry file. |
| `[stderr]` | Standard-error output from your program. |
| (no prefix) | Standard-output (`print`) from your program. |

## Run exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success. |
| `1` | User-code error (an exception or non-zero exit). |
| `2` | Runner bootstrap/configuration failure. |
| `3` | Invalid run manifest. |
| `130` | Terminated by the user. |

## Where to go next

- Understand the panels these states appear in: "Panels & UI surfaces reference".
- Diagnose problem states in "Diagnostics & support tools" and "Troubleshooting by
  symptom".
