"""Unit tests for draft recovery compare/restore behavior."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QDialog  # noqa: E402

from app.persistence.history_models import LocalHistoryCheckpoint  # noqa: E402
from app.shell.local_history_dialog import LocalHistoryDialog  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp(qapp):  # type: ignore[no-untyped-def]
    return qapp


def _checkpoint(revision_id: int, created_at: str, *, label: str = "", source: str = "save") -> LocalHistoryCheckpoint:
    return LocalHistoryCheckpoint(
        revision_id=revision_id,
        file_key="file_1",
        project_id="proj_demo",
        file_path="/tmp/project/main.py",
        relative_path="main.py",
        blob_sha256=f"sha-{revision_id}",
        created_at=created_at,
        source=source,
        label=label,
    )


def test_local_history_dialog_compares_selected_revision_with_current_and_previous() -> None:
    loader_calls: list[int] = []
    contents = {
        2: "print('second')\n",
        1: "print('first')\n",
    }
    dialog = LocalHistoryDialog(
        file_name="main.py",
        checkpoints=[
            _checkpoint(2, "2026-03-24T10:05:00", label="Second Save"),
            _checkpoint(1, "2026-03-24T10:00:00", label="First Save"),
        ],
        current_text="print('current')\n",
        checkpoint_content_loader=lambda revision_id: loader_calls.append(revision_id) or contents[revision_id],
        restore_to_buffer=lambda _content: None,
    )

    assert "Current Buffer" in dialog._diff_view.toPlainText()
    assert "2026-03-24T10:05:00" in dialog._diff_view.toPlainText()
    assert loader_calls == [2]

    dialog._compare_with_previous()

    diff_text = dialog._diff_view.toPlainText()
    assert "2026-03-24T10:00:00" in diff_text
    assert "2026-03-24T10:05:00" in diff_text
    assert loader_calls == [2, 1]

    dialog._compare_with_current()
    assert loader_calls == [2, 1]


def test_local_history_dialog_restore_to_buffer_uses_selected_revision() -> None:
    restored: list[str] = []
    dialog = LocalHistoryDialog(
        file_name="main.py",
        checkpoints=[_checkpoint(1, "2026-03-24T10:00:00", label="First Save")],
        current_text="print('current')\n",
        checkpoint_content_loader=lambda _revision_id: "print('restored')\n",
        restore_to_buffer=restored.append,
    )

    dialog._handle_restore()

    assert restored == ["print('restored')\n"]
    assert dialog.result() == QDialog.Accepted


