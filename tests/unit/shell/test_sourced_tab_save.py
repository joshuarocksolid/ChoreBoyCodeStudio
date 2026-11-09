"""Save writes a sourced tab's current text exactly, and still normalizes plain text."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
from app.shell.save_workflow import SaveWorkflow  # noqa: E402

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


class _SaveHost:
    def __init__(self, editor_manager: EditorManager, *, python_style_on_save: bool) -> None:
        self._editor_manager = editor_manager
        self._python_style_on_save = python_style_on_save

    def editor_manager(self) -> EditorManager:
        return self._editor_manager

    def dialog_parent(self) -> SimpleNamespace:
        return SimpleNamespace()

    def editor_trim_trailing_whitespace_on_save(self) -> bool:
        return True

    def editor_insert_final_newline_on_save(self) -> bool:
        return True

    def editor_organize_imports_on_save(self) -> bool:
        return self._python_style_on_save

    def editor_format_on_save(self) -> bool:
        return self._python_style_on_save

    def resolve_python_tooling_project_root(self, file_path: str) -> str:
        return str(Path(file_path).parent)

    def apply_text_to_open_tab(self, file_path: str, transformed_text: str) -> None:
        self._editor_manager.replace_tab_content(file_path, transformed_text)

    def workflow_broker(self) -> object:
        return object()

    def has_editor_tabs_widget(self) -> bool:
        return False

    def logger(self) -> SimpleNamespace:
        return SimpleNamespace(info=lambda *_a, **_k: None, warning=lambda *_a, **_k: None)

    def refresh_save_action_states(self) -> None:
        return None

    def update_editor_status_for_path(self, file_path: str) -> None:
        return None

    def loaded_project(self) -> None:
        return None

    def intelligence_runtime_settings(self) -> SimpleNamespace:
        return SimpleNamespace()

    def render_lint_for_file(self, file_path: str, *, trigger: str) -> None:
        return None

    def refresh_test_discovery(self) -> None:
        return None


def _workflow(editor_manager: EditorManager, *, python_style_on_save: bool) -> SaveWorkflow:
    return SaveWorkflow(
        local_history=SimpleNamespace(
            discard_pending_autosave=lambda *_a, **_k: None,
            record_checkpoint=lambda *_a, **_k: None,
            delete_draft=lambda *_a, **_k: None,
            local_history_context_for_path=lambda *_a, **_k: (None, None),
        ),
        intelligence_cache=SimpleNamespace(start_symbol_indexing=lambda *_a, **_k: None),
        host=_SaveHost(editor_manager, python_style_on_save=python_style_on_save),
        settings_service=SimpleNamespace(update_global=lambda updater: updater({})),
    )


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
    workflow = _workflow(manager, python_style_on_save=True)

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
    workflow = _workflow(manager, python_style_on_save=True)

    assert workflow.save_tab(str(path)) is True

    assert path.read_bytes() == b"alpha\nbeta\n"
