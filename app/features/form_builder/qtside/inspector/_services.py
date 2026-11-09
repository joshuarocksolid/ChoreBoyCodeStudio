"""Inspector writes: the shared services, and edit sessions.

A **session** is the time one row's field keeps keyboard focus, or one popover
stays open. Every write in a session is one undo step, named for the session.

Invariant (UX-PED-004). A session owns one merge token, unique for the process
(not per ``Services``). Each write runs inside ``CommandLog.transaction(label,
merge_token=token, merge_within_s=inf)``. The log folds the write into the top
undo entry when that entry carries the same token, so the session's writes form
one entry, and the entry exists only once the session has written something. A
session that never writes leaves no entry. Two visits to one row use two
tokens, so they are two steps. A save (``mark_saved``) inside a session makes
the log start a second entry for the same token; the session still reverts as a
whole, because it is reverted by token, not by "the top entry".

The session takes a ``Checkpoint`` of the log when it begins. ``revert()``
(Esc, Ctrl+Z in a popover) calls ``CommandLog.rollback(checkpoint, token)``:
every entry above the checkpoint is undone as one change set, the redo stack is
put back as it was (entries and tokens), and the save point is put back (or
cleared when a save happened inside). The result is the document bytes, the
undo stack, the redo stack and the dirty state of the moment the session began.
The log refuses when anything foreign landed (the stack below changed, an entry
above carries another token, something was redone). A session therefore
watches the log, and when any change set arrives that it did not make itself,
it calls its owner (on the next event-loop turn, so the owner's focus flush can
still write) to close and keep what was written.
"""


from __future__ import annotations

import itertools
import math
import weakref
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, Iterator, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.base import (
    Command,
    CommandOutcome,
    CommandRejected,
    ReentrantCommandError,
)
from app.features.form_builder.engine.commands.log import Checkpoint
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.inspector.catalog import Catalog
from app.qt.QtCore import QTimer
from app.qt.qt_compat import wrapper_is_valid
from app.qt.QtWidgets import QApplication, QLayout, QWidget

if TYPE_CHECKING:
    from app.features.form_builder.qtside.theme.chrome import FormChrome

#: A session's writes merge whatever the gap between them. Only the token ends a merge.
SESSION_WINDOW_S = math.inf
#: Listeners that close a popover run after the views have painted.
_WATCH_PRIORITY = 1000
#: Session tokens are unique for the process, so two Services (two form tabs) never share one.
_TOKENS = itertools.count(1)

@dataclass(frozen=True)
class Rejected:
    message: str
    code: Optional[str] = None

@dataclass(frozen=True)
class Dropped:
    pass


def rejection_text(result: Rejected) -> str:
    if result.code:
        return "%s %s" % (result.code, result.message)
    return result.message


