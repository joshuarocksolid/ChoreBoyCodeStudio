"""FormSession: everything one open form owns (CONTRACTS.md section 3.7).

One session per editor tab. Two tabs never share a session, a document, a
command log or a selection. The clipboard is the only cross-form channel, and
it carries XML text.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.commands.log import CommandLog, SelectionSnapshot
from app.features.form_builder.engine.diagnostics import DiagnosticsStore, FormDiagnostic
from app.features.form_builder.engine.events import (
    PRIORITY_DIAGNOSTICS,
    PRIORITY_SELECTION,
    PRIORITY_SELECTION_NOTIFY,
    ChangeSet,
)
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.logic.storage import SUPPORTED_LOGIC_VERSION
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionModel, SelectionState
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.writer import SerializationCache


class FormSession:
    """Open with ``FormSession.open``. ``dispose`` closes the session's subscriptions."""

    def __init__(
        self,
        path: str,
        scope: FormScope,
        document: UiDocument,
        allocator: IdAllocator,
        diagnostics: DiagnosticsStore,
        serializer: SerializationCache,
    ) -> None:
        self._path = path
        self._scope = scope
        self._document = document
        self._allocator = allocator
        self._diagnostics = diagnostics
        self._serializer = serializer
        self._selection = SelectionModel(document)
        self._disposed = False
        self._log = CommandLog(
            document,
            allocator,
            selection_provider=self._selection_snapshot,
        )
        self._subscriptions = [
            self._log.subscribe(self._on_selection, priority=PRIORITY_SELECTION),
            self._log.subscribe(self._on_selection_notify, priority=PRIORITY_SELECTION_NOTIFY),
            self._log.subscribe(self._on_replaced, priority=PRIORITY_DIAGNOSTICS),
        ]

    @classmethod
    def open(cls, text: str, *, path: str, scope: FormScope) -> "FormSession":
        """Read ``text``. ``UiReadError`` propagates to the caller."""
        allocator = IdAllocator()
        result = read_ui(text, allocator=allocator, source_path=path)
        diagnostics = DiagnosticsStore()
        diagnostics.publish("reader", result.diagnostics)
        return cls(path, scope, result.document, allocator, diagnostics, SerializationCache())

    @property
    def path(self) -> str:
        self._live()
        return self._path

    @property
    def scope(self) -> FormScope:
        self._live()
        return self._scope

    @property
    def document(self) -> UiDocument:
        self._live()
        return self._document

    @property
    def log(self) -> CommandLog:
        self._live()
        return self._log

    @property
    def selection(self) -> SelectionModel:
        self._live()
        return self._selection

    @property
    def diagnostics(self) -> DiagnosticsStore:
        self._live()
        return self._diagnostics

    @property
    def serializer(self) -> SerializationCache:
        self._live()
        return self._serializer

    @property
    def allocator(self) -> IdAllocator:
        self._live()
        return self._allocator

    def text(self) -> str:
        """Lazily serialized XML for the current document."""
        self._live()
        return self._serializer.text(self._document)

    def logic_read_only(self) -> bool:
        """True when ``cbcsLogic`` is newer than this build understands (FB402)."""
        self._live()
        version = self._document.logic_version()
        return version is not None and version > SUPPORTED_LOGIC_VERSION

    def set_path(self, new_path: str, scope: Optional[FormScope] = None) -> None:
        """Rename or move the file. The document is unchanged."""
        self._live()
        self._path = new_path
        if scope is not None:
            self._scope = scope

    def dispose(self) -> None:
        """Close every log subscription and the selection listeners.

        Later calls raise ``RuntimeError``. The realizer's subscription lives
        on the log, so ``log.close`` drops it with the session's own listeners.
        """
        if self._disposed:
            return
        self._disposed = True
        for subscription in self._subscriptions:
            subscription.close()
        self._subscriptions = []
        self._log.close()
        self._selection.clear_listeners()

    def _on_selection(self, changeset: ChangeSet) -> None:
        snap = self._log.selection
        if changeset.origin == "do" and _pure_prune(self._selection.state, snap, changeset):
            self._selection.apply_changeset(changeset, None)
            return
        self._selection.apply_changeset(
            changeset,
            SelectionState(snap.ids, snap.current),
        )

    def _on_replaced(self, changeset: ChangeSet) -> None:
        """A replaced document has new ids. Read it again so reader rows point at live nodes."""
        if not changeset.replaced:
            return
        text = self._serializer.text(self._document)
        self._diagnostics.publish("reader", live_reader_diagnostics(self._document, text))

    def _on_selection_notify(self, changeset: ChangeSet) -> None:
        del changeset
        self._selection.release()

    def _selection_snapshot(self) -> SelectionSnapshot:
        state = self._selection.state
        return SelectionSnapshot(state.ids, state.current)

    def _live(self) -> None:
        if self._disposed:
            raise RuntimeError("session is disposed")


def live_reader_diagnostics(document: UiDocument, text: str) -> Tuple[FormDiagnostic, ...]:
    """Reader findings for ``text`` (the serialization of ``document``) keyed to its node ids.

    The fresh read has the same tree as ``document``, so the n-th node in
    pre-order is the same node. When the trees differ the object name is used.
    """
    try:
        result = read_ui(text, allocator=IdAllocator())
    except UiReadError:
        return ()
    fresh = [node.id for node in result.document.iter_preorder()]
    live = [node.id for node in document.iter_preorder()]
    same_shape = len(fresh) == len(live)
    position: Dict[NodeId, int] = {node_id: index for index, node_id in enumerate(fresh)}
    found: List[FormDiagnostic] = []
    for diagnostic in result.diagnostics:
        location = diagnostic.location
        node_id = location.node_id
        if node_id is not None:
            mapped: Optional[NodeId] = None
            if same_shape and node_id in position:
                mapped = live[position[node_id]]
            elif location.object_name:
                named = document.by_name(location.object_name)
                mapped = named[0] if named else None
            location = replace(location, node_id=mapped)
        found.append(replace(diagnostic, location=location))
    return tuple(found)


def _pure_prune(before: SelectionState, snap: SelectionSnapshot, changeset: ChangeSet) -> bool:
    """True when the log snapshot only dropped ids this ChangeSet removed.

    A command that called ``ctx.select`` produces a different id list, and that
    snapshot is restored as-is. A plain removal lets the selection model move
    ``current`` to the surviving ancestor.
    """
    kept: List[object] = [node_id for node_id in before.ids if node_id not in changeset.removed]
    if tuple(snap.ids) != tuple(kept):
        return False
    if before.current in changeset.removed:
        return snap.current is None
    return snap.current == before.current
