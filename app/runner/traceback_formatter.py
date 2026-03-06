"""Traceback formatting helpers for runner diagnostics."""

from __future__ import annotations

import traceback
from types import TracebackType


def format_traceback(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> str:
    """Return full traceback text for a captured exception."""
    return "".join(traceback.format_exception(exc_type, exc, tb))


def format_current_exception() -> str:
    """Return full traceback for the currently handled exception."""
    return traceback.format_exc()
