"""Reusable themed chrome (header / body / footer) for shell dialogs.

The helpers here factor out the layout pattern established by
``RuntimeCenterDialog`` so that future dialogs do not need to re-create
the same outer layout, header band, footer band, and primary/secondary
button styling rules.

The chrome relies on stable object names so the stylesheet section in
``style_sheet_sections_dialogs.py`` can target it without each caller
re-styling its widgets.  Use :func:`add_footer_button` to obtain a
``QPushButton`` that already carries the right object name and role
attribute for the QSS section to pick up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


FOOTER_ROLE_PRIMARY = "primary"
FOOTER_ROLE_SECONDARY = "secondary"
FOOTER_ROLE_DESTRUCTIVE_SECONDARY = "destructive_secondary"
FOOTER_ROLE_LINK = "link"

_FOOTER_ROLE_OBJECT_NAMES = {
    FOOTER_ROLE_PRIMARY: "shell.dialogChrome.button.primary",
    FOOTER_ROLE_SECONDARY: "shell.dialogChrome.button.secondary",
    FOOTER_ROLE_DESTRUCTIVE_SECONDARY: "shell.dialogChrome.button.destructiveSecondary",
    FOOTER_ROLE_LINK: "shell.dialogChrome.button.link",
}


@dataclass
class DialogChrome:
    """Container holding the chrome widgets returned by :func:`build_dialog_chrome`.

    ``body`` is the widget callers should populate with content.  Its layout
    margins are already set to a comfortable inset; pass ``body_margins=False``
    when the caller wants to manage its own margins.
    """

    header: QWidget
    body: QWidget
    footer: QWidget
    title_label: QLabel
    subtitle_label: QLabel
    icon_label: QLabel
    meta_row: QWidget
    footer_layout: QHBoxLayout


def build_dialog_chrome(
    dialog: QDialog,
    *,
    title: str,
    subtitle: str = "",
    object_name: str,
    icon: Optional[QIcon] = None,
    body_margins: bool = True,
) -> DialogChrome:
    """Install the standard header/body/footer chrome on ``dialog``.

    The dialog's existing layout (if any) is replaced.  The returned
    :class:`DialogChrome` exposes the widgets the caller fills in: the
    ``body`` widget for the main content, ``meta_row`` for header chips,
    and ``footer_layout`` for footer buttons (use
    :func:`add_footer_button`).
    """

    dialog.setObjectName(object_name)

    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    header = QWidget(dialog)
    header.setObjectName("shell.dialogChrome.header")
    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(20, 16, 20, 14)
    header_layout.setSpacing(4)

    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(10)

    icon_label = QLabel(header)
    icon_label.setObjectName("shell.dialogChrome.icon")
    icon_label.setFixedSize(22, 22)
    if icon is not None:
        icon_label.setPixmap(icon.pixmap(22, 22))
    else:
        icon_label.setVisible(False)
    title_row.addWidget(icon_label, 0, Qt.AlignVCenter)

    title_label = QLabel(title, header)
    title_label.setObjectName("shell.dialogChrome.title")
    title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    title_row.addWidget(title_label, 1, Qt.AlignVCenter)

    header_layout.addLayout(title_row)

    subtitle_label = QLabel(subtitle, header)
    subtitle_label.setObjectName("shell.dialogChrome.subtitle")
    subtitle_label.setWordWrap(True)
    subtitle_label.setVisible(bool(subtitle))
    header_layout.addWidget(subtitle_label)

    meta_row = QWidget(header)
    meta_row.setObjectName("shell.dialogChrome.metaRow")
    meta_row_layout = QHBoxLayout(meta_row)
    meta_row_layout.setContentsMargins(0, 6, 0, 0)
    meta_row_layout.setSpacing(6)
    meta_row_layout.addStretch(1)
    meta_row.setVisible(False)
    header_layout.addWidget(meta_row)

    outer.addWidget(header)

    body = QWidget(dialog)
    body.setObjectName("shell.dialogChrome.body")
    body_layout = QVBoxLayout(body)
    if body_margins:
        body_layout.setContentsMargins(20, 14, 20, 12)
    else:
        body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(10)
    outer.addWidget(body, 1)

    footer = QWidget(dialog)
    footer.setObjectName("shell.dialogChrome.footer")
    footer_layout = QHBoxLayout(footer)
    footer_layout.setContentsMargins(20, 12, 20, 14)
    footer_layout.setSpacing(8)
    outer.addWidget(footer)

    return DialogChrome(
        header=header,
        body=body,
        footer=footer,
        title_label=title_label,
        subtitle_label=subtitle_label,
        icon_label=icon_label,
        meta_row=meta_row,
        footer_layout=footer_layout,
    )


def add_meta_chip(meta_row: QWidget, text: str) -> QLabel:
    """Append a labelled chip to the header meta row and reveal the row."""

    layout = meta_row.layout()
    assert isinstance(layout, QHBoxLayout)
    chip = QLabel(text, meta_row)
    chip.setObjectName("shell.dialogChrome.meta.chip")
    chip.setProperty("metaChip", True)
    layout.insertWidget(layout.count() - 1, chip)
    meta_row.setVisible(True)
    return chip


def clear_meta_chips(meta_row: QWidget) -> None:
    """Remove existing chips from the meta row, leaving the trailing stretch."""

    layout = meta_row.layout()
    assert isinstance(layout, QHBoxLayout)
    while layout.count() > 1:
        item = layout.takeAt(0)
        widget = item.widget() if item is not None else None
        if widget is not None:
            widget.deleteLater()
    meta_row.setVisible(False)


def add_footer_button(
    chrome: DialogChrome,
    label: str,
    *,
    role: str,
    default: bool = False,
) -> QPushButton:
    """Append a footer button with the right object name for the QSS section."""

    object_name = _FOOTER_ROLE_OBJECT_NAMES.get(role)
    if object_name is None:
        raise ValueError(f"Unknown footer button role: {role!r}")
    button = QPushButton(label, chrome.footer)
    button.setObjectName(object_name)
    button.setProperty("buttonRole", role)
    button.setAutoDefault(False)
    if default:
        button.setDefault(True)
    chrome.footer_layout.addWidget(button)
    return button


def add_footer_stretch(chrome: DialogChrome) -> None:
    """Insert a flexible spacer at the current end of the footer row."""

    chrome.footer_layout.addStretch(1)
