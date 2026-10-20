#!/usr/bin/env python
"""Read mount and idesk files from confined AppRun. Creates nothing in $HOME."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(ROOT, "results")


def _run(argv, timeout=15):
    rec = {"argv": argv}
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout, text=True)
        rec["returncode"] = proc.returncode
        rec["stdout"] = (proc.stdout or "")[:30000]
        rec["stderr"] = (proc.stderr or "")[:4000]
    except Exception as exc:
        rec["error_type"] = type(exc).__name__
        rec["errno"] = getattr(exc, "errno", None)
        rec["error"] = str(exc)
    return rec


def main():
    os.makedirs(RESULTS, exist_ok=True)
    script = r"""
echo '## mounts'
cat /proc/mounts
echo '## ideskrc'
ls -la /home/default/.ideskrc /home/default/.idesktop /home/default/share /home/default/.nfs_log.txt
echo '## ideskrc body'
cat /home/default/.ideskrc
echo '## idesktop'
ls -la /home/default/.idesktop
for f in /home/default/.idesktop/*; do
  echo "FILE $f"
  cat "$f"
  echo
done
echo '## nfs log head'
head -c 2000 /home/default/.nfs_log.txt
echo
echo '## share stat'
stat -c 'share dev=%d ino=%i %F' /home/default/share
stat -c 'home dev=%d ino=%i %F' /home/default
"""
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "sh": _run(["/bin/sh", "-c", script], timeout=20),
    }
    path = os.path.join(RESULTS, "read_more.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    item = report["sh"]
    print("rc", item.get("returncode"), item.get("error_type"))
    print((item.get("stdout") or item.get("error") or "")[:2000])


if __name__ == "__main__":
    main()