class Services:
    def __init__(self, session: FormSession, catalog: Catalog, realizer: object = None) -> None:
        self._session = session
        self._catalog = catalog
        self._realizer = realizer
        self._depth = 0
        self._inline: Dict[str, "EditSession"] = {}
        self._inline_rows: Dict[str, "weakref.ReferenceType[QWidget]"] = {}
        self._chrome: Optional["FormChrome"] = None
        self._settle_queued = False
        # Open popovers' close callbacks, so dispose closes them (keep) while the log is alive.
        self._watchers: Dict[int, Callable[[], None]] = {}
        self._watch_seq = 0
        # One hook for every row (UX-PED-004): a row's session ends when focus
        # lands outside it. No new focus widget means the window deactivated
        # (ActiveWindowFocusReason). An open popup list (PopupFocusReason) does
        # not end it either. A selection change ends them all, so the same row
        # key on a new owner starts a new step. This is a signal, not an
        # application event filter: a filter runs for every event in the process.
        self._app: Optional[QApplication] = None
        app = QApplication.instance()
        if isinstance(app, QApplication):
            self._app = app
            app.focusChanged.connect(self._on_focus)
        self._stop_selection = session.selection.subscribe(lambda _change: self.end_inline_sessions())

    def dispose(self) -> None:
        for on_change in list(self._watchers.values()):
            on_change()
        self._watchers.clear()
        app = self._app
        if app is not None:
            try:
                app.focusChanged.disconnect(self._on_focus)
            except (RuntimeError, TypeError):
                pass
            self._app = None
        self._stop_selection()
        self.end_inline_sessions()

    def _on_focus(self, _old: object, new: object) -> None:
        if not self._inline or new is None or self._settle_queued:
            return
        if QApplication.activePopupWidget() is not None:
            return
        # Deferred: the field's own focus-out commit runs first, so it joins the session.
        self._settle_queued = True
        QTimer.singleShot(0, self._settle_inline)

    def _settle_inline(self) -> None:
        self._settle_queued = False
        if QApplication.activePopupWidget() is not None:
            return
        focus = QApplication.focusWidget()
        if focus is None:
            return
        for key in list(self._inline):
            ref = self._inline_rows.get(key)
            row = ref() if ref is not None else None
            if row is None or not wrapper_is_valid(row):
                self.end_inline_session(key)
            elif focus is not row and not row.isAncestorOf(focus):
                self.end_inline_session(key)

    def add_watcher(self, on_change: Callable[[], None]) -> int:
        self._watch_seq += 1
        self._watchers[self._watch_seq] = on_change
        return self._watch_seq

    def drop_watcher(self, key: int) -> None:
        self._watchers.pop(key, None)

    def end_inline_sessions(self) -> None:
        for key in list(self._inline):
            self.end_inline_session(key)

    @property
    def session(self) -> FormSession:
        return self._session

    @property
    def catalog(self) -> Catalog:
        return self._catalog

    @property
    def chrome(self) -> "FormChrome":
        if self._chrome is None:
            from app.features.form_builder.qtside.theme.chrome import default_chrome

            self._chrome = default_chrome()
        return self._chrome

    def set_chrome(self, chrome: "FormChrome") -> None:
        self._chrome = chrome

    def refused(self, node_id: NodeId, name: str) -> bool:
        """Whether the canvas widget did not take the saved value of ``name`` (UX-PED-009)."""
        finder = getattr(self._realizer, "refused", None)
        return finder is not None and finder(node_id, name) is not None

    def live(self, node_id: NodeId) -> Optional[QWidget]:
        realizer = self._realizer
        if realizer is None:
            return None
        widget = realizer.widget_for(node_id)
        if isinstance(widget, QWidget):
            return widget
        return None

    def layout(self, node_id: NodeId) -> Optional[QLayout]:
        realizer = self._realizer
        finder = getattr(realizer, "layout_for", None)
        if not callable(finder):
            return None
        found = finder(node_id)
        if isinstance(found, QLayout):
            return found
        return None

    @contextmanager
    def painting(self) -> Iterator[None]:
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1

    def begin_session(self, label: str) -> "EditSession":
        """A session not tied to a row's focus: a popover's. The caller closes it."""
        return EditSession(self, "inspector-%d" % next(_TOKENS), label, self._session.log.checkpoint())

    def inline_session(self, row_key: str, label: str, row: Optional[QWidget] = None) -> "EditSession":
        """The session of a row's field while it has focus. Created on the first write."""
        session = self._inline.get(row_key)
        if session is None or session.closed:
            session = self.begin_session(label)
            self._inline[row_key] = session
        if row is not None:
            self._inline_rows[row_key] = weakref.ref(row)
        return session

    def end_inline_session(self, row_key: str) -> None:
        self._inline_rows.pop(row_key, None)
        session = self._inline.pop(row_key, None)
        if session is not None:
            session.close()

    def run_in(self, session: "EditSession", commands: Sequence[Command]) -> Union[Tuple[object, ...], Rejected, Dropped]:
        if self._depth or session.closed:
            return Dropped()
        try:
            results = []
            with self._session.log.transaction(
                session.label,
                merge_token=session.token,
                merge_within_s=SESSION_WINDOW_S,
            ) as txn:
                for command in commands:
                    results.append(txn.execute(command))
            return tuple(results)
        except CommandRejected as exc:
            return Rejected(str(exc), exc.code)
        except ReentrantCommandError:
            # A close that runs inside a log listener cannot write; the write is dropped.
            return Dropped()

    def rollback(self, checkpoint: Checkpoint, token: str) -> bool:
        if self._depth:
            return False
        try:
            return self._session.log.rollback(checkpoint, token)
        except (CommandRejected, ReentrantCommandError):
            return False

    def execute(self, command: Command) -> Union[CommandOutcome, Rejected, Dropped]:
        if self._depth:
            return Dropped()
        try:
            return self._session.log.execute(command)
        except CommandRejected as exc:
            return Rejected(str(exc), exc.code)

    def execute_all(
        self, label: str, commands: Sequence[Command]
    ) -> Union[Tuple[object, ...], Rejected, Dropped]:
        if self._depth:
            return Dropped()
        try:
            results = []
            with self._session.log.transaction(label) as txn:
                for command in commands:
                    results.append(txn.execute(command))
            return tuple(results)
        except CommandRejected as exc:
            return Rejected(str(exc), exc.code)


