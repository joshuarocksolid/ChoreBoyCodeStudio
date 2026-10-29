"""``.qrc`` files open in the resource editor, and forms watch their pictures (UX-RES-004, 005, 007).

``QrcTabProvider`` builds the resource editor tab. ``attach_picture_checks``
publishes FB031 and FB032 for one form session and keeps them current while the
form changes. ``FormTabProvider`` calls both; this module is the only place
that knows how.
"""

from __future__ import annotations

from typing import Callable, List

from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.engine.project.picture_checks import SOURCE, picture_diagnostics
from app.features.form_builder.engine.project.qrc_edit import QrcEditSource
from app.features.form_builder.engine.session import FormSession
from app.qt.QtCore import QEvent, QObject
from app.shell.tab_content_providers import ProviderDeclined, TabSurfaceRequest

QRC_SUFFIX = ".qrc"


def is_qrc(file_path: str) -> bool:
    return file_path.lower().endswith(QRC_SUFFIX)


class QrcTabProvider:
    """Creates the resource editor for a ``.qrc`` path. ``FormTabProvider`` delegates to it."""

    def create_surface(self, request: TabSurfaceRequest) -> object:
        from app.features.form_builder.qtside.resources.editor import QrcSurface

        try:
            source = QrcEditSource(request.initial_text, request.file_path, request.project_root or "")
        except Exception as exc:  # a parse failure opens XML, so this is a bug; fall back to text
            raise ProviderDeclined("This pictures file can't be opened as pictures.") from exc
        surface = QrcSurface(request, source, chrome_for)  # type: ignore[arg-type]
        _ShellUndo(surface)
        source.subscribe_saved(refresh_picture_checks)
        return surface


#: One refresh per open form session; a ``.qrc`` save asks them all (FB032 follows the file).
_REFRESHERS: List[Callable[[], None]] = []


def refresh_picture_checks() -> None:
    """Recompute FB031/FB032 for every open form. Called after a ``.qrc`` is saved in its tab."""
    for refresh in tuple(_REFRESHERS):
        refresh()


def attach_picture_drops(session: FormSession, project_root: str) -> Callable[[], None]:
    """Picture files dropped on this form's canvas (UX-RES-003). Returns a function that stops.

    The handler answers only for ``session``; a drop on another open form is
    left to that form's handler. The file work runs first, then the form part as
    one undo step whose toast carries the "Undo keeps the copied file" sentence.
    """
    from app.features.form_builder.engine.project.fs import ProjectOpError
    from app.features.form_builder.qtside.canvas.file_drops import register_file_drop
    from app.features.form_builder.qtside.resources import notices
    from app.features.form_builder.qtside.resources.drops import plan_file_drop

    holder: List[Callable[[], None]] = []

    def handle(owner: object, target_id: object, paths: object) -> object:
        if session.disposed:
            stop()
            return None
        if owner is not session:
            return None
        try:
            drop = plan_file_drop(session.document, session.path, project_root, target_id, paths)  # type: ignore[arg-type]
        except ProjectOpError as exc:
            return str(exc)
        notices.remember(drop.label, drop.notice)
        with session.log.transaction(drop.label) as txn:
            for command in drop.commands:
                txn.execute(command)
        return ""  # the toast says it

    def stop() -> None:
        while holder:
            holder.pop()()

    holder.append(register_file_drop(handle))  # type: ignore[arg-type]
    # Sessions have no dispose callback; drop the handlers of closed forms whenever a form opens.
    for other, other_stop in tuple(_DROP_STOPS):
        if other.disposed:
            other_stop()
            _DROP_STOPS.remove((other, other_stop))
    _DROP_STOPS.append((session, stop))
    return stop


_DROP_STOPS: List[tuple] = []


