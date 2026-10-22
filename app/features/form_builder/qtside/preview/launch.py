"""How the editor starts the preview child."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List

from app.run.runtime_launch import build_runpy_bootstrap_payload

_PREVIEW_SCRIPT = "run_form_preview.py"


def repo_root() -> str:
    return str(Path(__file__).resolve().parents[5])


def default_apprun() -> str:
    configured = os.environ.get("CBCS_FB_APPRUN_11", "").strip()
    if configured:
        return configured
    return "/opt/freecad-1.1/AppRun"


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


def python_preview_command(python: str, root: str) -> List[str]:
    """A child on an already-warm interpreter. Unit tests use this."""
    return [python, os.path.join(root, _PREVIEW_SCRIPT)]


def apprun_preview_command(apprun: str, root: str) -> List[str]:
    """The ChoreBoy command. AppRun ``-c`` stays short via the runpy bootstrap."""
    script = os.path.join(root, _PREVIEW_SCRIPT)
    payload = build_runpy_bootstrap_payload(script_path=script, path_entries=(root,))
    return [apprun, "-c", payload]