class EditSession:
    """One session (see the module docstring). Editors reach it through ``EditorHost``."""

    def __init__(self, services: Services, token: str, label: str, checkpoint: Checkpoint) -> None:
        self._services = services
        self._token = token
        self._label = label
        self._checkpoint = checkpoint
        self._closed = False
        self._own = 0
        self._wrote = False

    @property
    def token(self) -> str:
        return self._token

    @property
    def label(self) -> str:
        return self._label

    @property
    def closed(self) -> bool:
        return self._closed

    def set_label(self, label: str) -> None:
        """The name of the step. It takes effect for the first write; a merged step keeps its first name."""
        self._label = label

    def run(self, commands: Sequence[Command]) -> Union[Tuple[object, ...], Rejected, Dropped]:
        """Run ``commands`` as part of this session's one undo step. Returns each command's result."""
        self._own += 1
        try:
            result = self._services.run_in(self, commands)
        finally:
            self._own -= 1
        if isinstance(result, tuple):
            self._wrote = True
        return result

    def watch(self, on_change: Callable[[], None]) -> Callable[[], None]:
        """Call ``on_change`` on a selection change or on any step this session did not make.

        That is a foreign write, an undo or redo, or a structural command. The
        owner then closes and keeps what the session wrote (rollback would be refused).
        """
        session = self._services.session

        def foreign(_change_set: object) -> None:
            if not self._own and not self._closed:
                # Deferred: a close flushes focus so a pending field commits into
                # the session, and a log listener cannot write.
                QTimer.singleShot(0, on_change)

        subscription = session.log.subscribe(foreign, priority=_WATCH_PRIORITY)
        stop_selection = session.selection.subscribe(lambda _change: on_change())
        key = self._services.add_watcher(on_change)

        def stop() -> None:
            subscription.close()
            stop_selection()
            self._services.drop_watcher(key)

        return stop

    def has_step(self) -> bool:
        """True when any undo entry above this session's checkpoint carries its token.

        A save splits the session into two entries. A foreign step on top used
        to hide both, because only the top entry was checked, and Esc then kept
        the writes. Rollback still refuses when a foreign token is in that range.
        """
        entries = self._services.session.log.entries_since(self._checkpoint.tip_token)
        if not entries:
            return False
        return any(entry.merge_token == self._token for entry in entries)

    def undo(self) -> bool:
        """Take back everything this session wrote, as one change set. See ``revert``.

        False when the session wrote nothing, or the log refused.
        """
        self._own += 1
        try:
            rolled = self._services.rollback(self._checkpoint, self._token)
        finally:
            self._own -= 1
        return rolled and self._wrote

    def revert(self) -> bool:
        """Roll the log back to the checkpoint taken when the session began, and close the session.

        Document bytes, undo stack, redo stack and dirty state are as they were.
        False when the log refused (something foreign landed).
        """
        undone = self.undo()
        self.close()
        return undone

    def close(self) -> None:
        """No more writes. Idempotent."""
        self._closed = True
