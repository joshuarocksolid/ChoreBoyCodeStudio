"""Runner output bridging utilities (stdout/stderr + per-run log)."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sys
from typing import Iterator, TextIO


class TeeTextIO(io.TextIOBase):
    """File-like stream that duplicates writes to multiple targets."""

    def __init__(self, *streams: TextIO) -> None:
        self._streams = streams

    def write(self, text: str) -> int:
        for stream in self._streams:
            stream.write(text)
        return len(text)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()


@contextmanager
def redirect_output_to_log(log_file_path: str) -> Iterator[None]:
    """Mirror stdout/stderr to both process pipes and run log file."""
    log_path = Path(log_file_path).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        stdout_target = sys.__stdout__ if sys.__stdout__ is not None else sys.stdout
        stderr_target = sys.__stderr__ if sys.__stderr__ is not None else sys.stderr
        stdout_tee = TeeTextIO(log_file, stdout_target)
        stderr_tee = TeeTextIO(log_file, stderr_target)
        with redirect_stdout(stdout_tee), redirect_stderr(stderr_tee):
            yield
