"""Dialogs for resolving dirty-buffer lifecycle decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide2.QtCore import QPoint, QSize, Qt
from PySide2.QtGui import (
    QColor,
    QFontMetrics,
    QIcon,
    QPainter,
    QPixmap,
    QPolygon,
)
from PySide2.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.shell.dialog_chrome import (
    FOOTER_ROLE_DESTRUCTIVE_SECONDARY,
    FOOTER_ROLE_LINK,
    FOOTER_ROLE_PRIMARY,
    FOOTER_ROLE_SECONDARY,
    add_footer_button,
    add_footer_stretch,
    add_meta_chip,
    build_dialog_chrome,
)
from app.shell.document_safety import (
    DirtyBufferSnapshot,
    DocumentCloseIntent,
    DocumentSafetyDecision,
    DocumentScope,
)
from app.shell.icon_provider import file_icon, file_type_icon_map, filename_icon_map
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette


_LIST_OBJECT_NAME = "shell.unsavedChangesDialog.fileList"
_ROW_OBJECT_NAME = "shell.unsavedChangesDialog.row"
_ROW_NAME_OBJECT_NAME = "shell.unsavedChangesDialog.row.name"
_ROW_PATH_OBJECT_NAME = "shell.unsavedChangesDialog.row.path"
_DIALOG_OBJECT_NAME = "shell.unsavedChangesDialog"


def _resolve_tokens(dialog: QDialog) -> ShellThemeTokens:
    parent = dialog.parent()
    accessor = getattr(parent, "current_theme_tokens", None)
    if callable(accessor):
        try:
            resolved = accessor()
        except Exception:  # pragma: no cover - defensive: parent in shutdown
            resolved = None
        if isinstance(resolved, ShellThemeTokens):
            return resolved
    return tokens_from_palette(dialog.palette())


def _warning_icon(color_hex: str, size: int = 22) -> QIcon:
    """Filled warning triangle, sized for the dialog header."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.NoPen)
    inset = max(1, size // 12)
    triangle = QPolygon()
    triangle.append(QPoint(size // 2, inset))
    triangle.append(QPoint(size - inset, size - inset))
    triangle.append(QPoint(inset, size - inset))
    painter.drawPolygon(triangle)
    bar_color = QColor("#FFFFFF")
    painter.setBrush(bar_color)
    bar_width = max(2, size // 10)
    bar_height = max(4, size // 3)
    bar_x = (size - bar_width) // 2
    bar_y = size // 2 - bar_height // 2 + size // 12
    painter.drawRoundedRect(bar_x, bar_y, bar_width, bar_height, 1.0, 1.0)
    dot_size = bar_width
    dot_x = (size - dot_size) // 2
    dot_y = bar_y + bar_height + max(1, size // 16)
    painter.drawEllipse(dot_x, dot_y, dot_size, dot_size)
    painter.end()
    return QIcon(pixmap)


def _resolve_file_icon(
    file_path: str,
    *,
    extension_map: dict[str, QIcon],
    filename_map: dict[str, QIcon],
    fallback: QIcon,
) -> QIcon:
    name = Path(file_path).name.lower()
    icon = filename_map.get(name)
    if icon is not None:
        return icon
    suffix = Path(file_path).suffix.lower()
    return extension_map.get(suffix, fallback)


def _format_parent_directory(file_path: str) -> str:
    """Return a readable parent-directory hint for the row's secondary line."""
    raw = (file_path or "").strip()
    if not raw:
        return ""
    parent = Path(raw).parent
    text = str(parent)
    if text in ("", "."):
        return ""
    home = str(Path.home())
    if home and text == home:
        return "~"
    if home and text.startswith(home + "/"):
        return "~" + text[len(home):]
    return text


def _build_file_row(
    snapshot: DirtyBufferSnapshot,
    *,
    icon: QIcon,
    parent: QWidget,
) -> QWidget:
    row = QWidget(parent)
    row.setObjectName(_ROW_OBJECT_NAME)

    layout = QHBoxLayout(row)
    layout.setContentsMargins(10, 6, 10, 6)
    layout.setSpacing(10)

    icon_label = QLabel(row)
    icon_label.setFixedSize(20, 20)
    icon_label.setPixmap(icon.pixmap(16, 16))
    icon_label.setAlignment(Qt.AlignCenter)
    layout.addWidget(icon_label, 0, Qt.AlignVCenter)

    text_column = QVBoxLayout()
    text_column.setContentsMargins(0, 0, 0, 0)
    text_column.setSpacing(1)

    name_label = QLabel(snapshot.display_name or Path(snapshot.file_path).name, row)
    name_label.setObjectName(_ROW_NAME_OBJECT_NAME)
    name_label.setTextInteractionFlags(Qt.NoTextInteraction)
    text_column.addWidget(name_label)

    parent_dir = _format_parent_directory(snapshot.file_path)
    path_label = QLabel(parent_dir, row)
    path_label.setObjectName(_ROW_PATH_OBJECT_NAME)
    path_label.setTextInteractionFlags(Qt.NoTextInteraction)
    path_label.setVisible(bool(parent_dir))
    text_column.addWidget(path_label)

    layout.addLayout(text_column, 1)

    if snapshot.file_path:
        row.setToolTip(snapshot.file_path)
    return row


def _elide_path_for_row(label: QLabel, full_text: str) -> None:
    """Front-elide the parent-dir text to fit the available row width."""
    if not full_text:
        label.setText("")
        return
    metrics = QFontMetrics(label.font())
    available = max(40, label.width())
    label.setText(metrics.elidedText(full_text, Qt.ElideMiddle, available))


class _UnsavedChangesDialog(QDialog):
    """Themed prompt for resolving dirty buffers before a lifecycle action."""

    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        action_description: str,
        dirty_buffers: tuple[DirtyBufferSnapshot, ...],
        allow_keep_for_next_launch: bool,
    ) -> None:
        super().__init__(parent)
        self._intent: DocumentCloseIntent = DocumentCloseIntent.CANCEL
        self._tokens = _resolve_tokens(self)
        self._dirty_buffers = dirty_buffers

        self.setWindowTitle("Unsaved Changes")
        self.setModal(True)

        warning_color = self._tokens.diag_warning_color or (
            "#F59F00" if self._tokens.is_dark else "#E08E00"
        )

        title = self._build_title(action_description)
        subtitle = self._build_subtitle(allow_keep_for_next_launch)

        chrome = build_dialog_chrome(
            self,
            title=title,
            subtitle=subtitle,
            object_name=_DIALOG_OBJECT_NAME,
            icon=_warning_icon(warning_color, size=22),
        )
        self._chrome = chrome

        file_count = len(dirty_buffers)
        chip_text = f"{file_count} unsaved file" if file_count == 1 else f"{file_count} unsaved files"
        add_meta_chip(chrome.meta_row, chip_text)

        body_layout = chrome.body.layout()
        assert isinstance(body_layout, QVBoxLayout)

        self._file_list = self._build_file_list(chrome.body, dirty_buffers)
        body_layout.addWidget(self._file_list, 1)

        cancel_button = add_footer_button(chrome, "&Cancel", role=FOOTER_ROLE_SECONDARY)
        add_footer_stretch(chrome)
        keep_button = None
        if allow_keep_for_next_launch:
            keep_button = add_footer_button(
                chrome, "&Keep for Next Launch", role=FOOTER_ROLE_LINK
            )
        discard_button = add_footer_button(
            chrome, "&Discard Changes", role=FOOTER_ROLE_DESTRUCTIVE_SECONDARY
        )
        save_button = add_footer_button(
            chrome, "&Save All", role=FOOTER_ROLE_PRIMARY, default=True
        )

        cancel_button.clicked.connect(self._handle_cancel)
        discard_button.clicked.connect(self._handle_discard)
        save_button.clicked.connect(self._handle_save)
        if keep_button is not None:
            keep_button.clicked.connect(self._handle_keep)

        self._size_to_content(file_count)

    @property
    def chosen_intent(self) -> DocumentCloseIntent:
        return self._intent

    def _build_title(self, action_description: str) -> str:
        action = (action_description or "").strip()
        if not action:
            return "Save changes before continuing?"
        return f"Save changes before {action}?"

    def _build_subtitle(self, allow_keep: bool) -> str:
        if allow_keep:
            return (
                "Your unsaved edits will be lost unless you save them, or "
                "keep them for the next launch."
            )
        return "Your unsaved edits will be lost unless you save them first."

    def _build_file_list(
        self,
        parent: QWidget,
        snapshots: tuple[DirtyBufferSnapshot, ...],
    ) -> QListWidget:
        list_widget = QListWidget(parent)
        list_widget.setObjectName(_LIST_OBJECT_NAME)
        list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        list_widget.setFocusPolicy(Qt.NoFocus)
        list_widget.setUniformItemSizes(True)
        list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        list_widget.setFrameShape(QListWidget.NoFrame)

        extension_map = file_type_icon_map()
        filename_map = filename_icon_map()
        fallback_color = self._tokens.icon_muted or self._tokens.text_muted or "#8B8F95"
        fallback_icon = file_icon(fallback_color)

        for snapshot in snapshots:
            icon = _resolve_file_icon(
                snapshot.file_path,
                extension_map=extension_map,
                filename_map=filename_map,
                fallback=fallback_icon,
            )
            row_widget = _build_file_row(snapshot, icon=icon, parent=list_widget)
            item = QListWidgetItem(list_widget)
            item.setSizeHint(QSize(0, max(46, row_widget.sizeHint().height() + 4)))
            item.setFlags(Qt.ItemIsEnabled)
            list_widget.addItem(item)
            list_widget.setItemWidget(item, row_widget)

        return list_widget

    def _size_to_content(self, file_count: int) -> None:
        visible_rows = min(max(file_count, 1), 6)
        row_height = 50
        list_height = visible_rows * row_height + 8
        self._file_list.setMinimumHeight(min(list_height, 320))
        self._file_list.setMaximumHeight(320)
        self.setMinimumWidth(520)
        self.adjustSize()

    def _handle_cancel(self) -> None:
        self._intent = DocumentCloseIntent.CANCEL
        self.reject()

    def _handle_discard(self) -> None:
        self._intent = DocumentCloseIntent.DISCARD
        self.accept()

    def _handle_save(self) -> None:
        self._intent = DocumentCloseIntent.SAVE
        self.accept()

    def _handle_keep(self) -> None:
        self._intent = DocumentCloseIntent.KEEP_FOR_NEXT_LAUNCH
        self.accept()

    def reject(self) -> None:  # type: ignore[override]
        # Esc / window-close map to Cancel without overriding an explicit intent.
        if self._intent not in (
            DocumentCloseIntent.SAVE,
            DocumentCloseIntent.DISCARD,
            DocumentCloseIntent.KEEP_FOR_NEXT_LAUNCH,
        ):
            self._intent = DocumentCloseIntent.CANCEL
        super().reject()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh_path_elision()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._refresh_path_elision()

    def _refresh_path_elision(self) -> None:
        for index in range(self._file_list.count()):
            item = self._file_list.item(index)
            widget = self._file_list.itemWidget(item)
            if widget is None:
                continue
            label = widget.findChild(QLabel, _ROW_PATH_OBJECT_NAME)
            if label is None:
                continue
            full = label.toolTip() or label.text()
            if not label.toolTip() and self._dirty_buffers:
                full = _format_parent_directory(self._dirty_buffers[index].file_path)
                label.setToolTip(full)
            _elide_path_for_row(label, full)


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

    dialog = _UnsavedChangesDialog(
        parent,
        action_description=action_description,
        dirty_buffers=dirty_buffers,
        allow_keep_for_next_launch=allow_keep_for_next_launch,
    )
    dialog.exec_()

    return DocumentSafetyDecision(
        intent=dialog.chosen_intent,
        scope=scope,
        dirty_buffers=dirty_buffers,
    )
