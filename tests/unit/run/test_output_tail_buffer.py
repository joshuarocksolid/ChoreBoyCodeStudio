"""Unit tests for bounded run output tail buffer."""

from __future__ import annotations

import pytest

from app.run.output_tail_buffer import OutputTailBuffer

pytestmark = pytest.mark.unit


def test_output_tail_buffer_trims_oldest_chunks_by_char_limit() -> None:
    buffer = OutputTailBuffer(max_chars=10, max_chunks=100)

    buffer.append("abc")
    buffer.append("def")
    buffer.append("ghijk")

    assert buffer.text() == "defghijk"
    assert buffer.total_chars == len("defghijk")


def test_output_tail_buffer_trims_by_chunk_limit() -> None:
    buffer = OutputTailBuffer(max_chars=1_000, max_chunks=3)

    buffer.append("1")
    buffer.append("2")
    buffer.append("3")
    buffer.append("4")

    assert buffer.text() == "234"
    assert buffer.chunk_count == 3


def test_output_tail_buffer_clear_resets_state() -> None:
    buffer = OutputTailBuffer(max_chars=10, max_chunks=10)
    buffer.append("hello")
    buffer.clear()

    assert buffer.text() == ""
    assert buffer.total_chars == 0
    assert buffer.chunk_count == 0
