"""Small ``.ui`` drafts turned into writer-canonical text.

Templates and the from-table builder share this so every new form is already
in a layout and ``write(read(text))`` is byte-identical to ``text``.
"""

from __future__ import annotations

from typing import Sequence, Tuple
from xml.sax.saxutils import escape

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.numfmt import format_double
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
    connections: Sequence[Tuple[str, str, str, str]] = (),
) -> str:
    """A root widget with geometry and window title, then ``inner`` markup.

    ``connections`` is ``(sender, signal, receiver, slot)`` in Designer order.
    The receiver for the dialog's own slots is the root object name.
    """
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
        "%s"
        "</ui>\n"
    ) % (title, root_class, title, title, inner, stops, _connection_block(connections))
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


def number_property(name: str, value: int, indent: str = "     ") -> str:
    return (
        '%s<property name="%s">\n'
        "%s <number>%d</number>\n"
        "%s</property>\n"
    ) % (indent, name, indent, value, indent)


def double_property(name: str, value: float, indent: str = "     ") -> str:
    return (
        '%s<property name="%s">\n'
        "%s <double>%s</double>\n"
        "%s</property>\n"
    ) % (indent, name, indent, format_double(value), indent)


def string_property(name: str, text: str, indent: str = "     ") -> str:
    return (
        "%s<property name=\"%s\">\n"
        "%s <string>%s</string>\n"
        "%s</property>\n"
    ) % (indent, name, indent, escape(text), indent)


def _connection_block(connections: Sequence[Tuple[str, str, str, str]]) -> str:
    if not connections:
        return ""
    lines = [" <connections>\n"]
    for sender, signal, receiver, slot in connections:
        lines.append(
            "  <connection>\n"
            "   <sender>%s</sender>\n"
            "   <signal>%s</signal>\n"
            "   <receiver>%s</receiver>\n"
            "   <slot>%s</slot>\n"
            "  </connection>\n"
            % (escape(sender), escape(signal), escape(receiver), escape(slot))
        )
    lines.append(" </connections>\n")
    return "".join(lines)


def tabstop_block(names: tuple) -> str:
    if not names:
        return ""
    lines = [" <tabstops>\n"]
    for name in names:
        lines.append("  <tabstop>%s</tabstop>\n" % name)
    lines.append(" </tabstops>\n")
    return "".join(lines)
