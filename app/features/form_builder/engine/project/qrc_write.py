"""Deterministic ``.qrc`` writes and the copy rules for "Add picture" (UX-RES-002, UX-RES-004).

Qt-free. A ``.qrc`` is read into a ``QrcLayout`` (groups of entries, empty groups
kept) and written back as stable bytes: ``<!DOCTYPE RCC>``, two-space indent,
entries in the order held, ``\\n`` line ends, one final newline. Two writes of the
same layout are the same bytes. Comments and elements Qt's ``rcc`` does not read
are not kept (``QrcLayout.lossy`` says when a file had any).

What may be read or written. Writes go only to files inside the project root
(``inside_project``, which also refuses a symlink that leaves it). The one read
outside the project is a picture the owner chose, to copy it in. Every entry of
a ``.qrc`` is resolved from the ``.qrc``'s folder and is refused when it leaves
the project, so a hand-written ``../../etc/passwd`` entry is never read.

Files are written through a ``Journal``: when a later write fails, the earlier
ones are put back. A copied picture and the ``.qrc`` are not part of the form's
undo history; the caller says so on screen.
"""

from __future__ import annotations

import os
import xml.parsers.expat
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape, quoteattr

from app.features.form_builder.engine.project.fs import (
    Journal,
    OsFileSystem,
    ProjectOpError,
    inside_project,
    relative_posix,
)
from app.features.form_builder.engine.project.pictures import (
    clear_picture_cache,
    is_image_name,
    resource_path,
)

DEFAULT_QRC = "forms/resources.qrc"
PICTURES_FOLDER = "pictures"
DEFAULT_PREFIX = "/"
NOT_A_PICTURE = "Only pictures can go here."
#: A picture is compiled into the form's ``*_rc.py``; past this it is not a picture for a form.
MAX_PICTURE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class QrcEntry:
    """``<file alias="..">path</file>``. ``path`` is relative to the ``.qrc``'s folder, with ``/``."""

    path: str
    alias: Optional[str] = None


@dataclass(frozen=True)
class QrcGroup:
    """``<qresource prefix=".." lang="..">``. A group with no entries is kept."""

    prefix: str = DEFAULT_PREFIX
    lang: Optional[str] = None
    entries: Tuple[QrcEntry, ...] = ()


@dataclass(frozen=True)
class QrcLayout:
    groups: Tuple[QrcGroup, ...] = ()
    version: str = "1.0"
    #: True when the file held a comment or an element that a rewrite drops.
    lossy: bool = False

    def entry_count(self) -> int:
        return sum(len(group.entries) for group in self.groups)


@dataclass(frozen=True)
class AddOutcome:
    """What ``add_pictures`` did. Paths in ``copied`` and ``qrc_path`` are absolute."""

    qrc_path: str
    qrc_relative: str
    qrc_created: bool
    #: One ``:/`` path per source, in the order given.
    resource_paths: Tuple[str, ...]
    #: The file name each source got inside the project (``logo.png`` or ``logo_2.png``).
    file_names: Tuple[str, ...]
    copied: Tuple[str, ...]
    #: Project-relative paths of the files written by this call, ``.qrc`` first.
    written: Tuple[str, ...]
    #: The layout after the add. With ``write=False`` it is only in memory.
    layout: "QrcLayout" = QrcLayout()
    #: True when the rewrite dropped comments or parts ``rcc`` does not read.
    dropped_parts: bool = False


def new_layout() -> QrcLayout:
    return QrcLayout(groups=(QrcGroup(DEFAULT_PREFIX, None, ()),))