class _ShellUndo:
    """Edit > Undo and Redo follow the resource editor's own history while its tab is shown.

    The form surface drives the same two actions for a form tab; it clears them
    when it hides, and this takes them only while no form holds them, so the
    two never fight. The XML view keeps the editor's own undo, so the menu
    items are off there.
    """

    def __init__(self, surface: object) -> None:
        self._surface = surface
        self._filter = _ShowHideFilter(surface, self.bind, self.unbind)
        surface.installEventFilter(self._filter)  # type: ignore[attr-defined]
        surface.source.subscribe_changed(self.sync)  # type: ignore[attr-defined]
        surface.released_hook = self.release  # type: ignore[attr-defined]

    def release(self) -> None:
        """Before Qt deletes the surface: hand back the menu items and stop hearing its events."""
        self.unbind()
        self._surface.removeEventFilter(self._filter)  # type: ignore[attr-defined]

    def _window(self) -> object:
        return self._surface.window()  # type: ignore[attr-defined]

    def _actions(self) -> tuple:
        from app.features.form_builder.integration.surface import _shell_registry  # pyright: ignore[reportPrivateUsage]

        registry = _shell_registry(self._window())  # type: ignore[arg-type]
        if registry is None:
            return (None, None)
        return (
            registry.action("shell.action.edit.undo"),  # type: ignore[attr-defined]
            registry.action("shell.action.edit.redo"),  # type: ignore[attr-defined]
        )

    def bind(self) -> None:
        if self._surface.released:  # type: ignore[attr-defined]
            return
        window = self._window()
        undo, redo = self._actions()
        if undo is None or redo is None:
            return
        if not getattr(window, "_qrc_undo_wired", False):
            undo.triggered.connect(lambda _checked=False, host=window: _route(host, False))
            redo.triggered.connect(lambda _checked=False, host=window: _route(host, True))
            window._qrc_undo_wired = True  # type: ignore[attr-defined]
        window._qrc_undo_surface = self._surface  # type: ignore[attr-defined]
        self.sync()

    def unbind(self) -> None:
        window = self._window()
        if getattr(window, "_qrc_undo_surface", None) is not self._surface:
            return
        window._qrc_undo_surface = None  # type: ignore[attr-defined]
        if getattr(window, "_form_undo_surface", None) is None:
            self._set("Undo", False, "Redo", False)

    def sync(self) -> None:
        from app.features.form_builder.integration.chrome_text import undo_menu_text

        window = self._window()
        if getattr(window, "_qrc_undo_surface", None) is not self._surface:
            return
        if getattr(window, "_form_undo_surface", None) is not None:
            return
        if self._surface.released:  # type: ignore[attr-defined]
            return
        source = self._surface.source  # type: ignore[attr-defined]
        if source.mode != "pictures":
            self._set("Undo", False, "Redo", False)
            return
        self._set(
            undo_menu_text("Undo", source.undo_label()),
            source.can_undo(),
            undo_menu_text("Redo", source.redo_label()),
            source.can_redo(),
        )

    def _set(self, undo_text: str, undo_on: bool, redo_text: str, redo_on: bool) -> None:
        undo, redo = self._actions()
        if undo is not None:
            undo.setText(undo_text)
            undo.setEnabled(undo_on)
        if redo is not None:
            redo.setText(redo_text)
            redo.setEnabled(redo_on)


class _ShowHideFilter(QObject):
    def __init__(self, parent: object, on_show: Callable[[], None], on_hide: Callable[[], None]) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._on_show = on_show
        self._on_hide = on_hide

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802
        del watched
        kind = event.type()  # type: ignore[attr-defined]
        if kind == QEvent.Type.Show:
            self._on_show()
        elif kind == QEvent.Type.Hide:
            self._on_hide()
        return False


def _route(window: object, redo: bool) -> None:
    surface = getattr(window, "_qrc_undo_surface", None)
    if surface is None or getattr(window, "_form_undo_surface", None) is not None:
        return
    if not surface.isVisible():  # type: ignore[attr-defined]
        return
    if redo:
        surface.redo()  # type: ignore[attr-defined]
    else:
        surface.undo()  # type: ignore[attr-defined]


def attach_picture_checks(session: FormSession, project_root: str) -> Callable[[], None]:
    """Publish FB031/FB032 now and after each change to the form. Returns a function that stops.

    The rows are computed again only when something that can change them did:
    a property or the include list. An unchanged answer is not published, so
    the Problems panel does not repaint for a keystroke elsewhere.
    """
    from app.features.form_builder.engine.events import PRIORITY_DIAGNOSTICS

    state = {"last": ()}  # type: dict

    def refresh(_change: object = None) -> None:
        if session.disposed:
            return
        found = picture_diagnostics(session.document, session.path, project_root)
        if found == state["last"]:
            return
        state["last"] = found
        session.diagnostics.publish(SOURCE, found)

    def outside() -> None:
        if session.disposed:
            try:
                _REFRESHERS.remove(outside)
            except ValueError:
                pass
            return
        state["last"] = None
        refresh()

    refresh()
    subscription = session.log.subscribe(refresh, priority=PRIORITY_DIAGNOSTICS)
    _REFRESHERS.append(outside)

    def stop() -> None:
        subscription.close()
        try:
            _REFRESHERS.remove(outside)
        except ValueError:
            pass

    return stop




__all__ = ["QrcTabProvider", "attach_picture_checks", "attach_picture_drops", "is_qrc", "refresh_picture_checks"]
