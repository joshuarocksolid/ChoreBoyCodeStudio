# Isolation

A farm lease has one desktop (`net1`) and one guest app runner. The runner processes one session at a time. If another session is `running`, `app-run` waits or fails. `control-cbcs launch` reuses `CBFARM_ENV` when it is set, and refuses a second live `cbcs-verify-*` session on that desktop.

Do not stop a session you did not start. Wait, or refuse. A stale `running` row whose heartbeat is dead is not the active job. On the farm, `cbapp stop` marks a dead session done.

## Lab fallback

`--backend lab` uses one Debian slot (`cb-slot`). The same one-session rule applies. `launch` acquires that slot. `ssh debian` and `cb-virsh` are how doctor checks the slot is up. Do not use `ChoreBoy5` or `cb-slot` with `--cb-slot any`.

## Refuse

`control-cbcs launch` and `doctor` fail if another `cbcs-verify-*` session is `launching`, `ready`, or `running`. Stop that session, or wait. Do not attach to it.

Do not drive a Code Studio window that is already open on the guest unless `run.json` for this run names its session id.

## Disposable HOME

The live app writes settings JSON and local state to different roots. `control-cbcs launch` still sets:

```text
HOME=/home/default/cbcs-verify-<run-id>
CBCS_STATE_ROOT=/home/default/cbcs-verify-<run-id>/choreboy_code_studio_state
```

`CBCS_STATE_ROOT` now selects only the shared settings directory (`settings.json`, `recent_projects.json`, `python_console_history.json`). Logs, history, plugins, and SQLite stay at `/home/default/FreeCAD/CBCS/state`. A verify session can write those files into the product dest. Shop share pointers are opt-in; do not write `/home/default/share/Chore_Boy/CBCS/cbcs_state_root` on the human share.

That path is on the guest disk. HOME on the share (`/mnt/cbprobe/...`) makes SQLite local-history WAL locks fail and the editor exits during startup.

Confirm with `control-cbcs doctor` (it reads `os.environ['HOME']`). If HOME is exactly `/home/default`, stop. You are on the human's profile.

Per-project metadata lives in `<project>/cbcs/`. Put scratch projects under `/mnt/cbprobe/cbcs-verify/<run-id>/project` or a folder inside the disposable HOME.

## What is shared anyway

| Resource | Shared? | What to do |
|----------|---------|------------|
| VM desktop / DISPLAY `:0` | Per lease (lab: per slot) | One verify session per desktop |
| Loopback debug / REPL ports | No (ephemeral) | Fine |
| Share `/mnt/cbprobe` | Yes | Use only your `cbcs-verify-<run-id>` tree (`incoming/` on the farm) |
| `repo/vendor` on the Mac | Yes | Rsync copies into the run tree |
| Human `~/choreboy_code_studio_state` | Only if HOME is wrong | Doctor must catch this |

## Cleanup vs proof

`control-cbcs stop` removes this run's share tree (`/mnt/cbprobe/incoming/cbcs-verify-<run-id>/` on the farm, `/mnt/cbprobe/cbcs-verify/<run-id>/` on the lab). It does not touch `~/ChoreBoy/artifacts/verify-cbcs/<run-id>/` on the Mac. A farm lease that was already in `CBFARM_ENV` is not released.

After stop, `ls` that artifact directory. If it is gone, the run failed the contract.
