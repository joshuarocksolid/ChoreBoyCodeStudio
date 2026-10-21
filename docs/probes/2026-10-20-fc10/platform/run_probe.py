#!/usr/bin/env python
"""FreeCAD 1.0 platform matrix. Runs inside confined AppRun.

Creates only names containing cbcs_phase0_20261020, then deletes them.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import traceback
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
HOME = "/home/default"
PREFIX = "cbcs_phase0_20261020"

PARENTS = [
    HOME,
    os.path.join(HOME, "FreeCAD"),
    os.path.join(HOME, "FreeCAD", "CBCS"),
    os.path.join(HOME, ".local", "share", "FreeCAD"),
    os.path.join(HOME, ".local", "share", "FreeCAD", "Macro", "Apps"),
    os.path.join(HOME, ".cache", "FreeCAD"),
    "/tmp",
    os.path.join(HOME, "share"),
    os.path.join(HOME, "share", "Chore_Boy"),
    os.path.join(HOME, "Desktop"),
]


def _err(exc):
    errno = getattr(exc, "errno", None)
    return {"error_type": type(exc).__name__, "errno": errno, "error": str(exc)}


def _read(path, limit=20000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except Exception as exc:
        return _err(exc)


def _stat(path):
    try:
        st = os.lstat(path)
    except OSError as exc:
        return _err(exc)
    info = {
        "mode": oct(st.st_mode),
        "uid": st.st_uid,
        "gid": st.st_gid,
        "size": st.st_size,
        "dev": st.st_dev,
        "ino": st.st_ino,
        "is_dir": stat.S_ISDIR(st.st_mode),
        "is_link": stat.S_ISLNK(st.st_mode),
    }
    if info["is_link"]:
        try:
            info["link_target"] = os.readlink(path)
        except OSError as exc:
            info["link_target_error"] = _err(exc)
    return info


def _ours(name):
    return PREFIX in name


def _remove_path(path):
    base = os.path.basename(path)
    if not _ours(base):
        return "refused"
    try:
        if os.path.islink(path) or os.path.isfile(path):
            os.unlink(path)
            return "removed"
        if os.path.isdir(path):
            shutil.rmtree(path)
            return "removed"
        os.unlink(path)
        return "removed"
    except OSError as exc:
        return _err(exc)


def _sweep(parent):
    try:
        names = os.listdir(parent)
    except OSError as exc:
        return {"listdir": _err(exc)}
    removed = {}
    for name in names:
        if _ours(name):
            removed[name] = _remove_path(os.path.join(parent, name))
    left = []
    try:
        for name in os.listdir(parent):
            if _ours(name):
                left.append(name)
    except OSError as exc:
        left.append(_err(exc))
    return {"removed": removed, "left": left}


def _mkdir(path):
    try:
        os.mkdir(path)
    except OSError as exc:
        return _err(exc)
    return {"ok": True, "stat": _stat(path)}


def _write_file(path):
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("phase0\n")
    except OSError as exc:
        return _err(exc)
    return {"ok": True, "stat": _stat(path)}


def _lock(path):
    fd = None
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        os.write(fd, b"x" * 64)
    except OSError as exc:
        return _err(exc)
    try:
        import fcntl

        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return {"ok": True, "op": "fcntl.lockf LOCK_EX|LOCK_NB"}
    except OSError as exc:
        return _err(exc)
    finally:
        if fd is not None:
            os.close(fd)


def _sqlite(path, mode):
    out = {"requested": mode}
    try:
        conn = sqlite3.connect(path, timeout=2.0)
        try:
            row = conn.execute("PRAGMA journal_mode = {}".format(mode)).fetchone()
            out["journal_mode"] = None if row is None else row[0]
            conn.execute("CREATE TABLE IF NOT EXISTS t(x INTEGER)")
            conn.execute("INSERT INTO t(x) VALUES (1)")
            conn.commit()
            got = conn.execute("SELECT x FROM t").fetchone()
            out["read_back"] = None if got is None else got[0]
            out["ok"] = got == (1,)
        finally:
            conn.close()
    except Exception as exc:
        out.update(_err(exc))
    out["files"] = {
        os.path.basename(name): _stat(name)
        for name in (path, path + "-wal", path + "-shm", path + "-journal")
    }
    return out


def _probe_parent(parent):
    rec = {"parent": parent, "stat": _stat(parent), "is_link": os.path.islink(parent)}
    exists = os.path.isdir(parent)
    rec["exists_dir"] = exists
    if not exists:
        rec["skipped"] = "parent_missing_or_not_dir"
        return rec
    vis = os.path.join(parent, PREFIX + "_vis")
    hid = os.path.join(parent, "." + PREFIX + "_hid")
    fil = os.path.join(parent, PREFIX + "_file.txt")
    lockp = os.path.join(parent, PREFIX + "_lock.bin")
    wal = os.path.join(parent, PREFIX + "_wal.sqlite3")
    delete = os.path.join(parent, PREFIX + "_del.sqlite3")
    try:
        rec["mkdir_visible"] = _mkdir(vis)
        rec["mkdir_hidden"] = _mkdir(hid)
        rec["write_file"] = _write_file(fil)
        rec["fcntl_lock"] = _lock(lockp)
        rec["sqlite_wal"] = _sqlite(wal, "WAL")
        rec["sqlite_delete"] = _sqlite(delete, "DELETE")
    finally:
        rec["cleanup"] = _sweep(parent)
    return rec


def _exec_case(argv, timeout):
    record = {"argv": list(argv), "timeout_s": timeout}
    if argv and os.path.isabs(argv[0]):
        record["exists"] = os.path.exists(argv[0])
        record["stat"] = _stat(argv[0])
        record["access_x"] = os.access(argv[0], os.X_OK)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        record["returncode"] = proc.returncode
        record["stdout"] = (proc.stdout or "")[-1500:]
        record["stderr"] = (proc.stderr or "")[-1500:]
    except Exception as exc:
        record.update(_err(exc))
        stdout = getattr(exc, "stdout", None) or ""
        stderr = getattr(exc, "stderr", None) or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        record["stdout"] = stdout[-1500:]
        record["stderr"] = stderr[-1500:]
    return record


def _list_dir(path, limit=200):
    try:
        names = sorted(os.listdir(path))
    except OSError as exc:
        return _err(exc)
    return {"count": len(names), "names": names[:limit], "truncated": len(names) > limit}


def _read_small_files(directory, suffixes, limit_files=25, limit_chars=8000):
    listing = _list_dir(directory, limit=400)
    if "error_type" in listing:
        return {"list": listing, "files": []}
    files = []
    for name in listing["names"]:
        if len(files) >= limit_files:
            break
        lower = name.lower()
        if not any(lower.endswith(suffix) for suffix in suffixes):
            continue
        path = os.path.join(directory, name)
        item = {"name": name, "stat": _stat(path)}
        if os.path.isfile(path) and not os.path.islink(path):
            item["text"] = _read(path, limit_chars)
        files.append(item)
    return {"list": listing, "files": files}


def _interesting_share_parents(share):
    extra = []
    listing = _list_dir(share, limit=400)
    if "error_type" in listing:
        return extra, listing
    for name in listing["names"]:
        lower = name.lower()
        if lower.startswith("net") or "chore_boy" in lower or lower == "cbcs":
            extra.append(os.path.join(share, name))
    return extra, listing


def _desktop_notes():
    notes = {
        "ideskrc": _read(os.path.join(HOME, ".ideskrc"), 12000),
        "idesktop": _read_small_files(os.path.join(HOME, ".idesktop"), (".lnk", ".desktop", ".txt")),
        "desktop_dir": _read_small_files(os.path.join(HOME, "Desktop"), (".desktop", ".lnk")),
        "home_desktop_files": [],
        "intellaquote": _read(os.path.join(HOME, "IntellaQuote.desktop"), 8000),
        "fluxbox_keys": _read(os.path.join(HOME, ".fluxbox", "keys"), 8000),
        "fluxbox_startup": _read(os.path.join(HOME, ".fluxbox", "startup"), 8000),
        "usr_share_idesk": _list_dir("/usr/share/idesk", limit=50),
    }
    try:
        names = sorted(os.listdir(HOME))
    except OSError as exc:
        notes["home_list"] = _err(exc)
        return notes
    notes["home_list"] = {"count": len(names), "names": names[:300]}
    for name in names:
        lower = name.lower()
        if lower.endswith(".desktop") or lower.endswith(".lnk") or "intella" in lower:
            path = os.path.join(HOME, name)
            item = {"name": name, "stat": _stat(path)}
            if os.path.isfile(path) and not os.path.islink(path) and os.path.getsize(path) < 20000:
                item["text"] = _read(path, 8000)
            notes["home_desktop_files"].append(item)
    return notes


def main():
    os.makedirs(RESULTS, exist_ok=True)
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "prefix": PREFIX,
        "python": sys.version.replace("\n", " "),
        "executable": sys.executable,
        "sqlite": sqlite3.sqlite_version,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "cwd": os.getcwd(),
        "hostname_file": _read("/etc/hostname", 200),
        "os_release": _read("/etc/os-release", 2000),
        "debian_version": _read("/etc/debian_version", 200),
        "apparmor_current": _read("/proc/self/attr/current", 400),
        "proc_mounts": _read("/proc/mounts", 30000),
        "proc_mountinfo": _read("/proc/self/mountinfo", 4000),
        "fstab": _read("/etc/fstab", 8000),
    }
    try:
        import platform

        report["hostname"] = platform.node()
        report["kernel"] = platform.release()
    except Exception as exc:
        report["platform_error"] = _err(exc)
    try:
        import FreeCAD

        report["freecad_version"] = list(FreeCAD.Version())
    except Exception as exc:
        report["freecad_version_error"] = _err(exc)

    dev_paths = [
        "/",
        "/home",
        HOME,
        os.path.join(HOME, "share"),
        os.path.join(HOME, "FreeCAD"),
        os.path.join(HOME, ".local"),
        os.path.join(HOME, ".cache"),
        "/tmp",
        "/mnt",
        "/mnt/cbprobe",
    ]
    report["dev_ids"] = {path: _stat(path) for path in dev_paths}

    which = (
        "command -v pdftoppm; command -v pcmanfm; command -v xdg-open; "
        "command -v okular; command -v soffice; command -v libreoffice; "
        "command -v python3; command -v bash; command -v env; command -v ls; "
        "command -v which"
    )
    exec_plan = [
        (["/opt/freecad/AppRun", "-c", "print('APPRUN_CHILD_OK')"], 45),
        (["/bin/sh", "-c", "echo SH_OK"], 8),
        (["/bin/sh", "-c", "pdftoppm -v"], 15),
        (["/bin/ls", "/bin/sh"], 8),
        (["/usr/bin/pdftoppm", "-v"], 15),
        (["/usr/bin/python3", "--version"], 8),
        (["/bin/bash", "-c", "echo BASH_OK"], 8),
        (["pcmanfm", "--version"], 8),
        (["/usr/bin/pcmanfm", "--version"], 8),
        (["xdg-open", "--help"], 5),
        (["/usr/bin/xdg-open", "--help"], 5),
        (["okular", "--version"], 12),
        (["/usr/bin/okular", "--version"], 12),
        (["soffice", "--version"], 20),
        (["/usr/bin/soffice", "--version"], 20),
        (["libreoffice", "--version"], 20),
        (["/usr/bin/libreoffice", "--version"], 20),
        (["/usr/bin/env", "true"], 8),
        (["/bin/sh", "-c", which], 8),
    ]
    report["exec"] = [_exec_case(argv, timeout) for argv, timeout in exec_plan]

    share = os.path.join(HOME, "share")
    extra, share_listing = _interesting_share_parents(share)
    report["share_listing"] = share_listing
    parents = list(PARENTS)
    for path in extra:
        if path not in parents:
            parents.append(path)
    report["parents_probed"] = parents
    report["paths"] = [_probe_parent(parent) for parent in parents]
    report["desktop"] = _desktop_notes()

    path = os.path.join(RESULTS, "platform.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("wrote", path)
    print("freecad", report.get("freecad_version") or report.get("freecad_version_error"))
    print("hostname", report.get("hostname"))
    for item in report["exec"]:
        argv0 = item["argv"][0]
        print(
            "exec",
            argv0,
            item.get("returncode"),
            item.get("error_type"),
            (item.get("stderr") or item.get("error") or "")[:180],
        )
    for case in report["paths"]:
        lock = case.get("fcntl_lock") or {}
        wal = case.get("sqlite_wal") or {}
        left = (case.get("cleanup") or {}).get("left")
        print(
            "path",
            case["parent"],
            "dir",
            case.get("exists_dir"),
            "lock",
            lock.get("ok") or lock.get("error_type"),
            "wal",
            wal.get("journal_mode") or wal.get("error_type"),
            "left",
            left,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
