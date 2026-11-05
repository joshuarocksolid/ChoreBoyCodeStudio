"""Behavior section headers. One SectionHeader, and a click hides the section body."""

from __future__ import annotations

from app.features.form_builder.qtside.theme.section_header import SectionHeader
from app.qt.QtWidgets import QWidget


def section_heading(parent: QWidget, object_name: str, title: str) -> SectionHeader:
    """An overline with a chevron. Checked means the section is open."""

    header = SectionHeader(
        parent,
        title,
        collapsible=True,
        checkable=True,
        object_name=object_name,
        accessible_name="%s group" % title.capitalize(),
    )
    header.toggled.connect(lambda checked, host=header: _toggle(host, checked))
    return header


def _toggle(header: SectionHeader, checked: bool) -> None:
    overline = header.parentWidget()
    host = overline.parentWidget() if overline is not None else None
    layout = host.layout() if host is not None else None
    if layout is None or overline is None:
        return
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if widget is None or widget is overline:
            continue
        widget.setVisible(checked)
