"""Deterministic ``.ui`` writer and the lazy serialization cache
(CONTRACTS.md sections 8.2-8.4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.ids import DOCUMENT_ID, IdAllocator, NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import Node, OpaqueNode
from app.features.form_builder.engine.ui4.numfmt import (
    format_bool,
    format_double,
    format_float,
    format_int,
)
from app.features.form_builder.engine.ui4.opaque import OpaqueComment, OpaqueElement, OpaquePI
from app.features.form_builder.engine.ui4.schema import (
    SCHEMA,
    ConnectionHint,
    HeaderDecl,
    LayoutDefault,
    LayoutFunction,
    SlotsDecl,
)
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    BrushValue,
    CStringValue,
    CharValue,
    ColorValue,
    CursorShapeValue,
    CursorValue,
    DateTimeValue,
    DateValue,
    DoubleValue,
    EnumValue,
    FloatValue,
    FontValue,
    GradientValue,
    ICON_STATES,
    IconSetValue,
    LocaleValue,
    LongLongValue,
    NumberValue,
    OpaqueValue,
    PaletteValue,
    PointFValue,
    PointValue,
    RectFValue,
    RectValue,
    ResourcePixmap,
    SetValue,
    SizeFValue,
    SizePolicyValue,
    SizeValue,
    StringListValue,
    StringValue,
    TimeValue,
    UIntValue,
    ULongLongValue,
    UrlValue,
    Value,
)

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'
INDENT = " "

_SLOTS = {
    kind: {item.name: item for item in spec.slots}
    for kind, spec in SCHEMA.items()
}
_CHILD_FIELDS = {
    kind: {
        field.xml[len("child:"):]: field.name
        for field in spec.fields
        if field.xml.startswith("child:")
    }
    for kind, spec in SCHEMA.items()
}
_FONT_ORDER = (
    "family", "pointsize", "weight", "italic", "bold", "underline", "strikeout",
    "antialiasing", "stylestrategy", "kerning", "hintingpreference", "fontweight",
)


@dataclass(frozen=True)
class WriteResult:
    """``text``: the file content (``\\n`` newlines, trailing newline after
    ``</ui>``). ``line_map``: node id -> 1-based line of its start tag in ``text``
    (feeds Problems line numbers)."""

    text: str
    line_map: Dict[NodeId, int]


def write_ui(doc: UiDocument) -> WriteResult:
    """Serialize per CONTRACTS.md 8.2. Escaping: ``& < > "`` in text and
    attributes; tab/LF/CR as character references in attributes; CR in text as
    ``&#13;``; non-ASCII as raw UTF-8. No trailing whitespace outside text
    content. Empty-element forms and real precision follow the M0.4b-pinned
    tables (provisional until then). A pure function of the document's content (ids excluded):
    no clock, locale, environment, hash seed or set iteration. O(form).
    Budget: 10 ms CPU for a 300-widget form."""
    writer = _Writer()
    writer.node(doc.ui, 0)
    return WriteResult(writer.finish(), writer.line_map)


def write_fragment(fragment: Fragment) -> str:
    """Clipboard text for ``fragment`` (same byte rules as ``write_ui``)."""
    allocator = IdAllocator()
    spec = _fragment_spec(fragment, allocator)
    return write_ui(UiDocument.from_spec(spec)).text


class SerializationCache:
    """Per-session memo: ``text(doc)`` serializes only when ``doc.revision``
    changed since the last call. The ONLY path by which shell-visible XML is
    produced (save, local-history snapshot, draft timer, View XML, preview load).

    ``serialize_count`` is observable so tests can assert that N edits cause
    zero serializations (section 13).
    """

    def __init__(self) -> None:
        self._revision: Optional[int] = None
        self._result: Optional[WriteResult] = None
        self._count = 0

    def text(self, doc: UiDocument) -> str:
        return self.result(doc).text

    def result(self, doc: UiDocument) -> WriteResult:
        if self._result is not None and self._revision == doc.revision:
            return self._result
        self._count += 1
        self._result = write_ui(doc)
        self._revision = doc.revision
        return self._result

    def last_line_map(self) -> Optional[Dict[NodeId, int]]:
        """Line map from the most recent serialization (may be stale), or None."""
        if self._result is None:
            return None
        return self._result.line_map

    @property
    def serialize_count(self) -> int:
        return self._count


class _Writer:
    def __init__(self) -> None:
        self.lines: List[str] = [XML_DECLARATION]
        self.line_map: Dict[NodeId, int] = {}

    def finish(self) -> str:
        return "\n".join(self.lines) + "\n"

    def node(self, node: Node, indent: int) -> None:
        if isinstance(node, OpaqueNode):
            self.line_map[node.id] = self._next_line()
            self.opaque(node.element, indent)
            return
        if node.kind == "include":
            text = node.field("text")
            if isinstance(text, str) and text and not node.opaque():
                self.line_map[node.id] = self._next_line()
                self._text_element("include", text, indent, _attrs(node))
                return
        spec = SCHEMA[node.kind]
        tag = _tag(node)
        attrs = _attrs(node)
        self.line_map[node.id] = self._next_line()
        opaque_nodes = node.opaque()
        buckets = _buckets(opaque_nodes)
        if not _has_body(node) and not buckets:
            self._empty(indent, tag, attrs)
            return
        self._open(indent, tag, attrs)
        self._flush(buckets, ("", 0), indent + 1)
        for group in spec.write_order:
            self._group(node, group, indent + 1, buckets)
        for key in list(buckets):
            self._flush(buckets, key, indent + 1)
        self._close(indent, tag)

    def opaque(self, element: OpaqueElement, indent: int) -> None:
        if element.tag == "":
            for child in element.children:
                if isinstance(child, str):
                    if child.strip():
                        self._raw_text_line(indent, child)
                elif isinstance(child, OpaqueComment):
                    self.lines.append((" " * indent) + "<!--%s-->" % child.text)
                elif isinstance(child, OpaquePI):
                    self.lines.append((" " * indent) + "<?%s %s?>" % (child.target, child.data))
                elif isinstance(child, OpaqueElement):
                    self.opaque(child, indent)
            return
        attrs = "".join(' %s="%s"' % (key, _esc_attr(value)) for key, value in element.attrs)
        if not element.children:
            self._empty(indent, element.tag, attrs)
            return
        if all(isinstance(child, str) for child in element.children):
            text = "".join(child for child in element.children if isinstance(child, str))
            self.lines.append("%s<%s%s>%s</%s>" % (" " * indent, element.tag, attrs, _esc_text(text), element.tag))
            return
        if _mixed(element):
            self._mixed(element, indent, attrs)
            return
        self._open(indent, element.tag, attrs)
        for child in element.children:
            if isinstance(child, str):
                continue
            if isinstance(child, OpaqueComment):
                self.lines.append((" " * (indent + 1)) + "<!--%s-->" % child.text)
            elif isinstance(child, OpaquePI):
                self.lines.append((" " * (indent + 1)) + "<?%s %s?>" % (child.target, child.data))
            elif isinstance(child, OpaqueElement):
                self.opaque(child, indent + 1)
        self._close(indent, element.tag)

    def value(self, item: Value, indent: int) -> None:
        if isinstance(item, OpaqueValue):
            self.opaque(item.element, indent)
            return
        if isinstance(item, StringValue):
            self._text_element("string", item.text, indent, _string_attrs(item))
            return
        if isinstance(item, CStringValue):
            self._text_element("cstring", item.text, indent)
            return
        if isinstance(item, EnumValue):
            self._text_element("enum", item.text, indent)
            return
        if isinstance(item, SetValue):
            self._text_element("set", item.text, indent)
            return
        if isinstance(item, BoolValue):
            self._text_element("bool", format_bool(item.value), indent)
            return
        if isinstance(item, (NumberValue, UIntValue, LongLongValue, ULongLongValue, CursorValue)):
            self._text_element(item.ELEMENT, format_int(item.value), indent)
            return
        if isinstance(item, DoubleValue):
            self._text_element("double", format_double(item.value), indent)
            return
        if isinstance(item, FloatValue):
            self._text_element("float", format_float(item.value), indent)
            return
        if isinstance(item, CursorShapeValue):
            self._text_element("cursorshape", item.name, indent)
            return
        if isinstance(item, StringListValue):
            self._open(indent, "stringlist", _string_attrs(item))
            for text in item.items:
                self._text_element("string", text, indent + 1)
            self._close(indent, "stringlist")
            return
        if isinstance(item, RectValue):
            self._int_box("rect", (("x", item.x), ("y", item.y), ("width", item.width), ("height", item.height)), indent)
            return
        if isinstance(item, RectFValue):
            self._real_box("rectf", (("x", item.x), ("y", item.y), ("width", item.width), ("height", item.height)), indent)
            return
        if isinstance(item, SizeValue):
            self._int_box("size", (("width", item.width), ("height", item.height)), indent)
            return
        if isinstance(item, SizeFValue):
            self._real_box("sizef", (("width", item.width), ("height", item.height)), indent)
            return
        if isinstance(item, PointValue):
            self._int_box("point", (("x", item.x), ("y", item.y)), indent)
            return
        if isinstance(item, PointFValue):
            self._real_box("pointf", (("x", item.x), ("y", item.y)), indent)
            return
        if isinstance(item, SizePolicyValue):
            attrs = ' hsizetype="%s" vsizetype="%s"' % (_esc_attr(item.hsizetype), _esc_attr(item.vsizetype))
            self._open(indent, "sizepolicy", attrs)
            self._text_element("horstretch", format_int(item.horstretch), indent + 1)
            self._text_element("verstretch", format_int(item.verstretch), indent + 1)
            self._close(indent, "sizepolicy")
            return
        if isinstance(item, FontValue):
            self._open(indent, "font", "")
            for name in _FONT_ORDER:
                child = getattr(item, name)
                if child is None:
                    continue
                if isinstance(child, bool):
                    self._text_element(name, format_bool(child), indent + 1)
                elif isinstance(child, int):
                    self._text_element(name, format_int(child), indent + 1)
                else:
                    self._text_element(name, str(child), indent + 1)
            self._close(indent, "font")
            return
        if isinstance(item, CharValue):
            self._open(indent, "char", "")
            self._text_element("unicode", format_int(item.unicode), indent + 1)
            self._close(indent, "char")
            return
        if isinstance(item, ColorValue):
            alpha = "" if item.alpha is None else ' alpha="%s"' % format_int(item.alpha)
            self._open(indent, "color", alpha)
            self._text_element("red", format_int(item.red), indent + 1)
            self._text_element("green", format_int(item.green), indent + 1)
            self._text_element("blue", format_int(item.blue), indent + 1)
            self._close(indent, "color")
            return
        if isinstance(item, DateValue):
            self._int_box("date", (("year", item.year), ("month", item.month), ("day", item.day)), indent)
            return
        if isinstance(item, TimeValue):
            self._int_box("time", (("hour", item.hour), ("minute", item.minute), ("second", item.second)), indent)
            return
        if isinstance(item, DateTimeValue):
            self._int_box(
                "datetime",
                (
                    ("hour", item.hour), ("minute", item.minute), ("second", item.second),
                    ("year", item.year), ("month", item.month), ("day", item.day),
                ),
                indent,
            )
            return
        if isinstance(item, LocaleValue):
            self._empty(
                indent,
                "locale",
                ' language="%s" country="%s"' % (_esc_attr(item.language), _esc_attr(item.country)),
            )
            return
        if isinstance(item, UrlValue):
            self._open(indent, "url", "")
            self.value(item.string, indent + 1)
            self._close(indent, "url")
            return
        if isinstance(item, ResourcePixmap):
            self._pixmap(item, indent)
            return
        if isinstance(item, IconSetValue):
            self._iconset(item, indent)
            return
        if isinstance(item, BrushValue):
            self._brush(item, indent)
            return
        if isinstance(item, PaletteValue):
            self._palette(item, indent)
            return
        raise TypeError("cannot write value %s" % (type(item).__name__,))

    def _pixmap(self, item: ResourcePixmap, indent: int) -> None:
        self._pixmap_tag("pixmap", item, indent, duplicate_path=False)

    def _pixmap_tag(self, tag: str, item: ResourcePixmap, indent: int, duplicate_path: bool) -> None:
        attrs = _optional_str_attrs((("resource", item.resource), ("alias", item.alias)))
        if item.path == "" and not duplicate_path:
            self._empty(indent, tag, attrs)
            return
        if not duplicate_path:
            self._text_element(tag, item.path, indent, attrs)
            return
        prefix = " " * indent
        path = _esc_text(item.path)
        self.lines.append("%s<%s%s>%s</%s>%s" % (prefix, tag, attrs, path, tag, path))

    def _iconset(self, item: IconSetValue, indent: int) -> None:
        attrs = _optional_str_attrs((("theme", item.theme), ("resource", item.resource)))
        present: List[Tuple[str, ResourcePixmap]] = []
        for name in ICON_STATES:
            pixmap = getattr(item, name)
            if isinstance(pixmap, ResourcePixmap):
                present.append((name, pixmap))
        if not present:
            if item.text is None:
                self._empty(indent, "iconset", attrs)
                return
            self._text_element("iconset", item.text, indent, attrs)
            return
        # Each state already carries its path. The repeated path is the Designer trailer.
        self._open(indent, "iconset", attrs)
        for name, pixmap in present:
            self._pixmap_tag(name, pixmap, indent + 1, duplicate_path=True)
        self._close(indent, "iconset")

    def _brush(self, item: BrushValue, indent: int) -> None:
        attrs = _optional_str_attrs((("brushstyle", item.brushstyle),))
        if item.color is None and item.texture is None and item.gradient is None:
            self._empty(indent, "brush", attrs)
            return
        self._open(indent, "brush", attrs)
        if item.color is not None:
            self.value(item.color, indent + 1)
        if item.texture is not None:
            self._open(indent + 1, "texture", _optional_str_attrs((("name", item.texture_name),)))
            self._pixmap(item.texture, indent + 2)
            self._close(indent + 1, "texture")
        if item.gradient is not None:
            self._gradient(item.gradient, indent + 1)
        self._close(indent, "brush")

    def _gradient(self, item: GradientValue, indent: int) -> None:
        pairs: List[Tuple[str, str]] = []
        for name in (
            "type",
            "spread",
            "coordinatemode",
            "startx",
            "starty",
            "endx",
            "endy",
            "centralx",
            "centraly",
            "focalx",
            "focaly",
            "radius",
            "angle",
        ):
            value = getattr(item, name)
            if isinstance(value, float):
                pairs.append((name, format_double(value)))
            elif isinstance(value, str):
                pairs.append((name, value))
        attrs = _optional_str_attrs(pairs)
        if not item.stops:
            self._empty(indent, "gradient", attrs)
            return
        self._open(indent, "gradient", attrs)
        for stop in item.stops:
            self._open(
                indent + 1,
                "gradientStop",
                _optional_str_attrs((("position", format_double(stop.position)),)),
            )
            self.value(stop.color, indent + 2)
            self._close(indent + 1, "gradientStop")
        self._close(indent, "gradient")

    def _palette(self, item: PaletteValue, indent: int) -> None:
        self._open(indent, "palette", "")
        for name in ("active", "inactive", "disabled"):
            roles = getattr(item, name)
            if not roles:
                self._empty(indent + 1, name, "")
                continue
            self._open(indent + 1, name, "")
            for role in roles:
                self._open(indent + 2, "colorrole", _optional_str_attrs((("role", role.role),)))
                self._brush(role.brush, indent + 3)
                self._close(indent + 2, "colorrole")
            self._close(indent + 1, name)
        self._close(indent, "palette")

    def _group(
        self,
        node: Node,
        group: str,
        indent: int,
        buckets: Dict[Tuple[str, int], List[OpaqueNode]],
    ) -> None:
        if group == "properties":
            self._sequence(
                group,
                node.properties(),
                lambda entry: self._property("property", entry, indent),
                buckets,
                indent,
            )
            return
        if group == "attributes":
            self._sequence(
                group,
                node.attributes(),
                lambda entry: self._property("attribute", entry, indent),
                buckets,
                indent,
            )
            return
        if group.startswith("child:"):
            tag = group[len("child:"):]
            if tag == "zorder":
                self._zorder(node, group, indent, buckets)
                return
            self._flush(buckets, (group, 0), indent)
            wrote = self._child_field(node, tag, indent)
            typed = 1 if wrote else 0
            if wrote:
                self._flush(buckets, (group, 1), indent)
            self._drain_group(buckets, group, typed, indent)
            return
        slot = _slot(node.kind, group)
        if slot is None:
            return
        children = node.children(group)
        if slot.wrapper:
            present = _wrappers(node)
            if not children and group not in present:
                self._drain_all(buckets, group, indent)
                return
            inner = "%s:inner" % group
            if not children and not _group_pending(buckets, inner):
                self._empty(indent, slot.wrapper, "")
                self._drain_all(buckets, group, indent)
                return
            self._open(indent, slot.wrapper, "")
            self._flush(buckets, (inner, 0), indent + 1)
            for index, child in enumerate(children, start=1):
                self.node(child, indent + 1)
                self._flush(buckets, (inner, index), indent + 1)
            self._drain_group(buckets, inner, len(children), indent + 1)
            self._close(indent, slot.wrapper)
            self._drain_all(buckets, group, indent)
            return
        self._flush(buckets, (group, 0), indent)
        for index, child in enumerate(children, start=1):
            self.node(child, indent)
            self._flush(buckets, (group, index), indent)
        self._drain_group(buckets, group, len(children), indent)

    def _sequence(
        self,
        group: str,
        entries: Sequence[PropertyEntry],
        write: Callable[[PropertyEntry], None],
        buckets: Dict[Tuple[str, int], List[OpaqueNode]],
        indent: int,
    ) -> None:
        self._flush(buckets, (group, 0), indent)
        for index, entry in enumerate(entries, start=1):
            write(entry)
            self._flush(buckets, (group, index), indent)
        self._drain_group(buckets, group, len(entries), indent)

    def _zorder(
        self,
        node: Node,
        group: str,
        indent: int,
        buckets: Dict[Tuple[str, int], List[OpaqueNode]],
    ) -> None:
        value = node.field("zorder")
        names = value if isinstance(value, tuple) else ()
        self._flush(buckets, (group, 0), indent)
        written = 0
        for name in names:
            if not isinstance(name, str):
                continue
            written += 1
            self._text_element("zorder", name, indent)
            self._flush(buckets, (group, written), indent)
        self._drain_group(buckets, group, written, indent)

    def _child_field(self, node: Node, tag: str, indent: int) -> bool:
        field_name = _child_field_name(node.kind, tag)
        if field_name is None:
            return False
        value = node.field(field_name)
        if value is None:
            return False
        if isinstance(value, str):
            self._text_element(tag, value, indent)
            return True
        if isinstance(value, int) and not isinstance(value, bool):
            self._text_element(tag, format_int(value), indent)
            return True
        if isinstance(value, tuple) and tag == "zorder":
            return False
        if isinstance(value, tuple) and tag == "tabstops":
            self._open(indent, "tabstops", "")
            for name in value:
                if isinstance(name, str):
                    self._text_element("tabstop", name, indent + 1)
            self._close(indent, "tabstops")
            return True
        if isinstance(value, LayoutDefault):
            self._empty(indent, "layoutdefault", _optional_int_attrs((("spacing", value.spacing), ("margin", value.margin))))
            return True
        if isinstance(value, LayoutFunction):
            self._empty(indent, "layoutfunction", _optional_str_attrs((("spacing", value.spacing), ("margin", value.margin))))
            return True
        if isinstance(value, SlotsDecl):
            self._open(indent, "slots", "")
            for signature in value.signals:
                self._text_element("signal", signature, indent + 1)
            for signature in value.slots:
                self._text_element("slot", signature, indent + 1)
            self._close(indent, "slots")
            return True
        if isinstance(value, HeaderDecl):
            location = "" if value.location is None else ' location="%s"' % _esc_attr(value.location)
            self._text_element("header", value.text, indent, location)
            return True
        if isinstance(value, tuple) and tag == "hints":
            self._open(indent, "hints", "")
            for hint in value:
                if isinstance(hint, ConnectionHint):
                    self._open(indent + 1, "hint", ' type="%s"' % _esc_attr(hint.type))
                    self._text_element("x", format_int(hint.x), indent + 2)
                    self._text_element("y", format_int(hint.y), indent + 2)
                    self._close(indent + 1, "hint")
            self._close(indent, "hints")
            return True
        if tag == "sizehint" and isinstance(value, SizeValue):
            self._open(indent, "sizehint", "")
            self._text_element("width", format_int(value.width), indent + 1)
            self._text_element("height", format_int(value.height), indent + 1)
            self._close(indent, "sizehint")
            return True
        if isinstance(value, OpaqueElement):
            self.opaque(value, indent)
            return True
        return False

    def _property(self, tag: str, entry: PropertyEntry, indent: int) -> None:
        attrs = ' name="%s"' % _esc_attr(entry.name)
        if entry.stdset is not None:
            attrs += ' stdset="%s"' % _esc_attr(entry.stdset)
        attrs += "".join(' %s="%s"' % (key, _esc_attr(value)) for key, value in entry.extra_attrs)
        value = entry.value
        if isinstance(value, OpaqueValue) and value.element.tag == "" and not value.element.children:
            # ``<property name="x"/>`` kept as written: no content, so no open element (8.2.4).
            self._empty(indent, tag, attrs)
            return
        self._open(indent, tag, attrs)
        self.value(entry.value, indent + 1)
        self._close(indent, tag)

    def _int_box(self, tag: str, pairs: Sequence[Tuple[str, int]], indent: int) -> None:
        self._open(indent, tag, "")
        for name, value in pairs:
            self._text_element(name, format_int(value), indent + 1)
        self._close(indent, tag)

    def _real_box(self, tag: str, pairs: Sequence[Tuple[str, float]], indent: int) -> None:
        self._open(indent, tag, "")
        for name, value in pairs:
            self._text_element(name, format_double(value), indent + 1)
        self._close(indent, tag)

    def _text_element(self, tag: str, text: str, indent: int, attrs: str = "") -> None:
        if text == "" and _empty_form(tag) == "self":
            self._empty(indent, tag, attrs)
            return
        escaped = _esc_text(text)
        prefix = " " * indent
        if "\n" not in escaped:
            self.lines.append("%s<%s%s>%s</%s>" % (prefix, tag, attrs, escaped, tag))
            return
        parts = escaped.split("\n")
        self.lines.append("%s<%s%s>%s" % (prefix, tag, attrs, parts[0]))
        self.lines.extend(parts[1:-1])
        self.lines.append("%s</%s>" % (parts[-1], tag))

    def _raw_text_line(self, indent: int, text: str) -> None:
        escaped = _esc_text(text)
        if "\n" not in escaped:
            self.lines.append((" " * indent) + escaped)
            return
        parts = escaped.split("\n")
        self.lines.append((" " * indent) + parts[0])
        self.lines.extend(parts[1:])

    def _mixed(self, element: OpaqueElement, indent: int, attrs: str) -> None:
        chunks: List[str] = [(" " * indent) + "<%s%s>" % (element.tag, attrs)]
        for child in element.children:
            if isinstance(child, str):
                chunks.append(_esc_text(child))
            elif isinstance(child, OpaqueComment):
                chunks.append("<!--%s-->" % child.text)
            elif isinstance(child, OpaquePI):
                chunks.append("<?%s %s?>" % (child.target, child.data))
            elif isinstance(child, OpaqueElement):
                chunks.append(_inline_opaque(child))
        chunks.append("</%s>" % element.tag)
        self.lines.extend("".join(chunks).split("\n"))

    def _flush(
        self,
        buckets: Dict[Tuple[str, int], List[OpaqueNode]],
        key: Tuple[str, int],
        indent: int,
    ) -> None:
        for item in buckets.pop(key, ()):
            self.node(item, indent)

    def _drain_group(
        self,
        buckets: Dict[Tuple[str, int], List[OpaqueNode]],
        group: str,
        typed: int,
        indent: int,
    ) -> None:
        extra = [key for key in buckets if key[0] == group and key[1] > typed]
        for key in extra:
            self._flush(buckets, key, indent)

    def _drain_all(
        self,
        buckets: Dict[Tuple[str, int], List[OpaqueNode]],
        group: str,
        indent: int,
    ) -> None:
        for key in [key for key in buckets if key[0] == group]:
            self._flush(buckets, key, indent)

    def _open(self, indent: int, tag: str, attrs: str) -> None:
        self.lines.append("%s<%s%s>" % (" " * indent, tag, attrs))

    def _close(self, indent: int, tag: str) -> None:
        self.lines.append("%s</%s>" % (" " * indent, tag))

    def _empty(self, indent: int, tag: str, attrs: str) -> None:
        if _empty_form(tag) == "pair":
            self.lines.append("%s<%s%s></%s>" % (" " * indent, tag, attrs, tag))
            return
        self.lines.append("%s<%s%s/>" % (" " * indent, tag, attrs))

    def _next_line(self) -> int:
        return len(self.lines) + 1


def _tag(node: Node) -> str:
    if node.kind == "header":
        axis = node.field("axis")
        if axis == "column":
            return "column"
        return "row"
    return SCHEMA[node.kind].element


def _attrs(node: Node) -> str:
    spec = SCHEMA[node.kind]
    parts: List[str] = []
    for attr_name in spec.attr_order:
        field_name = _attr_field(node.kind, attr_name)
        if field_name is None:
            continue
        value = node.field(field_name)
        if value is None:
            continue
        if isinstance(value, bool):
            text = format_bool(value)
        elif isinstance(value, int):
            text = format_int(value)
        else:
            text = str(value)
        parts.append(' %s="%s"' % (attr_name, _esc_attr(text)))
    parts.extend(' %s="%s"' % (key, _esc_attr(value)) for key, value in node.extra_attrs())
    return "".join(parts)


def _attr_field(kind: str, attr_name: str) -> Optional[str]:
    for field in SCHEMA[kind].fields:
        if field.xml == "attr:" + attr_name:
            return field.name
    return None


def _child_field_name(kind: str, tag: str) -> Optional[str]:
    return _CHILD_FIELDS.get(kind, {}).get(tag)


def _slot(kind: str, name: str):
    return _SLOTS.get(kind, {}).get(name)


def _wrappers(node: Node) -> frozenset:
    value = node.field("present_wrappers")
    if isinstance(value, frozenset):
        return value
    return frozenset()


def _has_body(node: Node) -> bool:
    spec = SCHEMA[node.kind]
    if node.properties() or node.attributes() or node.opaque():
        return True
    for group in spec.write_order:
        if group in ("properties", "attributes"):
            continue
        if group.startswith("child:"):
            field_name = _child_field_name(node.kind, group[len("child:"):])
            if field_name is not None and node.field(field_name) is not None:
                return True
            continue
        if node.children(group):
            return True
        slot = _slot(node.kind, group)
        if slot is not None and slot.wrapper and group in _wrappers(node):
            return True
    if node.kind == "include":
        text = node.field("text")
        if isinstance(text, str) and text != "":
            return True
    return False


def _pending_opaque(node: Node) -> bool:
    return bool(node.opaque())


def _buckets(items: Sequence[OpaqueNode]) -> Dict[Tuple[str, int], List[OpaqueNode]]:
    grouped: Dict[Tuple[str, int], List[OpaqueNode]] = {}
    for item in items:
        grouped.setdefault(item.anchor, []).append(item)
    return grouped


def _group_pending(buckets: Dict[Tuple[str, int], List[OpaqueNode]], group: str) -> bool:
    return any(key[0] == group for key in buckets)


def _string_attrs(item: Union[StringValue, StringListValue]) -> str:
    parts: List[str] = []
    if item.notr is not None:
        parts.append(' notr="%s"' % format_bool(item.notr))
    if item.comment is not None:
        parts.append(' comment="%s"' % _esc_attr(item.comment))
    if item.extracomment is not None:
        parts.append(' extracomment="%s"' % _esc_attr(item.extracomment))
    if item.id is not None:
        parts.append(' id="%s"' % _esc_attr(item.id))
    return "".join(parts)


def _optional_int_attrs(pairs: Sequence[Tuple[str, Optional[int]]]) -> str:
    return "".join(
        ' %s="%s"' % (name, format_int(value))
        for name, value in pairs
        if value is not None
    )


def _optional_str_attrs(pairs: Sequence[Tuple[str, Optional[str]]]) -> str:
    return "".join(
        ' %s="%s"' % (name, _esc_attr(value))
        for name, value in pairs
        if value is not None
    )


def _mixed(element: OpaqueElement) -> bool:
    for child in element.children:
        if isinstance(child, str) and child.strip():
            return True
        if isinstance(child, (OpaqueComment, OpaquePI)):
            return True
    return False


def _inline_opaque(element: OpaqueElement) -> str:
    attrs = "".join(' %s="%s"' % (key, _esc_attr(value)) for key, value in element.attrs)
    if not element.children:
        return "<%s%s/>" % (element.tag, attrs)
    if all(isinstance(child, str) for child in element.children):
        text = "".join(child for child in element.children if isinstance(child, str))
        return "<%s%s>%s</%s>" % (element.tag, attrs, _esc_text(text), element.tag)
    if element.tag == "":
        return "".join(_esc_text(child) for child in element.children if isinstance(child, str))
    parts = ["<%s%s>" % (element.tag, attrs)]
    for child in element.children:
        if isinstance(child, str):
            if child.strip():
                parts.append(_esc_text(child))
        elif isinstance(child, OpaqueElement):
            parts.append(_inline_opaque(child))
        elif isinstance(child, OpaqueComment):
            parts.append("<!--%s-->" % child.text)
        elif isinstance(child, OpaquePI):
            parts.append("<?%s %s?>" % (child.target, child.data))
    parts.append("</%s>" % element.tag)
    return "".join(parts)


# XML 1.0 Char: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
_ILLEGAL_XML = re.compile("[^\t\n\r\u0020-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]")


def require_xml_text(text: str) -> None:
    """Raise ValueError when ``text`` contains a character XML 1.0 cannot store."""
    if _ILLEGAL_XML.search(text):
        raise ValueError("text contains a character XML 1.0 cannot store")


# Provisional until M0.4b's Designer-resave corpus. Expat cannot tell
# ``<author/>`` from ``<author></author>``; each row is the writer's choice.
# ``self`` is ``<x/>`` (and ``<x attrs/>``). ``pair`` is ``<x></x>``.
# ``string`` is verified. Other text leaves follow writeTextElement (pair).
# Structural elements with no content are self, including empty resources
# and connections. M0.4b flips a row in this table and nowhere else.
EMPTY_ELEMENT_FORM = {
    "string": "self",
    "cstring": "pair",
    "enum": "pair",
    "set": "pair",
    "bool": "pair",
    "number": "pair",
    "uint": "pair",
    "longlong": "pair",
    "ulonglong": "pair",
    "double": "pair",
    "float": "pair",
    "cursor": "pair",
    "cursorshape": "pair",
    "author": "pair",
    "comment": "pair",
    "exportmacro": "pair",
    "class": "pair",
    "pixmapfunction": "pair",
    # ``<include location="..."/>`` has no text; a text include uses the pair
    # only when text is non-empty (the writer takes that path directly).
    "include": "self",
    "header": "pair",
    "zorder": "pair",
    "tabstop": "pair",
    "signal": "pair",
    "slot": "pair",
    "horstretch": "pair",
    "verstretch": "pair",
    "unicode": "pair",
    "red": "pair",
    "green": "pair",
    "blue": "pair",
    "x": "pair",
    "y": "pair",
    "width": "pair",
    "height": "pair",
    "year": "pair",
    "month": "pair",
    "day": "pair",
    "hour": "pair",
    "minute": "pair",
    "second": "pair",
    "family": "pair",
    "pointsize": "pair",
    "weight": "pair",
    "italic": "pair",
    "bold": "pair",
    "underline": "pair",
    "strikeout": "pair",
    "antialiasing": "pair",
    "stylestrategy": "pair",
    "kerning": "pair",
    "hintingpreference": "pair",
    "fontweight": "pair",
    "ui": "self",
    "widget": "self",
    "layout": "self",
    "spacer": "self",
    "item": "self",
    "property": "self",
    "attribute": "self",
    "action": "self",
    "actiongroup": "self",
    "addaction": "self",
    "row": "self",
    "column": "self",
    "buttongroup": "self",
    "connection": "self",
    "customwidget": "self",
    "resources": "self",
    "connections": "self",
    "customwidgets": "self",
    "includes": "self",
    "buttongroups": "self",
    "layoutdefault": "self",
    "layoutfunction": "self",
    "locale": "self",
    "font": "self",
    "char": "self",
    "color": "self",
    "rect": "self",
    "rectf": "self",
    "size": "self",
    "sizef": "self",
    "point": "self",
    "pointf": "self",
    "date": "self",
    "time": "self",
    "datetime": "self",
    "url": "self",
    "stringlist": "self",
    "sizepolicy": "self",
    "sizehint": "self",
    "hints": "self",
    "hint": "self",
    "tabstops": "self",
    "slots": "self",
}


def _empty_form(tag: str) -> str:
    """The provisional empty-element form for ``tag`` (``self`` or ``pair``).

    Unlisted tags self-close, matching an element with no content.
    """
    return EMPTY_ELEMENT_FORM.get(tag, "self")


def _esc_text(text: str) -> str:
    require_xml_text(text)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\r", "&#13;")
    )


def _esc_attr(text: str) -> str:
    return _esc_text(text).replace("\t", "&#9;").replace("\n", "&#10;")


def _fragment_spec(fragment: Fragment, allocator: IdAllocator) -> NodeSpec:
    from app.features.form_builder.engine.ui4.schema import SCHEMA as schema

    def mint(spec: NodeSpec) -> NodeSpec:
        return NodeSpec(
            kind=spec.kind,
            id=allocator.alloc(),
            fields=spec.fields,
            properties=spec.properties,
            attributes=spec.attributes,
            slots=tuple((name, tuple(mint(child) for child in kids)) for name, kids in spec.slots),
            extra_attrs=spec.extra_attrs,
        )

    buckets: Dict[str, List[NodeSpec]] = {}
    for spec in fragment.nodes:
        placed = False
        for slot in schema["widget"].slots:
            if spec.kind in slot.accepts and slot.name != "opaque":
                buckets.setdefault(slot.name, []).append(mint(spec))
                placed = True
                break
        if not placed:
            buckets.setdefault("opaque", []).append(mint(spec))
    root_slots = tuple((name, tuple(kids)) for name, kids in buckets.items() if kids)
    root = NodeSpec(
        kind="widget",
        id=allocator.alloc(),
        fields=(("class_name", "QWidget"), ("object_name", "_cbcs_fragment")),
        slots=root_slots,
    )
    ui_slots: List[Tuple[str, Tuple[NodeSpec, ...]]] = [("root", (root,))]
    if fragment.customwidgets:
        ui_slots.append(("customwidgets", tuple(mint(item) for item in fragment.customwidgets)))
    if fragment.resources:
        ui_slots.append(("resources", tuple(mint(item) for item in fragment.resources)))
    if fragment.connections:
        ui_slots.append(("connections", tuple(mint(item) for item in fragment.connections)))
    present = []
    if fragment.customwidgets:
        present.append("customwidgets")
    if fragment.resources:
        present.append("resources")
    if fragment.connections:
        present.append("connections")
    return NodeSpec(
        kind="ui",
        id=DOCUMENT_ID,
        fields=(
            ("version", "4.0"),
            ("class_name", "Fragment"),
            ("present_wrappers", frozenset(present)),
        ),
        slots=tuple(ui_slots),
    )
