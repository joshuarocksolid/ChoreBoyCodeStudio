
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional, Sequence, Tuple, Union

from app.features.form_builder.engine.commands.base import Command, CommandOutcome, CommandRejected
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.inspector.catalog import Catalog
from app.qt.QtWidgets import QLayout, QWidget

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
        self._token_key = ""
        self._token = ""
        self._seq = 0

    @property
    def session(self) -> FormSession:
        return self._session

    @property
    def catalog(self) -> Catalog:
        return self._catalog

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

    def token(self, row_key: str) -> str:
        if row_key != self._token_key or not self._token:
            self._seq += 1
            self._token_key = row_key
            self._token = "inspector-%d" % self._seq
        return self._token

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
