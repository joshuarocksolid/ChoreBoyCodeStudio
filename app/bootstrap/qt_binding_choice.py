"""Choose PySide6 or PySide2 without importing Qt."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Optional

ENV_VAR = "CBCS_QT_API"
_DEFAULT_ORDER = ("PySide6", "PySide2")
_ENV_BINDINGS = {"pyside6": "PySide6", "pyside2": "PySide2"}

_latch_ready = False
_latched_env = ""


def reset_choice_state() -> None:
    """Clear the env latch so a unit test can isolate a later call."""
    global _latch_ready, _latched_env
    _latch_ready = False
    _latched_env = ""


def forced_by_env() -> bool:
    """True when the first observed CBCS_QT_API value is pyside6 or pyside2."""
    global _latch_ready, _latched_env
    if not _latch_ready:
        _latched_env = os.environ.get(ENV_VAR, "").strip().lower()
        _latch_ready = True
    return _latched_env in _ENV_BINDINGS


def binding_candidates() -> tuple[str, ...]:
    """Return the ordered binding names to try. Always reads the live env."""
    forced_by_env()
    forced = _ENV_BINDINGS.get(os.environ.get(ENV_VAR, "").strip().lower())
    if forced is not None:
        return (forced,)
    shim = _freecad_shim_binding()
    if shim is not None:
        return (shim,)
    return _DEFAULT_ORDER


def select_binding() -> str:
    """Return the first candidate that can be imported. Does not import it."""
    for name in binding_candidates():
        if importlib.util.find_spec(name) is not None:
            return name
    current = os.environ.get(ENV_VAR, "")
    raise ImportError(
        "No Qt for Python binding is importable (%s=%r)." % (ENV_VAR, current)
    )


def _freecad_shim_binding() -> Optional[str]:
    spec = importlib.util.find_spec("PySide")
    if spec is None:
        return None
    origin = getattr(spec, "origin", None)
    if not isinstance(origin, str) or "Ext" not in Path(origin).parts[:-1]:
        return None
    try:
        text = Path(origin).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return _binding_named_in_shim(text)


def _binding_named_in_shim(text: str) -> Optional[str]:
    six_at = text.find("from PySide6 import")
    two_at = text.find("from PySide2 import")
    if six_at < 0 and two_at < 0:
        return None
    if six_at >= 0 and (two_at < 0 or six_at < two_at):
        return "PySide6"
    return "PySide2"
