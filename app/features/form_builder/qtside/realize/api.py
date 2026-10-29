"""Realize: model to live widgets, kept in step by patches (CONTRACTS.md section 5)."""

from __future__ import annotations

import enum
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple, cast

from app.qt.QtCore import QObject, Qt, qRegisterResourceData, qUnregisterResourceData
from app.qt.QtWidgets import (
    QApplication,
    QBoxLayout,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLayout,
    QListWidget,
    QMenu,
    QMenuBar,
    QSpacerItem,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTabWidget,
    QToolBar,
    QToolBox,
    QTreeWidget,
    QWidget,
    QWizard,
)
from app.qt.qt_compat import delete_now, enum_value, wrapper_is_valid
from app.features.form_builder.engine.codegen.resources import compile_resource_tree, read_qrc
from app.features.form_builder.engine.events import (
    PRIORITY_REALIZE,
    ChangeSet,
    FieldChanged,
    NodeMoved,
    NodeRemoved,
)
from app.features.form_builder.engine.commands.live import LiveProp, PropKey
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.storage import is_logic_key, splitter_sizes
from app.features.form_builder.engine.project.pictures import label_text_hides_picture
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    CustomWidgetNode,
    LayoutItemNode,
    LayoutNode,
    Node,
    ResourceNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.spec import PropertyEntry
from app.features.form_builder.qtside.realize.props import (
    REFUSED_BY_QT,
    Refusals,
    apply_entry,
    norm_qt,
    ordered_layout_metrics,
    resolve_stored_picture,
    set_property_checked,
    text_of,
)
from app.features.form_builder.qtside.realize.slots import LayoutHints, _Mirror, collect_layout_hints
from app.features.form_builder.qtside.realize.tree import (
    CANVAS_OVERRIDES,
    NODE_ID_PROPERTY,
    _GEOMETRY_PROPS,
    _Structure,
    _grid_extent,
    _node_id,
    settle_page_index,
)
from app.features.form_builder.qtside.theme.runtime import isolate_widget

logger = logging.getLogger(__name__)

REBUILD_PROPERTIES: frozenset = frozenset()

_LAYOUT_FIELDS = frozenset(
    {
        "row",
        "column",
        "rowspan",
        "colspan",
        "alignment",
        "stretch",
        "rowstretch",
        "columnstretch",
        "rowminimumheight",
        "columnminimumwidth",
    }
)
_MARGIN_FAMILY = frozenset({"margin", "leftMargin", "topMargin", "rightMargin", "bottomMargin"})
_SPACING_FAMILY = frozenset({"spacing", "horizontalSpacing", "verticalSpacing"})
_LAYOUT_FAMILIES = _MARGIN_FAMILY | _SPACING_FAMILY
_FRESH: Dict[Tuple[str, bool], QWidget] = {}
_FRESH_HOST: Optional[QWidget] = None


@dataclass(frozen=True)
class PatchStats:
    """Per ChangeSet. ``fallback_rebuilds`` is 0 for the standard command set."""

    patched_properties: int
    reconciled_containers: int
    created_widgets: int
    destroyed_widgets: int
    fallback_rebuilds: int
    rebuilt_roots: Tuple[NodeId, ...]
    cpu_ms: float


