"""Guest entry: ensure disposable HOME exists, then start the editor.

Lives in the rsynced checkout. SQLite state must not sit on virtiofs.
"""

from __future__ import annotations

import os
import runpy
import sys


def main() -> None:
    home = os.environ.get("HOME") or "/home/default/cbcs-verify-home"
    os.makedirs(home, exist_ok=True)
    root = os.environ.get("CBCS_PACKAGE_ROOT")
    if not root:
        # scripts/ -> verify-cbcs -> skills -> .cursor -> repo
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    entry = os.path.join(root, "run_editor.py")
    if root not in sys.path:
        sys.path.insert(0, root)
    os.chdir(root)
    sys.argv = [entry] + sys.argv[1:]
    runpy.run_path(entry, run_name="__main__")


if __name__ == "__main__":
    main()
