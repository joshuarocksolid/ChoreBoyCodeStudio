"""Dialogs for resolving dirty-buffer lifecycle decisions."""

from __future__ import annotations

from PySide2.QtWidgets import QMessageBox, QWidget

from app.shell.document_safety import (
    DirtyBufferSnapshot,
    DocumentCloseIntent,
    DocumentSafetyDecision,
    DocumentScope,
)


def prompt_for_unsaved_changes(
    parent: QWidget,
    *,
    action_description: str,
    scope: DocumentScope,
    dirty_buffers: tuple[DirtyBufferSnapshot, ...],
    allow_keep_for_next_launch: bool = False,
) -> DocumentSafetyDecision:
    """Ask how to handle dirty buffers before a close/switch lifecycle action."""
    if not dirty_buffers:
        return DocumentSafetyDecision(intent=DocumentCloseIntent.PROCEED, scope=scope)

    file_count = len(dirty_buffers)
    file_word = "file" if file_count == 1 else "files"
    names = ", ".join(buffer.display_name for buffer in dirty_buffers[:3])
    if file_count > 3:
        names = f"{names}, and {file_count - 3} more"

    message = (
        f"You have {file_count} unsaved {file_word} before {action_description}.\n\n"
        f"{names}\n\n"
        "Choose whether to save, keep the unsaved buffers for next launch, discard them, or cancel."
    )
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("Unsaved Changes")
    box.setText(message)
    save_button = box.addButton("Save All", QMessageBox.AcceptRole)
    discard_button = box.addButton("Discard Changes", QMessageBox.DestructiveRole)
    cancel_button = box.addButton("Cancel", QMessageBox.RejectRole)
    keep_button = None
    if allow_keep_for_next_launch:
        keep_button = box.addButton("Keep Unsaved Changes For Next Launch", QMessageBox.ActionRole)
    box.setDefaultButton(save_button)
    box.exec_()

    clicked = box.clickedButton()
    if clicked == cancel_button:
        intent = DocumentCloseIntent.CANCEL
    elif clicked == discard_button:
        intent = DocumentCloseIntent.DISCARD
    elif keep_button is not None and clicked == keep_button:
        intent = DocumentCloseIntent.KEEP_FOR_NEXT_LAUNCH
    else:
        intent = DocumentCloseIntent.SAVE

    return DocumentSafetyDecision(
        intent=intent,
        scope=scope,
        dirty_buffers=dirty_buffers,
    )
