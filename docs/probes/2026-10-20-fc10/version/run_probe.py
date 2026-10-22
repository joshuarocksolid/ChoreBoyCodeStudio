#!/usr/bin/env python
"""Read-only FreeCAD version, plus whether ~/share is a separate filesystem."""

from __future__ import annotations

import os
import platform
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")
HOME = "/home/default"


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(800)
    except OSError as exc:
        return "ERR %s errno=%s %s" % (type(exc).__name__, getattr(exc, "errno", None), exc)


def _dev(path):
    try:
        st = os.lstat(path)
    except OSError as exc:
        return "ERR %s errno=%s" % (type(exc).__name__, getattr(exc, "errno", None))
    return "dev=%s dir=%s link=%s" % (
        st.st_dev,
        (st.st_mode & 0o170000) == 0o040000,
        (st.st_mode & 0o170000) == 0o120000,
    )


def main():
    lines = []
    lines.append("hostname %s" % platform.node())
    lines.append("python %s" % sys.version.replace("\n", " "))
    lines.append("executable %s" % sys.executable)
    lines.append("kernel %s" % platform.release())
    lines.append("os_release %s" % _read("/etc/os-release").replace("\n", " | "))
    try:
        import FreeCAD

        lines.append("freecad %s" % (list(FreeCAD.Version()),))
    except Exception as exc:
        lines.append("freecad_error %s %s" % (type(exc).__name__, exc))
    lines.append("apparmor %s" % _read("/proc/self/attr/current").strip())
    lines.append("uid %s" % os.getuid())
    for path in (HOME, os.path.join(HOME, "share"), "/tmp", "/mnt/cbprobe"):
        lines.append("stat %s %s" % (path, _dev(path)))
    share = os.path.join(HOME, "share")
    try:
        names = sorted(os.listdir(share))
        lines.append("share_names %s" % names[:40])
    except OSError as exc:
        lines.append("share_names ERR %s errno=%s" % (type(exc).__name__, getattr(exc, "errno", None)))
    desktop = os.path.join(HOME, "Desktop")
    lines.append("desktop_exists %s" % os.path.isdir(desktop))
    text = "\n".join(lines) + "\n"
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "version.txt"), "w", encoding="utf-8") as handle:
        handle.write(text)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
