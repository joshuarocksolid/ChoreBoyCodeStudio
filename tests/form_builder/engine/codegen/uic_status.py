"""Decide when our setupUi failure is the same failure uic hit.

``env`` and ``same-error`` used to match on the exception type alone, so a
different message on our side still counted as agreement. Addresses, paths
and line numbers are not part of that message.
"""

from __future__ import annotations

import re

_HEX_ADDR = re.compile(r"0x[0-9a-fA-F]+")
_WIN_PATH = re.compile(r"[A-Za-z]:\\[^\s'\"]+")
_UNIX_PATH = re.compile(r"(?:/|\./|\.\./)[^\s:'\"]+")
_PY_FILE = re.compile(r"[\w./\\-]+\.py\b")
_LINE = re.compile(r"(?i)\bline\s+\d+\b")
_COLON_NUM = re.compile(r":\d+\b")
_SPACE = re.compile(r"\s+")


def normalise_exception_text(text: str) -> str:
    """Strip addresses, paths and line numbers so two reports can be compared."""
    cleaned = _HEX_ADDR.sub("0xADDR", text)
    cleaned = _WIN_PATH.sub("<path>", cleaned)
    cleaned = _UNIX_PATH.sub("<path>", cleaned)
    cleaned = _PY_FILE.sub("<file>", cleaned)
    cleaned = _LINE.sub("line N", cleaned)
    cleaned = _COLON_NUM.sub(":N", cleaned)
    return _SPACE.sub(" ", cleaned).strip()


def same_failure(left: BaseException, right: BaseException) -> bool:
    """True when both failures are the same type and the same normalised message."""
    if type(left).__name__ != type(right).__name__:
        return False
    return normalise_exception_text(str(left)) == normalise_exception_text(str(right))