class Realizer(_Structure):
    """One per FormSession. ``build`` once, then patch each ChangeSet."""

    def __init__(self, session: FormSession, *, own_resources: bool = True) -> None:
        self._session = session
        self._own_resources = own_resources
        self._widgets: Dict[NodeId, QWidget] = {}
        self._layouts: Dict[NodeId, QLayout] = {}
        self._actions: Dict[NodeId, object] = {}
        self._objects: Dict[NodeId, object] = {}
        self._spacers: Dict[NodeId, object] = {}
        self._pool: Dict[NodeId, object] = {}
        # Layout mirrors (slots.py): layout id -> (QLayout, entries), and the
        # layout each placed content id sits in.
        self._placed: Dict[NodeId, _Mirror] = {}
        self._slot_of: Dict[NodeId, NodeId] = {}
        self._spacer_ids: Dict[int, NodeId] = {}
        # Per patch: what each dirty layout must take out and place, the
        # layouts already filled, and grids whose row count may have shrunk.
        self._layout_hints: Dict[NodeId, LayoutHints] = {}
        self._filled: Set[NodeId] = set()
        self._grid_check: Set[NodeId] = set()
        # Form layouts with a cell two items claim. They always diff in full.
        self._crowded: Set[NodeId] = set()
        # Per patch: widgets obtained or created, the ones created, the ones a
        # taken form cell left loose, and the widgets whose geometry is re-applied.
        self._touched: Set[NodeId] = set()
        self._fresh: Set[NodeId] = set()
        self._unplaced: Set[NodeId] = set()
        self._geometry_targets: Set[NodeId] = set()
        # Lasting: widgets a layout places that store a rect (see _target_laid_out_rects).
        self._laid_out_rects: Set[NodeId] = set()
        # Pooled widgets whose children were never filled (a morph's new object).
        self._needs_fill: Set[NodeId] = set()
        self._mdi: Dict[NodeId, object] = {}
        self._retired_windows: List[QWidget] = []
        self._nursery_widget: Optional[QWidget] = None
        self._buddy_of: Dict[NodeId, str] = {}
        self._buddy_users: Dict[str, List[NodeId]] = {}
        self._pending_containers: set = set()
        self._morph_buddies: set = set()
        self._registered: List[object] = []
        self._problems: List[str] = []
        # (node id, property) -> why Qt did not take the value (UX-PED-009).
        self._refusals: Refusals = {}
        self._root: Optional[QWidget] = None
        # Live splitter sizes at the start of a preview, restored on Escape.
        self._splitter_at_preview: Dict[NodeId, List[int]] = {}
        self._created = 0
        self._patched = 0
        self._reconciled = 0
        self._last_error = ""
        self._last_stats = PatchStats(0, 0, 0, 0, 0, (), 0.0)
        self._base_dir = os.path.dirname(session.path)
        _ensure_app()
        self._subscription = session.log.subscribe(self.on_changeset, priority=PRIORITY_REALIZE)

    def build(self) -> QWidget:
        """Create the whole tree. Also the recovery path for DocumentReplaced."""
        self._destroy_tree()
        self._pool.clear()
        self._problems.clear()
        self._refusals.clear()
        self._start_patch()
        if self._own_resources:
            self._register_resources()
        root_node = self._session.document.root
        widget = self._create_widget(root_node, None)
        self._root = widget
        self._sweep_pool()
        isolate_widget(widget)
        self._reapply_authored_look(root_node, widget)
        self._index_buddies()
        self._reapply_document_geometry()
        return widget

    def _start_patch(self) -> None:
        self._layout_hints = {}
        self._filled.clear()
        self._grid_check.clear()
        self._touched.clear()
        self._fresh.clear()
        self._unplaced.clear()
        self._geometry_targets.clear()
        self._needs_fill.clear()

    def on_changeset(self, changeset: ChangeSet) -> PatchStats:
        """Reconcile in three phases. Patches re-read the document, not ``change.new``."""
        started = time.process_time()
        self._created = 0
        self._patched = 0
        self._reconciled = 0
        self._last_error = ""
        destroyed = 0
        fallbacks = 0
        roots: List[NodeId] = []
        self._start_patch()
        try:
            if changeset.replaced or self._root is None:
                destroyed = self._removed_widget_count(changeset)
                self.build()
            else:
                destroyed = self._patch(changeset)
        except Exception as exc:
            self._last_error = str(exc)
            logger.exception("FB901 realize patch failed on %s", changeset.label)
            fallbacks += 1
            try:
                roots.append(self._fallback(changeset))
                self._sweep_pool()
            except Exception:
                logger.exception("FB901 realize ancestor rebuild failed on %s", changeset.label)
                self.build()
        stats = PatchStats(
            patched_properties=self._patched,
            reconciled_containers=self._reconciled,
            created_widgets=self._created,
            destroyed_widgets=destroyed,
            fallback_rebuilds=fallbacks,
            rebuilt_roots=tuple(roots),
            cpu_ms=(time.process_time() - started) * 1000.0,
        )
        self._last_stats = stats
        return stats

    @property
    def root_widget(self) -> Optional[QWidget]:
        if self._root is None or not wrapper_is_valid(self._root):
            return None
        return self._root

    @property
    def document(self) -> UiDocument:
        return self._session.document

    @property
    def last_stats(self) -> PatchStats:
        return self._last_stats

    @property
    def last_error(self) -> str:
        return self._last_error

    def widget_for(self, node_id: NodeId) -> Optional[QWidget]:
        widget = self._widgets.get(node_id)
        if widget is None or not wrapper_is_valid(widget):
            return None
        return widget

    def layout_for(self, node_id: NodeId) -> Optional[QLayout]:
        layout = self._layouts.get(node_id)
        if layout is None or not wrapper_is_valid(layout):
            return None
        return layout

    def object_for(self, node_id: NodeId) -> Optional[object]:
        obj = self._objects.get(node_id)
        if obj is None or not wrapper_is_valid(obj):
            return None
        return obj

    def spacer_for(self, node_id: NodeId) -> Optional[QSpacerItem]:
        spacer = self._spacers.get(node_id)
        if not isinstance(spacer, QSpacerItem) or not wrapper_is_valid(spacer):
            return None
        return spacer

    def apply_live(self, props: Sequence[LiveProp]) -> None:
        """Show ``props`` on the live objects. The document does not change."""
        document = self._session.document
        for prop in props:
            if prop.name == "cbcsSplitterSizes" and prop.owner not in self._splitter_at_preview:
                widget = self.widget_for(prop.owner)
                if widget is not None and isinstance(widget, QSplitter):
                    self._splitter_at_preview[prop.owner] = list(widget.sizes())
            node = document.get(prop.owner)
            obj = self.object_for(prop.owner)
            if node is None or obj is None:
                continue
            entry = None if prop.value is None else PropertyEntry("property", prop.name, prop.value)
            self._put(node, obj, prop.name, entry)

    def reapply(self, keys: Sequence[PropKey]) -> None:
        """Put the document's values for ``keys`` back on the live objects."""
        self._reapply_document_geometry({owner for owner, name in keys if name == "geometry"})
        for owner, name in keys:
            if name != "geometry":
                self._patch_property(owner, "property", name)

    def node_for(self, obj: object) -> Optional[NodeId]:
        current = obj
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            node_id = _node_id(current)
            if node_id is not None:
                return node_id
            parent = None
            if hasattr(current, "parentWidget"):
                parent = current.parentWidget()
            if parent is None and hasattr(current, "parent"):
                parent = current.parent()
            current = parent
        return None

    def signature(self) -> Tuple[object, ...]:
        """Class, name, parent, layout membership and the properties the file sets."""
        parts: List[object] = []
        for node in self._session.document.iter_preorder():
            if isinstance(node, WidgetNode):
                widget = self.widget_for(node.id)
                if widget is None:
                    parts.append(("missing-widget", int(node.id)))
                    continue
                parts.append(self._widget_signature(node, widget))
            elif isinstance(node, LayoutNode):
                parts.append(self._layout_signature(node))
        return tuple(parts)

    def problems(self) -> Tuple[str, ...]:
        """Classes and properties that could not be applied during the last build."""
        return tuple(self._problems)

    def refused(self, node_id: NodeId, name: str) -> Optional[str]:
        """Why the canvas widget did not take the value of ``name``, or None when it did. O(1).

        Set when Qt refuses a value (``setProperty`` returns False or the setter
        raises); cleared when the property is next applied or the node is removed.
        """
        return self._refusals.get((int(node_id), name))

    def dispose(self) -> None:
        self._subscription.close()
        self._destroy_tree()
        self._unregister_resources()
        if self._nursery_widget is not None:
            delete_now(self._nursery_widget)
            self._nursery_widget = None

    def _patch(self, changeset: ChangeSet) -> int:
        # Count before reconcile parks removed widgets out of the map.
        destroyed = self._removed_widget_count(changeset)
        document = self._session.document
        self._layout_hints = collect_layout_hints(changeset, document, self._slot_of)
        for change in changeset.changes:
            if not isinstance(change, FieldChanged):
                continue
            node = document.get(change.node)
            if change.field == "class_name":
                if isinstance(node, WidgetNode):
                    self._morph_widget(node)
                elif isinstance(node, LayoutNode):
                    self._morph_layout(node)
            elif change.field == "extends" and isinstance(node, CustomWidgetNode):
                self._rebuild_class(node.class_name)
        for change in changeset.changes:
            if isinstance(change, NodeMoved):
                self._detach_moved(change.node)
        containers = set(changeset.structure_dirty)
        containers.update(self._pending_containers)
        self._pending_containers.clear()
        for change in changeset.changes:
            if isinstance(change, FieldChanged) and change.field in _LAYOUT_FIELDS:
                node = document.get(change.node)
                if isinstance(node, LayoutItemNode) and node.parent_id is not None:
                    containers.add(node.parent_id)
                elif isinstance(node, LayoutNode):
                    containers.add(node.id)
                    self._grid_check.add(node.id)
        self._reconcile_ids(containers)
        self._destroy_removed(changeset)
        for owner, kind, name in changeset.property_dirty:
            node = document.get(owner)
            if isinstance(node, WidgetNode) and (node.class_name, name) in REBUILD_PROPERTIES:
                self._morph_widget(node)
                continue
            self._patch_property(owner, kind, name)
        if self._pending_containers:
            extra = set(self._pending_containers)
            self._pending_containers.clear()
            self._reconcile_ids(extra)
        renamed = set()
        for change in changeset.changes:
            if isinstance(change, FieldChanged) and change.field in ("object_name", "name"):
                self._rename(change.node)
                if isinstance(change.old, str):
                    renamed.add(change.old)
                current = _document_object_name(document.get(change.node))
                if current:
                    renamed.add(current)
            elif isinstance(change, FieldChanged) and change.field == "zorder":
                self._restack(change.node)
        self._sweep_pool()
        self._buddies_touched()
        self._refresh_buddies(changeset, renamed)
        self._flush_morph_buddies()
        targets = self._geometry_targets
        targets.update(self._touched)
        targets.update(_geometry_owners(changeset))
        self._target_laid_out_rects()
        if targets:
            self._reapply_document_geometry(targets)
        return destroyed

    def _reconcile_ids(self, node_ids: set) -> None:
        document = self._session.document
        ordered = sorted(
            (node_id for node_id in node_ids if document.contains(node_id)),
            key=self._order_key,
        )
        for node_id in ordered:
            self._reconcile_node(node_id)

    def _flush_morph_buddies(self) -> None:
        document = self._session.document
        pending = list(self._morph_buddies)
        self._morph_buddies.clear()
        for node_id in pending:
            node = document.get(node_id)
            if isinstance(node, WidgetNode):
                self._set_buddy(node)

    def _patch_property(self, owner: NodeId, kind: str, name: str) -> None:
        node = self._session.document.get(owner)
        if node is None:
            return
        if kind == "attribute":
            self._patch_attribute(node, name)
            return
        obj = self._objects.get(owner)
        if obj is None or not wrapper_is_valid(obj):
            return
        entry = node.prop(name)
        if name == "cbcsSplitterSizes" and entry is not None:
            self._splitter_at_preview.pop(owner, None)
        self._put(node, obj, name, entry)
        if entry is not None and name == "buddy" and isinstance(node, WidgetNode):
            self._note_buddy(node)
            self._set_buddy(node)

    def _put(self, node: Node, obj: object, name: str, entry: Optional[PropertyEntry]) -> None:
        """Apply ``entry``, or restore what a fresh build holds when the file does not set ``name``.

        A patch, undo, preview end and Esc all land here.
        """
        if isinstance(node, LayoutNode) and isinstance(obj, QLayout) and name in _LAYOUT_FAMILIES:
            self._apply_family(node, obj, name, entry)
            return
        if entry is None:
            self._reset_property(node, obj, name)
            self._settle_label(node, obj, name)
            return
        if name == "cbcsSplitterSizes":
            if isinstance(obj, QSplitter):
                obj.setSizes(list(splitter_sizes(entry.value)))
                self._patched += 1
            return
        if apply_entry(
            obj,
            entry,
            is_root=obj is self._root,
            resolve_path=self._resolve_path,
            problems=self._problems,
            refusals=self._refusals,
        ):
            self._patched += 1
        if name == "currentIndex" and isinstance(obj, QWidget):
            settle_page_index(obj, entry)
        self._settle_label(node, obj, name)

    def _settle_label(self, node: Node, obj: object, name: str) -> None:
        """QLabel text and pixmap clear each other: end on the one the running app shows."""
        if name not in ("text", "pixmap") or not isinstance(obj, QLabel) or not isinstance(node, WidgetNode):
            return
        last = "text" if label_text_hides_picture(node) else "pixmap"
        if last == name:
            return
        entry = node.prop(last)
        if entry is None:
            return
        apply_entry(
            obj,
            entry,
            is_root=obj is self._root,
            resolve_path=self._resolve_path,
            problems=self._problems,
            refusals=self._refusals,
        )

    def _patch_attribute(self, node: object, name: str) -> None:
        if not isinstance(node, WidgetNode) or node.parent_id is None:
            return
        parent = self._widgets.get(node.parent_id)
        widget = self._widgets.get(node.id)
        if parent is None or widget is None:
            return
        entry = node.attr(name)
        text = "" if entry is None else text_of(entry.value)
        if isinstance(parent, QTabWidget):
            index = parent.indexOf(widget)
            if index < 0:
                return
            if name in ("title", "label"):
                parent.setTabText(index, text)
            elif name == "toolTip":
                parent.setTabToolTip(index, text)
            elif name == "whatsThis":
                parent.setTabWhatsThis(index, text)
            self._patched += 1
        elif isinstance(parent, QToolBox):
            index = parent.indexOf(widget)
            if index < 0:
                return
            if name in ("title", "label"):
                parent.setItemText(index, text)
            elif name == "toolTip":
                parent.setItemToolTip(index, text)
            self._patched += 1

    def _reset_property(self, node: object, obj: object, name: str) -> None:
        if name in CANVAS_OVERRIDES:
            return
        if name == "cbcsSplitterSizes":
            if isinstance(obj, QSplitter):
                node_id = _node_id(obj)
                saved = None if node_id is None else self._splitter_at_preview.pop(node_id, None)
                if saved is not None:
                    obj.setSizes(saved)
                else:
                    obj.setSizes(_distributed_sizes(obj))
                self._patched += 1
            return
        if not isinstance(node, WidgetNode):
            return
        window = isinstance(obj, QWidget) and obj.isWindow()
        fresh = _fresh_widget(
            self._qt_class_name(node.class_name),
            self._widget_type(node.class_name),
            window=window,
        )
        if fresh is None:
            return
        info = QtClassTable.shared().property_info(self._qt_class_name(node.class_name), name)
        if info is not None and info.default is not None and not info.volatile:
            synthetic = PropertyEntry("property", name, info.default)
            apply_entry(
                obj,
                synthetic,
                is_root=obj is self._root,
                resolve_path=self._resolve_path,
                problems=self._problems,
                refusals=self._refusals,
            )
            self._patched += 1
            return
        try:
            value = fresh.property(name)  # type: ignore[attr-defined]
            # PySide6 refuses an enum or flag object here; Qt takes its number.
            if isinstance(value, enum.Enum):
                value = enum_value(value)
            if set_property_checked(obj, name, value):
                self._refusals.pop((int(node.id), name), None)
                self._patched += 1
            else:
                self._refusals[(int(node.id), name)] = REFUSED_BY_QT
        except (TypeError, RuntimeError, AttributeError, ValueError):
            return

    def _apply_family(self, node: LayoutNode, layout: QLayout, name: str, entry: Optional[PropertyEntry]) -> None:
        """Reset one family, then apply it in uic order.

        ``margin`` is applied before any stored side, and ``spacing`` before a
        stored ``horizontalSpacing`` or ``verticalSpacing``. File order does
        not change the result. A preview value for ``name`` is included even
        when the document does not store it yet.
        """
        family = _MARGIN_FAMILY if name in _MARGIN_FAMILY else _SPACING_FAMILY
        if family is _MARGIN_FAMILY:
            layout.setContentsMargins(-1, -1, -1, -1)
        else:
            layout.setSpacing(-1)
        for each in ordered_layout_metrics(node.properties(), name, entry):
            if each.name not in family:
                continue
            apply_entry(
                layout,
                each,
                is_root=False,
                resolve_path=self._resolve_path,
                problems=self._problems,
                refusals=self._refusals,
            )
        self._patched += 1

    def _rename(self, node_id: NodeId, new: object = None) -> None:
        """Re-read the name from the document. ``new`` is the event value and is ignored."""
        del new
        node = self._session.document.get(node_id)
        name = _document_object_name(node)
        if not name and node is None:
            return
        obj = self._objects.get(node_id)
        if obj is not None and wrapper_is_valid(obj):
            obj.setObjectName(name)  # type: ignore[attr-defined]

    def _refresh_buddies(self, changeset: ChangeSet, renamed: set) -> None:
        document = self._session.document
        touched = set()
        for owner, _kind, name in changeset.property_dirty:
            if name != "buddy":
                continue
            node = document.get(owner)
            if isinstance(node, WidgetNode):
                self._note_buddy(node)
                self._set_buddy(node)
                touched.add(node.id)
        for name in renamed:
            for node_id in list(self._buddy_users.get(name, ())):
                if node_id in touched:
                    continue
                node = document.get(node_id)
                if isinstance(node, WidgetNode):
                    self._note_buddy(node)
                    self._set_buddy(node)

    def _buddies_touched(self) -> None:
        """Buddies of the widgets this patch placed, and labels naming new widgets."""
        document = self._session.document
        for node_id in self._touched:
            node = document.get(node_id)
            if isinstance(node, WidgetNode) and node.prop("buddy") is not None:
                if node_id in self._fresh:
                    self._note_buddy(node)
                self._set_buddy(node)
        for node_id in self._fresh:
            node = document.get(node_id)
            if not isinstance(node, WidgetNode) or not node.object_name:
                continue
            for user_id in list(self._buddy_users.get(node.object_name, ())):
                user = document.get(user_id)
                if isinstance(user, WidgetNode):
                    self._set_buddy(user)

    def _index_buddies(self) -> None:
        self._buddy_of.clear()
        self._buddy_users.clear()
        for node in self._session.document.iter_preorder():
            if isinstance(node, WidgetNode):
                self._note_buddy(node)
                self._set_buddy(node)

    def _note_buddy(self, node: WidgetNode) -> None:
        entry = node.prop("buddy")
        target = text_of(entry.value) if entry is not None else ""
        previous = self._buddy_of.get(node.id)
        if previous and previous in self._buddy_users and node.id in self._buddy_users[previous]:
            self._buddy_users[previous].remove(node.id)
        if target:
            self._buddy_of[node.id] = target
            users = self._buddy_users.setdefault(target, [])
            if node.id not in users:
                users.append(node.id)
        else:
            self._buddy_of.pop(node.id, None)

    def _set_buddy(self, node: WidgetNode) -> None:
        widget = self._widgets.get(node.id)
        if widget is None or not hasattr(widget, "setBuddy"):
            return
        entry = node.prop("buddy")
        if entry is None:
            widget.setBuddy(None)
            return
        widget.setBuddy(self._widget_named(text_of(entry.value)))

    def _widget_named(self, name: str) -> Optional[QWidget]:
        for node_id in self._session.document.by_name(name):
            widget = self._widgets.get(node_id)
            if widget is not None and wrapper_is_valid(widget):
                return widget
        return None

    def _rebuild_class(self, class_name: str) -> None:
        for node in list(self._session.document.iter_preorder()):
            if isinstance(node, WidgetNode) and node.class_name == class_name:
                self._morph_widget(node)

    def _destroy_removed(self, changeset: ChangeSet) -> int:
        count = self._removed_widget_count(changeset)
        removed = set(changeset.removed)
        for pooled in list(self._pool.values()):
            # A moved widget waits in the pool under its old host. If that
            # host dies here, the widget must not die with it.
            if isinstance(pooled, QWidget) and wrapper_is_valid(pooled) and _node_id(pooled) not in removed:
                host = pooled.parentWidget()
                if host is not None and _node_id(host) in removed:
                    pooled.setParent(None)
        for node_id in list(changeset.removed):
            found: object = self._widgets.get(node_id)
            if found is None:
                found = self._pool.get(node_id)
            if not isinstance(found, QWidget) or not wrapper_is_valid(found):
                continue
            target: QWidget = found
            parent = target.parentWidget()
            parent_id = _node_id(parent) if parent is not None else None
            if parent_id in removed and wrapper_is_valid(parent):
                continue
            self._pool.pop(node_id, None)
            self._delete_widget(target)
        for node_id in changeset.removed:
            self._drop_removed_object(node_id)
            self._wipe(node_id)
        for change in changeset.changes:
            if isinstance(change, NodeRemoved):
                for node_id in change.subtree:
                    self._wipe(node_id)
        return count

    def _removed_widget_count(self, changeset: ChangeSet) -> int:
        return len([node_id for node_id in changeset.removed if node_id in self._widgets])

    def _drop_removed_object(self, node_id: NodeId) -> None:
        """Delete a removed layout or action now instead of leaving it to the GC."""
        layout = self._layouts.get(node_id)
        if layout is not None and wrapper_is_valid(layout):
            self._delete_layout_object(layout)
        action = self._actions.get(node_id)
        if action is not None and wrapper_is_valid(action):
            delete_now(action)

    def _wipe(self, node_id: NodeId) -> None:
        if self._refusals:
            gone = int(node_id)
            for key in [key for key in self._refusals if key[0] == gone]:
                del self._refusals[key]
        self._widgets.pop(node_id, None)
        self._layouts.pop(node_id, None)
        self._objects.pop(node_id, None)
        self._actions.pop(node_id, None)
        spacer = self._spacers.pop(node_id, None)
        if spacer is not None:
            self._spacer_ids.pop(id(spacer), None)
        self._pool.pop(node_id, None)
        self._mdi.pop(node_id, None)
        target = self._buddy_of.pop(node_id, None)
        users = self._buddy_users.get(target) if target else None
        if users is not None and node_id in users:
            users.remove(node_id)
        self._forget_slots(node_id)
        self._slot_of.pop(node_id, None)

    def _fallback(self, changeset: ChangeSet) -> NodeId:
        document = self._session.document
        target: Optional[NodeId] = None
        for node_id in sorted(changeset.structure_dirty, key=self._order_key):
            if node_id in self._widgets:
                target = node_id
                break
        if target is None:
            for owner, _kind, _name in changeset.property_dirty:
                if owner in self._widgets:
                    target = owner
                    break
        if target is None or self._widgets.get(target) is self._root:
            self.build()
            return document.root.id
        node = document.get(target)
        widget = self._widgets.get(target)
        if not isinstance(node, WidgetNode) or widget is None or not wrapper_is_valid(widget):
            self.build()
            return document.root.id
        self._park_children(node, widget)
        self._settle_descendants(widget, replacing=target)
        self._fill_widget(node, widget)
        return target

    def _widget_signature(self, node: WidgetNode, widget: QWidget) -> Tuple[object, ...]:
        props: List[object] = []
        for entry in node.properties():
            if entry.name in ("buddy",) or is_logic_key(entry.name):
                continue
            if entry.name == "geometry":
                geo = widget.geometry()
                parent = widget.parentWidget()
                managed = widget is self._root or (parent is not None and parent.layout() is not None)
                if managed:
                    props.append(("geometry", geo.width(), geo.height()))
                else:
                    props.append(("geometry", geo.x(), geo.y(), geo.width(), geo.height()))
                continue
            if entry.name == "cbcsSplitterSizes" and isinstance(widget, QSplitter):
                props.append(("cbcsSplitterSizes", tuple(widget.sizes())))
                continue
            props.append((entry.name, norm_qt(widget.property(entry.name))))
        parent = widget.parentWidget()
        parent_id = _node_id(parent) if parent is not None else None
        sibling_index = _sibling_index(self._session.document, node, widget)
        buddy_name = None
        if hasattr(widget, "buddy") and widget.buddy() is not None and wrapper_is_valid(widget.buddy()):
            buddy_name = widget.buddy().objectName()
        pages: Tuple[str, ...] = ()
        if isinstance(widget, QTabWidget):
            pages = tuple(widget.tabText(index) for index in range(widget.count()))
        elif isinstance(widget, QToolBox):
            pages = tuple(widget.itemText(index) for index in range(widget.count()))
        return (
            type(widget).__name__,
            widget.objectName(),
            int(node.id),
            None if parent_id is None else int(parent_id),
            sibling_index,
            tuple(props),
            buddy_name,
            pages,
            widget.styleSheet(),
            _current_index(widget),
            _item_texts(widget),
            _action_names(widget),
        )

    def _layout_signature(self, node: LayoutNode) -> Tuple[object, ...]:
        layout = self.layout_for(node.id)
        if layout is None:
            return ("missing-layout", int(node.id))
        items: List[object] = []
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item is None:
                items.append(None)
                continue
            items.append(self._layout_item_signature(layout, item, index))
        if isinstance(layout, (QGridLayout, QFormLayout)):
            # Grid and form items carry their cell. Qt's item order is only
            # insertion order there, so the cells are compared, not the order.
            items.sort(key=repr)
        return (
            type(layout).__name__,
            layout.objectName(),
            int(node.id),
            tuple(items),
            _layout_metrics(layout, node),
        )

    def _layout_item_signature(self, layout: QLayout, item: object, index: int) -> Tuple[object, ...]:
        align = _align_int(item)
        position = _item_position(layout, index)
        spacer = item.spacerItem() if hasattr(item, "spacerItem") else None
        if spacer is not None:
            hint = spacer.sizeHint()
            spacer_id = self._spacer_of(spacer)
            if spacer_id is None:
                spacer_id = self._spacer_of(item)
            return (
                "spacer",
                None if spacer_id is None else int(spacer_id),
                int(hint.width()),
                int(hint.height()),
                align,
                position,
            )
        child = item.widget() if hasattr(item, "widget") else None
        nested = item.layout() if hasattr(item, "layout") else None
        child_id = _node_id(child) if child is not None else None
        kind = "widget"
        if child_id is None and nested is not None:
            child_id = _node_id(nested)
            kind = "layout"
        return (kind, None if child_id is None else int(child_id), align, position)

    def _register_resources(self) -> None:
        self._unregister_resources()
        for node in self._session.document.ui.children("resources"):
            if not isinstance(node, ResourceNode) or not node.location:
                continue
            path = node.location
            if not os.path.isabs(path):
                path = os.path.join(self._base_dir, path)
            try:
                with open(path, encoding="utf-8") as handle:
                    text = handle.read()
                qrc = read_qrc(text)
            except (OSError, ValueError) as exc:
                self._problems.append("resource %s: %s" % (node.location, exc))
                continue
            folder = os.path.dirname(path)

            def read_file(relative: str, folder: str = folder) -> bytes:
                with open(os.path.join(folder, relative), "rb") as handle:
                    return handle.read()

            try:
                tree, _diagnostics = compile_resource_tree(qrc, read_file=read_file)
            except (OSError, ValueError) as exc:
                self._problems.append("resource %s: %s" % (node.location, exc))
                continue
            qRegisterResourceData(tree.version, tree.struct, tree.names, tree.data)
            self._registered.append(tree)

    def _unregister_resources(self) -> None:
        for tree in self._registered:
            qUnregisterResourceData(tree.version, tree.struct, tree.names, tree.data)
        self._registered.clear()

    def _reapply_authored_look(self, node: WidgetNode, widget: QWidget) -> None:
        for name in ("styleSheet", "palette", "font"):
            entry = node.prop(name)
            if entry is None:
                continue
            apply_entry(
                widget,
                entry,
                is_root=True,
                resolve_path=self._resolve_path,
                problems=self._problems,
                refusals=self._refusals,
            )

    def _destroy_tree(self) -> None:
        # Subwindows taken off an MDI area are parentless. Delete them before
        # the form. Deleting them while they were still in the area corrupts it.
        retired = list(getattr(self, "_retired_windows", ()))
        self._retired_windows = []
        for window in retired:
            if wrapper_is_valid(window):
                window.setParent(None)
                delete_now(window)
        root = self._root
        self._root = None
        # A replaced layout can sit in the pool still holding widgets that the
        # live tree also parents. Deleting the root first frees those widgets,
        # and deleting the layout afterwards crashes. Empty those layouts now,
        # while the widgets are alive, and delete the layouts before the root.
        self._delete_layouts_outside(root)
        orphans = [obj for obj in self._pool.values() if wrapper_is_valid(obj)]
        if root is not None and wrapper_is_valid(root):
            self._wipe_ids_under(root)
            root.setParent(None)
            delete_now(root)
        for pooled in orphans:
            if wrapper_is_valid(pooled):
                delete_now(pooled)
        self._widgets.clear()
        self._layouts.clear()
        self._actions.clear()
        self._objects.clear()
        self._spacers.clear()
        self._spacer_ids.clear()
        self._placed.clear()
        self._slot_of.clear()
        self._crowded.clear()
        self._pool.clear()
        self._mdi.clear()

    def _delete_layouts_outside(self, root: Optional[QWidget]) -> None:
        seen = set()
        pending = list(self._pool.values()) + list(self._layouts.values())
        for obj in pending:
            if not isinstance(obj, QLayout) or not wrapper_is_valid(obj) or id(obj) in seen:
                continue
            seen.add(id(obj))
            if root is not None and _nested_under(obj, root):
                continue
            while obj.count():
                obj.takeAt(0)
            if wrapper_is_valid(obj):
                delete_now(obj)

    def _wipe_ids_under(self, root: QWidget) -> None:
        """Drop map entries for a tree that ``delete_now`` is about to free."""
        self._wipe_if_tagged(root)
        if not hasattr(root, "findChildren"):
            return
        for child in root.findChildren(QObject):
            self._wipe_if_tagged(child)

    def _wipe_if_tagged(self, obj: object) -> None:
        node_id = _node_id(obj)
        if node_id is not None:
            self._wipe(node_id)

    def _resolve_path(self, path: str) -> str:
        return resolve_stored_picture(path, self._base_dir, self._session.document)


