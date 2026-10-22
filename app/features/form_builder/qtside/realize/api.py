"""Realize: model to live widgets, kept in step by patches (CONTRACTS.md section 5)."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from app.qt.QtCore import qRegisterResourceData, qUnregisterResourceData
from app.qt.QtWidgets import QApplication, QLayout, QSplitter, QTabWidget, QToolBox, QWidget
from app.qt.qt_compat import delete_now, wrapper_is_valid
from app.features.form_builder.engine.codegen.resources import compile_resource_tree, read_qrc
from app.features.form_builder.engine.events import (
    PRIORITY_REALIZE,
    ChangeSet,
    FieldChanged,
    NodeMoved,
    NodeRemoved,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.logic.storage import is_logic_key
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.nodes import (
    CustomWidgetNode,
    LayoutItemNode,
    LayoutNode,
    ResourceNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.spec import PropertyEntry
from app.features.form_builder.qtside.realize.props import (
    apply_entry,
    norm_qt,
    path_under,
    splitter_sizes,
    text_of,
)
from app.features.form_builder.qtside.realize.tree import NODE_ID_PROPERTY, _Structure, _node_id
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
_FRESH: Dict[str, QWidget] = {}


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

    def __init__(self, session: FormSession) -> None:
        self._session = session
        self._widgets: Dict[NodeId, QWidget] = {}
        self._layouts: Dict[NodeId, QLayout] = {}
        self._actions: Dict[NodeId, object] = {}
        self._objects: Dict[NodeId, object] = {}
        self._spacers: Dict[NodeId, object] = {}
        self._pool: Dict[NodeId, object] = {}
        self._mdi: Dict[NodeId, object] = {}
        self._buddy_of: Dict[NodeId, str] = {}
        self._buddy_users: Dict[str, List[NodeId]] = {}
        self._registered: List[object] = []
        self._problems: List[str] = []
        self._root: Optional[QWidget] = None
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
        self._register_resources()
        root_node = self._session.document.root
        widget = self._create_widget(root_node, None)
        self._root = widget
        isolate_widget(widget)
        self._reapply_authored_look(root_node, widget)
        self._index_buddies()
        return widget

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

    def dispose(self) -> None:
        self._subscription.close()
        self._destroy_tree()
        self._unregister_resources()

    def _patch(self, changeset: ChangeSet) -> int:
        document = self._session.document
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
        for change in changeset.changes:
            if isinstance(change, FieldChanged) and change.field in _LAYOUT_FIELDS:
                node = document.get(change.node)
                if isinstance(node, LayoutItemNode) and node.parent_id is not None:
                    containers.add(node.parent_id)
                elif isinstance(node, LayoutNode):
                    containers.add(node.id)
        ordered = sorted(
            (node_id for node_id in containers if document.contains(node_id)),
            key=self._order_key,
        )
        for node_id in ordered:
            self._reconcile_node(node_id)
        self._buddies_in(ordered)
        destroyed = self._destroy_removed(changeset)
        for owner, kind, name in changeset.property_dirty:
            node = document.get(owner)
            if isinstance(node, WidgetNode) and (node.class_name, name) in REBUILD_PROPERTIES:
                self._morph_widget(node)
                continue
            self._patch_property(owner, kind, name)
        renamed = set()
        for change in changeset.changes:
            if isinstance(change, FieldChanged) and change.field in ("object_name", "name"):
                self._rename(change.node, change.new)
                if isinstance(change.old, str):
                    renamed.add(change.old)
                if isinstance(change.new, str):
                    renamed.add(change.new)
            elif isinstance(change, FieldChanged) and change.field == "zorder":
                self._restack(change.node)
        self._refresh_buddies(changeset, renamed)
        return destroyed

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
        if name == "cbcsSplitterSizes" and isinstance(obj, QSplitter):
            entry = node.prop(name)
            if entry is not None:
                obj.setSizes(list(splitter_sizes(entry.value)))
                self._patched += 1
            return
        entry = node.prop(name) if kind == "property" else node.attr(name)
        if entry is None:
            self._reset_property(node, obj, name)
            return
        if apply_entry(
            obj,
            entry,
            is_root=obj is self._root,
            resolve_path=self._resolve_path,
            problems=self._problems,
        ):
            self._patched += 1
        if name == "buddy" and isinstance(node, WidgetNode):
            self._note_buddy(node)
            self._set_buddy(node)

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
        if not isinstance(node, WidgetNode):
            return
        fresh = _fresh_widget(self._qt_class_name(node.class_name), self._widget_type(node.class_name))
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
            )
            self._patched += 1
            return
        try:
            obj.setProperty(name, fresh.property(name))  # type: ignore[attr-defined]
            self._patched += 1
        except (TypeError, RuntimeError, AttributeError):
            return

    def _rename(self, node_id: NodeId, new: object) -> None:
        if not isinstance(new, str):
            return
        obj = self._objects.get(node_id)
        if obj is not None and wrapper_is_valid(obj):
            obj.setObjectName(new)  # type: ignore[attr-defined]

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

    def _buddies_in(self, roots: Sequence[NodeId]) -> None:
        document = self._session.document
        for node_id in roots:
            if not document.contains(node_id):
                continue
            for node in document.iter_preorder(node_id):
                if isinstance(node, WidgetNode) and node.prop("buddy") is not None:
                    self._set_buddy(node)

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
            self._buddy_users.setdefault(target, []).append(node.id)
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
        for node_id in list(changeset.removed):
            if node_id not in self._widgets:
                continue
            widget = self._widgets.get(node_id)
            pooled = self._pool.get(node_id)
            target = widget if isinstance(widget, QWidget) else pooled
            if not isinstance(target, QWidget) or not wrapper_is_valid(target):
                continue
            parent = target.parentWidget()
            parent_id = _node_id(parent) if parent is not None else None
            if parent_id in changeset.removed:
                continue
            self._detach_widget(target)
            delete_now(target)
        for node_id in changeset.removed:
            self._wipe(node_id)
        for change in changeset.changes:
            if isinstance(change, NodeRemoved):
                for node_id in change.subtree:
                    self._wipe(node_id)
        return count

    def _removed_widget_count(self, changeset: ChangeSet) -> int:
        return len([node_id for node_id in changeset.removed if node_id in self._widgets])

    def _wipe(self, node_id: NodeId) -> None:
        self._widgets.pop(node_id, None)
        self._layouts.pop(node_id, None)
        self._objects.pop(node_id, None)
        self._actions.pop(node_id, None)
        self._spacers.pop(node_id, None)
        self._pool.pop(node_id, None)
        self._mdi.pop(node_id, None)
        self._buddy_of.pop(node_id, None)

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
        if not isinstance(node, WidgetNode) or widget is None:
            self.build()
            return document.root.id
        for desc in document.iter_preorder(target):
            if desc.id != target:
                self._wipe(desc.id)
        self._park_children(node, widget)
        for pooled in list(self._pool.values()):
            if isinstance(pooled, QWidget):
                delete_now(pooled)
        self._pool.clear()
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
        buddy_name = None
        if hasattr(widget, "buddy") and widget.buddy() is not None:
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
            tuple(props),
            buddy_name,
            pages,
            widget.styleSheet(),
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
            child = item.widget()
            nested = item.layout()
            child_id = _node_id(child) if child is not None else None
            if child_id is None and nested is not None:
                child_id = _node_id(nested)
            items.append(None if child_id is None else int(child_id))
        return (type(layout).__name__, layout.objectName(), int(node.id), tuple(items))

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
            )

    def _destroy_tree(self) -> None:
        root = self._root
        self._root = None
        if root is not None and wrapper_is_valid(root):
            root.setParent(None)
            delete_now(root)
        self._widgets.clear()
        self._layouts.clear()
        self._actions.clear()
        self._objects.clear()
        self._spacers.clear()
        self._pool.clear()
        self._mdi.clear()

    def _resolve_path(self, path: str) -> str:
        return path_under(self._base_dir, path)


def _fresh_widget(short_name: str, cls: type) -> Optional[QWidget]:
    cached = _FRESH.get(short_name)
    if cached is not None and wrapper_is_valid(cached):
        return cached
    try:
        created = cls()
    except (TypeError, RuntimeError):
        return None
    if not isinstance(created, QWidget):
        return None
    created.setObjectName("_cbcsFresh")
    _FRESH[short_name] = created
    return created


def _ensure_app() -> None:
    if QApplication.instance() is None:
        QApplication([])
