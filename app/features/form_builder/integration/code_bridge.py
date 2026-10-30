"""The code bridge: how the form builder edits and shows your code (CONTRACTS.md section 16.4, M6.0s).

One bridge per window. It is the only way the form builder touches a
``.py`` file:

* ``text_of(path)``: the text of the file's open tab (the buffer, saved or
  not), or ``None`` when no tab holds it. ``read_window`` takes this as its
  ``text`` so the checks see what the person sees.
* ``apply(path, edit)``: one edit. In an open tab it is **one edit of that
  tab's document**, so it is one step in the tab's own undo; a tab that had
  no unsaved changes is saved after the edit, a tab with unsaved changes keeps
  them unsaved (the person's unsaved work is never saved for them). With no
  tab the file is written atomically (temp file in the same directory, fsync,
  rename) keeping its mode bits and bytes outside the edit, then reported as the
  editor's own write so no reload prompt follows. A file that does not exist
  yet is created (UX D9), also atomically. Only UTF-8 (BOM kept) or ASCII files
  are edited. The write goes through a descriptor of the directory checked to
  be inside the project, never follows a symlink at the file name, and is
  refused when the file changed on disk between reading and the rename.
* ``open_at(path, line, select)``: show the file in a tab, reusing one.
* ``on_saved(listener)``: ``listener(path)`` runs after the bridge saved or wrote
  a file, and when the owner calls ``notify_saved(path)`` for a save the
  person made. The checks listen here.

It never imports, executes or compiles the code it edits, and it refuses any
path that is not inside the project (a symlink that leaves it counts as
outside). Edits are described by anything with ``start``, ``end`` and ``text``
(``TextEdit`` of ``window_template``, M6.2a): character offsets into the text
the plan was made from. ``base_text`` lets the caller refuse a stale plan.

The Qt side is behind ``CodePort`` so the engine-side callers and the tests
need no window. ``ShellPort`` is the real one.
"""

from __future__ import annotations

import codecs
import logging
import os
import secrets
import stat
import tokenize
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Protocol, Tuple

from app.features.form_builder.engine.project.fs import inside_project
from app.features.form_builder.engine.project.written_files import note_written_files

logger = logging.getLogger(__name__)

_MAX_BYTES = 1024 * 1024
OUTSIDE = "That file is outside the project, so Code Studio won't change it."
TOO_BIG = "That file is too large for Code Studio to change."
UNREADABLE = "That file can't be read as text, so Code Studio won't change it."
CHANGED = "That file changed since the plan was made."
NOT_UTF8 = "That file isn't UTF-8 text, so Code Studio won't change it."
WRITE_FAILED = "Code Studio couldn't write that file: %s"


class TextEditLike(Protocol):
    """Read-only so a frozen ``TextEdit`` satisfies it."""

    @property
    def start(self) -> int: ...

    @property
    def end(self) -> int: ...

    @property
    def text(self) -> str: ...


@dataclass(frozen=True)
class BridgeEdit:
    """A plain edit: replace ``text[start:end]`` with ``text``. The inverse of an applied edit."""

    start: int
    end: int
    text: str


def bridge_edit(edit: TextEditLike) -> BridgeEdit:
    """Copy a stub edit into a ``BridgeEdit``. ``opened_line`` stays in the undo memo."""
    return BridgeEdit(int(edit.start), int(edit.end), str(edit.text))


@dataclass(frozen=True)
class BridgeResult:
    """``mode`` is ``"tab"`` or ``"disk"`` (``""`` when refused). ``inverse`` undoes the edit exactly
    when nothing else changed the text in between. ``saved`` is True when the file is on disk now."""

    ok: bool
    mode: str = ""
    reason: str = ""
    saved: bool = False
    created: bool = False
    inverse: Optional[BridgeEdit] = None


def refused(reason: str) -> BridgeResult:
    return BridgeResult(False, reason=reason)


