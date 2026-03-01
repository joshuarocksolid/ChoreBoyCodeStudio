"""Unit tests for traceback problem parser."""

import pytest

from app.run.problem_parser import parse_traceback_problems

pytestmark = pytest.mark.unit


def test_parse_traceback_problems_extracts_file_line_entries() -> None:
    """Parser should produce one problem entry per traceback frame."""
    traceback_text = """
Traceback (most recent call last):
  File "/tmp/project/run.py", line 4, in <module>
    main()
  File "/tmp/project/app/main.py", line 8, in main
    raise RuntimeError("boom")
RuntimeError: boom
"""
    problems = parse_traceback_problems(traceback_text)

    assert len(problems) == 2
    assert problems[0].file_path == "/tmp/project/run.py"
    assert problems[0].line_number == 4
    assert problems[1].file_path == "/tmp/project/app/main.py"
    assert problems[1].message == "RuntimeError: boom"


def test_parse_traceback_problems_returns_empty_for_non_traceback_text() -> None:
    """Non-traceback output should not create fake problem entries."""
    assert parse_traceback_problems("plain output only") == []
