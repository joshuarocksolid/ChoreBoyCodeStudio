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
  tab the file is written atomically (temp file and ``os.replace``) keeping its
  mode bits, then reported as the editor's own write so no reload prompt
  follows. A file that does not exist yet is created (UX D9), also atomically.
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

import logging
import os
import secrets
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


class TextEditLike(Protocol):
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class BridgeEdit:
    """A plain edit: replace ``text[start:end]`` with ``text``. The inverse of an applied edit."""

    start: int
    end: int
    text: str


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
        if saved:
            self.notify_saved(path)
        return BridgeResult(True, "tab", saved=saved, inverse=BridgeEdit(start, start + len(text), current[start:end]))

    def _apply_on_disk(
        self, path: str, start: int, end: int, text: str, base_text: Optional[str]
    ) -> BridgeResult:
        existed = os.path.lexists(path)
        mode: Optional[int] = None
        current = ""
        if existed:
            if not os.path.isfile(path):
                return refused(UNREADABLE)
            try:
                current, encoding = _read_text(path)
            except _Refusal as why:
                return refused(str(why))
            mode = os.stat(path).st_mode & 0o7777
        else:
            encoding = "utf-8"
        if base_text is not None and base_text != current:
            return refused(CHANGED)
        if not 0 <= start <= end <= len(current):
            return refused(CHANGED)
        updated = current[:start] + text + current[end:]
        try:
            data = updated.encode(encoding)
            _write_atomic(path, data, mode)
        except (OSError, UnicodeError) as exc:
            logger.warning("code bridge could not write %s: %s", path, exc)
            return refused("Code Studio couldn't write that file: %s" % exc)
        note_written_files((path,))
        self.notify_saved(path)
        return BridgeResult(
            True, "disk", saved=True, created=not existed, inverse=BridgeEdit(start, start + len(text), current[start:end])
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


def _read_text(path: str) -> Tuple[str, str]:
    """``(text, encoding)`` of a file the bridge may edit; raises ``_Refusal`` with the sentence otherwise."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(_MAX_BYTES + 1)
    except OSError:
        raise _Refusal(UNREADABLE)
    if len(data) > _MAX_BYTES:
        raise _Refusal(TOO_BIG)
    if b"\0" in data:
        raise _Refusal(UNREADABLE)
    try:
        encoding, _lines = tokenize.detect_encoding(iter(data.splitlines(True)).__next__)
        return data.decode(encoding), encoding
    except (SyntaxError, UnicodeError, LookupError, StopIteration):
        raise _Refusal(UNREADABLE)


def _write_atomic(path: str, data: bytes, mode: Optional[int]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    temp = os.path.join(directory, ".cbcs_code_%s.tmp" % secrets.token_hex(6))
    try:
        with open(temp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
    except Exception:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise


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
        workflow = getattr(self._window, "_save_workflow", None)
        save = getattr(workflow, "save_tab", None)
        if not callable(save):
            return False
        return bool(save(path, show_style_warnings=False, apply_transforms=False))

    def show(self, path: str, line: int, select: Optional[Tuple[int, int]]) -> bool:
        workflow = getattr(self._window, "_editor_tab_workflow", None)
        opener = getattr(workflow, "open_file_at_line", None)
        if not callable(opener):
            return False
        opener(path, line)
        widget = self._widget(path)
        if widget is None:
            return False
        if select is not None:
            from app.qt.QtGui import QTextCursor

            block = widget.document().findBlockByNumber(line - 1)
            if block.isValid():
                cursor = QTextCursor(widget.document())
                cursor.setPosition(block.position() + select[0])
                cursor.setPosition(block.position() + select[1], QTextCursor.MoveMode.KeepAnchor)
                widget.setTextCursor(cursor)
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
