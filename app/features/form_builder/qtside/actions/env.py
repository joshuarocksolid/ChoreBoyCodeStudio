"""The ``Env`` a menu editor runs in: a form session plus the surface's voices."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator, List, Optional, Sequence

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.document import UiDocument


class SessionEnv:
    def __init__(
        self,
        session: FormSession,
        say: Optional[Callable[[str], None]] = None,
        toast: Optional[Callable[[str], None]] = None,
        confirm: Optional[Callable[[str, str], bool]] = None,
    ) -> None:
        self._session = session
        self._say = say or (lambda sentence: None)
        self._toast = toast or (lambda sentence: None)
        self._confirm = confirm or (lambda sentence, ok: True)
        self._tx: List[Any] = []

    @property
    def document(self) -> UiDocument:
        return self._session.document

    def run(self, command: Any) -> Any:
        if self._tx:
            return self._tx[-1].execute(command)
        return self._session.log.execute(command).result

    @contextmanager
    def group(self, label: str) -> Iterator[Any]:
        with self._session.log.transaction(label) as tx:
            self._tx.append(tx)
            try:
                yield tx
            finally:
                self._tx.pop()

    def select(self, ids: Sequence[NodeId]) -> None:
        self._session.selection.set(tuple(ids), source=SelectionSource.PROGRAM)

    def say(self, sentence: str) -> None:
        self._say(sentence)

    def toast(self, sentence: str) -> None:
        self._toast(sentence)

    def confirm(self, sentence: str, ok: str) -> bool:
        return self._confirm(sentence, ok)
