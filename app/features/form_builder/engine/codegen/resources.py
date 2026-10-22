"""``.qrc`` to ``*_rc.py`` and the in-editor resource tree (CONTRACTS.md section 9).

The binary layout is the version-3 blob ``QtCore.qRegisterResourceData`` reads.
Integers are big-endian. Children are ordered by Qt's resource-name hash then
name. File payloads are uncompressed, each prefixed with its length, and the
modification time is 0 so the bytes do not depend on the clock.
"""

from __future__ import annotations

import hashlib
import struct
import xml.parsers.expat
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QLocale

from app.features.form_builder.engine.codegen.header import render_resource_header
from app.features.form_builder.engine.codegen.literals import py_bytes
from app.features.form_builder.engine.diagnostics import (
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.engine.diagnostic_codes import fb5xx as _fb5xx

del _fb5xx

_FLAG_DIRECTORY = 0x02
# QLocale.Language.C, country AnyCountry. rcc writes this when ``<qresource>`` has no lang.
_LOCALE_C = 1


@dataclass(frozen=True)
class QrcFile:
    """One ``<file alias="..">path</file>`` under a ``<qresource prefix=".." lang="..">``."""

    prefix: str
    path: str
    alias: Optional[str] = None
    lang: Optional[str] = None


@dataclass(frozen=True)
class QrcDocument:
    files: Tuple[QrcFile, ...]


def read_qrc(text: str) -> QrcDocument:
    """Parse a ``.qrc``. ValueError on bad input.

    A bare ``<!DOCTYPE RCC>`` is removed first. Qt writes that token on ordinary
    resource files, and it has no internal subset. A doctype that declares
    entities still fails, same as the ui reader.
    """
    text = _without_plain_doctype(text)
    parser = xml.parsers.expat.ParserCreate()
    parser.ordered_attributes = True
    stack: List[dict] = []
    files: List[QrcFile] = []

    def position() -> str:
        return "line %s" % parser.CurrentLineNumber

    def doctype(*_args: object) -> None:
        raise ValueError("This resource file uses a DOCTYPE, which the form builder refuses (%s)." % position())

    def entity(*_args: object) -> None:
        raise ValueError("This resource file declares an XML entity, which the form builder refuses (%s)." % position())

    def start(name: str, attrs: List[str]) -> None:
        mapping = {}
        for index in range(0, len(attrs), 2):
            mapping[attrs[index]] = attrs[index + 1]
        stack.append({"tag": name, "attrs": mapping, "text": []})

    def data(value: str) -> None:
        if stack:
            stack[-1]["text"].append(value)

    def end(name: str) -> None:
        frame = stack.pop()
        if name == "file":
            parent = stack[-1]["attrs"] if stack else {}
            path = "".join(frame["text"]).strip()
            alias = frame["attrs"].get("alias")
            files.append(
                QrcFile(
                    prefix=parent.get("prefix", ""),
                    path=path,
                    alias=alias,
                    lang=parent.get("lang"),
                )
            )
        del name

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = data
    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = entity
    try:
        parser.Parse(text, True)
    except xml.parsers.expat.ExpatError as exc:
        raise ValueError("This resource file is not valid XML (%s)." % exc) from exc
    return QrcDocument(files=tuple(files))


def _without_plain_doctype(text: str) -> str:
    lower = text.lower()
    start = lower.find("<!doctype")
    if start < 0:
        return text
    end = text.find(">", start)
    if end < 0:
        return text
    body = text[start:end]
    if "[" in body:
        return text
    return text[:start] + text[end + 1 :]


def qt_hash(text: str) -> int:
    """Qt's resource-name hash. Children are ordered by this, then by name.

    Qt walks UTF-16 code units. A non-BMP character is two units, not one
    Python code point.
    """
    value = 0
    encoded = text.encode("utf-16-be")
    for index in range(0, len(encoded), 2):
        unit = int.from_bytes(encoded[index : index + 2], "big")
        value = (value << 4) + unit
        high = value & 0xF0000000
        if high:
            value ^= high >> 23
        value &= 0x0FFFFFFF
    return value


def _locale_field(lang: Optional[str]) -> int:
    """Language in the low 16 bits, territory in the high 16.

    ``lang="fr"`` is French with territory 0. ``lang="fr_CA"`` carries both.
    A missing lang is the C locale, language 1.
    """
    if not lang:
        return _LOCALE_C
    locale = QLocale(lang)
    language = int(locale.language().value)
    territory = int(locale.territory().value) if "_" in lang else 0
    return (territory << 16) | language


@dataclass
class _TreeNode:
    name: str
    data: Optional[bytes] = None
    locale: int = 0
    children: Dict[Tuple[str, Optional[int]], "_TreeNode"] = field(default_factory=dict)

    def directory(self, name: str) -> "_TreeNode":
        key = (name, None)
        found = self.children.get(key)
        if found is None:
            found = _TreeNode(name=name)
            self.children[key] = found
        return found

    def file(self, name: str, payload: bytes, locale: int) -> None:
        self.children[(name, locale)] = _TreeNode(name=name, data=payload, locale=locale)


@dataclass(frozen=True)
class ResourceTree:
    """The binary resource structure Qt's ``qRegisterResourceData`` accepts
    (format version 3): ``struct``, ``names``, ``data`` bytes. Files are stored
    uncompressed and with modification time 0, so output depends only on the
    file bytes (zlib versions differ between machines)."""

    version: int
    struct: bytes
    names: bytes
    data: bytes


def _segments(entry: QrcFile) -> Tuple[str, ...]:
    prefix = entry.prefix.strip().strip("/")
    if entry.alias:
        tail = entry.alias.strip().strip("/")
    else:
        tail = entry.path.replace("\\", "/").strip().strip("/")
    parts: List[str] = []
    if prefix:
        parts.extend(part for part in prefix.split("/") if part)
    if tail:
        parts.extend(part for part in tail.split("/") if part)
    return tuple(parts)


def compile_resource_tree(
    qrc: QrcDocument,
    *,
    read_file: Callable[[str], bytes],
) -> Tuple[ResourceTree, Tuple[FormDiagnostic, ...]]:
    """Build the tree. ``read_file`` resolves a qrc-relative path (missing file:
    FB503 and the entry is skipped). Children are ordered exactly as rcc orders
    them (by Qt's name hash, then name) so lookup works."""
    root = _TreeNode(name="")
    diagnostics: List[FormDiagnostic] = []
    for entry in qrc.files:
        parts = _segments(entry)
        if not parts:
            continue
        try:
            payload = read_file(entry.path)
        except OSError:
            diagnostics.append(
                FormDiagnostic(
                    code="FB503",
                    severity=Severity.ERROR,
                    message='The resource file "%s" is missing.' % entry.path,
                    location=DiagnosticLocation(object_name=entry.path),
                    source="codegen",
                )
            )
            continue
        node = root
        for part in parts[:-1]:
            node = node.directory(part)
        node.file(parts[-1], payload, _locale_field(entry.lang))
    _sort_tree(root)
    return _serialize(root), tuple(diagnostics)


def _child_sort(child: _TreeNode) -> Tuple[int, str, int, int]:
    """rcc orders ties by language, then territory, both descending."""
    language = child.locale & 0xFFFF
    territory = child.locale >> 16
    return (qt_hash(child.name), child.name, -language, -territory)


def _sort_tree(node: _TreeNode) -> None:
    ordered = sorted(node.children.values(), key=_child_sort)
    rebuilt: Dict[Tuple[str, Optional[int]], _TreeNode] = {}
    for child in ordered:
        key = (child.name, None if child.data is None else child.locale)
        rebuilt[key] = child
    node.children = rebuilt
    for child in ordered:
        if child.data is None:
            _sort_tree(child)


def _name_blob(order: List["_TreeNode"], root: "_TreeNode") -> Tuple[bytes, Dict[str, int]]:
    """Directory names in visit order, then file names. A repeated name shares one entry."""
    directories: List[str] = []
    files: List[str] = []
    for node in order:
        if node is root or not node.name:
            continue
        if node.data is None:
            directories.append(node.name)
        else:
            files.append(node.name)
    blob = bytearray()
    offsets: Dict[str, int] = {}
    for name in directories + files:
        if name in offsets:
            continue
        offsets[name] = len(blob)
        encoded = name.encode("utf-16-be")
        units = len(encoded) // 2
        blob += struct.pack(">HI", units, qt_hash(name))
        blob += encoded
    return bytes(blob), offsets


def _serialize(root: _TreeNode) -> ResourceTree:
    order: List[_TreeNode] = [root]
    cursor = 0
    first_child: Dict[int, int] = {}
    while cursor < len(order):
        node = order[cursor]
        cursor += 1
        if node.data is None and node.children:
            first_child[id(node)] = len(order)
            order.extend(node.children.values())
    name_bytes, name_offsets = _name_blob(order, root)
    data = bytearray()
    data_at: Dict[int, int] = {}
    for node in order:
        if node.data is None:
            continue
        data_at[id(node)] = len(data)
        payload = node.data
        data += struct.pack(">I", len(payload))
        data += payload
    struct_blob = bytearray()
    for node in order:
        name_offset = 0 if node is root else name_offsets.get(node.name, 0)
        if node.data is None:
            struct_blob += struct.pack(
                ">IHIIQ",
                name_offset,
                _FLAG_DIRECTORY,
                len(node.children),
                first_child.get(id(node), 0),
                0,
            )
        else:
            struct_blob += struct.pack(
                ">IHIIQ",
                name_offset,
                0,
                node.locale or _LOCALE_C,
                data_at[id(node)],
                0,
            )
    return ResourceTree(version=3, struct=bytes(struct_blob), names=name_bytes, data=bytes(data))


def render_rc_module(tree: ResourceTree, *, qrc_file_name: str) -> str:
    """``*_rc.py`` in the shape of ``rcc -g python``."""
    body = "\n".join(
        (
            "from PySide6 import QtCore",
            "",
            "qt_resource_data = %s" % py_bytes(tree.data),
            "qt_resource_name = %s" % py_bytes(tree.names),
            "qt_resource_struct = %s" % py_bytes(tree.struct),
            "",
            "def qInitResources():",
            "    QtCore.qRegisterResourceData(0x03, qt_resource_struct, qt_resource_name, qt_resource_data)",
            "",
            "def qCleanupResources():",
            "    QtCore.qUnregisterResourceData(0x03, qt_resource_struct, qt_resource_name, qt_resource_data)",
            "",
            "qInitResources()",
            "",
        )
    )
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    header = render_resource_header(qrc_file_name=qrc_file_name, body_sha256=body_hash)
    return header + body
