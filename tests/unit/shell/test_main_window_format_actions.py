"""Unit tests for MainWindow format/import actions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.plugins.workflow_broker import WorkflowProviderDescriptor
from app.python_tools.models import (
    PYTHON_TOOLING_CONFIG_SOURCE_DEFAULTS,
    PYTHON_TOOLING_STATUS_FORMATTED,
    PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
    PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
    PythonTextTransformResult,
    PythonToolingSettings,
)
from app.shell.main_window import MainWindow

pytestmark = pytest.mark.unit


class _FakeEditorWidget:
    def __init__(self, text: str) -> None:
        self._text = text
        self.replacements: list[str] = []

    def toPlainText(self) -> str:
        return self._text

    def replace_document_text(self, replacement_text: str) -> bool:
        self.replacements.append(replacement_text)
        self._text = replacement_text
        return True


class _FakeEditorManager:
    def __init__(self, file_path: str, text: str) -> None:
        self._tab = SimpleNamespace(
            file_path=file_path,
            current_content=text,
            is_dirty=True,
            display_name=Path(file_path).name,
        )
        self.saved_contents: list[str] = []

    def active_tab(self) -> object:
        return self._tab

    def all_tabs(self) -> list[object]:
        return [self._tab]

    def get_tab(self, file_path: str) -> object | None:
        return self._tab if self._tab.file_path == file_path else None

    def update_tab_content(self, file_path: str, content: str) -> object:
        assert self._tab.file_path == file_path
        self._tab.current_content = content
        self._tab.is_dirty = True
        return self._tab

    def save_tab(self, file_path: str) -> object:
        assert self._tab.file_path == file_path
        self.saved_contents.append(self._tab.current_content)
        self._tab.is_dirty = False
        return self._tab


def _dummy_python_settings(file_path: str) -> PythonToolingSettings:
    path = Path(file_path)
    return PythonToolingSettings(
        project_root=path.parent,
        file_path=path,
        pyproject_path=None,
        config_source=PYTHON_TOOLING_CONFIG_SOURCE_DEFAULTS,
        config_error=None,
        python_target_minor=39,
        black_line_length=88,
        black_target_versions=("py39",),
    )


def _wf_descriptor(*, title: str = "Test provider") -> WorkflowProviderDescriptor:
    return WorkflowProviderDescriptor(
        provider_key="test",
        kind="test",
        lane="test",
        title=title,
        source_kind="builtin",
    )


def _build_window(file_path: str, text: str) -> tuple[MainWindow, _FakeEditorWidget]:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    editor_widget = _FakeEditorWidget(text)
    window_any._editor_manager = SimpleNamespace(active_tab=lambda: SimpleNamespace(file_path=file_path))
    window_any._editor_widgets_by_path = {file_path: editor_widget}
    window_any._loaded_project = SimpleNamespace(project_root=str(Path(file_path).parent))
    window_any._workflow_broker = object()
    return window, editor_widget


def _build_save_window(file_path: str, text: str) -> tuple[MainWindow, _FakeEditorManager]:
    window = MainWindow.__new__(MainWindow)
    window_any = cast(Any, window)
    editor_manager = _FakeEditorManager(file_path, text)
    window_any._editor_manager = editor_manager
    window_any._editor_widgets_by_path = {}
    window_any._editor_trim_trailing_whitespace_on_save = True
    window_any._editor_insert_final_newline_on_save = True
    window_any._editor_organize_imports_on_save = False
    window_any._editor_format_on_save = False
    window_any._editor_tabs_widget = None
    window_any._local_history_workflow = SimpleNamespace(
        discard_pending_autosave=lambda *_args, **_kwargs: None,
        record_checkpoint=lambda *_args, **_kwargs: None,
        delete_draft=lambda *_args, **_kwargs: None,
        local_history_context_for_path=lambda *_args, **_kwargs: (None, None),
    )
    window_any._refresh_save_action_states = lambda: None
    window_any._update_editor_status_for_path = lambda *_args, **_kwargs: None
    window_any._intelligence_runtime_settings = SimpleNamespace()
    window_any._loaded_project = SimpleNamespace(project_root=str(Path(file_path).parent))
    window_any._workflow_broker = object()
    window_any._background_tasks = SimpleNamespace(run=lambda **_kwargs: None)
    window_any._test_explorer_panel = None
    window_any._test_outcomes_by_node_id = {}
    window_any._render_lint_diagnostics_for_file = lambda *_args, **_kwargs: None
    window_any._start_symbol_indexing = lambda *_args, **_kwargs: None
    window_any._logger = SimpleNamespace(info=lambda *_a, **_kw: None, warning=lambda *_a, **_kw: None)
    return window, editor_manager


def test_handle_format_current_file_action_uses_black_for_python_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, editor_widget = _build_window("/tmp/project/main.py", "value={'alpha':1}\n")
    calls: list[dict[str, str]] = []
    infos: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []

    def _fake_format(
        _broker: object,
        *,
        source_text: str,
        file_path: str,
        project_root: str,
        preferred_provider_key: str | None = None,
    ) -> tuple[WorkflowProviderDescriptor, PythonTextTransformResult]:
        calls.append(
            {
                "source_text": source_text,
                "file_path": file_path,
                "project_root": project_root,
            }
        )
        return (
            _wf_descriptor(title="Black"),
            PythonTextTransformResult(
                formatted_text='value = {"alpha": 1}\n',
                changed=True,
                status=PYTHON_TOOLING_STATUS_FORMATTED,
                settings=_dummy_python_settings(file_path),
            ),
        )

    monkeypatch.setattr("app.shell.main_window.format_python_with_workflow", _fake_format)
    monkeypatch.setattr(
        "app.shell.main_window.format_text_basic",
        lambda *_args, **_kwargs: pytest.fail("Non-Python formatter should not run for .py files"),
    )
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    MainWindow._handle_format_current_file_action(window)

    assert calls == [
        {
            "source_text": "value={'alpha':1}\n",
            "file_path": "/tmp/project/main.py",
            "project_root": "/tmp/project",
        }
    ]
    assert editor_widget.replacements == ['value = {"alpha": 1}\n']
    assert infos == [("Format Current File", "Formatting applied via Black.")]
    assert warnings == []


def test_handle_format_current_file_action_uses_basic_formatter_for_non_python_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, editor_widget = _build_window("/tmp/project/notes.txt", "alpha   \n")
    infos: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.shell.main_window.format_python_with_workflow",
        lambda *_a, **_kw: pytest.fail("Python formatter should not run for non-Python files"),
    )
    monkeypatch.setattr(
        "app.shell.main_window.format_text_basic",
        lambda *_args, **_kwargs: SimpleNamespace(changed=True, formatted_text="alpha\n"),
    )
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )

    MainWindow._handle_format_current_file_action(window)

    assert editor_widget.replacements == ["alpha\n"]
    assert infos == [("Format Current File", "Formatting applied.")]


def test_handle_format_current_file_action_surfaces_python_syntax_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, editor_widget = _build_window("/tmp/project/main.py", "def broken(:\n    pass\n")
    warnings: list[tuple[str, str]] = []

    def _fake_format(
        _broker: object,
        *,
        source_text: str,
        file_path: str,
        project_root: str,
        preferred_provider_key: str | None = None,
    ) -> tuple[WorkflowProviderDescriptor, PythonTextTransformResult]:
        return (
            _wf_descriptor(title="Black"),
            PythonTextTransformResult(
                formatted_text="def broken(:\n    pass\n",
                changed=False,
                status=PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
                settings=_dummy_python_settings("/tmp/project/main.py"),
                error_message="Cannot parse",
            ),
        )

    monkeypatch.setattr("app.shell.main_window.format_python_with_workflow", _fake_format)
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    MainWindow._handle_format_current_file_action(window)

    assert editor_widget.replacements == []
    assert warnings == [
        (
            "Format Current File",
            "Formatting skipped because the file contains Python syntax errors.",
        )
    ]


def test_handle_organize_imports_action_uses_isort_for_python_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, editor_widget = _build_window("/tmp/project/main.py", "import b\nimport a\n")
    calls: list[dict[str, str]] = []
    infos: list[tuple[str, str]] = []

    def _fake_organize(
        _broker: object,
        *,
        source_text: str,
        file_path: str,
        project_root: str,
        preferred_provider_key: str | None = None,
    ) -> tuple[WorkflowProviderDescriptor, PythonTextTransformResult]:
        calls.append(
            {
                "source_text": source_text,
                "file_path": file_path,
                "project_root": project_root,
            }
        )
        return (
            _wf_descriptor(title="isort"),
            PythonTextTransformResult(
                formatted_text="import a\nimport b\n",
                changed=True,
                status=PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
                settings=_dummy_python_settings(file_path),
            ),
        )

    monkeypatch.setattr("app.shell.main_window.organize_imports_with_workflow", _fake_organize)
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )

    MainWindow._handle_organize_imports_action(window)

    assert calls == [
        {
            "source_text": "import b\nimport a\n",
            "file_path": "/tmp/project/main.py",
            "project_root": "/tmp/project",
        }
    ]
    assert editor_widget.replacements == ["import a\nimport b\n"]
    assert infos == [("Organize Imports", "Imports organized via isort.")]


def test_handle_organize_imports_action_rejects_non_python_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, editor_widget = _build_window("/tmp/project/notes.txt", "alpha\n")
    infos: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.shell.main_window.organize_imports_with_workflow",
        lambda *_a, **_kw: pytest.fail("isort should not run for non-Python files"),
    )
    monkeypatch.setattr(
        "app.shell.main_window.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )

    MainWindow._handle_organize_imports_action(window)

    assert editor_widget.replacements == []
    assert infos == [
        (
            "Organize Imports",
            "Organize Imports is currently available for Python files only.",
        )
    ]


def test_save_tab_runs_hygiene_then_organize_then_format_for_python_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, editor_manager = _build_save_window("/tmp/project/main.py", "import b  \nimport a")
    window_any = cast(Any, window)
    window_any._editor_organize_imports_on_save = True
    window_any._editor_format_on_save = True
    organize_calls: list[str] = []
    format_calls: list[str] = []

    def _fake_organize_save(
        _broker: object,
        *,
        source_text: str,
        file_path: str,
        project_root: str,
        preferred_provider_key: str | None = None,
    ) -> tuple[WorkflowProviderDescriptor, PythonTextTransformResult]:
        organize_calls.append(source_text)
        return (
            _wf_descriptor(title="isort"),
            PythonTextTransformResult(
                formatted_text="import a\nimport b\n",
                changed=True,
                status=PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
                settings=_dummy_python_settings("/tmp/project/main.py"),
            ),
        )

    def _fake_format_save(
        _broker: object,
        *,
        source_text: str,
        file_path: str,
        project_root: str,
        preferred_provider_key: str | None = None,
    ) -> tuple[WorkflowProviderDescriptor, PythonTextTransformResult]:
        format_calls.append(source_text)
        return (
            _wf_descriptor(title="Black"),
            PythonTextTransformResult(
                formatted_text="import a\n\nimport b\n",
                changed=True,
                status=PYTHON_TOOLING_STATUS_FORMATTED,
                settings=_dummy_python_settings("/tmp/project/main.py"),
            ),
        )

    monkeypatch.setattr("app.shell.save_workflow.organize_imports_with_workflow", _fake_organize_save)
    monkeypatch.setattr("app.shell.save_workflow.format_python_with_workflow", _fake_format_save)
    monkeypatch.setattr(
        "app.shell.save_workflow.should_refresh_index_after_save",
        lambda *_args, **_kwargs: False,
    )

    assert MainWindow._save_tab(window, "/tmp/project/main.py") is True
    assert organize_calls == ["import b\nimport a\n"]
    assert format_calls == ["import a\nimport b\n"]
    assert editor_manager.saved_contents == ["import a\n\nimport b\n"]


def test_save_tab_still_saves_when_python_style_automation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, editor_manager = _build_save_window("/tmp/project/main.py", "import b\nimport a")
    window_any = cast(Any, window)
    window_any._editor_organize_imports_on_save = True
    warnings: list[tuple[str, str]] = []

    def _fake_organize_err(
        _broker: object,
        *,
        source_text: str,
        file_path: str,
        project_root: str,
        preferred_provider_key: str | None = None,
    ) -> tuple[WorkflowProviderDescriptor, PythonTextTransformResult]:
        return (
            _wf_descriptor(title="isort"),
            PythonTextTransformResult(
                formatted_text="import b\nimport a\n",
                changed=False,
                status=PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
                settings=_dummy_python_settings("/tmp/project/main.py"),
                error_message="Cannot parse",
            ),
        )

    monkeypatch.setattr("app.shell.save_workflow.organize_imports_with_workflow", _fake_organize_err)
    monkeypatch.setattr(
        "app.shell.save_workflow.should_refresh_index_after_save",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "app.shell.save_workflow.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    assert MainWindow._save_tab(window, "/tmp/project/main.py") is True
    assert editor_manager.saved_contents == ["import b\nimport a\n"]
    assert warnings == [
        (
            "Save formatting",
            "Organize Imports on save skipped because the file contains Python syntax errors.",
        )
    ]


def test_save_tab_skips_python_style_automation_when_file_exceeds_guardrail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, editor_manager = _build_save_window("/tmp/project/main.py", "import b\nimport a\n")
    window_any = cast(Any, window)
    window_any._editor_organize_imports_on_save = True
    window_any._editor_format_on_save = True
    warnings: list[tuple[str, str]] = []

    monkeypatch.setattr("app.shell.save_workflow.PYTHON_STYLE_SAVE_GUARDRAIL_CHAR_LIMIT", 5)
    monkeypatch.setattr(
        "app.shell.save_workflow.organize_imports_with_workflow",
        lambda *_a, **_kw: pytest.fail("Guardrail should skip organize imports"),
    )
    monkeypatch.setattr(
        "app.shell.save_workflow.format_python_with_workflow",
        lambda *_a, **_kw: pytest.fail("Guardrail should skip formatting"),
    )
    monkeypatch.setattr(
        "app.shell.save_workflow.should_refresh_index_after_save",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "app.shell.save_workflow.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    assert MainWindow._save_tab(window, "/tmp/project/main.py") is True
    assert editor_manager.saved_contents == ["import b\nimport a\n"]
    assert warnings == [
        (
            "Save formatting",
            "Python style automation was skipped on save because the file exceeds the size guardrail.",
        )
    ]


def test_save_tab_applies_generic_hygiene_without_python_format_on_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window, editor_manager = _build_save_window("/tmp/project/notes.txt", "note   ")

    monkeypatch.setattr(
        "app.shell.save_workflow.should_refresh_index_after_save",
        lambda *_args, **_kwargs: False,
    )

    assert MainWindow._save_tab(window, "/tmp/project/notes.txt") is True
    assert editor_manager.saved_contents == ["note\n"]


def test_flush_auto_save_to_file_does_not_apply_save_transforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Buffer ends in 4 trailing spaces, simulating a freshly auto-indented blank line
    # the user is sitting on. If auto-save runs trim_trailing_whitespace_on_save the
    # spaces vanish and the cursor jumps to column 0 (the bug Clair reported).
    file_path = "/tmp/project/main.py"
    buffer_with_trailing_indent = "def foo():\n    "
    window, editor_manager = _build_save_window(file_path, buffer_with_trailing_indent)
    window_any = cast(Any, window)
    window_any._editor_auto_save = True
    window_any._editor_organize_imports_on_save = True
    window_any._editor_format_on_save = True

    monkeypatch.setattr(
        "app.shell.save_workflow.should_refresh_index_after_save",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "app.shell.save_workflow.organize_imports_with_workflow",
        lambda *_a, **_kw: pytest.fail("Auto-save must not invoke isort"),
    )
    monkeypatch.setattr(
        "app.shell.save_workflow.format_python_with_workflow",
        lambda *_a, **_kw: pytest.fail("Auto-save must not invoke Black"),
    )
    monkeypatch.setattr(
        "app.shell.save_workflow.format_text_basic",
        lambda *_a, **_kw: pytest.fail("Auto-save must not invoke the basic formatter"),
    )

    MainWindow._flush_auto_save_to_file(window)

    assert editor_manager.saved_contents == [buffer_with_trailing_indent]
