"""Shared file-dialog helpers with stable option defaults."""

from __future__ import annotations

from pathlib import Path

from PySide2.QtWidgets import QFileDialog, QWidget


def _normalized_start_directory(start_directory: str) -> str:
    if not start_directory.strip():
        return str(Path.home())
    return str(Path(start_directory).expanduser())


def _default_dialog_options(*, directories_only: bool = False) -> QFileDialog.Options:
    options = QFileDialog.Options()
    options |= QFileDialog.DontUseNativeDialog
    if hasattr(QFileDialog, "DontUseCustomDirectoryIcons"):
        options |= QFileDialog.DontUseCustomDirectoryIcons
    if directories_only:
        options |= QFileDialog.ShowDirsOnly
    return options


def choose_existing_directory(parent: QWidget | None, title: str, start_directory: str) -> str:
    """Open a directory picker and return selected path or empty string."""
    return QFileDialog.getExistingDirectory(
        parent,
        title,
        _normalized_start_directory(start_directory),
        options=_default_dialog_options(directories_only=True),
    )


def choose_open_file(
    parent: QWidget | None,
    title: str,
    start_directory: str,
    file_filter: str,
) -> str:
    """Open a file picker and return one selected file path or empty string."""
    selected_path, _selected_filter = QFileDialog.getOpenFileName(
        parent,
        title,
        _normalized_start_directory(start_directory),
        file_filter,
        options=_default_dialog_options(),
    )
    return selected_path


def choose_open_files(
    parent: QWidget | None,
    title: str,
    start_directory: str,
    file_filter: str,
) -> list[str]:
    """Open a file picker and return selected file paths."""
    selected_paths, _selected_filter = QFileDialog.getOpenFileNames(
        parent,
        title,
        _normalized_start_directory(start_directory),
        file_filter,
        options=_default_dialog_options(),
    )
    return list(selected_paths)

