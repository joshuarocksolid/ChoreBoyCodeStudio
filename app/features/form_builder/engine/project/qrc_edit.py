"""The resource editor's document: a ``.qrc`` layout with undo, and the shell's content-source contract (UX-RES-004).

Qt-free. The tab shows ``layout``; the XML view shows ``current_text()``. A file
that has not been edited is served byte for byte, so opening a hand-written
``.qrc`` does not mark it dirty. After the first edit the text is
``render_qrc(layout)``: stable bytes, two-space indent, entries in the order shown.

Undo history is per tab and holds layouts, so one entry is one step with the
name from UX_SPEC 13.2.10 ("Add 3 pictures", "Remove logo.png", "Rename
logo.png", "New prefix /icons"). Files copied into the project are not part of
it.
"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Callable, Dict, List, Optional, Tuple

from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.engine.project.qrc_write import (
    QrcLayout,
    parse_qrc,
    renamed_resources,
    render_qrc,
)
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.pictures import PictureUse, picture_uses
from app.features.form_builder.engine.project.save import (
    WriteResult,
    forms_including,
    rewrite_resource_modules,
)
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui

_LIMIT = 100

#: Shown while the open file holds parts a change in Pictures drops (UX-RES-004).
LOSSY_NOTE = (
    "This file has comments or parts Code Studio doesn't read. A change in Pictures drops them; "
    "make it in XML to keep them."
)


class QrcEditSource:
    """One open ``.qrc``. The shell's ``TabContentSource`` plus the edit history."""

    def __init__(self, text: str, path: str, project_root: str) -> None:
        self._path = path
        self._root = project_root
        self._saved = text
        self._error = ""
        self._layout = QrcLayout()
        self._verbatim: Optional[str] = text
        self._verbatim_layout: Optional[QrcLayout] = None
        try:
            self._layout = parse_qrc(text)
            self._verbatim_layout = self._layout
        except ValueError as exc:
            self._error = str(exc)
            self._verbatim_layout = None
        self._mode = "pictures" if not self._error else "xml"
        self._typed = text
        self._undo: List[Tuple[str, QrcLayout]] = []
        self._redo: List[Tuple[str, QrcLayout]] = []
        self._listeners: List[Callable[[], None]] = []
        self._saved_listeners: List[Callable[[], None]] = []
        self._revision = 0
        self._notice = ""
        self._info = ""
        self._disk_layout: Optional[QrcLayout] = self._verbatim_layout

    @property
    def path(self) -> str:
        return self._path

    @property
    def project_root(self) -> str:
        return self._root

    @property
    def layout(self) -> QrcLayout:
        return self._layout

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def error(self) -> str:
        """Why the file can't be shown as pictures, or ``""``."""
        return self._error

    @property
    def notice(self) -> str:
        """A problem from the last save, or ``""``."""
        return self._notice

    @property
    def info(self) -> str:
        """What the last save also did (forms it updated), or ``""``."""
        return self._info

    @property
    def lossy_note(self) -> str:
        """``LOSSY_NOTE`` while the file on disk holds parts a Pictures edit would drop."""
        disk = self._disk_layout
        return LOSSY_NOTE if disk is not None and disk.lossy else ""

    def set_path(self, path: str) -> None:
        """The file was saved under another name."""
        self._path = path

    def current_text(self) -> str:
        if self._mode == "xml":
            return self._typed
        if self._verbatim is not None and self._verbatim_layout == self._layout:
            return self._verbatim
        return render_qrc(self._layout)

    def is_dirty(self) -> bool:
        return self.current_text() != self._saved

    def mark_saved(self, saved_text: str) -> None:
        self._saved = saved_text
        self._notify()

    def revision(self) -> int:
        return self._revision

    def subscribe_changed(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def stop() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return stop

    def subscribe_saved(self, listener: Callable[[], None]) -> None:
        """Called after each save, once the forms' modules are written."""
        self._saved_listeners.append(listener)

    def apply(self, label: str, layout: QrcLayout) -> None:
        """One undo step named ``label``. Nothing happens when the layout is the same."""
        if layout == self._layout:
            return
        self._undo.append((label, self._layout))
        del self._undo[: max(0, len(self._undo) - _LIMIT)]
        self._redo.clear()
        self._layout = layout
        self._changed()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo_label(self) -> Optional[str]:
        return self._undo[-1][0] if self._undo else None

    def redo_label(self) -> Optional[str]:
        return self._redo[-1][0] if self._redo else None

    def undo(self) -> bool:
        if not self._undo:
            return False
        label, before = self._undo.pop()
        self._redo.append((label, self._layout))
        self._layout = before
        self._changed()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        label, after = self._redo.pop()
        self._undo.append((label, self._layout))
        self._layout = after
        self._changed()
        return True

    def enter_xml(self) -> str:
        """Switch to the XML view; returns the text it starts from."""
        self._typed = self.current_text()
        self._mode = "xml"
        self._notify()
        return self._typed

    def xml_changed(self, text: str) -> None:
        if self._mode != "xml" or text == self._typed:
            return
        self._typed = text
        self._changed()

    def leave_xml(self) -> Optional[str]:
        """Back to Pictures. ``None`` when it worked, else the sentence for the banner (XML stays)."""
        if self._mode != "xml":
            return None
        try:
            parsed = parse_qrc(self._typed)
        except ValueError as exc:
            return str(exc)
        if parsed != self._layout:
            self._undo.append(("Edit XML", self._layout))
            self._redo.clear()
            self._layout = parsed
        self._verbatim = self._typed
        self._verbatim_layout = parsed
        self._error = ""
        self._mode = "pictures"
        self._changed()
        return None

    def restore_text(self, text: str) -> None:
        """Draft restore, history restore and external reload: the history starts again."""
        self._undo.clear()
        self._redo.clear()
        self._verbatim = text
        self._typed = text
        try:
            self._layout = parse_qrc(text)
            self._verbatim_layout = self._layout
            self._error = ""
        except ValueError as exc:
            self._error = str(exc)
            self._verbatim_layout = None
            self._mode = "xml"
        self._disk_layout = self._verbatim_layout
        self._changed()

    def after_save(self) -> None:
        """Step after the shell wrote the file: refresh the ``*_rc.py`` of every form that includes it."""
        self._notice = ""
        self._info = ""
        try:
            saved = parse_qrc(self._saved)
        except ValueError:
            saved = None
        before, self._disk_layout = self._disk_layout, saved
        if not self._root:
            return
        renamed = renamed_resources(before, saved) if before is not None and saved is not None else {}
        if renamed:
            try:
                updated = rename_picture_uses(self._root, self._path, renamed, OsFileSystem())
            except (OSError, UnicodeError, ProjectOpError):
                updated = ()
                self._notice = "The pictures file was saved, but the forms using the renamed picture were not updated."
            if updated:
                noun = "form" if len(updated) == 1 else "forms"
                self._info = "Updated %d %s to the new picture name." % (len(updated), noun)
        try:
            result = rewrite_resource_modules(self._root, self._path, OsFileSystem())
        except (OSError, ProjectOpError):
            self._notice = "The pictures file was saved, but a form's picture module could not be written."
            self._notify()
            return
        if not result.text_written and result.diagnostics:
            self._notice = result.diagnostics[0].message
        self._notify()
        for listener in tuple(self._saved_listeners):
            listener()

    def forms_using_file(self) -> Tuple[str, ...]:
        """Absolute paths of the project's forms that include this file."""
        if not self._root:
            return ()
        return forms_including(self._root, self._path, OsFileSystem())

    def _changed(self) -> None:
        self._revision += 1
        self._notify()

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()


def uses_of(
    project_root: str,
    qrc_path: str,
    resource_paths: Tuple[str, ...],
    fs: Optional[OsFileSystem] = None,
) -> Tuple[Tuple[str, PictureUse], ...]:
    """``(form path, use)`` for each picture or icon in the project's forms that shows one of ``resource_paths``."""
    files = fs if fs is not None else OsFileSystem()
    wanted = set(resource_paths)
    found: List[Tuple[str, PictureUse]] = []
    for ui_path in forms_including(project_root, qrc_path, files):
        try:
            document = read_ui(files.read_text(ui_path), allocator=IdAllocator()).document
        except (OSError, UnicodeError, UiReadError):
            continue
        for use in picture_uses(document):
            if use.path in wanted:
                found.append((ui_path, use))
    return tuple(found)


def rename_picture_uses(
    project_root: str,
    qrc_path: str,
    renamed: Dict[str, str],
    fs: Optional[OsFileSystem] = None,
) -> Tuple[str, ...]:
    """Point every picture and icon in the forms that include ``qrc_path`` at its new name.

    ``renamed`` maps old ``:/`` paths to new ones (``renamed_resources``). Each
    form is written whole (``.ui`` and its Python), so a run shows the picture.
    Returns the forms written. A form open in a tab sees the file change on disk
    as any outside change. Saving the ``.qrc`` again after Undo maps the names
    back the same way.
    """
    from app.features.form_builder.engine.commands.catalog import SetProperty
    from app.features.form_builder.engine.project.adoption import scope_for
    from app.features.form_builder.engine.project.packaging import save_form_now
    from app.features.form_builder.engine.project.picture_adopt import with_picture
    from app.features.form_builder.engine.session import FormSession
    from app.features.form_builder.engine.ui4.values import ResourcePixmap
    from app.features.form_builder.engine.ui4.writer import write_ui

    files = fs if fs is not None else OsFileSystem()
    root = os.path.abspath(project_root)
    written: List[str] = []
    for ui_path in forms_including(root, qrc_path, files):
        try:
            text = files.read_text(ui_path)
            session = FormSession.open(text, path=ui_path, scope=scope_for(ui_path, root, files))
        except (OSError, UnicodeError, UiReadError):
            continue
        try:
            uses = [use for use in picture_uses(session.document) if use.path in renamed]
            if not uses:
                continue
            with session.log.transaction("Rename picture") as txn:
                for use in uses:
                    entry = session.document.node(use.node_id).prop(use.property_name)  # type: ignore[attr-defined]
                    if entry is None:
                        continue
                    if use.state == "" and isinstance(entry.value, ResourcePixmap):
                        value = replace(entry.value, path=renamed[use.path])  # keeps Designer's resource attribute
                    else:
                        value = with_picture(entry.value, use.state, renamed[use.path])
                    txn.execute(SetProperty(use.node_id, use.property_name, value))  # type: ignore[arg-type]
            new_text = write_ui(session.document).text
        finally:
            session.dispose()
        if new_text == text:
            continue
        files.write_text(ui_path, new_text)
        save_form_now(root, ui_path, files)
        written.append(ui_path)
    return tuple(written)


def new_path_label(path: str, project_root: str) -> str:
    """The file as the tab names it: relative to the project when it is inside."""
    if project_root:
        try:
            relative = os.path.relpath(os.path.abspath(path), os.path.abspath(project_root))
        except ValueError:
            return os.path.basename(path)
        if not relative.startswith(".."):
            return relative.replace(os.sep, "/")
    return os.path.basename(path)


__all__ = ["LOSSY_NOTE", "QrcEditSource", "WriteResult", "new_path_label", "rename_picture_uses", "uses_of"]
