"""Unit tests for Black-backed Python formatting."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.python_tools.black_adapter import format_python_text

pytestmark = pytest.mark.unit


def _fixture_root(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "formatting" / name


def test_format_python_text_uses_project_local_black_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _fixture_root("py39_project")
    input_path = project_root / "input_format.py"
    expected_path = project_root / "expected_format.py"
    expected_text = expected_path.read_text(encoding="utf-8")

    class _FakeBlackModule:
        class TargetVersion:
            PY39 = object()

        class Mode:
            def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
                pass

        class NothingChanged(Exception):
            pass

        class InvalidInput(Exception):
            pass

        @staticmethod
        def format_file_contents(source_text: str, *, fast: bool, mode: object) -> str:  # noqa: ARG004
            _ = source_text
            return expected_text

    monkeypatch.setattr(
        "app.python_tools.black_adapter.import_python_tooling_modules",
        lambda: (_FakeBlackModule(), object(), object()),
    )
    result = format_python_text(
        input_path.read_text(encoding="utf-8"),
        file_path=str(input_path),
        project_root=str(project_root),
    )

    assert result.status == "formatted"
    assert result.changed is True
    assert result.formatted_text == expected_text


def test_format_python_text_reports_syntax_errors_without_mutating_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _fixture_root("broken_project")
    input_path = project_root / "broken.py"
    source = input_path.read_text(encoding="utf-8")

    class _FakeBlackModule:
        class TargetVersion:
            PY39 = object()

        class Mode:
            def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
                pass

        class NothingChanged(Exception):
            pass

        class InvalidInput(Exception):
            pass

        @staticmethod
        def format_file_contents(source_text: str, *, fast: bool, mode: object) -> str:  # noqa: ARG004
            raise _FakeBlackModule.InvalidInput("Cannot parse")

    monkeypatch.setattr(
        "app.python_tools.black_adapter.import_python_tooling_modules",
        lambda: (_FakeBlackModule(), object(), object()),
    )
    result = format_python_text(
        source,
        file_path=str(input_path),
        project_root=str(project_root),
    )

    assert result.status == "syntax_error"
    assert result.changed is False
    assert result.formatted_text == source


def test_format_python_text_reports_tool_unavailable_when_black_api_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.python_tools.black_adapter.import_python_tooling_modules",
        lambda: (_ for _ in ()).throw(RuntimeError("black missing APIs (format_file_contents)")),
    )

    result = format_python_text(
        "value={'alpha':1}\n",
        file_path="/tmp/project/main.py",
        project_root="/tmp/project",
    )

    assert result.status == "tool_unavailable"
    assert result.changed is False
    assert "black missing APIs" in (result.error_message or "")
