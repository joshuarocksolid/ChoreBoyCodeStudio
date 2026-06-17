"""Unit tests for MainWindow format/import actions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.core import constants
from app.plugins.workflow_broker import WorkflowProviderDescriptor
from app.python_tools.models import (
    PYTHON_TOOLING_CONFIG_SOURCE_DEFAULTS,
    PYTHON_TOOLING_STATUS_FORMATTED,
    PYTHON_TOOLING_STATUS_IMPORTS_ORGANIZED,
    PYTHON_TOOLING_STATUS_SYNTAX_ERROR,
    PythonTextTransformResult,
    PythonToolingSettings,
)
from app.shell.python_style_workflow import PythonStyleWorkflow
from app.shell.save_workflow import SaveWorkflow

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

    def replace_tab_content(self, file_path: str, content: str, *, mark_dirty: bool = True) -> object:
        return self.update_tab_content(file_path, content)

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


class _FormatSaveDocumentHost:
    def __init__(
        self,
        *,
        file_path: str,
        editor_manager: _FakeEditorManager,
        editor_widget: _FakeEditorWidget | None,
        editor_tab_workflow: Any,
    ) -> None:
        self._file_path = file_path
        self._editor_manager = editor_manager
        self._editor_widget = editor_widget
        self._editor_tab_workflow = editor_tab_workflow
        self._editor_exit_behavior = constants.UI_EDITOR_EXIT_BEHAVIOR_DEFAULT
        self._editor_auto_save = False
        self._editor_trim_trailing_whitespace_on_save = True
        self._editor_insert_final_newline_on_save = True
        self._editor_organize_imports_on_save = False
        self._editor_format_on_save = False
        self._editor_tabs_widget = None
        self._logger = SimpleNamespace(info=lambda *_a, **_kw: None, warning=lambda *_a, **_kw: None)
        self._intelligence_runtime_settings = SimpleNamespace()
        self._loaded_project = SimpleNamespace(project_root=str(Path(file_path).parent))
        self._workflow_broker = object()
        self._lint_workflow = SimpleNamespace(render_diagnostics_for_file=lambda *_args, **_kwargs: None)

    def dialog_parent(self) -> SimpleNamespace:
        return SimpleNamespace()

    def editor_manager(self) -> _FakeEditorManager:
        return self._editor_manager

    def editor_exit_behavior(self) -> str:
        return self._editor_exit_behavior

    def refresh_save_action_states(self) -> None:
        return None

    def editor_auto_save(self) -> bool:
        return self._editor_auto_save

    def set_editor_auto_save(self, enabled: bool) -> None:
        self._editor_auto_save = enabled

    def stop_auto_save_timer(self) -> None:
        return None

    def logger(self) -> object:
        return self._logger

    def has_editor_tabs_widget(self) -> bool:
        return self._editor_tabs_widget is not None

    def editor_trim_trailing_whitespace_on_save(self) -> bool:
        return self._editor_trim_trailing_whitespace_on_save

    def editor_insert_final_newline_on_save(self) -> bool:
        return self._editor_insert_final_newline_on_save

    def editor_organize_imports_on_save(self) -> bool:
        return self._editor_organize_imports_on_save

    def editor_format_on_save(self) -> bool:
        return self._editor_format_on_save

    def resolve_python_tooling_project_root(self, file_path: str) -> str:
        return str(Path(file_path).parent)

    def apply_text_to_open_tab(self, file_path: str, transformed_text: str) -> None:
        self._editor_manager.update_tab_content(file_path, transformed_text)
        if self._editor_widget is not None:
            self._editor_widget.replace_document_text(transformed_text)

    def intelligence_runtime_settings(self) -> object:
        return self._intelligence_runtime_settings

    def loaded_project(self) -> object | None:
        return self._loaded_project

    def project_inventory_snapshot(self) -> object:
        return None

    def workflow_broker(self) -> object:
        return self._workflow_broker

    def tab_index_for_path(self, file_path: str) -> int:
        return -1

    def refresh_tab_presentation(self, file_path: str) -> None:
        return None

    def update_editor_status_for_path(self, file_path: str) -> None:
        self._editor_tab_workflow.update_editor_status_for_path(file_path)

    def rescan_project_from_disk(self, *, reload_plugins: bool, reindex: bool) -> None:
        return None

    def render_lint_for_file(self, file_path: str, *, trigger: str) -> None:
        self._lint_workflow.render_diagnostics_for_file(file_path, trigger=trigger)

    def refresh_test_discovery(self) -> None:
        return None


class _PythonStyleHost:
    def __init__(
        self,
        *,
        file_path: str,
        editor_manager: _FakeEditorManager,
        editor_widget: _FakeEditorWidget,
        editor_tab_workflow: Any,
        save_workflow: SaveWorkflow,
    ) -> None:
        self._file_path = file_path
        self._editor_manager = editor_manager
        self._editor_widget = editor_widget
        self._editor_tab_workflow = editor_tab_workflow
        self._save_workflow = save_workflow
        self._workflow_broker = object()
        self._loaded_project = SimpleNamespace(project_root=str(Path(file_path).parent))
        self._known_runtime_modules = None
        self._selected_linter = constants.LINTER_PROVIDER_DEFAULT
        self._lint_rule_overrides: dict[str, dict[str, object]] = {}
        self._quick_fixes_enabled = False
        self._quick_fix_require_preview_for_multifile = False
        self._local_history_workflow = SimpleNamespace()
        self._lint_workflow = SimpleNamespace(render_diagnostics_for_file=lambda *_a, **_kw: None)
        self._project_tree_ui_workflow = SimpleNamespace()

    def dialog_parent(self) -> SimpleNamespace:
        return SimpleNamespace()

    def editor_manager(self) -> _FakeEditorManager:
        return self._editor_manager

    def editor_tab_workflow(self) -> Any:
        return self._editor_tab_workflow

    def workflow_broker(self) -> object:
        return self._workflow_broker

    def resolve_python_tooling_project_root(self, file_path: str) -> str | None:
        return str(Path(file_path).parent)

    def save_workflow(self) -> SaveWorkflow:
        return self._save_workflow

    def lint_workflow(self) -> Any:
        return self._lint_workflow

    def loaded_project(self) -> object | None:
        return self._loaded_project

    def set_loaded_project(self, project: object) -> None:
        self._loaded_project = project

    def known_runtime_modules(self) -> frozenset[str] | None:
        return self._known_runtime_modules

    def selected_linter(self) -> str:
        return self._selected_linter

    def lint_rule_overrides(self) -> dict[str, dict[str, object]]:
        return self._lint_rule_overrides

    def quick_fixes_enabled(self) -> bool:
        return self._quick_fixes_enabled

    def quick_fix_require_preview_for_multifile(self) -> bool:
        return self._quick_fix_require_preview_for_multifile

    def local_history_workflow(self) -> Any:
        return self._local_history_workflow

    def apply_text_to_open_tab(self, file_path: str, replacement_text: str) -> None:
        self._editor_manager.update_tab_content(file_path, replacement_text)
        self._editor_widget.replace_document_text(replacement_text)

    def refresh_open_tabs_from_disk(self, file_paths: list[str]) -> None:
        return None

    def project_tree_ui_workflow(self) -> Any:
        return self._project_tree_ui_workflow


def _build_format_workflows(
    file_path: str,
    text: str,
    *,
    include_editor_widget: bool = True,
) -> tuple[PythonStyleWorkflow, SaveWorkflow, _FormatSaveDocumentHost, _FakeEditorManager, _FakeEditorWidget | None]:
    editor_manager = _FakeEditorManager(file_path, text)
    editor_widget = _FakeEditorWidget(text) if include_editor_widget else None
    editor_tab_workflow = SimpleNamespace(
        active_editor_widget=lambda: editor_widget,
        update_editor_status_for_path=lambda *_args, **_kwargs: None,
        refresh_tab_presentation=lambda *_args, **_kwargs: None,
    )
    save_host = _FormatSaveDocumentHost(
        file_path=file_path,
        editor_manager=editor_manager,
        editor_widget=editor_widget,
        editor_tab_workflow=editor_tab_workflow,
    )
    local_history = SimpleNamespace(
        discard_drafts_for_paths=lambda *_args, **_kwargs: None,
        keep_drafts_for_paths=lambda *_args, **_kwargs: None,
        discard_pending_autosave=lambda *_args, **_kwargs: None,
        record_checkpoint=lambda *_args, **_kwargs: None,
        delete_draft=lambda *_args, **_kwargs: None,
        local_history_context_for_path=lambda *_args, **_kwargs: (None, None),
    )
    save_workflow = SaveWorkflow(
        local_history=local_history,
        intelligence_cache=SimpleNamespace(start_symbol_indexing=lambda *_a, **_kw: None),
        host=save_host,
        settings_service=SimpleNamespace(update_global=lambda updater: updater({})),
    )
    if editor_widget is None:
        python_style_workflow = PythonStyleWorkflow(
            _PythonStyleHost(
                file_path=file_path,
                editor_manager=editor_manager,
                editor_widget=_FakeEditorWidget(""),
                editor_tab_workflow=editor_tab_workflow,
                save_workflow=save_workflow,
            )
        )
        return python_style_workflow, save_workflow, save_host, editor_manager, None

    python_style_host = _PythonStyleHost(
        file_path=file_path,
        editor_manager=editor_manager,
        editor_widget=editor_widget,
        editor_tab_workflow=editor_tab_workflow,
        save_workflow=save_workflow,
    )
    return PythonStyleWorkflow(python_style_host), save_workflow, save_host, editor_manager, editor_widget


def _build_window(file_path: str, text: str) -> tuple[PythonStyleWorkflow, _FakeEditorWidget]:
    python_style_workflow, _save_workflow, _save_host, _editor_manager, editor_widget = _build_format_workflows(
        file_path,
        text,
    )
    assert editor_widget is not None
    return python_style_workflow, editor_widget


def _build_save_window(file_path: str, text: str) -> tuple[SaveWorkflow, _FormatSaveDocumentHost, _FakeEditorManager]:
    _python_style_workflow, save_workflow, save_host, editor_manager, _editor_widget = _build_format_workflows(
        file_path,
        text,
        include_editor_widget=False,
    )
    save_host._background_tasks = SimpleNamespace(run=lambda **_kwargs: None)
    return save_workflow, save_host, editor_manager


def test_handle_format_current_file_action_uses_black_for_python_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    python_style_workflow, editor_widget = _build_window("/tmp/project/main.py", "value={'alpha':1}\n")
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

    monkeypatch.setattr("app.shell.python_style_workflow.format_python_with_workflow", _fake_format)
    monkeypatch.setattr(
        "app.shell.python_style_workflow.format_text_basic",
        lambda *_args, **_kwargs: pytest.fail("Non-Python formatter should not run for .py files"),
    )
    monkeypatch.setattr(
        "app.shell.python_style_workflow.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )
    monkeypatch.setattr(
        "app.shell.python_style_workflow.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    python_style_workflow.handle_format_current_file_action()

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
    python_style_workflow, editor_widget = _build_window("/tmp/project/notes.txt", "alpha   \n")
    infos: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.shell.python_style_workflow.format_python_with_workflow",
        lambda *_a, **_kw: pytest.fail("Python formatter should not run for non-Python files"),
    )
    monkeypatch.setattr(
        "app.shell.python_style_workflow.format_text_basic",
        lambda *_args, **_kwargs: SimpleNamespace(changed=True, formatted_text="alpha\n"),
    )
    monkeypatch.setattr(
        "app.shell.python_style_workflow.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )

    python_style_workflow.handle_format_current_file_action()

    assert editor_widget.replacements == ["alpha\n"]
    assert infos == [("Format Current File", "Formatting applied.")]


def test_handle_format_current_file_action_surfaces_python_syntax_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    python_style_workflow, editor_widget = _build_window("/tmp/project/main.py", "def broken(:\n    pass\n")
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

    monkeypatch.setattr("app.shell.python_style_workflow.format_python_with_workflow", _fake_format)
    monkeypatch.setattr(
        "app.shell.python_style_workflow.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    python_style_workflow.handle_format_current_file_action()

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
    python_style_workflow, editor_widget = _build_window("/tmp/project/main.py", "import b\nimport a\n")
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

    monkeypatch.setattr("app.shell.python_style_workflow.organize_imports_with_workflow", _fake_organize)
    monkeypatch.setattr(
        "app.shell.python_style_workflow.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )

    python_style_workflow.handle_organize_imports_action()

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
    python_style_workflow, editor_widget = _build_window("/tmp/project/notes.txt", "alpha\n")
    infos: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "app.shell.python_style_workflow.organize_imports_with_workflow",
        lambda *_a, **_kw: pytest.fail("isort should not run for non-Python files"),
    )
    monkeypatch.setattr(
        "app.shell.python_style_workflow.QMessageBox.information",
        lambda _parent, title, text: infos.append((title, text)),
    )

    python_style_workflow.handle_organize_imports_action()

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
    save_workflow, save_host, editor_manager = _build_save_window("/tmp/project/main.py", "import b  \nimport a")
    save_host._editor_organize_imports_on_save = True
    save_host._editor_format_on_save = True
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

    assert save_workflow.save_tab("/tmp/project/main.py") is True
    assert organize_calls == ["import b\nimport a\n"]
    assert format_calls == ["import a\nimport b\n"]
    assert editor_manager.saved_contents == ["import a\n\nimport b\n"]


def test_save_tab_still_saves_when_python_style_automation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_workflow, save_host, editor_manager = _build_save_window("/tmp/project/main.py", "import b\nimport a")
    save_host._editor_organize_imports_on_save = True
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

    assert save_workflow.save_tab("/tmp/project/main.py") is True
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
    save_workflow, save_host, editor_manager = _build_save_window("/tmp/project/main.py", "import b\nimport a\n")
    save_host._editor_organize_imports_on_save = True
    save_host._editor_format_on_save = True
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

    assert save_workflow.save_tab("/tmp/project/main.py") is True
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
    save_workflow, _save_host, editor_manager = _build_save_window("/tmp/project/notes.txt", "note   ")

    monkeypatch.setattr(
        "app.shell.save_workflow.should_refresh_index_after_save",
        lambda *_args, **_kwargs: False,
    )

    assert save_workflow.save_tab("/tmp/project/notes.txt") is True
    assert editor_manager.saved_contents == ["note\n"]


def test_flush_auto_save_to_file_does_not_apply_save_transforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Buffer ends in 4 trailing spaces, simulating a freshly auto-indented blank line
    # the user is sitting on. If auto-save runs trim_trailing_whitespace_on_save the
    # spaces vanish and the cursor jumps to column 0 (the bug Clair reported).
    file_path = "/tmp/project/main.py"
    buffer_with_trailing_indent = "def foo():\n    "
    save_workflow, save_host, editor_manager = _build_save_window(file_path, buffer_with_trailing_indent)
    save_host._editor_auto_save = True
    save_host._editor_organize_imports_on_save = True
    save_host._editor_format_on_save = True

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

    save_workflow.flush_auto_save_to_file()

    assert editor_manager.saved_contents == [buffer_with_trailing_indent]
