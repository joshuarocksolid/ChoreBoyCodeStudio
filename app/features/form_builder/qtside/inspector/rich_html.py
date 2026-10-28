"""Stable Qt rich-text HTML (UX-PED-042, CONTRACTS §8.3).

``QTextDocument.toHtml()`` embeds the widget font and can format numbers with
the process locale, so the same bold click differs between macOS and Linux
and between ``C`` and ``de_DE``. This writer never calls ``toHtml``. It emits
one frozen skeleton (Sans Serif, 9 pt) from a list of paragraphs. The
formatted editor may display any font. Only this structure is saved.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

_FAMILY = "Sans Serif"
_NORMAL = 9
_SMALL = 7
_LARGE = 14

_HEAD = (
    "<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0//EN\" "
    "\"http://www.w3.org/TR/REC-html40/strict.dtd\">\n"
    "<html><head><meta name=\"qrichtext\" content=\"1\" /><meta charset=\"utf-8\" />"
    "<style type=\"text/css\">\n"
    "p, li { white-space: pre-wrap; }\n"
    "hr { height: 1px; border-width: 0; }\n"
    "</style></head><body style=\" font-family:'%s'; font-size:%dpt; "
    "font-weight:400; font-style:normal;\">\n"
) % (_FAMILY, _NORMAL)

_P_STYLE = (
    " margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px;"
    " -qt-block-indent:0; text-indent:0px;"
)


@dataclass(frozen=True)
class Span:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    href: str = ""
    size: str = "normal"


@dataclass(frozen=True)
class Paragraph:
    """``kind`` is ``p``, ``ul`` or ``ol``."""

    spans: Tuple[Span, ...]
    kind: str = "p"


def stable_html(paragraphs: Sequence[Paragraph]) -> str:
    """The bytes written for this structure. Identical on every OS and locale."""
    body = [_HEAD]
    list_kind = ""
    for para in paragraphs:
        if para.kind != list_kind:
            if list_kind:
                body.append("</%s>\n" % list_kind)
            if para.kind in ("ul", "ol"):
                body.append("<%s>\n" % para.kind)
            list_kind = para.kind if para.kind in ("ul", "ol") else ""
        inner = "".join(_span(span) for span in para.spans) or ""
        if para.kind in ("ul", "ol"):
            body.append("<li style=\"%s\">%s</li>\n" % (_P_STYLE, inner))
        else:
            body.append("<p style=\"%s\">%s</p>\n" % (_P_STYLE, inner))
    if list_kind:
        body.append("</%s>\n" % list_kind)
    body.append("</body></html>")
    return "".join(body)


def size_name(point_size: int, normal: int = _NORMAL) -> str:
    """Map a display point size back to small, normal or large.

    ``normal`` is the editor's font size. The file still stores 7, 9 and 14.
    A size within one step of ``normal`` stays normal, so the app font does
    not change the bytes.
    """
    if point_size <= 0:
        return "normal"
    baseline = normal if normal > 0 else _NORMAL
    small = max(1, baseline - 4)
    large = baseline + 5
    if point_size < baseline and abs(point_size - small) <= abs(point_size - baseline):
        return "small"
    if point_size > baseline and abs(point_size - large) <= abs(point_size - baseline):
        return "large"
    return "normal"


def point_size(name: str) -> int:
    if name == "small":
        return _SMALL
    if name == "large":
        return _LARGE
    return _NORMAL


def looks_like_html(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("<") and ">" in stripped


_SIZE_IN_HTML = re.compile(r"font-size\s*:\s*(\d+)")


def unsupported_formatting(text: str) -> bool:
    """True when Designer HTML has colour, alignment or a size this editor drops."""
    if not looks_like_html(text):
        return False
    lower = text.lower()
    if "color:" in lower or "background-color" in lower or "text-align" in lower or "align=" in lower:
        return True
    for found in _SIZE_IN_HTML.findall(lower):
        if int(found) not in (_SMALL, _NORMAL, _LARGE):
            return True
    return False


def _span(span: Span) -> str:
    # Shift+Enter in the formatted editor stores U+2028; both are line breaks.
    text = html.escape(span.text, quote=False).replace("\u2028", "\n").replace("\n", "<br />")
    styles: List[str] = []
    if span.bold:
        styles.append("font-weight:600")
    if span.italic:
        styles.append("font-style:italic")
    if span.underline:
        styles.append("text-decoration:underline")
    if span.size == "small":
        styles.append("font-size:%dpt" % _SMALL)
    elif span.size == "large":
        styles.append("font-size:%dpt" % _LARGE)
    if styles:
        text = '<span style=" %s;">%s</span>' % ("; ".join(styles), text)
    if span.href:
        text = '<a href="%s">%s</a>' % (html.escape(span.href, quote=True), text)
    return text


def paragraphs_from_document(document: object) -> Tuple[Paragraph, ...]:
    """Read bold, italic, underline, links, lists and the three sizes.

    Font family is ignored. A missing Qt document returns one empty paragraph.
    """
    begin = getattr(document, "begin", None)
    if not callable(begin):
        return (Paragraph((Span(""),)),)
    normal = _document_normal(document)
    found: List[Paragraph] = []
    block = begin()
    while getattr(block, "isValid", lambda: False)():
        spans = tuple(_fragments(block, normal))
        kind = _list_kind(block)
        found.append(Paragraph(spans or (Span(""),), kind))
        nxt = getattr(block, "next", None)
        if not callable(nxt):
            break
        block = nxt()
    if not found:
        return (Paragraph((Span(""),)),)
    return tuple(found)


def _list_kind(block: object) -> str:
    text_list = getattr(block, "textList", None)
    if not callable(text_list):
        return "p"
    listed = text_list()
    if listed is None:
        return "p"
    style = listed.format().style()
    raw = getattr(style, "value", style)
    # QTextListFormat: Disc -1, Circle -2, Square -3 are bullets; Decimal -4
    # and the alpha and roman styles (-5 … -8) are numbered.
    if int(raw) <= -4:
        return "ol"
    return "ul"


def _document_normal(document: object) -> int:
    default_font = getattr(document, "defaultFont", None)
    if not callable(default_font):
        return _NORMAL
    try:
        size = int(default_font().pointSize())
    except (TypeError, ValueError):
        return _NORMAL
    return size if size > 0 else _NORMAL


def _fragments(block: object, normal: int) -> List[Span]:
    iterator = block.begin()
    spans: List[Span] = []
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid():
            spans.append(_span_from(fragment, normal))
        iterator += 1
    if not spans:
        text = block.text()
        if text:
            spans.append(Span(text))
    return spans


def _span_from(fragment: object, normal: int) -> Span:
    fmt = fragment.charFormat()
    font = fmt.font()
    bold = bool(font.bold()) or int(font.weight()) >= 600
    size = size_name(int(font.pointSize()), normal)
    href = ""
    anchor = getattr(fmt, "anchorHref", None)
    if callable(anchor):
        href = str(anchor() or "")
    return Span(
        fragment.text(),
        bold=bold,
        italic=bool(font.italic()),
        underline=bool(font.underline()),
        href=href,
        size=size,
    )
