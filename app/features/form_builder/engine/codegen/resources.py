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

# Qt 6.8 QLocale.languageToCode / territoryToCode. The engine cannot import Qt.
_QT_LANGUAGE = {'C': 1, 'ab': 2, 'aa': 3, 'af': 4, 'agq': 5, 'ak': 6, 'akk': 7, 'bss': 8, 'sq': 9, 'ase': 10, 'am': 11, 'egy': 12, 'grc': 13, 'ar': 14, 'an': 15, 'arc': 16, 'hy': 17, 'as': 18, 'ast': 19, 'asa': 20, 'cch': 21, 'av': 22, 'ae': 23, 'ay': 24, 'az': 25, 'ksf': 26, 'ban': 27, 'bm': 28, 'bax': 29, 'bn': 30, 'bas': 31, 'ba': 32, 'eu': 33, 'bbc': 34, 'be': 35, 'bem': 36, 'bez': 37, 'bho': 38, 'bi': 39, 'byn': 40, 'brx': 41, 'bs': 42, 'br': 43, 'bug': 44, 'bg': 45, 'my': 46, 'yue': 47, 'ca': 48, 'ceb': 49, 'tzm': 50, 'ckb': 51, 'ccp': 52, 'ch': 53, 'ce': 54, 'chr': 55, 'cic': 56, 'cgg': 57, 'zh': 58, 'cu': 59, 'cv': 60, 'ksh': 61, 'cop': 62, 'kw': 63, 'co': 64, 'cr': 65, 'hr': 66, 'cs': 67, 'da': 68, 'dv': 69, 'doi': 70, 'dua': 71, 'nl': 72, 'dz': 73, 'ebu': 74, 'en': 75, 'myv': 76, 'eo': 77, 'et': 78, 'ee': 79, 'ewo': 80, 'fo': 81, 'fj': 82, 'fil': 83, 'fi': 84, 'fr': 85, 'fur': 86, 'ff': 87, 'gd': 88, 'gaa': 89, 'gl': 90, 'lg': 91, 'gez': 92, 'ka': 93, 'de': 94, 'got': 95, 'el': 96, 'gn': 97, 'gu': 98, 'guz': 99, 'ht': 100, 'ha': 101, 'haw': 102, 'he': 103, 'hz': 104, 'hi': 105, 'ho': 106, 'hu': 107, 'is': 108, 'io': 109, 'ig': 110, 'smn': 111, 'id': 112, 'inh': 113, 'ia': 114, 'ie': 115, 'iu': 116, 'ik': 117, 'ga': 118, 'it': 119, 'ja': 120, 'jv': 121, 'kaj': 122, 'dyo': 123, 'kea': 124, 'kab': 125, 'kkj': 126, 'kl': 127, 'kln': 128, 'kam': 129, 'kn': 130, 'kr': 131, 'ks': 132, 'kk': 133, 'ken': 134, 'km': 135, 'quc': 136, 'ki': 137, 'rw': 138, 'kv': 139, 'kg': 140, 'kok': 141, 'ko': 142, 'kfo': 143, 'ses': 144, 'khq': 145, 'kpe': 146, 'kj': 147, 'ku': 148, 'nmg': 149, 'ky': 150, 'lkt': 151, 'lag': 152, 'lo': 153, 'la': 154, 'lv': 155, 'lez': 156, 'li': 157, 'ln': 158, 'lzh': 159, 'lt': 160, 'jbo': 161, 'dsb': 162, 'nds': 163, 'lu': 164, 'smj': 165, 'luo': 166, 'lb': 167, 'luy': 168, 'mk': 169, 'jmc': 170, 'mai': 171, 'mgh': 172, 'kde': 173, 'mg': 174, 'ml': 175, 'ms': 176, 'mt': 177, 'man': 178, 'mni': 179, 'gv': 180, 'mi': 181, 'arn': 182, 'mr': 183, 'mh': 184, 'mas': 185, 'mzn': 186, 'men': 187, 'mer': 188, 'mgo': 189, 'moh': 190, 'mn': 191, 'mfe': 192, 'mua': 193, 'mus': 194, 'naq': 195, 'na': 196, 'nv': 197, 'ng': 198, 'ne': 199, 'new': 200, 'nnh': 201, 'jgo': 202, 'pcm': 203, 'nqo': 204, 'lrc': 205, 'se': 206, 'nso': 207, 'nd': 208, 'nb': 209, 'nn': 210, 'nus': 211, 'ny': 212, 'nyn': 213, 'oc': 214, 'or': 215, 'oj': 216, 'sga': 217, 'non': 218, 'peo': 219, 'om': 220, 'osa': 221, 'os': 222, 'pal': 223, 'pau': 224, 'pi': 225, 'pap': 226, 'ps': 227, 'fa': 228, 'phn': 229, 'pl': 230, 'pt': 231, 'prg': 232, 'pa': 233, 'qu': 234, 'ro': 235, 'rm': 236, 'rof': 237, 'rn': 238, 'ru': 239, 'rwk': 240, 'ssy': 241, 'sah': 242, 'saq': 243, 'sm': 244, 'sg': 245, 'sbp': 246, 'sa': 247, 'sat': 248, 'sc': 249, 'saz': 250, 'seh': 251, 'sr': 252, 'ksb': 253, 'sn': 254, 'ii': 255, 'scn': 256, 'sid': 257, 'szl': 258, 'sd': 259, 'si': 260, 'sms': 261, 'sk': 262, 'sl': 263, 'xog': 264, 'so': 265, 'sdh': 266, 'sma': 267, 'st': 268, 'nr': 269, 'es': 270, 'zgh': 271, 'su': 272, 'sw': 273, 'ss': 274, 'sv': 275, 'gsw': 276, 'syr': 277, 'shi': 278, 'ty': 279, 'blt': 280, 'dav': 281, 'tg': 282, 'ta': 283, 'trv': 284, 'twq': 285, 'tt': 286, 'te': 287, 'teo': 288, 'th': 289, 'bo': 290, 'tig': 291, 'ti': 292, 'tkl': 293, 'tpi': 294, 'to': 295, 'ts': 296, 'tn': 297, 'tr': 298, 'tk': 299, 'tvl': 300, 'kcg': 301, 'uga': 302, 'uk': 303, 'hsb': 304, 'ur': 305, 'ug': 306, 'uz': 307, 'vai': 308, 've': 309, 'vi': 310, 'vo': 311, 'vun': 312, 'wa': 313, 'wae': 314, 'wbp': 315, 'cy': 316, 'bgn': 317, 'fy': 318, 'wal': 319, 'wo': 320, 'xh': 321, 'yav': 322, 'yi': 323, 'yo': 324, 'dje': 325, 'za': 326, 'zu': 327, 'kgp': 328, 'yrl': 329, 'bgc': 330, 'frr': 331, 'raj': 332, 'mdf': 333, 'tok': 334, 'pis': 335, 'ann': 336, 'bal': 337, 'lij': 338, 'rhg': 339, 'trw': 340, 'blo': 341, 'xnr': 342, 'vec': 343, 'kxv': 344, 'kaa': 345, 'csw': 346}
_QT_TERRITORY = {'AF': 1, 'AX': 2, 'AL': 3, 'DZ': 4, 'AS': 5, 'AD': 6, 'AO': 7, 'AI': 8, 'AQ': 9, 'AG': 10, 'AR': 11, 'AM': 12, 'AW': 13, 'AC': 14, 'AU': 15, 'AT': 16, 'AZ': 17, 'BS': 18, 'BH': 19, 'BD': 20, 'BB': 21, 'BY': 22, 'BE': 23, 'BZ': 24, 'BJ': 25, 'BM': 26, 'BT': 27, 'BO': 28, 'BA': 29, 'BW': 30, 'BV': 31, 'BR': 32, 'IO': 33, 'VG': 34, 'BN': 35, 'BG': 36, 'BF': 37, 'BI': 38, 'KH': 39, 'CM': 40, 'CA': 41, 'IC': 42, 'CV': 43, 'BQ': 44, 'KY': 45, 'CF': 46, 'EA': 47, 'TD': 48, 'CL': 49, 'CN': 50, 'CX': 51, 'CP': 52, 'CC': 53, 'CO': 54, 'KM': 55, 'CG': 56, 'CD': 57, 'CK': 58, 'CR': 59, 'HR': 60, 'CU': 61, 'CW': 62, 'CY': 63, 'CZ': 64, 'DK': 65, 'DG': 66, 'DJ': 67, 'DM': 68, 'DO': 69, 'EC': 70, 'EG': 71, 'SV': 72, 'GQ': 73, 'ER': 74, 'EE': 75, 'SZ': 76, 'ET': 77, '150': 78, 'EU': 79, 'FK': 80, 'FO': 81, 'FJ': 82, 'FI': 83, 'FR': 84, 'GF': 85, 'PF': 86, 'TF': 87, 'GA': 88, 'GM': 89, 'GE': 90, 'DE': 91, 'GH': 92, 'GI': 93, 'GR': 94, 'GL': 95, 'GD': 96, 'GP': 97, 'GU': 98, 'GT': 99, 'GG': 100, 'GW': 101, 'GN': 102, 'GY': 103, 'HT': 104, 'HM': 105, 'HN': 106, 'HK': 107, 'HU': 108, 'IS': 109, 'IN': 110, 'ID': 111, 'IR': 112, 'IQ': 113, 'IE': 114, 'IM': 115, 'IL': 116, 'IT': 117, 'CI': 118, 'JM': 119, 'JP': 120, 'JE': 121, 'JO': 122, 'KZ': 123, 'KE': 124, 'KI': 125, 'XK': 126, 'KW': 127, 'KG': 128, 'LA': 129, '419': 130, 'LV': 131, 'LB': 132, 'LS': 133, 'LR': 134, 'LY': 135, 'LI': 136, 'LT': 137, 'LU': 138, 'MO': 139, 'MK': 140, 'MG': 141, 'MW': 142, 'MY': 143, 'MV': 144, 'ML': 145, 'MT': 146, 'MH': 147, 'MQ': 148, 'MR': 149, 'MU': 150, 'YT': 151, 'MX': 152, 'FM': 153, 'MD': 154, 'MC': 155, 'MN': 156, 'ME': 157, 'MS': 158, 'MA': 159, 'MZ': 160, 'MM': 161, 'NA': 162, 'NR': 163, 'NP': 164, 'NL': 165, 'NC': 166, 'NZ': 167, 'NI': 168, 'NG': 169, 'NE': 170, 'NU': 171, 'NF': 172, 'MP': 173, 'KP': 174, 'NO': 175, 'OM': 176, 'QO': 177, 'PK': 178, 'PW': 179, 'PS': 180, 'PA': 181, 'PG': 182, 'PY': 183, 'PE': 184, 'PH': 185, 'PN': 186, 'PL': 187, 'PT': 188, 'PR': 189, 'QA': 190, 'RE': 191, 'RO': 192, 'RU': 193, 'RW': 194, 'BL': 195, 'SH': 196, 'KN': 197, 'LC': 198, 'MF': 199, 'PM': 200, 'VC': 201, 'WS': 202, 'SM': 203, 'ST': 204, 'SA': 205, 'SN': 206, 'RS': 207, 'SC': 208, 'SL': 209, 'SG': 210, 'SX': 211, 'SK': 212, 'SI': 213, 'SB': 214, 'SO': 215, 'ZA': 216, 'GS': 217, 'KR': 218, 'SS': 219, 'ES': 220, 'LK': 221, 'SD': 222, 'SR': 223, 'SJ': 224, 'SE': 225, 'CH': 226, 'SY': 227, 'TW': 228, 'TJ': 229, 'TZ': 230, 'TH': 231, 'TL': 232, 'TG': 233, 'TK': 234, 'TO': 235, 'TT': 236, 'TA': 237, 'TN': 238, 'TR': 239, 'TM': 240, 'TC': 241, 'TV': 242, 'UG': 243, 'UA': 244, 'AE': 245, 'GB': 246, 'UM': 247, 'US': 248, 'VI': 249, 'UY': 250, 'UZ': 251, 'VU': 252, 'VA': 253, 'VE': 254, 'VN': 255, 'WF': 256, 'EH': 257, '001': 258, 'YE': 259, 'ZM': 260, 'ZW': 261}


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

    The codes are Qt 6.8 ``QLocale`` values. ``lang="fr"`` is French with
    territory 0. ``lang="fr_CA"`` carries both. A missing lang is the C locale.
    """
    if not lang:
        return _LOCALE_C
    parts = lang.replace("-", "_").split("_")
    language = _QT_LANGUAGE.get(parts[0], _LOCALE_C)
    territory = _QT_TERRITORY.get(parts[-1], 0) if len(parts) > 1 else 0
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
