"""Schema helper entry. One request, one response, then exit."""

from __future__ import annotations

from typing import IO, Sequence, Tuple

from app.features.form_builder.engine.data.helper.service import HelperCancelled, handle
from app.features.form_builder.engine.ipc.protocol import CancelHelper, decode_line, encode_frame


def main(argv: Sequence[str], streams: Tuple[IO[str], IO[str]]) -> int:
    del argv
    requests, frames = streams
    line = requests.readline()
    if line.endswith("\n"):
        line = line[:-1]
    if not line:
        return 0
    message = decode_line(line)
    if isinstance(message, CancelHelper):
        return 0
    try:
        response = handle(message, requests, frames)
    except HelperCancelled:
        return 0
    if response is not None:
        frames.write(encode_frame(response))
        frames.flush()
    return 0


__all__ = ["main"]
