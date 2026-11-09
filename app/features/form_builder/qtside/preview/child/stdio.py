"""Private frame streams for the preview child (CONTRACTS.md section 10.1).

User code must not see the host's request bytes. ``isolate_stdio`` dups stdin
onto a private fd, then points fd 0 at ``/dev/null``. It dups stdout onto the
frame fd, then points fd 1 at stderr, so a C-level print cannot split a frame.
"""

from __future__ import annotations

import os
import threading
from typing import IO, Tuple, Union

from app.features.form_builder.engine.ipc.protocol import ChildMessage, HostMessage, encode_frame

StreamPair = Tuple[IO[str], IO[str]]
_Message = Union[HostMessage, ChildMessage]


def isolate_stdio() -> StreamPair:
    """Return ``(requests, frames)`` and detach fd 0 and fd 1 from those pipes."""
    devnull = os.open(os.devnull, os.O_RDONLY)
    try:
        request_fd = os.dup(0)
        os.dup2(devnull, 0)
    finally:
        os.close(devnull)
    requests = os.fdopen(request_fd, "r", encoding="utf-8", newline="\n")
    frame_fd = os.dup(1)
    frames = os.fdopen(frame_fd, "w", encoding="utf-8", newline="\n", buffering=1)
    os.dup2(2, 1)
    return requests, frames


class FrameWriter:
    """Serialized writer for the private frame fd."""

    def __init__(self, stream: IO[str]) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def send(self, message: _Message) -> None:
        frame = encode_frame(message)
        with self._lock:
            self._stream.write(frame)
            self._stream.flush()
