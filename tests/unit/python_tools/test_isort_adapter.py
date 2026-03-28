"""Unit tests for isort-backed import organization."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.python_tools.isort_adapter import organize_imports_text

pytestmark = pytest.mark.unit


def _fixture_root(name: str) -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "formatting" / name


def test_organize_imports_defaults_to_python39_stdlib_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _fixture_root("default_project")
    input_path = project_root / "input_imports.py"
    expected_path = project_root / "expected_organized_imports.py"

    expected_text = expected_path.read_text(encoding="utf-8")

    class _FakeIsortModule:
        class Config:
            def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
                pass

        class api:
            @staticmethod
            def sort_code_string(source_text: str, *, config: object, file_path: Path) -> str:  # noqa: ARG004
                _ = source_text
                return expected_text

    monkeypatch.setattr(
        "app.python_tools.isort_adapter.import_python_tooling_modules",
        lambda: (object(), _FakeIsortModule(), object()),
    )
    result = organize_imports_text(
        input_path.read_text(encoding="utf-8"),
        file_path=str(input_path),
        project_root=str(project_root),
    )

    assert result.status == "imports_organized"
    assert result.changed is True
    assert result.formatted_text == expected_text


def test_organize_imports_preserves_future_imports_comments_and_src_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _fixture_root("py39_project")
    input_path = project_root / "input_imports.py"
    expected_path = project_root / "expected_organized_imports.py"

    expected_text = expected_path.read_text(encoding="utf-8")

    class _FakeIsortModule:
        class Config:
            def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
                pass

        class api:
            @staticmethod
            def sort_code_string(source_text: str, *, config: object, file_path: Path) -> str:  # noqa: ARG004
                _ = source_text
                return expected_text

    monkeypatch.setattr(
        "app.python_tools.isort_adapter.import_python_tooling_modules",
        lambda: (object(), _FakeIsortModule(), object()),
    )
    result = organize_imports_text(
        input_path.read_text(encoding="utf-8"),
        file_path=str(input_path),
        project_root=str(project_root),
    )

    assert result.status == "imports_organized"
    assert result.changed is True
    assert result.formatted_text == expected_text


def test_organize_imports_reports_syntax_errors_without_mutating_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _fixture_root("broken_project")
    input_path = project_root / "broken.py"
    source = input_path.read_text(encoding="utf-8")

    class _FakeIsortModule:
        class Config:
            def __init__(self, **_kwargs) -> None:  # type: ignore[no-untyped-def]
                pass

        class api:
            @staticmethod
            def sort_code_string(source_text: str, *, config: object, file_path: Path) -> str:  # noqa: ARG004
                raise SyntaxError("invalid syntax")

    monkeypatch.setattr(
        "app.python_tools.isort_adapter.import_python_tooling_modules",
        lambda: (object(), _FakeIsortModule(), object()),
    )
    result = organize_imports_text(
        source,
        file_path=str(input_path),
        project_root=str(project_root),
    )

    assert result.status == "syntax_error"
    assert result.changed is False
    assert result.formatted_text == source


def test_organize_imports_reports_tool_unavailable_when_isort_api_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.python_tools.isort_adapter.import_python_tooling_modules",
        lambda: (_ for _ in ()).throw(RuntimeError("isort missing APIs (api.sort_code_string)")),
    )

    result = organize_imports_text(
        "import os\nimport json\n",
        file_path="/tmp/project/main.py",
        project_root="/tmp/project",
    )

    assert result.status == "tool_unavailable"
    assert result.changed is False
    assert "isort missing APIs" in (result.error_message or "")