def _fresh_host() -> QWidget:
    """A parent so a probe is not a window.

    A parentless QStatusBar is a window, and a window pins its minimum size to
    the size hint. Resetting a child from that probe grows the live widget, so
    a child probe is parented and a window probe is not.
    """
    global _FRESH_HOST
    if _FRESH_HOST is None or not wrapper_is_valid(_FRESH_HOST):
        _ensure_app()
        host = QWidget()
        host.setObjectName("_cbcsFreshHost")
        # The probe is a hidden parent, not a window the desktop should show.
        host.setAttribute(Qt.WA_DontShowOnScreen, True)
        _FRESH_HOST = host
    return _FRESH_HOST


class _PaneStandIn(QWidget):
    """A scratch pane with one real pane's hint, limits and policy."""

    def __init__(self, hint: object, policy: object, minimum: object, maximum: object) -> None:
        super().__init__()
        self._hint = hint
        self.setSizePolicy(policy)  # type: ignore[arg-type]
        self.setMinimumSize(minimum)  # type: ignore[arg-type]
        self.setMaximumSize(maximum)  # type: ignore[arg-type]

    def sizeHint(self) -> object:  # type: ignore[override]
        return self._hint

    def minimumSizeHint(self) -> object:  # type: ignore[override]
        return self.minimumSize()