def parse_qrc(text: str) -> QrcLayout:
    """Read ``text`` into a layout. ``ValueError`` (a sentence) when it is not a resource file."""
    from app.features.form_builder.engine.codegen.resources import _without_plain_doctype  # pyright: ignore[reportPrivateUsage]

    body = _without_plain_doctype(text)
    parser = xml.parsers.expat.ParserCreate()
    parser.ordered_attributes = True
    state = {"depth": 0, "lossy": False, "version": "1.0", "root_seen": False}
    groups: List[QrcGroup] = []
    current: List[QrcEntry] = []
    head: List[object] = []  # [prefix, lang] of the open group
    file_alias: List[Optional[str]] = []
    file_text: List[str] = []

    def refuse(*_args: object) -> None:
        raise ValueError("This resource file uses a DOCTYPE or an entity, which the form builder refuses.")

    def start(name: str, attrs: List[str]) -> None:
        mapping = {attrs[i]: attrs[i + 1] for i in range(0, len(attrs), 2)}
        state["depth"] = int(state["depth"]) + 1
        depth = int(state["depth"])
        if depth == 1:
            if name != "RCC":
                raise ValueError("This resource file does not start with <RCC>.")
            state["root_seen"] = True
            state["version"] = mapping.get("version", "1.0")
        elif depth == 2 and name == "qresource":
            head[:] = [mapping.get("prefix", ""), mapping.get("lang")]
            current[:] = []
            if set(mapping) - {"prefix", "lang"}:
                state["lossy"] = True
        elif depth == 3 and name == "file" and head:
            file_alias[:] = [mapping.get("alias")]
            file_text[:] = []
            if set(mapping) - {"alias"}:
                state["lossy"] = True
        else:
            state["lossy"] = True

    def data(value: str) -> None:
        if file_alias:
            file_text.append(value)

    def end(name: str) -> None:
        depth = int(state["depth"])
        if depth == 3 and name == "file" and file_alias:
            path = "".join(file_text).strip().replace("\\", "/")
            current.append(QrcEntry(path, file_alias[0]))
            file_alias[:] = []
        elif depth == 2 and name == "qresource" and head:
            groups.append(QrcGroup(str(head[0]), head[1] if isinstance(head[1], str) else None, tuple(current)))
            head[:] = []
            current[:] = []
        state["depth"] = depth - 1

    def comment(_text: str) -> None:
        state["lossy"] = True

    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = data
    parser.CommentHandler = comment
    try:
        parser.Parse(body, True)
    except xml.parsers.expat.ExpatError as exc:
        raise ValueError("This resource file is not valid XML (%s)." % exc) from exc
    if not state["root_seen"]:
        raise ValueError("This resource file does not start with <RCC>.")
    return QrcLayout(tuple(groups), str(state["version"]), bool(state["lossy"]))


def render_qrc(layout: QrcLayout) -> str:
    """Stable text for ``layout``."""
    lines = ["<!DOCTYPE RCC>", "<RCC version=%s>" % quoteattr(layout.version)]
    for group in layout.groups:
        attrs = " prefix=%s" % quoteattr(group.prefix)
        if group.lang:
            attrs += " lang=%s" % quoteattr(group.lang)
        if not group.entries:
            lines.append("  <qresource%s/>" % attrs)
            continue
        lines.append("  <qresource%s>" % attrs)
        for entry in group.entries:
            alias = " alias=%s" % quoteattr(entry.alias) if entry.alias else ""
            lines.append("    <file%s>%s</file>" % (alias, escape(entry.path)))
        lines.append("  </qresource>")
    lines.append("</RCC>")
    return "\n".join(lines) + "\n"


def read_layout(path: str, fs: Optional[OsFileSystem] = None) -> QrcLayout:
    """The layout of the ``.qrc`` at ``path``. ``ProjectOpError`` with a sentence when it can't be read."""
    files = fs or OsFileSystem()
    name = os.path.basename(path)
    try:
        text = files.read_text(path)
    except (OSError, UnicodeError) as exc:
        raise ProjectOpError("Code Studio can't read %s." % name) from exc
    try:
        return parse_qrc(text)
    except ValueError as exc:
        raise ProjectOpError("%s is not a valid pictures file." % name) from exc


