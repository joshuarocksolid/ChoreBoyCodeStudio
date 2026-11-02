"""FormSession: everything one open form owns (CONTRACTS.md section 3.7).

One session per editor tab. Two tabs never share a session, a document, a
command log or a selection. The clipboard is the only cross-form channel, and
it carries XML text.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from app.features.form_builder.engine.commands.log import (
    DEFAULT_UNDO_LIMIT,
    CommandLog,
    SelectionSnapshot,
)
from app.features.form_builder.engine.diagnostics import DiagnosticsStore, FormDiagnostic
from app.features.form_builder.engine.events import (
    PRIORITY_DIAGNOSTICS,
    PRIORITY_MODEL_CACHES,
    PRIORITY_SELECTION,
    PRIORITY_SELECTION_NOTIFY,
    ChangeSet,
    FieldChanged,
)
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.logic.codec import marker_read_only
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.ref_index import RefIndex
from app.features.form_builder.engine.query.connections import missing_connection_diagnostics
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
        undo_limit: int = DEFAULT_UNDO_LIMIT,
    ) -> None:
        self._path = path
        self._scope = scope
        self._document = document
        self._allocator = allocator
        self._diagnostics = diagnostics
        self._serializer = serializer
        self._selection = SelectionModel(document)
        self._disposed = False
        self._refs = RefIndex()
        self._refs.rebuild(document)
        self._base_methods: FrozenSet[str] = frozenset()
        self._log = CommandLog(
            document,
            allocator,
            selection_provider=self._selection_snapshot,
            undo_limit=undo_limit,
        )
        self._connection_rows = missing_connection_diagnostics(document)
        self._subscriptions = [
            self._log.subscribe(self._on_refs, priority=PRIORITY_MODEL_CACHES),
            self._log.subscribe(self._on_selection, priority=PRIORITY_SELECTION),
            self._log.subscribe(self._on_selection_notify, priority=PRIORITY_SELECTION_NOTIFY),
            self._log.subscribe(self._on_replaced, priority=PRIORITY_DIAGNOSTICS),
        ]

    @classmethod
    def open(cls, text: str, *, path: str, scope: FormScope, undo_limit: int = DEFAULT_UNDO_LIMIT) -> "FormSession":
        """Read ``text``. ``UiReadError`` propagates to the caller."""
        allocator = IdAllocator()
        result = read_ui(text, allocator=allocator, source_path=path)
        diagnostics = DiagnosticsStore()
        diagnostics.publish("reader", result.diagnostics)
        diagnostics.publish("connections", missing_connection_diagnostics(result.document))
        session = cls(path, scope, result.document, allocator, diagnostics, SerializationCache(), undo_limit)
        session._publish_behavior()
        return session

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
    def refs(self) -> RefIndex:
        self._live()
        return self._refs

    @property
    def base_methods(self) -> FrozenSet[str]:
        self._live()
        return self._base_methods

    def set_base_methods(self, methods: FrozenSet[str]) -> None:
        """Window method names for ``Rename``. Not a document edit."""
        self._live()
        self._base_methods = frozenset(methods)
        self._log.set_base_methods(self._base_methods)

    @property
    def allocator(self) -> IdAllocator:
        self._live()
        return self._allocator

    def text(self) -> str:
        """Lazily serialized XML for the current document."""
        self._live()
        return self._serializer.text(self._document)

    def logic_read_only(self) -> bool:
        """True when ``cbcsLogic`` is newer than this build understands, or can't be read (FB402)."""
        self._live()
        return marker_read_only(self._document.root.prop("cbcsLogic"))

    def set_path(self, new_path: str, scope: Optional[FormScope] = None) -> None:
        """Rename or move the file. The document is unchanged."""
        self._live()
        self._path = new_path
        if scope is not None:
            self._scope = scope

    @property
    def disposed(self) -> bool:
        """True after ``dispose``. Reading this does not raise."""
        return self._disposed

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

    def _on_refs(self, changeset: ChangeSet) -> None:
        self._refs.apply(self._document, changeset)

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
        """A replaced document has new ids. Read it again so reader rows point at live nodes.

        FB014 is scanned when names or connections change, including undo and redo.
        """
        if changeset.replaced:
            text = self._serializer.text(self._document)
            self._diagnostics.publish("reader", live_reader_diagnostics(self._document, text))
        if _behavior_scan_needed(changeset):
            self._publish_behavior(changeset)
        if not _connection_scan_needed(changeset):
            return
        found = missing_connection_diagnostics(self._document)
        if found != self._connection_rows:
            self._connection_rows = found
            self._diagnostics.publish("connections", found)

    def _publish_behavior(self, changeset: Optional[ChangeSet] = None) -> None:
        """Logic and event rows. A step edit republishes only the senders it edited.

        A formula commit republishes logic for the widgets it edited. Event rows
        stay as they are: the step lists did not change.
        """
        from app.features.form_builder.engine.logic.events import take_event_narrow

        narrow = take_event_narrow(self._document)
        if narrow:
            self._publish_behavior_for(narrow)
            return
        nodes = _formula_nodes(self._document, changeset)
        if nodes is not None:
            self._publish_formula(nodes)
            return
        from app.features.form_builder.engine.diagnostic_codes.fb406 import name_diagnostics
        from app.features.form_builder.engine.diagnostic_codes.fb40x_events import event_diagnostics
        from app.features.form_builder.engine.diagnostic_codes.fb4xx_logic import logic_diagnostics

        self._diagnostics.publish("logic.storage", logic_diagnostics(self._document))
        self._diagnostics.publish("events", event_diagnostics(self._document) + name_diagnostics(self._document))

    def _publish_behavior_for(self, pairs: Set[Tuple[str, str]]) -> None:
        from app.features.form_builder.engine.diagnostic_codes.fb406 import name_diagnostics
        from app.features.form_builder.engine.diagnostic_codes.fb40x_events import event_diagnostics
        from app.features.form_builder.engine.diagnostic_codes.fb4xx_logic import logic_diagnostics
        from app.features.form_builder.engine.logic.codec import read_marker
        from app.features.form_builder.engine.logic.storage import SUPPORTED_LOGIC_VERSION, signal_property

        doc = self._document
        fresh = event_diagnostics(doc, only=pairs) + name_diagnostics(doc, only=pairs)
        edited = {(sender, signal_property(signal)) for sender, signal in pairs}
        kept = tuple(
            row
            for row in self._diagnostics.rows("events")
            if (row.location.object_name, row.location.property) not in edited
        )
        self._diagnostics.publish("events", kept + fresh)
        marker = read_marker(doc.root.prop("cbcsLogic"))
        blocked = (not marker.readable) or (
            marker.version is not None and marker.version > SUPPORTED_LOGIC_VERSION
        )
        if blocked or doc.logic_property_count() == 0:
            self._diagnostics.publish("logic.storage", logic_diagnostics(doc))
            return
        nodes = []
        for sender, _signal in pairs:
            found = doc.by_name(sender)
            if found:
                nodes.append(doc.node(found[0]))
        fresh_logic = logic_diagnostics(doc, nodes=tuple(nodes))
        ids = {node.id for node in nodes}
        kept_logic = tuple(
            row
            for row in self._diagnostics.rows("logic.storage")
            if row.code != "FB402"
            and row.location.property != "cbcsLogic"
            and row.location.node_id not in ids
        )
        self._diagnostics.publish("logic.storage", kept_logic + fresh_logic)

    def _publish_formula(self, nodes: Tuple[object, ...]) -> None:
        from app.features.form_builder.engine.diagnostic_codes.fb4xx_logic import logic_diagnostics

        fresh = logic_diagnostics(self._document, nodes=nodes)
        ids = {getattr(node, "id") for node in nodes}
        current = self._diagnostics.rows("logic.storage")
        kept = tuple(row for row in current if row.location.node_id not in ids)
        merged = kept + fresh
        if merged == current:
            return
        self._diagnostics.publish("logic.storage", merged)

    def _on_selection_notify(self, changeset: ChangeSet) -> None:
        del changeset
        self._selection.release()

    def _selection_snapshot(self) -> SelectionSnapshot:
        state = self._selection.state
        return SelectionSnapshot(state.ids, state.current)

    def _live(self) -> None:
        if self._disposed:
            raise RuntimeError("session is disposed")


