"""Inspector writes: the shared services, and edit sessions.

A **session** is the time one row's field keeps keyboard focus, or one popover
stays open. Every write in a session is one undo step, named for the session.

Invariant (UX-PED-004). A session owns one merge token, unique for the session's
life. Each write runs inside ``CommandLog.transaction(label, merge_token=token,
merge_within_s=inf)``. The log folds the write into the top undo entry when that
entry carries the same token, so the session's writes form exactly one entry,
and the entry exists only once the session has written something. A session
that never writes leaves no entry. Two visits to one row use two tokens, so
they are two steps.

``revert()`` undoes the session's entry, when it is the top one, through the
public ``CommandLog.undo``. That restores the document bytes and the undo stack.
The entry then stays on the redo stack; ``CommandLog`` has no public way to drop
it, so the redo stack is not restored yet (strict xfail in
``tests/form_builder/qtside/test_inspector_session_undo.py``; the owner of
``engine/commands/log.py`` decides the fix).
"""


from __future__ import annotations

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Iterator, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.base import Command, CommandRejected
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.inspector.catalog import Catalog
from app.qt.QtWidgets import QLayout, QWidget

if TYPE_CHECKING:
    from app.features.form_builder.qtside.theme.chrome import FormChrome

#: A session's writes merge whatever the gap between them. Only the token ends a merge.
SESSION_WINDOW_S = math.inf

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
        self._seq = 0
        self._inline: Dict[str, "EditSession"] = {}
        self._chrome: Optional["FormChrome"] = None

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
        self._seq += 1
        return EditSession(self, "inspector-%d" % self._seq, label)

    def inline_session(self, row_key: str, label: str) -> "EditSession":
        """The session of a row's field while it has focus. Created on the first write."""
        session = self._inline.get(row_key)
        if session is None or session.closed:
            session = self.begin_session(label)
            self._inline[row_key] = session
        return session

    def end_inline_session(self, row_key: str) -> None:
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

    def top_entry_has_token(self, token: str) -> bool:
        entries = self._session.log.entries()
        return bool(entries) and entries[-1].merge_token == token

    def undo_top(self) -> bool:
        if self._depth:
            return False
        return self._session.log.undo()

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

    def __init__(self, services: Services, token: str, label: str) -> None:
        self._services = services
        self._token = token
        self._label = label
        self._closed = False

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
        return self._services.run_in(self, commands)

    def has_step(self) -> bool:
        """True when this session's step is the top undo entry."""
        return self._services.top_entry_has_token(self._token)

    def undo(self) -> bool:
        """Undo this session's step as an ordinary undo (its entry moves to redo)."""
        if not self.has_step():
            return False
        return self._services.undo_top()

    def revert(self) -> bool:
        """Undo this session's step and close the session. See the module docstring for the redo stack."""
        undone = self.undo()
        self.close()
        return undone

    def close(self) -> None:
        """No more writes. Idempotent."""
        self._closed = True
