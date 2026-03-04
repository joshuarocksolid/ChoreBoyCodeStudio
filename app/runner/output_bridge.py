"""Runner output redirection helpers.

This module keeps stdout/stderr behavior explicit:
- runner output still streams to the parent process pipes
- the same output is also persisted to the per-run log file
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
from typing import IO, Iterator


class TeeTextIO:
    """Mirror text writes to both the primary stream and a log file."""

    def __init__(self, primary: IO[str], log_stream: IO[str]) -> None:
        self._primary = primary
        self._log_stream = log_stream
        self.encoding = getattr(primary, "encoding", "utf-8")

    def write(self, text: str) -> int:
        written = self._primary.write(text)
        self._log_stream.write(text)
        return written

    def flush(self) -> None:
        self._primary.flush()
        self._log_stream.flush()

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return bool(getattr(self._primary, "isatty", lambda: False)())


@contextmanager
def redirect_output_to_log(log_file_path: str) -> Iterator[None]:
    """Mirror stdout/stderr to *log_file_path* while preserving pipe output."""
    path = Path(log_file_path).expanduser().resolve()
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        log_stream = path.open("a", encoding="utf-8")
    except OSError as exc:
        try:
            print(f"[runner] unable to open run log at {path}: {exc}", file=original_stderr)
        except Exception:
            pass
        yield
        return

    try:
        with log_stream:
            sys.stdout = TeeTextIO(original_stdout, log_stream)  # type: ignore[assignment]
            sys.stderr = TeeTextIO(original_stderr, log_stream)  # type: ignore[assignment]
            try:
                yield
            finally:
                try:
                    sys.stdout.flush()
                    sys.stderr.flush()
                except Exception:
                    # Flushing should not mask user-code failures.
                    pass
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