def _distributed_sizes(splitter: QSplitter) -> List[int]:
    """Sizes a fresh splitter gives these panes at this splitter's size.

    ``setSizes(sizeHint)`` ignores stretch, so unequal shares collapse to an
    even split. A scratch splitter with the same hints, limits, policies and
    stretch factors lays the panes out the way a fresh build does.
    """
    scratch = QSplitter()
    scratch.setAttribute(Qt.WA_DontShowOnScreen, True)
    scratch.setOrientation(splitter.orientation())
    scratch.setHandleWidth(splitter.handleWidth())
    scratch.setChildrenCollapsible(splitter.childrenCollapsible())
    for index in range(splitter.count()):
        pane = splitter.widget(index)
        if pane is None:
            scratch.addWidget(QWidget())
            continue
        scratch.addWidget(
            _PaneStandIn(pane.sizeHint(), pane.sizePolicy(), pane.minimumSize(), pane.maximumSize())
        )
    scratch.resize(max(splitter.width(), 1), max(splitter.height(), 1))
    scratch.show()
    sizes = [int(size) for size in scratch.sizes()]
    scratch.hide()
    scratch.setParent(None)
    delete_now(scratch)
    if len(sizes) != splitter.count():
        return _pane_hints(splitter)
    return sizes


def _pane_hints(splitter: QSplitter) -> List[int]:
    horizontal = splitter.orientation() == Qt.Orientation.Horizontal
    hints: List[int] = []
    for index in range(splitter.count()):
        pane = splitter.widget(index)
        hint = pane.sizeHint() if pane is not None else None
        if hint is None:
            hints.append(0)
        else:
            hints.append(max(0, hint.width() if horizontal else hint.height()))
    return hints


