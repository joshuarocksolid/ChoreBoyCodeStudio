"""Lightweight titled section wrapper for run dialog forms."""

from __future__ import annotations

from PySide2.QtWidgets import QLabel, QVBoxLayout, QWidget


def build_run_form_section(parent: QWidget, title: str) -> tuple[QWidget, QVBoxLayout]:
    """Create a section with a muted title label and content layout.

    Returns ``(section_widget, content_layout)`` where callers add fields to
    ``content_layout``.
    """

    section = QWidget(parent)
    section.setObjectName("shell.runFormSection")
    section_layout = QVBoxLayout(section)
    section_layout.setContentsMargins(0, 0, 0, 0)
    section_layout.setSpacing(10)

    title_label = QLabel(title, section)
    title_label.setObjectName("shell.runFormSection.title")
    title_label.setProperty("formSectionTitle", True)
    section_layout.addWidget(title_label)

    content_host = QWidget(section)
    content_layout = QVBoxLayout(content_host)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(10)
    section_layout.addWidget(content_host)

    return section, content_layout
