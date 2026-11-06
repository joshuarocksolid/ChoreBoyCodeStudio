"""cbfarm transport for control-cbcs.

The process boundary is one `cbfarm-mcp-call` per guest action. Callers pass
the same argv they used to pass to `cbapp`. This module maps that argv onto
`do` / `push` / `pull` and does not lease when `CBFARM_ENV` is already set.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

DEFAULT_MCP = "/Users/local/Projects/cb_probes-wt/main/harness/cbfarm-mcp-call"
_APP_HEADS = ("app-run", "install-test", "sessions", "status", "stop")


def launch_sid(text: str, requested: str) -> str:
    """cbapp appends -YYYYMMDDTHHMMSSZ-hex to --name. Return that full id."""
    found = re.findall(r"cbcs-verify(?:-install)?-[A-Za-z0-9._-]+", text or "")
    if requested:
        longer = [item for item in found if item.startswith(requested + "-")]
        if longer:
            return max(longer, key=len)
        if requested in found:
            return requested
    return ""


def resolve_backend(argv: Sequence[str], env: dict) -> tuple:
    """Return `(backend, argv)` with `--backend` removed. The flag wins over the env."""
    backend = (env.get("CBCS_VERIFY_BACKEND") or "farm").strip().lower()
    out: List[str] = []
    index = 0
    items = list(argv)
    while index < len(items):
        arg = items[index]
        if arg == "--backend":
            if index + 1 >= len(items):
                raise SystemExit("error: --backend needs farm or lab")
            backend = items[index + 1].strip().lower()
            index += 2
            continue
        if arg.startswith("--backend="):
            backend = arg.split("=", 1)[1].strip().lower()
            index += 1
            continue
        out.append(arg)
        index += 1
    if backend not in ("farm", "lab"):
        raise SystemExit("error: backend must be farm or lab, got " + backend)
    return backend, out


def holds_farm_env(env: dict) -> bool:
    """True when this process must reuse a lease instead of making one."""
    return bool(str(env.get("CBFARM_ENV") or "").strip())


def env_id() -> str:
    env = os.environ.get("CBFARM_ENV", "").strip()
    if not env:
        raise SystemExit(
            "error: CBFARM_ENV is unset. Lease a solo env, or pass --backend lab"
        )
    return env


def machine() -> str:
    return os.environ.get("CBFARM_MACHINE", "net1").strip() or "net1"


def do_payload(args: Sequence[str], timeout: Optional[int] = None) -> dict:
    """Map a cbapp argv onto a `do` tool payload. ctl does not get timeout_s.

    The farm adds `--wait` whenever ctl carries timeout_s. Screenshot and click
    must not grow that flag.
    """
    if not args:
        raise SystemExit("error: empty guest command")
    head = str(args[0])
    payload = {
        "env": env_id(),
        "machine": machine(),
        "verb": "ctl" if head == "ctl" else "app",
        "args": [str(item) for item in (args[1:] if head == "ctl" else args)],
    }
    if head in ("app-run", "install-test") and timeout:
        payload["timeout_s"] = min(int(timeout), 3600)
    if head not in _APP_HEADS and head != "ctl":
        payload["verb"] = "app"
        payload["args"] = [str(item) for item in args]
    return payload


def call(
    tool: str,
    arguments: dict,
    save_dir: Optional[str] = None,
    timeout: int = 600,
    allow_roots: Optional[Sequence[str]] = None,
) -> subprocess.CompletedProcess:
    mcp = os.environ.get("CBFARM_MCP_CALL", DEFAULT_MCP)
    host = os.environ.get("CBFARM_HOST", "aws-1")
    argv = [mcp, "--host", host]
    for root in allow_roots or ():
        argv.extend(["--allow-root", root])
    if save_dir:
        argv.extend(["--save-dir", save_dir])
    argv.extend([tool, json.dumps(arguments)])
    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def invoke(
    args: Sequence[str],
    timeout: Optional[int] = None,
    save_dir: Optional[str] = None,
) -> subprocess.CompletedProcess:
    payload = do_payload(args, timeout=timeout)
    limit = int(payload.get("timeout_s") or timeout or 300) + 90
    return call("do", payload, save_dir=save_dir, timeout=limit)


def guest_mkdir(path: str) -> None:
    proc = guest_sh("mkdir -p " + shlex.quote(path) + " && echo OK")
    if proc.returncode != 0 or "OK" not in (proc.stdout or ""):
        raise SystemExit("error: could not create " + path + "\n" + (proc.stderr or "") + (proc.stdout or ""))


def confirm_file(path: str) -> None:
    proc = guest_sh("test -f " + shlex.quote(path) + " && echo OK")
    if proc.returncode != 0 or "OK" not in (proc.stdout or ""):
        raise SystemExit(
            "error: missing on the guest: " + path + "\n" + (proc.stderr or "") + (proc.stdout or "")
        )


def guest_sh(command: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return call(
        "do",
        {
            "env": env_id(),
            "machine": machine(),
            "verb": "sh",
            "command": command,
            "timeout_s": int(timeout),
        },
        timeout=int(timeout) + 60,
    )


def publish_tree(local: Path, dest: str) -> str:
    """Push a real directory. Returns the guest path of that directory."""
    path = local.expanduser().resolve()
    if path.is_symlink():
        raise SystemExit("error: refusing to push a symlink: " + str(path))
    if not path.is_dir():
        raise SystemExit("error: not a directory: " + str(path))
    proc = call(
        "push",
        {
            "env": env_id(),
            "machine": machine(),
            "local_path": [str(path)],
            "dest": dest,
        },
        timeout=600,
        allow_roots=[str(path)],
    )
    if proc.returncode != 0:
        raise SystemExit(
            "error: push failed\n" + (proc.stderr or "") + (proc.stdout or "")
        )
    return "/mnt/cbprobe/incoming/{}/{}".format(dest, path.name)


def publish_file(local: Path, dest: str) -> str:
    path = local.expanduser().resolve()
    if path.is_symlink() or not path.is_file():
        raise SystemExit("error: push needs a real file: " + str(path))
    proc = call(
        "push",
        {
            "env": env_id(),
            "machine": machine(),
            "local_path": [str(path)],
            "dest": dest,
        },
        timeout=600,
        allow_roots=[str(path.parent)],
    )
    if proc.returncode != 0:
        raise SystemExit(
            "error: push failed\n" + (proc.stderr or "") + (proc.stdout or "")
        )
    return "@share:incoming/{}/{}".format(dest, path.name)


def remove_incoming(dest: str) -> None:
    if not re.fullmatch(r"cbcs-verify-[A-Za-z0-9._-]{1,80}", dest):
        return
    guest_sh("rm -rf " + shlex.quote("/mnt/cbprobe/incoming/" + dest), timeout=120)


def pull_file(relpath: str, dest_dir: Path) -> subprocess.CompletedProcess:
    dest_dir.mkdir(parents=True, exist_ok=True)
    return call(
        "pull",
        {
            "env": env_id(),
            "machine": machine(),
            "path": relpath,
            "to": str(dest_dir),
        },
        timeout=180,
        allow_roots=[str(dest_dir)],
    )


def acquire() -> dict:
    """Reuse `CBFARM_ENV` when it is set. Lease a solo env only when it is not."""
    leased = False
    env = os.environ.get("CBFARM_ENV", "").strip()
    if not holds_farm_env(dict(os.environ)):
        proc = call("lease", {"template": "solo", "ttl": "2h"}, timeout=180)
        if proc.returncode != 0:
            raise SystemExit(
                "error: farm lease failed\n" + (proc.stderr or "") + (proc.stdout or "")
            )
        env = _lease_id(proc.stdout or "")
        if not env:
            raise SystemExit("error: farm lease did not print an env id\n" + (proc.stdout or ""))
        os.environ["CBFARM_ENV"] = env
        leased = True
    return {
        "backend": "farm",
        "farm_env": env,
        "farm_machine": machine(),
        "farm_leased_by_us": leased,
    }


def release(rec: Optional[dict]) -> None:
    if not rec or not rec.get("farm_leased_by_us"):
        return
    env = str(rec.get("farm_env") or "")
    if not env:
        return
    proc = call("release", {"env": env}, timeout=180)
    if proc.returncode != 0:
        print("note: farm release failed: " + (proc.stderr or proc.stdout or ""), flush=True)


def _lease_id(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and payload.get("id"):
        return str(payload["id"])
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("id"):
                return str(payload["id"])
    return ""
