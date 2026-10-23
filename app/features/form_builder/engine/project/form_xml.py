"""Small ``.ui`` drafts turned into writer-canonical text.

Templates and the from-table builder share this so every new form is already
in a layout and ``write(read(text))`` is byte-identical to ``text``.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui


def canonicalize(draft: str) -> str:
    """Parse ``draft`` and return the writer's bytes."""
    document = read_ui(draft, allocator=IdAllocator()).document
    return write_ui(document).text


def form_document(
    class_name: str,
    root_class: str,
    inner: str,
    *,
    tabstops: str = "",
) -> str:
    """A root widget with geometry and window title, then ``inner`` markup."""
    title = escape(class_name)
    stops = tabstops
    if stops and not stops.endswith("\n"):
        stops += "\n"
    draft = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n'
        " <class>%s</class>\n"
        ' <widget class="%s" name="%s">\n'
        "  <property name=\"geometry\">\n"
        "   <rect>\n"
        "    <x>0</x>\n"
        "    <y>0</y>\n"
        "    <width>640</width>\n"
        "    <height>480</height>\n"
        "   </rect>\n"
        "  </property>\n"
        "  <property name=\"windowTitle\">\n"
        "   <string>%s</string>\n"
        "  </property>\n"
        "%s"
        " </widget>\n"
        "%s"
        "</ui>\n"
    ) % (title, root_class, title, title, inner, stops)
    return canonicalize(draft)


def form_row(
    row: int,
    label_name: str,
    label_text: str,
    buddy: str,
    widget_class: str,
    widget_name: str,
    extra: str = "",
) -> str:
    """One ``QFormLayout`` row: a label with a buddy, then the field."""
    body = extra
    if body and not body.endswith("\n"):
        body += "\n"
    widget = (
        '    <widget class="%s" name="%s">\n%s    </widget>\n'
        % (widget_class, widget_name, body)
    )
    if not body:
        widget = '    <widget class="%s" name="%s"/>\n' % (widget_class, widget_name)
    return (
        '   <item row="%d" column="0">\n'
        '    <widget class="QLabel" name="%s">\n'
        "     <property name=\"text\">\n"
        "      <string>%s</string>\n"
        "     </property>\n"
        "     <property name=\"buddy\">\n"
        "      <cstring>%s</cstring>\n"
        "     </property>\n"
        "    </widget>\n"
        "   </item>\n"
        '   <item row="%d" column="1">\n'
        "%s"
        "   </item>\n"
    ) % (row, label_name, escape(label_text), buddy, row, widget)


def string_property(name: str, text: str, indent: str = "     ") -> str:
    return (
        "%s<property name=\"%s\">\n"
        "%s <string>%s</string>\n"
        "%s</property>\n"
    ) % (indent, name, indent, escape(text), indent)


def tabstop_block(names: tuple) -> str:
    if not names:
        return ""
    lines = [" <tabstops>\n"]
    for name in names:
        lines.append("  <tabstop>%s</tabstop>\n" % name)
    lines.append(" </tabstops>\n")
    return "".join(lines)
