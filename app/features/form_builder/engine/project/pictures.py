"""Read-only picture index for the ``.qrc`` files a form includes.

Qt-free. A bad resource file becomes a sentence. The parse is cached per
absolute path and mtime, so opening a picker does not read the file again.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.resources import read_qrc

_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".xpm",
        ".xbm",
        ".pbm",
        ".pgm",
        ".ppm",
        ".svg",
        ".svgz",
        ".ico",
        ".webp",
        ".tif",
        ".tiff",
        ".icns",
    }
)

# (absolute qrc path, mtime_ns) -> parsed document or a problem sentence.
_CACHE: Dict[Tuple[str, int], object] = {}


@dataclass(frozen=True)
class QrcPicture:
    """One image listed by a resource file."""

    qrc_path: str
    qrc_name: str
    prefix: str
    file_name: str
    resource_path: str
    disk_path: str


@dataclass(frozen=True)
class QrcIssue:
    """Why one ``.qrc`` could not be read. ``sentence`` is shown to the user."""

    qrc_path: str
    sentence: str


@dataclass(frozen=True)
class PictureIndex:
    pictures: Tuple[QrcPicture, ...]
    issues: Tuple[QrcIssue, ...]
    by_path: Dict[str, QrcPicture]


def clear_picture_cache() -> None:
    _CACHE.clear()


def resource_locations(document: object) -> Tuple[str, ...]:
    """``<resources><include location=...>`` values, in file order."""
    ui = getattr(document, "ui", None)
    if ui is None:
        return ()
    found: List[str] = []
    for node in ui.children("resources"):
        location = getattr(node, "location", "")
        if isinstance(location, str) and location.strip():
            found.append(location.strip())
    return tuple(found)


def index_for_document(document: object, base_dir: str) -> PictureIndex:
    return load_pictures(resource_locations(document), base_dir)


def load_pictures(locations: Sequence[str], base_dir: str) -> PictureIndex:
    """Images in each ``.qrc``, plus a sentence for each file that will not parse.

    Listing does not stat every image. Callers ask ``is_missing`` for the ones
    they show.
    """
    pictures: List[QrcPicture] = []
    issues: List[QrcIssue] = []
    by_path: Dict[str, QrcPicture] = {}
    for location in locations:
        qrc_path = location if os.path.isabs(location) else os.path.normpath(os.path.join(base_dir, location))
        parsed = _cached_document(qrc_path)
        if isinstance(parsed, QrcIssue):
            issues.append(parsed)
            continue
        folder = os.path.dirname(qrc_path)
        name = os.path.basename(qrc_path)
        for entry in parsed.files:
            relative = (entry.path or "").replace("\\", "/").strip()
            if not relative or not _is_image(relative, os.path.join(folder, relative)):
                continue
            disk = os.path.normpath(os.path.join(folder, relative))
            alias = entry.alias.strip() if isinstance(entry.alias, str) and entry.alias.strip() else ""
            prefix = (entry.prefix or "").replace("\\", "/").strip().strip("/")
            resource = resource_path(prefix, alias, relative)
            shown = os.path.basename(alias or relative) or relative
            picture = QrcPicture(qrc_path, name, prefix, shown, resource, disk)
            pictures.append(picture)
            by_path.setdefault(resource, picture)
    pictures.sort(key=lambda item: (item.qrc_name.lower(), item.prefix.lower(), item.file_name.lower(), item.resource_path))
    return PictureIndex(tuple(pictures), tuple(issues), by_path)


def resource_path(prefix: str, alias: str, relative: str) -> str:
    """The ``:/`` path Qt publishes for one ``<file>``."""
    head = [part for part in prefix.replace("\\", "/").strip("/").split("/") if part]
    tail_source = alias if alias else relative
    tail = [part for part in tail_source.replace("\\", "/").strip("/").split("/") if part]
    parts = head + tail
    if not parts:
        return ":/"
    return ":/" + "/".join(parts)


def canon_resource(stored: str) -> str:
    if not stored.startswith(":/"):
        return stored
    parts = [part for part in stored[2:].split("/") if part]
    if not parts:
        return ":/"
    return ":/" + "/".join(parts)


def is_missing(picture: QrcPicture) -> bool:
    return not os.path.isfile(picture.disk_path)


def lookup_stored(stored: str, base_dir: str, index: PictureIndex) -> Tuple[str, bool]:
    """``(disk path, missing)`` for a pixmap path stored in a ``.ui``.

    A ``:/`` path that is not in the index is missing. A relative path is
    joined to the form directory. An empty path is not a picture.
    """
    if not stored:
        return "", False
    if stored.startswith(":/"):
        found = index.by_path.get(canon_resource(stored))
        if found is None or is_missing(found):
            return "", True
        return found.disk_path, False
    disk = stored if os.path.isabs(stored) else os.path.join(base_dir, stored) if base_dir else stored
    return disk, not os.path.isfile(disk)


def stored_for_file(absolute: str, form_dir: str, index: PictureIndex) -> str:
    """A resource path when the file is in a ``.qrc``, else a form-relative path."""
    target = os.path.normcase(os.path.abspath(absolute))
    for picture in index.pictures:
        if os.path.normcase(os.path.abspath(picture.disk_path)) == target and not is_missing(picture):
            return picture.resource_path
    relative = os.path.relpath(os.path.abspath(absolute), form_dir or os.getcwd())
    return relative.replace(os.sep, "/")


def label_text_hides_picture(node: object) -> bool:
    """True when the running app shows a QLabel's text instead of its pixmap.

    ``QLabel.setText`` and ``setPixmap`` each clear the other, so the one set
    last wins. Generated code sets properties in file order, except
    translatable strings, which ``retranslateUi`` sets at the end. An empty
    text never clears a pixmap (QLabel ignores setting the text it already has).
    """
    from app.features.form_builder.engine.ui4.values import ResourcePixmap, StringValue

    prop = getattr(node, "prop", None)
    if prop is None or getattr(node, "class_name", "") != "QLabel":
        return False
    text = prop("text")
    pixmap = prop("pixmap")
    if text is None or pixmap is None:
        return False
    if not isinstance(text.value, StringValue) or not text.value.text:
        return False
    if not isinstance(pixmap.value, ResourcePixmap) or not pixmap.value.path:
        return False
    if text.value.notr is not True:
        return True
    names = [entry.name for entry in node.properties()]  # type: ignore[attr-defined]
    return names.index("text") > names.index("pixmap")


def file_name_of(stored: str) -> str:
    text = stored.replace("\\", "/")
    if text.startswith(":/"):
        text = text[2:]
    name = text.rsplit("/", 1)[-1]
    return name or stored


def _cached_document(path: str) -> object:
    if not os.path.isfile(path):
        return QrcIssue(path, "Code Studio can't find %s." % os.path.basename(path))
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        return QrcIssue(path, "Code Studio can't read %s." % os.path.basename(path))
    key = (os.path.abspath(path), mtime)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        document = read_qrc(text)
    except (OSError, ValueError):
        issue = QrcIssue(path, "%s is not a valid resource file." % os.path.basename(path))
        _CACHE[key] = issue
        return issue
    _CACHE[key] = document
    return document


def _is_image(relative: str, disk_path: str) -> bool:
    if os.path.splitext(relative)[1].lower() in _EXTENSIONS:
        return True
    if not os.path.isfile(disk_path):
        return False
    return _header_is_image(disk_path)


def _header_is_image(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            head = handle.read(256)
    except OSError:
        return False
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if head.startswith(b"\xff\xd8\xff"):
        return True
    if head.startswith((b"GIF87a", b"GIF89a")):
        return True
    if head.startswith(b"BM"):
        return True
    if head.startswith(b"\x00\x00\x01\x00"):
        return True
    if len(head) >= 12 and head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return True
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return True
    if head.startswith((b"/* XPM */", b"! XPM2")):
        return True
    folded = head.lstrip().lower()
    return folded.startswith(b"<svg") or b"<svg" in folded
