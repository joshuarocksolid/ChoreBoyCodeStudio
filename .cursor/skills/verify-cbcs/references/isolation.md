# Isolation

The lab has two named desktops (`ChoreBoy`, `ChoreBoyTim`). Each slot still has one desktop **and one guest app runner**. The runner processes one `cbapp` session at a time. If another session is `running` (STATE heartbeat updating), your `START` file will sit unclaimed until that session stops. `wait-ready` then times out with no STATE file. `control-cbcs launch` acquires a slot so two agents can use two desktops.

Do not stop a session you did not start. Wait, or refuse. Stale `running` rows whose STATE timestamp is hours old are orphans, not the active runner job.

## Refuse

`control-cbcs launch` and `doctor` fail if another `cbcs-verify-*` session is `launching`, `ready`, or `running`. Stop that session, or wait. Do not attach to it.

Do not drive a Code Studio window that is already open on the guest unless `run.json` for this run names its session id.

## Disposable HOME

The live app writes global state to `$HOME/choreboy_code_studio_state/` (settings, recents, logs, history, plugins). There is no `CBCS_STATE_ROOT` env var.

`control-cbcs launch` sets:

```text
HOME=/home/default/cbcs-verify-<run-id>
```

That path is on the guest disk. Do not put HOME on virtiofs (`/mnt/cbprobe/...`): SQLite local-history WAL locks there and the editor exits during startup.

Confirm with `control-cbcs doctor` (it reads `os.environ['HOME']`). If HOME is exactly `/home/default`, stop. You are on the human's profile.

Per-project metadata lives in `<project>/cbcs/`. Put scratch projects under `/mnt/cbprobe/cbcs-verify/<run-id>/project` or a folder inside the disposable HOME.

## What is shared anyway

| Resource | Shared? | What to do |
|----------|---------|------------|
| VM desktop / DISPLAY `:0` | Per slot | One verify session per leased desktop |
| Loopback debug / REPL ports | No (ephemeral) | Fine |
| virtiofs `/mnt/cbprobe` | Yes | Use only your `<run-id>` subtree |
| `repo/vendor` on the Mac | Yes | Rsync copies into the run tree |
| Human `~/choreboy_code_studio_state` | Only if HOME is wrong | Doctor must catch this |

## Cleanup vs proof

`control-cbcs stop` removes `/mnt/cbprobe/cbcs-verify/<run-id>/` on the share (source + disposable HOME). It does not touch `~/ChoreBoy/artifacts/verify-cbcs/<run-id>/` on the Mac.

After stop, `ls` that artifact directory. If it is gone, the run failed the contract.
