"""Unit tests for project reference discovery service."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.intelligence.reference_service import extract_symbol_under_cursor, find_references

pytestmark = pytest.mark.unit


def test_extract_symbol_under_cursor_returns_identifier_token() -> None:
    source = "result = helper_task(value)"
    cursor_position = source.index("helper_task") + 3

    symbol = extract_symbol_under_cursor(source, cursor_position)

    assert symbol == "helper_task"


def test_find_references_collects_definitions_and_usages_across_files(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.py").write_text(
        "def helper_task(value):\n"
        "    return value\n\n"
        "helper_task(1)\n",
        encoding="utf-8",
    )
    current_file = project_root / "b.py"
    current_source = "from a import helper_task\nresult = helper_task(2)\n"
    current_file.write_text(current_source, encoding="utf-8")

    class _Facade:
        def find_references(self, **_kwargs):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                symbol_name="helper_task",
                hits=[
                    SimpleNamespace(
                        symbol_name="helper_task",
                        file_path=str((project_root / "a.py").resolve()),
                        line_number=1,
                        column_number=4,
                        line_text="def helper_task(value):",
                        is_definition=True,
                    ),
                    SimpleNamespace(
                        symbol_name="helper_task",
                        file_path=str((project_root / "a.py").resolve()),
                        line_number=4,
                        column_number=0,
                        line_text="helper_task(1)",
                        is_definition=False,
                    ),
                    SimpleNamespace(
                        symbol_name="helper_task",
                        file_path=str(current_file.resolve()),
                        line_number=2,
                        column_number=9,
                        line_text="result = helper_task(2)",
                        is_definition=False,
                    ),
                ],
                metadata=SimpleNamespace(source="semantic", unsupported_reason="", confidence="exact"),
                found=True,
            )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.intelligence.reference_service._facade", lambda _project_root: _Facade())
    try:
        result = find_references(
            project_root=str(project_root.resolve()),
            current_file_path=str(current_file.resolve()),
            source_text=current_source,
            cursor_position=current_source.rfind("helper_task") + 2,
        )
    finally:
        monkeypatch.undo()

    assert result.symbol_name == "helper_task"
    assert len(result.hits) >= 3
    assert any(hit.is_definition for hit in result.hits)
    assert any(hit.file_path.endswith("b.py") and not hit.is_definition for hit in result.hits)


def test_find_references_excludes_comments_and_string_literals(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    current_file = project_root / "main.py"
    current_source = (
        "def helper_task():\n"
        "    return 'helper_task'\n"
        "# helper_task in comment\n"
        "value = helper_task()\n"
    )
    current_file.write_text(current_source, encoding="utf-8")

    class _Facade:
        def find_references(self, **_kwargs):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                symbol_name="helper_task",
                hits=[
                    SimpleNamespace(
                        symbol_name="helper_task",
                        file_path=str(current_file.resolve()),
                        line_number=1,
                        column_number=4,
                        line_text="def helper_task():",
                        is_definition=True,
                    ),
                    SimpleNamespace(
                        symbol_name="helper_task",
                        file_path=str(current_file.resolve()),
                        line_number=4,
                        column_number=8,
                        line_text="value = helper_task()",
                        is_definition=False,
                    ),
                ],
                metadata=SimpleNamespace(source="semantic", unsupported_reason="", confidence="exact"),
                found=True,
            )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.intelligence.reference_service._facade", lambda _project_root: _Facade())
    try:
        result = find_references(
            project_root=str(project_root.resolve()),
            current_file_path=str(current_file.resolve()),
            source_text=current_source,
            cursor_position=current_source.index("helper_task()") + 1,
        )
    finally:
        monkeypatch.undo()

    assert result.symbol_name == "helper_task"
    assert len(result.hits) == 2
    assert all("comment" not in hit.line_text for hit in result.hits)
    assert all("'helper_task'" not in hit.line_text for hit in result.hits)


def test_find_references_returns_empty_when_no_symbol_at_cursor(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    source = "value = 1 + 2"

    result = find_references(
        project_root=str(project_root.resolve()),
        current_file_path=str((project_root / "main.py").resolve()),
        source_text=source,
        cursor_position=source.index("+"),
    )

    assert result.symbol_name == ""
    assert result.hits == []


def test_find_references_runtime_unavailable_does_not_fallback_to_file_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    helper = project_root / "helper.py"
    helper.write_text("def helper_task(value):\n    return value\nhelper_task(1)\n", encoding="utf-8")
    current_file = project_root / "main.py"
    current_source = "from helper import helper_task\nresult = helper_task(2)\n"
    current_file.write_text(current_source, encoding="utf-8")

    read_counts: dict[str, int] = {}

    def counting_read_text(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        resolved = str(self.resolve())
        read_counts[resolved] = read_counts.get(resolved, 0) + 1
        return ""

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    monkeypatch.setattr(
        "app.intelligence.reference_service._facade",
        lambda _project_root: SimpleNamespace(
            find_references=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("semantic backend unavailable"))
        ),
    )

    result = find_references(
        project_root=str(project_root.resolve()),
        current_file_path=str(current_file.resolve()),
        source_text=current_source,
        cursor_position=current_source.rfind("helper_task") + 2,
    )

    assert result.symbol_name == "helper_task"
    assert result.hits == []
    assert result.metadata is not None
    assert result.metadata.source == "semantic_unavailable"
    assert "runtime_unavailable" in result.metadata.unsupported_reason
    assert read_counts == {}


def test_find_references_surfaces_semantic_runtime_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    current_file = project_root / "main.py"
    source = "value = helper_task\n"
    current_file.write_text(source, encoding="utf-8")

    class _FailingFacade:
        def find_references(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("semantic backend unavailable")

    monkeypatch.setattr(
        "app.intelligence.reference_service._facade",
        lambda _project_root: _FailingFacade(),
    )

    result = find_references(
        project_root=str(project_root.resolve()),
        current_file_path=str(current_file.resolve()),
        source_text=source,
        cursor_position=source.index("helper_task") + 2,
    )

    assert result.symbol_name == "helper_task"
    assert result.hits == []
    assert result.metadata is not None
    assert result.metadata.source == "semantic_unavailable"
    assert "runtime_unavailable" in result.metadata.unsupported_reason