def _fresh_widget(short_name: str, cls: type, *, window: bool = True) -> Optional[QWidget]:
    key = (short_name, window)
    cached = _FRESH.get(key)
    if cached is not None and wrapper_is_valid(cached):
        return cached
    try:
        created = cls() if window else cls(_fresh_host())
    except (TypeError, RuntimeError):
        return None
    if not isinstance(created, QWidget):
        return None
    created.setObjectName("_cbcsFresh")
    _FRESH[key] = created
    return created


def _ensure_app() -> None:
    if QApplication.instance() is None:
        QApplication([])


def _geometry_owners(changeset: ChangeSet) -> Set[NodeId]:
    return {owner for owner, kind, name in changeset.property_dirty if kind == "property" and name in _GEOMETRY_PROPS}


def _document_object_name(node: object) -> str:
    if node is None:
        return ""
    object_name = getattr(node, "object_name", None)
    if isinstance(object_name, str) and object_name:
        return object_name
    name = getattr(node, "name", None)
    if isinstance(name, str):
        return name
    if isinstance(object_name, str):
        return object_name
    return ""


def _sibling_index(document: UiDocument, node: WidgetNode, widget: QWidget) -> int:
    """Layout children use the cell. Free widgets use the live named-child order.

    A patch and a fresh build both read the document for a cell, so that index
    cannot see a z-order miss. Free widgets stack as named children of the
    parent widget, and that live order is what a mismatch has to catch.
    """
    if node.parent_id is None:
        return 0
    parent = document.get(node.parent_id)
    if isinstance(parent, LayoutItemNode):
        return _layout_item_spot(document, parent)
    if isinstance(parent, WidgetNode):
        return _named_child_index(widget)
    return 0