def write_layout(
    project_root: str,
    qrc_path: str,
    layout: QrcLayout,
    fs: Optional[OsFileSystem] = None,
) -> bool:
    """Write ``layout`` when its bytes differ from the file. True when the file changed."""
    files = fs or OsFileSystem()
    _check_inside(project_root, qrc_path)
    data = render_qrc(layout).encode("utf-8")
    if files.is_file(qrc_path) and files.read_bytes(qrc_path) == data:
        return False
    try:
        files.write_bytes(qrc_path, data)
    except OSError as exc:
        raise ProjectOpError("Code Studio couldn't write %s." % os.path.basename(qrc_path)) from exc
    clear_picture_cache()
    return True


def entry_disk_path(qrc_path: str, entry: QrcEntry, project_root: str) -> str:
    """The file an entry names, or ``""`` when it would leave the project."""
    target = os.path.normpath(os.path.join(os.path.dirname(qrc_path), *entry.path.split("/")))
    return target if inside_project(target, project_root) else ""


def default_qrc_path(project_root: str) -> str:
    return os.path.join(os.path.abspath(project_root), *DEFAULT_QRC.split("/"))


def include_location(form_path: str, qrc_path: str) -> str:
    """The ``<include location>`` a form saved at ``form_path`` uses for ``qrc_path``."""
    relative = os.path.relpath(os.path.abspath(qrc_path), os.path.dirname(os.path.abspath(form_path)))
    return relative.replace(os.sep, "/")


def add_pictures(
    project_root: str,
    qrc_path: str,
    sources: Sequence[str],
    fs: Optional[OsFileSystem] = None,
    *,
    prefix: str = DEFAULT_PREFIX,
    layout: Optional[QrcLayout] = None,
    write: bool = True,
) -> AddOutcome:
    """List ``sources`` in ``qrc_path``, creating the file when it is missing (UX-RES-002).

    A picture already inside the ``.qrc``'s folder is listed where it is. Any
    other is copied to ``{qrc folder}/pictures/{name}``; when that name holds a
    different file the copy is ``name_2.ext``, ``name_3.ext`` and so on, and when
    it holds the same bytes it is reused. A picture already listed is not listed
    twice. Raises ``ProjectOpError`` with a sentence, having written nothing.
    """
    files = fs or OsFileSystem()
    root = os.path.abspath(project_root)
    qrc = os.path.abspath(qrc_path)
    if not qrc.lower().endswith(".qrc"):
        raise ProjectOpError("That is not a pictures file.")
    _check_inside(root, qrc)
    if not sources:
        raise ProjectOpError("Choose a picture first.")
    existed = files.is_file(qrc)
    if layout is None:
        layout = read_layout(qrc, files) if existed else new_layout()
    original = layout
    folder = os.path.dirname(qrc)
    journal = Journal(files)
    pictures_dir = os.path.join(folder, PICTURES_FOLDER)
    made_dirs = [d for d in (folder, pictures_dir) if not files.is_dir(d)]
    copied: List[str] = []
    pending: Dict[str, bytes] = {}
    resource_paths: List[str] = []
    file_names: List[str] = []
    try:
        for source in sources:
            name = os.path.basename(source)
            if not is_image_name(name):
                raise ProjectOpError(NOT_A_PICTURE)
            relative, copy_to = _place(folder, root, source, files, pending)
            if copy_to is not None:
                data = _read_source(source, files)
                journal.put(copy_to, data)
                pending[copy_to] = data
                copied.append(copy_to)
            layout, resource = _list_entry(layout, prefix, relative)
            resource_paths.append(resource)
            file_names.append(os.path.basename(relative))
        if write and (not existed or layout != original):
            journal.put(qrc, render_qrc(layout).encode("utf-8"))
    except ProjectOpError:
        _undo(journal, made_dirs, files)
        raise
    except OSError as exc:
        _undo(journal, made_dirs, files)
        raise ProjectOpError("Code Studio couldn't write the picture into the project.") from exc
    clear_picture_cache()
    written = tuple(relative_posix(path, root) for path in [qrc] + copied if _changed(journal, path))
    return AddOutcome(
        qrc_path=qrc,
        qrc_relative=relative_posix(qrc, root),
        qrc_created=not existed,
        resource_paths=tuple(resource_paths),
        file_names=tuple(file_names),
        copied=tuple(copied),
        written=written,
        layout=layout,
        dropped_parts=bool(write and existed and original.lossy and _changed(journal, qrc)),
    )