_CONNECTION_FIELDS = frozenset({"sender", "signal", "receiver", "slot"})


def _formula_nodes(doc: UiDocument, changeset: Optional[ChangeSet]) -> Optional[Tuple[object, ...]]:
    """Widgets a formula commit edited, or None when the form must be rescanned.

    Event lists, names, and structure still take the full scan. A formula
    property does not change them.
    """
    from app.features.form_builder.engine.logic.storage import FORMULA_KEYS, JSON_KEYS, is_signal_property

    if changeset is None:
        return None
    if changeset.replaced or changeset.added or changeset.removed or changeset.renamed:
        return None
    if any(
        isinstance(change, FieldChanged) and change.field in _CONNECTION_FIELDS
        for change in changeset.changes
    ):
        return None
    if not changeset.property_dirty:
        return None
    allowed = set(FORMULA_KEYS) | set(JSON_KEYS)
    nodes = []
    seen = set()
    for owner, _kind, name in changeset.property_dirty:
        if is_signal_property(name) or name not in allowed:
            return None
        if owner in seen or not doc.contains(owner):
            continue
        seen.add(owner)
        nodes.append(doc.node(owner))
    if not nodes:
        return None
    return tuple(nodes)


def _behavior_scan_needed(changeset: ChangeSet) -> bool:
    """True for a cbcs* property, a connection field, or an add, remove or rename.

    A replaced document is included so undo republishes. Other property edits do not.
    """
    if changeset.replaced or changeset.added or changeset.removed or changeset.renamed:
        return True
    if any(name.startswith("cbcs") for _owner, _kind, name in changeset.property_dirty):
        return True
    return any(
        isinstance(change, FieldChanged) and change.field in _CONNECTION_FIELDS
        for change in changeset.changes
    )


def _connection_scan_needed(changeset: ChangeSet) -> bool:
    """True when a name or a connection may have changed."""
    if changeset.replaced or changeset.renamed or changeset.added or changeset.removed:
        return True
    return any(
        isinstance(change, FieldChanged) and change.field in _CONNECTION_FIELDS
        for change in changeset.changes
    )


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
