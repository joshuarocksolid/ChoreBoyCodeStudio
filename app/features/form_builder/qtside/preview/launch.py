"""How the editor starts the preview child."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from app.core.constants import APP_RUN_PATH
from app.run.runtime_launch import build_runpy_bootstrap_payload

_PREVIEW_SCRIPT = "run_form_preview.py"


def repo_root() -> str:
    return str(Path(__file__).resolve().parents[5])


def default_apprun() -> str:
    """AppRun for the preview child.

    ``CBCS_FB_APPRUN`` wins. ``CBCS_FB_APPRUN_11`` is the older name for the
    same override. The default is the ChoreBoy Qt 6 runtime.
    """
    primary = os.environ.get("CBCS_FB_APPRUN", "").strip()
    if primary:
        return primary
    alias = os.environ.get("CBCS_FB_APPRUN_11", "").strip()
    if alias:
        return alias
    return APP_RUN_PATH


def current_runtime_python() -> str:
    """Python for a preview child started from this process.

    AppRun's ``sys.executable`` is ``freecad``, and that binary does not run a
    script path. The ``python`` next to it does, with the AppRun environment
    the parent already holds.
    """
    name = os.path.basename(sys.executable).lower()
    sibling = os.path.join(sys.prefix, "bin", "python")
    if name in {"freecad", "freecadcmd"} and os.path.isfile(sibling):
        return sibling
    return sys.executable


def python_preview_command(python: str, root: str, script: str = _PREVIEW_SCRIPT) -> List[str]:
    """A child on an already-warm interpreter. Unit tests use this."""
    return [python, os.path.join(root, script)]


def preview_command(root: str, script: str = _PREVIEW_SCRIPT) -> List[str]:
    """The preview child command.

    ChoreBoy uses AppRun when that file exists. A machine without it starts
    the child on the interpreter that is already running the editor.
    ``script`` is a repo-root filename. The schema helper uses the same builder.
    """
    apprun = default_apprun()
    if os.path.isfile(apprun):
        return apprun_preview_command(apprun, root, script)
    return python_preview_command(current_runtime_python(), root, script)


def apprun_preview_command(apprun: str, root: str, script: str = _PREVIEW_SCRIPT) -> List[str]:
    """The ChoreBoy command. AppRun ``-c`` stays short via the runpy bootstrap."""
    script_path = os.path.join(root, script)
    payload = build_runpy_bootstrap_payload(script_path=script_path, path_entries=(root,))
    return [apprun, "-c", payload]
