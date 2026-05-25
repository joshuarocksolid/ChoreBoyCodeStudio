"""Unit tests for unified disk-to-editor synchronization."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.editors.editor_tab import EditorTabState  # noqa: E402
from app.shell.editor_sync_workflow import EditorDiskSyncSource, EditorSyncWorkflow, EditorWidgetPort  # noqa: E402

pytestmark = pytest.mark.unit


class _FakeEditorWidget:
    def __init__(self, text: str) -> None:
        self.text = text
        self.blocked = False
        self.revision_bumps: list[str] = []

    def blockSignals(self, blocked: bool) -> bool:  # noqa: N802
        previous = self.blocked
        self.blocked = blocked
        return previous

    def setPlainText(self, text: str) -> None:
        self.text = text

    def toPlainText(self) -> str:
        return self.text


@dataclass
class _RecordingSyncHost:
    widgets: dict[str, _FakeEditorWidget] = field(default_factory=dict)
    revision_bumps: list[str] = field(default_factory=list)
    indent_calls: list[tuple[str, str]] = field(default_factory=list)
    refreshed_paths: list[str] = field(default_factory=list)
    tab_indices: dict[str, int] = field(default_factory=dict)
    has_tabs_widget: bool = True

    def editor_widget_for_path(self, file_path: str) -> _FakeEditorWidget | None:
        return self.widgets.get(file_path)

    def advance_buffer_revision(self, file_path: str) -> int:
        self.revision_bumps.append(file_path)
        return len(self.revision_bumps)

    def apply_detected_indentation(
        self,
        file_path: str,
        editor_widget: EditorWidgetPort,
        source_text: str,
    ) -> None:
        del editor_widget
        self.indent_calls.append((file_path, source_text))

    def tab_index_for_path(self, file_path: str) -> int:
        return self.tab_indices.get(file_path, -1)

    def refresh_tab_presentation(self, file_path: str) -> None:
        self.refreshed_paths.append(file_path)

    def has_editor_tabs_widget(self) -> bool:
        return self.has_tabs_widget


def _open_tab(
    manager: EditorManager,
    file_path: Path,
    *,
    content: str,
    mtime: float,
) -> EditorTabState:
    file_path.write_text(content, encoding="utf-8")
    result = manager.open_file(str(file_path))
    tab = result.tab
    tab.mark_saved(last_known_mtime=mtime)
    return tab


def test_apply_disk_content_updates_widget_tab_state_and_revision(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    tab = _open_tab(manager, file_path, content="print('old')\n", mtime=1.0)
    widget = _FakeEditorWidget(tab.current_content)
    host = _RecordingSyncHost(
        widgets={tab.file_path: widget},
        tab_indices={tab.file_path: 0},
    )
    workflow = EditorSyncWorkflow(editor_manager=manager, host=host)

    applied = workflow.apply_disk_content(
        tab.file_path,
        "print('new')\n",
        source=EditorDiskSyncSource.TOOL_REFRESH,
        last_known_mtime=2.0,
    )

    assert applied is True
    assert widget.text == "print('new')\n"
    assert tab.current_content == "print('new')\n"
    assert tab.original_content == "print('new')\n"
    assert tab.is_dirty is False
    assert tab.last_known_mtime == 2.0
    assert host.revision_bumps == [tab.file_path]
    assert host.indent_calls == [(tab.file_path, "print('new')\n")]
    assert host.refreshed_paths == [tab.file_path]


def test_apply_disk_content_returns_false_when_tab_or_widget_missing(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    tab = _open_tab(manager, file_path, content="print('old')\n", mtime=1.0)
    host = _RecordingSyncHost()
    workflow = EditorSyncWorkflow(editor_manager=manager, host=host)

    assert (
        workflow.apply_disk_content(
            tab.file_path,
            "print('new')\n",
            source=EditorDiskSyncSource.QUICK_FIX,
        )
        is False
    )
    assert tab.current_content == "print('old')\n"


def test_apply_disk_content_skips_tab_refresh_when_widget_unavailable(tmp_path: Path) -> None:
    file_path = tmp_path / "main.py"
    manager = EditorManager()
    tab = _open_tab(manager, file_path, content="print('old')\n", mtime=1.0)
    widget = _FakeEditorWidget(tab.current_content)
    host = _RecordingSyncHost(
        widgets={tab.file_path: widget},
        tab_indices={tab.file_path: 0},
        has_tabs_widget=False,
    )
    workflow = EditorSyncWorkflow(editor_manager=manager, host=host)

    assert (
        workflow.apply_disk_content(
            tab.file_path,
            "print('new')\n",
            source=EditorDiskSyncSource.EXTERNAL_RELOAD,
        )
        is True
    )
    assert host.refreshed_paths == []