def _named_child_index(widget: QWidget) -> int:
    """Page index in a page container, else the stacking index among siblings.

    The owner is the nearest realized ancestor. Qt puts unnamed internals
    (a tab widget's stack, a tool box's scroll area) between a page and its
    container. Windows such as menus are not stacked: they read -2 and do not
    count among their siblings.
    """
    if widget.isWindow():
        return -2
    owner = widget.parentWidget()
    while owner is not None and _node_id(owner) is None:
        owner = owner.parentWidget()
    if isinstance(owner, QWizard):
        wizard = cast(QWizard, owner)
        pages = [wizard.page(page_id) for page_id in wizard.pageIds()]
        if widget in pages:
            return pages.index(widget)
    if isinstance(owner, (QTabWidget, QToolBox, QStackedWidget, QSplitter)):
        # A splitter's pane order is indexOf; its child list order is not.
        page = int(cast(QStackedWidget, owner).indexOf(widget))
        if page >= 0:
            return page
    parent = widget.parentWidget()
    if parent is None:
        return 0
    named = [
        child
        for child in parent.children()
        if isinstance(child, QWidget) and not child.isWindow() and _node_id(child) is not None
    ]
    try:
        return named.index(widget)
    except ValueError:
        return -1


def _layout_item_spot(document: UiDocument, item: LayoutItemNode) -> int:
    if item.parent_id is None:
        return 0
    layout = document.get(item.parent_id)
    if not isinstance(layout, LayoutNode):
        return 0
    row = 0 if item.row is None else item.row
    column = 0 if item.column is None else item.column
    if layout.class_name == "QFormLayout":
        return row * 3 + column
    if layout.class_name == "QGridLayout":
        return row * 1000 + column
    for index, candidate in enumerate(layout.items):
        if candidate.id == item.id:
            return index
    return -1


