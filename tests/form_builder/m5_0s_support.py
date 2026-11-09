"""A throwaway package of contributor modules for the M5.0s seam tests.

Each seam finds contributors by listing the modules of a package. A test
writes a few modules into a temporary package and hands it to the seam's
loader, which proves a lane can add a file and edit nothing shared.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Dict

import pytest


def make_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, files: Dict[str, str]) -> ModuleType:
    root = tmp_path / name
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    for module, body in files.items():
        (root / (module + ".py")).write_text(textwrap.dedent(body), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return __import__(name)


def forget_package(name: str) -> None:
    for loaded in list(sys.modules):
        if loaded == name or loaded.startswith(name + "."):
            del sys.modules[loaded]
