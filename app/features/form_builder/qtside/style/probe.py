"""Asks Qt whether it can read a style sheet (UX-STYLE-004). No subprocess, no external tool.

The text is set on a hidden widget with a message handler installed, and the
widget is polished so Qt parses it. Qt reports an unreadable sheet as
"Could not parse stylesheet of object ..."; an unknown property is reported as
"Unknown property <name>". Qt's verdict is final (UX-STYLE-004).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from app.qt.QtCore import qInstallMessageHandler
from app.qt.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

_UNREADABLE = "Could not parse stylesheet"
_UNKNOWN = "Unknown property "

_PROBE: Optional[QWidget] = None


@dataclass(frozen=True)
class QtVerdict:
    readable: bool
    unknown_properties: Tuple[str, ...] = ()


def _widget() -> Optional[QWidget]:
    global _PROBE
    if QApplication.instance() is None:
        return None
    if _PROBE is None:
        _PROBE = QWidget()
        _PROBE.setObjectName("formBuilder.styleProbe")
    return _PROBE


def ask_qt(text: str) -> Optional[QtVerdict]:
    """Qt's verdict on ``text``, or None when there is no application to ask."""
    probe = _widget()
    if probe is None:
        return None
    seen: List[str] = []

    def handler(_mode: object, _context: object, message: str) -> None:
        seen.append(message)

    previous: Optional[Callable[..., None]] = qInstallMessageHandler(handler)
    try:
        probe.setStyleSheet("")
        probe.setStyleSheet(text)
        probe.ensurePolished()
    finally:
        qInstallMessageHandler(previous)
        try:
            probe.setStyleSheet("")
        except RuntimeError:
            logger.exception("style probe could not be cleared")
    readable = not any(_UNREADABLE in message for message in seen)
    unknown = tuple(
        sorted({message[len(_UNKNOWN) :].strip() for message in seen if message.startswith(_UNKNOWN)})
    )
    return QtVerdict(readable, unknown)


def qt_reads(text: str) -> Optional[bool]:
    verdict = ask_qt(text)
    return None if verdict is None else verdict.readable
