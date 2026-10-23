"""Save writes a sourced tab's current text exactly, and still normalizes plain text."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.editors.formatting_service import format_text_basic  # noqa: E402
from app.python_tools.models import (  # noqa: E402
    PYTHON_TOOLING_CONFIG_SOURCE_DEFAULTS,
    PYTHON_TOOLING_STATUS_FORMATTED,
    PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
    PythonTextTransformResult,
    PythonToolingSettings,
)
from tests.support.shell_host_stubs import save_workflow_stub  # noqa: E402

pytestmark = pytest.mark.unit

_SOURCED_TEXT = "keep \r this  \ntrailing  "
_PLAIN_TEXT = "alpha  \nbeta\t"


class _FixedSource:
    def __init__(self, text: str) -> None:
        self._text = text

    def current_text(self) -> str:
        return self._text

    def is_dirty(self) -> bool:
        return True

    def mark_saved(self, saved_text: str) -> None:
        return None

    def revision(self) -> int:
        return 1

    def subscribe_changed(self, listener: object) -> object:
        return lambda: None


def _rewritten_tool_result(file_path: str, *, status: str) -> PythonTextTransformResult:
    path = Path(file_path)
    return PythonTextTransformResult(
        formatted_text="formatter rewrote this\n",
        changed=True,
        status=status,
        settings=PythonToolingSettings(
            project_root=path.parent,
            file_path=path,
            pyproject_path=None,
            config_source=PYTHON_TOOLING_CONFIG_SOURCE_DEFAULTS,
            config_error=None,
            python_target_minor=9,
            black_line_length=88,
        ),
    )


def test_sourced_tab_save_writes_current_text_bytes_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trailing spaces, a CR, and a missing final newline survive save."""
    path = tmp_path / "widget.py"
    path.write_bytes(b"OLD\n")
    manager = EditorManager()
    opened = manager.open_file_with_content(str(path), "stale buffer")
    source = _FixedSource(_SOURCED_TEXT)
    opened.tab.content_source = source
    normalized = format_text_basic(
        _SOURCED_TEXT,
        trim_trailing_whitespace=True,
        ensure_final_newline=True,
    ).formatted_text
    assert normalized != _SOURCED_TEXT

    def _organize(*_args: object, **kwargs: object) -> tuple[object, PythonTextTransformResult]:
        file_path = str(kwargs["file_path"])
        return (
            object(),
            _rewritten_tool_result(file_path, status=PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED),
        )

    def _format(*_args: object, **kwargs: object) -> tuple[object, PythonTextTransformResult]:
        file_path = str(kwargs["file_path"])
        return (
            object(),
            _rewritten_tool_result(file_path, status=PYTHON_TOOLING_STATUS_FORMATTED),
        )

    monkeypatch.setattr("app.shell.save_workflow.organize_imports_with_workflow", _organize)
    monkeypatch.setattr("app.shell.save_workflow.format_python_with_workflow", _format)
    workflow = save_workflow_stub(manager, python_style_on_save=True)

    assert workflow.save_tab(str(path)) is True

    assert path.read_bytes() == _SOURCED_TEXT.encode("utf-8")


@pytest.mark.parametrize("file_name", ["notes.txt", "readme.md"])
def test_unsourced_tab_save_applies_text_hygiene(tmp_path: Path, file_name: str) -> None:
    """Plain text and Markdown have no content source, so save still normalizes them."""
    path = tmp_path / file_name
    path.write_bytes(b"OLD\n")
    manager = EditorManager()
    opened = manager.open_file_with_content(str(path), _PLAIN_TEXT)
    assert opened.tab.content_source is None
    workflow = save_workflow_stub(manager, python_style_on_save=True)

    assert workflow.save_tab(str(path)) is True

    assert path.read_bytes() == b"alpha\nbeta\n"