class CodePort(Protocol):
    """What the bridge needs from the window."""

    def open_text(self, path: str) -> Optional[str]:
        """The text of the open tab for ``path``, or None."""
        ...

    def replace_range(self, path: str, start: int, end: int, text: str) -> bool:
        """One edit of the open tab's document (character offsets). False if the tab is gone."""
        ...

    def is_dirty(self, path: str) -> bool:
        ...

    def save(self, path: str) -> bool:
        ...

    def show(self, path: str, line: int, select: Optional[Tuple[int, int]]) -> bool:
        ...


class CodeBridge:
    def __init__(self, project_root: str, port: CodePort) -> None:
        self._root = project_root
        self._port = port
        self._listeners: List[Callable[[str], None]] = []

    @property
    def project_root(self) -> str:
        return self._root

    # ------------------------------------------------------------------ reading

    def text_of(self, path: str) -> Optional[str]:
        if not self._allowed(path):
            return None
        return self._port.open_text(path)

    # ------------------------------------------------------------------ writing

    def apply(self, path: str, edit: TextEditLike, *, base_text: Optional[str] = None) -> BridgeResult:
        if not self._allowed(path):
            return refused(OUTSIDE)
        start, end, text = int(edit.start), int(edit.end), str(edit.text)
        open_text = self._port.open_text(path)
        if open_text is not None:
            return self._apply_in_tab(path, open_text, start, end, text, base_text)
        return self._apply_on_disk(path, start, end, text, base_text)

    def _apply_in_tab(
        self, path: str, current: str, start: int, end: int, text: str, base_text: Optional[str]
    ) -> BridgeResult:
        if base_text is not None and base_text != current:
            return refused(CHANGED)
        if not 0 <= start <= end <= len(current):
            return refused(CHANGED)
        was_dirty = self._port.is_dirty(path)
        if not self._port.replace_range(path, start, end, text):
            return refused(CHANGED)
        saved = False
        if not was_dirty:
            saved = bool(self._port.save(path))
            if not saved:
                undo_last = getattr(self._port, "undo_last_edit", None)
                undone = bool(undo_last(path)) if callable(undo_last) else False
                if not undone:
                    self._port.replace_range(path, start, start + len(text), current[start:end])
                mark = getattr(self._port, "mark_clean", None)
                if callable(mark):
                    mark(path)
                reason = getattr(self._port, "last_save_error", "") or "the file could not be saved"
                return refused(WRITE_FAILED % reason)
            self.notify_saved(path)
        return BridgeResult(True, "tab", saved=saved, inverse=BridgeEdit(start, start + len(text), current[start:end]))

    def _apply_on_disk(
        self, path: str, start: int, end: int, text: str, base_text: Optional[str]
    ) -> BridgeResult:
        # The file actually written: a symlink inside the project is followed to its
        # target (which must be inside too), so the link stays a link.
        target = _real_target(path, self._root)
        if target is None:
            return refused(OUTSIDE)
        directory, name = os.path.split(target)
        try:
            os.makedirs(directory, exist_ok=True)
            dir_fd = os.open(directory, _DIR_FLAGS)
        except OSError as exc:
            return refused(WRITE_FAILED % exc)
        try:
            # Everything below goes through ``dir_fd``: a directory swapped for a
            # symlink after the check above can't redirect the write.
            if not _dir_inside(dir_fd, self._root):
                return refused(OUTSIDE)
            try:
                found = _read_at(dir_fd, name)
                original = None if found is None else found[0]
                mode = None if found is None else found[1]
                current, encoding = ("", "utf-8") if original is None else _decode(original)
            except _Refusal as why:
                return refused(str(why))
            if base_text is not None and base_text != current:
                return refused(CHANGED)
            if not 0 <= start <= end <= len(current):
                return refused(CHANGED)
            updated = current[:start] + text + current[end:]
            try:
                data = updated.encode(encoding)
            except UnicodeError:
                return refused(UNREADABLE)
            try:
                _write_at(dir_fd, name, data, mode, original)
            except _Refusal as why:
                return refused(str(why))
            except OSError as exc:
                logger.warning("code bridge could not write %s: %s", path, exc)
                return refused(WRITE_FAILED % exc)
        finally:
            os.close(dir_fd)
        note_written_files((path,))
        self.notify_saved(path)
        return BridgeResult(
            True,
            "disk",
            saved=True,
            created=original is None,
            inverse=BridgeEdit(start, start + len(text), current[start:end]),
        )

    # ------------------------------------------------------------------ showing

    def open_at(self, path: str, line: int, select: Optional[Tuple[int, int]] = None) -> bool:
        if not self._allowed(path):
            return False
        return bool(self._port.show(path, max(1, int(line)), select))

    # ------------------------------------------------------------------ saved

    def on_saved(self, listener: Callable[[str], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def close() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                return

        return close

    def notify_saved(self, path: str) -> None:
        for listener in tuple(self._listeners):
            try:
                listener(path)
            except Exception:
                logger.exception("a saved listener failed")

    def _allowed(self, path: str) -> bool:
        return bool(path) and bool(self._root) and inside_project(path, self._root)


class _Refusal(Exception):
    pass


_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
_TEMP_FLAGS = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)
#: Encodings the bridge edits (UX-CODE-006: UTF-8 or ASCII text; a BOM is kept).
_ENCODINGS = ("utf-8", "utf-8-sig", "ascii")
_MAX_DEPTH = 256


def _real_target(path: str, root: str) -> Optional[str]:
    """The real path the bridge writes for ``path``, or None when it resolves outside ``root``."""
    real = os.path.realpath(path)
    root_real = os.path.realpath(root)
    try:
        inside = os.path.commonpath((real, root_real)) == root_real and real != root_real
    except ValueError:
        return None
    return real if inside else None


def _dir_inside(dir_fd: int, root: str) -> bool:
    """True when the directory open as ``dir_fd`` is ``root`` or under it.

    Walks the real parents of the open directory with ``..`` and compares
    device and inode with ``root``, so no path (and no letter case on macOS)
    is trusted after the directory was opened.
    """
    try:
        root_stat = os.stat(root)
    except OSError:
        return False
    current = os.dup(dir_fd)
    try:
        for _ in range(_MAX_DEPTH):
            here = os.fstat(current)
            if os.path.samestat(here, root_stat):
                return True
            parent = os.open("..", _DIR_FLAGS, dir_fd=current)
            os.close(current)
            current = parent
            if os.path.samestat(os.fstat(current), here):
                return False  # the file system root
        return False
    except OSError:
        return False
    finally:
        try:
            os.close(current)
        except OSError:
            pass


def _read_at(dir_fd: int, name: str) -> Optional[Tuple[bytes, int]]:
    """``(bytes, mode bits)`` of the regular file ``name`` in ``dir_fd``, None when there is none.

    Opened without following a symlink and non-blocking, then checked with
    ``fstat`` (M5.4's rules), so a link or FIFO swapped in is refused.
    """
    try:
        fd = os.open(name, _READ_FLAGS, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    except OSError:
        raise _Refusal(UNREADABLE)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise _Refusal(UNREADABLE)
        if info.st_size > _MAX_BYTES:
            raise _Refusal(TOO_BIG)
        chunks: List[bytes] = []
        size = 0
        while size <= _MAX_BYTES:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
    except OSError:
        raise _Refusal(UNREADABLE)
    finally:
        os.close(fd)
    if size > _MAX_BYTES:
        raise _Refusal(TOO_BIG)
    return b"".join(chunks), stat.S_IMODE(info.st_mode)


def _decode(data: bytes) -> Tuple[str, str]:
    """``(text, encoding)`` of bytes the bridge may edit; raises ``_Refusal`` otherwise.

    Only UTF-8 (with or without a BOM) and ASCII are edited: a file in any
    other encoding is refused rather than risk changing bytes it didn't mean to.
    """
    if b"\0" in data:
        raise _Refusal(UNREADABLE)
    try:
        encoding, _lines = tokenize.detect_encoding(iter(data.splitlines(True)).__next__)
        if codecs.lookup(encoding).name not in _ENCODINGS:
            raise _Refusal(NOT_UTF8)
        return data.decode(encoding), encoding
    except (SyntaxError, UnicodeError, LookupError, StopIteration):
        raise _Refusal(NOT_UTF8)


def _write_at(dir_fd: int, name: str, data: bytes, mode: Optional[int], original: Optional[bytes]) -> None:
    """Write ``name`` in ``dir_fd`` atomically: a temp file in the same directory, fsync, then rename.

    The mode bits of the old file are kept (a new file gets the umask's). Just
    before the rename the file is read again: when another program changed it
    (or created it) since it was read, nothing is replaced and ``CHANGED`` is raised.
    A new file is linked into place, so one made meanwhile is never overwritten.
    """
    temp = ".cbcs_code_%s.tmp" % secrets.token_hex(6)
    fd = os.open(temp, _TEMP_FLAGS, 0o600 if mode is not None else 0o666, dir_fd=dir_fd)
    try:
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view) :]
            if mode is not None:
                os.fchmod(fd, mode)
            os.fsync(fd)
        finally:
            os.close(fd)
        now = _read_at(dir_fd, name)
        if (None if now is None else now[0]) != original:
            raise _Refusal(CHANGED)
        if original is None and _link_new(dir_fd, temp, name):
            os.unlink(temp, dir_fd=dir_fd)
        else:
            os.rename(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException:
        try:
            os.unlink(temp, dir_fd=dir_fd)
        except OSError:
            pass
        raise
    try:
        os.fsync(dir_fd)
    except OSError:
        pass


def _link_new(dir_fd: int, temp: str, name: str) -> bool:
    """Hard-link ``temp`` as the new file ``name``. False when the file system has no hard links."""
    try:
        os.link(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd, follow_symlinks=False)
    except FileExistsError:
        raise _Refusal(CHANGED)
    except (NotImplementedError, OSError):
        return False
    return True


class ShellPort:
    """The real port: the shell's editor tabs, save workflow and file opener of ``window``."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def _widget(self, path: str) -> Any:
        controller = getattr(self._window, "_workspace_controller", None)
        finder = getattr(controller, "widget_for_path", None)
        return finder(path) if callable(finder) else None

    def open_text(self, path: str) -> Optional[str]:
        widget = self._widget(path)
        return None if widget is None else str(widget.toPlainText())

    def replace_range(self, path: str, start: int, end: int, text: str) -> bool:
        from app.qt.QtGui import QTextCursor

        widget = self._widget(path)
        if widget is None:
            return False
        document = widget.document()
        current = widget.toPlainText()
        # Qt counts UTF-16 code units; the plan counts characters.
        first = _utf16(current, start)
        last = _utf16(current, end)
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        cursor.setPosition(first)
        cursor.setPosition(last, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        cursor.endEditBlock()
        return True

    def is_dirty(self, path: str) -> bool:
        manager = getattr(self._window, "_editor_manager", None)
        tab = manager.get_tab(path) if manager is not None else None
        if tab is not None:
            return bool(tab.is_dirty)
        widget = self._widget(path)
        return bool(widget is not None and widget.document().isModified())

    def save(self, path: str) -> bool:
        self.last_save_error = ""
        workflow = getattr(self._window, "_save_workflow", None)
        save = getattr(workflow, "save_tab", None)
        if not callable(save):
            self.last_save_error = "the file could not be saved"
            return False
        decide = getattr(workflow, "_decide_stale_save", None)
        if callable(decide) and decide(path, prompt=False) == "abort":
            self.last_save_error = "the copy on disk changed"
            return False
        try:
            ok = bool(save(path, show_style_warnings=False, apply_transforms=False))
        except OSError as exc:
            self.last_save_error = str(exc)
            return False
        if not ok:
            if os.path.isfile(path) and not os.access(path, os.W_OK):
                self.last_save_error = "the file can't be written"
            else:
                self.last_save_error = "the copy on disk changed"
        return ok

    def undo_last_edit(self, path: str) -> bool:
        widget = self._widget(path)
        document = widget.document() if widget is not None else None
        undo = getattr(document, "undo", None)
        if not callable(undo):
            return False
        undo()
        return True

    def mark_clean(self, path: str) -> None:
        widget = self._widget(path)
        text = str(widget.toPlainText()) if widget is not None else ""
        if widget is not None:
            widget.document().setModified(False)
        manager = getattr(self._window, "_editor_manager", None)
        tab = manager.get_tab(path) if manager is not None else None
        if tab is not None:
            tab.mark_saved(saved_text=text)

    def show(self, path: str, line: int, select: Optional[Tuple[int, int]]) -> bool:
        workflow = getattr(self._window, "_editor_tab_workflow", None)
        opener = getattr(workflow, "open_file_at_line", None)
        if not callable(opener):
            return False
        opener(path, line)
        widget = self._widget(path)
        if widget is None:
            return False
        from app.qt.QtGui import QTextCursor

        block = widget.document().findBlockByNumber(max(0, line - 1))
        if block.isValid():
            cursor = QTextCursor(widget.document())
            start = block.position()
            if select is not None:
                cursor.setPosition(start + select[0])
                cursor.setPosition(start + select[1], QTextCursor.MoveMode.KeepAnchor)
            else:
                cursor.setPosition(start)
            widget.setTextCursor(cursor)
        widget.setFocus()
        _scroll_into_top_third(widget)
        return True


_ATTRIBUTE = "_form_builder_code_bridge"


def bridge_for(window: Any, project_root: str) -> CodeBridge:
    """The window's bridge for ``project_root``, made on first use. One per window, so every
    form tab shares its ``on_saved`` listeners; a different project root makes a new one."""
    found = getattr(window, _ATTRIBUTE, None)
    if isinstance(found, CodeBridge) and found.project_root == project_root:
        return found
    made = CodeBridge(project_root, ShellPort(window))
    try:
        setattr(window, _ATTRIBUTE, made)
    except (AttributeError, TypeError):
        pass
    return made


def _scroll_into_top_third(widget: Any) -> None:
    """Move the def toward the top third, only as far as the scroll range allows.

    A short file stays where it is. The document is never changed.
    """
    cursor_of = getattr(widget, "textCursor", None)
    geometry = getattr(widget, "blockBoundingGeometry", None)
    offset_of = getattr(widget, "contentOffset", None)
    bar = getattr(widget, "verticalScrollBar", None)
    if not callable(cursor_of) or not callable(geometry) or not callable(offset_of) or not callable(bar):
        return
    scroll = bar()
    view = getattr(widget, "viewport", None)
    if scroll is None or not callable(view):
        return
    block = cursor_of().block()
    seen = block
    for _ in range(6):
        previous = seen.previous()
        if not previous.isValid():
            break
        if previous.text().lstrip().startswith("def "):
            block = previous
            break
        seen = previous

    def place() -> None:
        bar_now = bar()
        if bar_now is None:
            return
        where = int(geometry(block).translated(offset_of()).top())
        third = int(view().height()) // 3
        delta = where - third
        if delta == 0:
            return
        bar_now.setValue(min(int(bar_now.maximum()), max(0, int(bar_now.value()) + delta)))

    place()
    from app.qt.QtCore import QTimer

    QTimer.singleShot(0, place)


def _utf16(text: str, offset: int) -> int:
    return len(text[:offset].encode("utf-16-le")) // 2


__all__ = [
    "BridgeEdit",
    "BridgeResult",
    "CodeBridge",
    "CodePort",
    "ShellPort",
    "TextEditLike",
    "bridge_for",
]