def remove_entries(layout: QrcLayout, group_index: int, entry_indexes: Sequence[int]) -> QrcLayout:
    """``layout`` without the listed entries of one group. The files on disk are not touched."""
    groups = list(layout.groups)
    group = groups[group_index]
    drop = set(entry_indexes)
    groups[group_index] = replace(group, entries=tuple(e for i, e in enumerate(group.entries) if i not in drop))
    return replace(layout, groups=tuple(groups))


def set_alias(layout: QrcLayout, group_index: int, entry_index: int, alias: str) -> QrcLayout:
    """Set (or, with an empty string, clear) one entry's alias."""
    groups = list(layout.groups)
    group = groups[group_index]
    entries = list(group.entries)
    clean = alias.strip().strip("/")
    entries[entry_index] = replace(entries[entry_index], alias=clean or None)
    groups[group_index] = replace(group, entries=tuple(entries))
    return replace(layout, groups=tuple(groups))


def add_prefix(layout: QrcLayout, prefix: str) -> QrcLayout:
    """A new, empty group. A prefix that already exists is left as it is."""
    clean = normalize_prefix(prefix)
    if any(group.prefix == clean and not group.lang for group in layout.groups):
        return layout
    return replace(layout, groups=layout.groups + (QrcGroup(clean, None, ()),))


def normalize_prefix(prefix: str) -> str:
    parts = [part for part in prefix.replace("\\", "/").split("/") if part]
    return "/" + "/".join(parts)


def add_entries(layout: QrcLayout, group_index: int, paths: Sequence[str]) -> QrcLayout:
    groups = list(layout.groups)
    group = groups[group_index]
    have = {(entry.path, entry.alias) for entry in group.entries}
    fresh = tuple(QrcEntry(path) for path in paths if (path, None) not in have)
    groups[group_index] = replace(group, entries=group.entries + fresh)
    return replace(layout, groups=tuple(groups))


def resource_of(group: QrcGroup, entry: QrcEntry) -> str:
    return resource_path(group.prefix.strip("/"), entry.alias or "", entry.path)


def renamed_resources(before: QrcLayout, after: QrcLayout) -> Dict[str, str]:
    """``{old :/ path: new :/ path}`` for the pictures whose name changed between two layouts.

    An entry is the same picture when its group (prefix and language) and file
    path are the same and it is the only such entry on both sides. A rename
    counts only when the old path no longer names anything in ``after``, so a
    picture that is still reachable under its old name is left alone.
    """
    def keyed(layout: QrcLayout) -> Dict[Tuple[str, str, str], List[str]]:
        found: Dict[Tuple[str, str, str], List[str]] = {}
        for group in layout.groups:
            for entry in group.entries:
                key = (normalize_prefix(group.prefix), group.lang or "", entry.path)
                found.setdefault(key, []).append(resource_of(group, entry))
        return found

    old_keys = keyed(before)
    new_keys = keyed(after)
    still = {path for paths in new_keys.values() for path in paths}
    mapping: Dict[str, str] = {}
    for key, olds in old_keys.items():
        news = new_keys.get(key, [])
        if len(olds) != 1 or len(news) != 1:
            continue
        old, new = olds[0], news[0]
        if old != new and old not in still:
            mapping[old] = new
    return mapping


def _list_entry(layout: QrcLayout, prefix: str, relative: str) -> Tuple[QrcLayout, str]:
    wanted = normalize_prefix(prefix)
    groups = list(layout.groups)
    index = next((i for i, g in enumerate(groups) if normalize_prefix(g.prefix) == wanted and not g.lang), -1)
    if index < 0:
        groups.append(QrcGroup(wanted, None, ()))
        index = len(groups) - 1
    group = groups[index]
    found = next((e for e in group.entries if e.path == relative and not e.alias), None)
    if found is None:
        entry = QrcEntry(relative)
        groups[index] = replace(group, entries=group.entries + (entry,))
    else:
        entry = found
    return replace(layout, groups=tuple(groups)), resource_path(wanted.strip("/"), "", entry.path)