def _current_index(widget: QWidget) -> Optional[int]:
    if isinstance(widget, QWizard):
        return int(widget.currentId())
    if isinstance(widget, (QStackedWidget, QTabWidget, QToolBox)):
        return int(widget.currentIndex())
    return None


def _item_texts(widget: QWidget) -> Tuple[object, ...]:
    if isinstance(widget, QComboBox):
        return tuple(widget.itemText(index) for index in range(widget.count()))
    if isinstance(widget, QListWidget):
        return tuple(widget.item(index).text() for index in range(widget.count()) if widget.item(index) is not None)
    if isinstance(widget, QTableWidget):
        texts: List[object] = []
        for row in range(widget.rowCount()):
            for column in range(widget.columnCount()):
                cell = widget.item(row, column)
                texts.append((row, column, "" if cell is None else cell.text()))
        return tuple(texts)
    if isinstance(widget, QTreeWidget):
        return tuple(_tree_signature(widget.topLevelItem(index)) for index in range(widget.topLevelItemCount()))
    return ()


def _tree_signature(item: object) -> Tuple[object, ...]:
    columns = int(item.columnCount()) if hasattr(item, "columnCount") else 1  # type: ignore[attr-defined]
    texts = tuple(item.text(index) for index in range(max(columns, 1)))  # type: ignore[attr-defined]
    children = tuple(
        _tree_signature(item.child(index))  # type: ignore[attr-defined]
        for index in range(int(item.childCount()))  # type: ignore[attr-defined]
    )
    return (texts, children)


