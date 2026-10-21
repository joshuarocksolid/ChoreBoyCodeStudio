#!/usr/bin/env python
"""List ~/share/Chore_Boy and ~/Desktop, and lock-test Chore_Boy if it exists."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
HOME = "/home/default"
PREFIX = "cbcs_phase0_20261020"


def _err(exc):
    return {
        "error_type": type(exc).__name__,
        "errno": getattr(exc, "errno", None),
        "error": str(exc),
    }


def _stat(path):
    try:
        st = os.lstat(path)
    except OSError as exc:
        return _err(exc)
    return {
        "mode": oct(st.st_mode),
        "uid": st.st_uid,
        "gid": st.st_gid,
        "dev": st.st_dev,
        "is_dir": stat.S_ISDIR(st.st_mode),
        "is_link": stat.S_ISLNK(st.st_mode),
    }


def _list(path, limit=60):
    try:
        names = sorted(os.listdir(path))
    except OSError as exc:
        return _err(exc)
    return {"count": len(names), "names": names[:limit], "truncated": len(names) > limit}


def _lock(path):
    fd = None
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        os.write(fd, b"x" * 64)
        import fcntl

        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return {"ok": True}
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
            out["ok"] = got == (1,)
        finally:
            conn.close()
    except Exception as exc:
        out.update(_err(exc))
    return out


def _sweep(parent):
    try:
        names = os.listdir(parent)
    except OSError as exc:
        return _err(exc)
    removed = []
    for name in names:
        if PREFIX not in name:
            continue
        path = os.path.join(parent, name)
        if os.path.islink(path) or not os.path.isdir(path):
            os.unlink(path)
        else:
            shutil.rmtree(path)
        removed.append(name)
    left = [name for name in os.listdir(parent) if PREFIX in name]
    return {"removed": removed, "left": left}


def _probe(parent):
    rec = {"parent": parent, "stat": _stat(parent), "exists_dir": os.path.isdir(parent)}
    if not rec["exists_dir"]:
        return rec
    try:
        rec["mkdir_visible"] = "ok"
        os.mkdir(os.path.join(parent, PREFIX + "_vis"))
    except OSError as exc:
        rec["mkdir_visible"] = _err(exc)
    try:
        os.mkdir(os.path.join(parent, "." + PREFIX + "_hid"))
        rec["mkdir_hidden"] = "ok"
    except OSError as exc:
        rec["mkdir_hidden"] = _err(exc)
    rec["fcntl_lock"] = _lock(os.path.join(parent, PREFIX + "_lock.bin"))
    rec["sqlite_wal"] = _sqlite(os.path.join(parent, PREFIX + "_wal.sqlite3"), "WAL")
    rec["sqlite_delete"] = _sqlite(os.path.join(parent, PREFIX + "_del.sqlite3"), "DELETE")
    rec["cleanup"] = _sweep(parent)
    return rec


def main():
    os.makedirs(RESULTS, exist_ok=True)
    import platform

    share = os.path.join(HOME, "share")
    chore = os.path.join(share, "Chore_Boy")
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "hostname": platform.node(),
        "share_stat": _stat(share),
        "share_list": _list(share, 80),
        "chore_boy": _probe(chore),
        "chore_boy_list_after": _list(chore, 80),
    }
    if os.path.isdir(chore):
        listing = report["chore_boy_list_after"]
        nested = {}
        if "names" in listing:
            for name in listing["names"]:
                if name.startswith("net") or name in ("CBCS", "cbcs"):
                    nested[name] = _list(os.path.join(chore, name), 40)
        report["nested_interest"] = nested
    desktop = os.path.join(HOME, "Desktop")
    report["desktop_stat"] = _stat(desktop)
    report["desktop_list"] = _list(desktop, 80)
    path = os.path.join(RESULTS, "share_extra.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("hostname", report["hostname"])
    print("share", report["share_list"])
    chore_rec = report["chore_boy"]
    print(
        "chore",
        chore_rec.get("exists_dir"),
        chore_rec.get("fcntl_lock"),
        (chore_rec.get("sqlite_wal") or {}).get("journal_mode")
        or (chore_rec.get("sqlite_wal") or {}).get("error_type"),
        (chore_rec.get("cleanup") or {}).get("left"),
    )
    print("desktop", report["desktop_list"])


if __name__ == "__main__":
    main()
