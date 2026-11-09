"""Report paths this process just wrote, so an open editor can refresh them.

The form builder installs the listener. With none set, the calls do nothing.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

_Listener = Callable[[Sequence[str]], None]
_listener: Optional[_Listener] = None


def set_written_file_listener(listener: Optional[_Listener]) -> Optional[_Listener]:
    """Install ``listener`` and return the previous one."""
    global _listener
    previous = _listener
    _listener = listener
    return previous


def note_written_files(paths: Sequence[str]) -> None:
    """Tell the listener about paths that were just written."""
    listener = _listener
    if listener is None:
        return
    reported = tuple(path for path in paths if path)
    if reported:
        listener(reported)