def _nested_under(obj: object, root: QWidget) -> bool:
    current = obj.parent() if hasattr(obj, "parent") else None
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if current is root:
            return True
        current = current.parent() if hasattr(current, "parent") else None
    return False


def _action_names(widget: QWidget) -> Tuple[str, ...]:
    if not isinstance(widget, (QMenu, QMenuBar, QToolBar)):
        return ()
    return tuple(action.objectName() for action in widget.actions())


def _layout_metrics(layout: QLayout, node: object) -> Tuple[object, ...]:
    if isinstance(layout, QGridLayout):
        # rowCount() never shrinks, so a patched grid can report empty rows a
        # fresh layout does not. Compare the rows the document still occupies.
        rows, columns = _grid_extent(node)  # type: ignore[arg-type]
        # Qt does not bound-check these getters. A row or column the grid does
        # not have reads as 0, which is what a fresh grid would hold.
        have_rows = layout.rowCount()
        have_columns = layout.columnCount()

        def per_row(getter: object) -> Tuple[int, ...]:
            return tuple(int(getter(index)) if index < have_rows else 0 for index in range(rows))  # type: ignore[operator]

        def per_column(getter: object) -> Tuple[int, ...]:
            return tuple(int(getter(index)) if index < have_columns else 0 for index in range(columns))  # type: ignore[operator]

        return (
            per_row(layout.rowStretch),
            per_column(layout.columnStretch),
            per_row(layout.rowMinimumHeight),
            per_column(layout.columnMinimumWidth),
        )
    if isinstance(layout, QBoxLayout):
        return tuple(int(layout.stretch(index)) for index in range(layout.count()))
    return ()


def _item_position(layout: QLayout, index: int) -> Optional[Tuple[int, ...]]:
    if isinstance(layout, QGridLayout):
        row, column, rowspan, colspan = layout.getItemPosition(index)
        return (int(row), int(column), int(rowspan), int(colspan))
    if isinstance(layout, QFormLayout):
        row, role = layout.getItemPosition(index)
        return (int(row), int(enum_value(role)))
    return None


def _align_int(item: object) -> int:
    try:
        return int(enum_value(item.alignment()))  # type: ignore[attr-defined]
    except (TypeError, AttributeError, ValueError):
        return 0