def _place(
    folder: str,
    root: str,
    source: str,
    files: OsFileSystem,
    pending: Dict[str, bytes],
) -> Tuple[str, Optional[str]]:
    """``(path listed in the .qrc, absolute path to copy to or None)``."""
    absolute = os.path.abspath(source)
    if _under(absolute, folder) and inside_project(absolute, root):
        return os.path.relpath(absolute, folder).replace(os.sep, "/"), None
    data = _read_source(source, files)
    name = os.path.basename(absolute)
    stem, ext = os.path.splitext(name)
    number = 1
    while True:
        candidate = name if number == 1 else "%s_%d%s" % (stem, number, ext)
        target = os.path.join(folder, PICTURES_FOLDER, candidate)
        if not inside_project(target, root):
            raise ProjectOpError("That picture would be written outside the project.")
        if target in pending:
            if pending[target] == data:
                return "%s/%s" % (PICTURES_FOLDER, candidate), None
            number += 1
            continue
        if _case_clash(target, candidate, files, pending):
            # ``Logo.png`` beside ``logo.png``: one file on macOS and Windows,
            # two on ChoreBoy. Never reuse or write either; take the next name.
            number += 1
            continue
        if not files.is_file(target):
            return "%s/%s" % (PICTURES_FOLDER, candidate), target
        try:
            if files.read_bytes(target) == data:
                return "%s/%s" % (PICTURES_FOLDER, candidate), None
        except OSError as exc:
            raise ProjectOpError("Code Studio can't read %s." % candidate) from exc
        number += 1


def _case_clash(target: str, candidate: str, files: OsFileSystem, pending: Dict[str, bytes]) -> bool:
    """True when the folder holds (or this call wrote) a name that differs from ``candidate`` only in case."""
    folder = os.path.dirname(target)
    folded = candidate.casefold()
    names = [os.path.basename(path) for path in pending if os.path.dirname(path) == folder]
    try:
        if files.is_dir(folder):
            names.extend(files.listdir(folder))
    except OSError:
        pass
    return any(name != candidate and name.casefold() == folded for name in names)


def _read_source(source: str, files: OsFileSystem) -> bytes:
    try:
        if os.path.getsize(source) > MAX_PICTURE_BYTES:
            raise ProjectOpError(
                "%s is larger than %d MB, too big to carry in a form's pictures."
                % (os.path.basename(source), MAX_PICTURE_BYTES // (1024 * 1024))
            )
    except OSError:
        pass
    try:
        return files.read_bytes(source)
    except OSError as exc:
        raise ProjectOpError("Code Studio can't read %s." % os.path.basename(source)) from exc


def _under(path: str, folder: str) -> bool:
    try:
        return os.path.commonpath((path, os.path.abspath(folder))) == os.path.abspath(folder)
    except ValueError:
        return False


def _check_inside(root: str, path: str) -> None:
    if not root or not inside_project(path, root):
        raise ProjectOpError("That pictures file is outside the project.")


def _undo(journal: Journal, made_dirs: Sequence[str], files: OsFileSystem) -> None:
    try:
        journal.rollback()
    except OSError:
        pass
    for directory in reversed(made_dirs):
        try:
            if files.is_dir(directory) and not files.listdir(directory):
                os.rmdir(directory)
        except OSError:
            pass


def _changed(journal: Journal, path: str) -> bool:
    return path in journal.originals


__all__ = [
    "AddOutcome",
    "DEFAULT_QRC",
    "NOT_A_PICTURE",
    "PICTURES_FOLDER",
    "QrcEntry",
    "QrcGroup",
    "QrcLayout",
    "add_entries",
    "add_pictures",
    "add_prefix",
    "default_qrc_path",
    "entry_disk_path",
    "include_location",
    "new_layout",
    "normalize_prefix",
    "parse_qrc",
    "read_layout",
    "remove_entries",
    "renamed_resources",
    "render_qrc",
    "resource_of",
    "set_alias",
    "write_layout",
]
