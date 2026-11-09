"""Context menu rows "Use my own class…" and "Back to {class}" (UX-CUST-001, 005).

Designer calls these Promote to and Demote. The row is absent on the form
itself, on a mix of classes and on parts of a main window. "Back to" shows on
widgets that use a class declared in the form, whatever the registry says.
"""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.commands.catalog_ext.promote import UseBaseClass
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.nodes import CustomWidgetNode, WidgetNode
from app.features.form_builder.integration.custom_registry import registry_of
from app.features.form_builder.integration.menu_ext import MenuContext
from app.features.form_builder.qtside.dialogs.promote import open_popover
from app.features.form_builder.qtside.dialogs.promote import friendly_of
from app.qt.QtCore import QRect, QTimer

ROW = "Use my own class…"
TOOLTIP = "Qt Designer calls this Promote to."
_SKIPPED = frozenset({"QMenuBar", "QMenu", "QToolBar", "QStatusBar", "QAction", "Line"})


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add("structure", build)


def _targets(ctx: MenuContext) -> Tuple[Tuple[NodeId, ...], Optional[str]]:
    """The selected widgets and their shared Qt class, or ``((), None)`` when the row does not apply."""
    doc = ctx.session.document
    ids = ctx.ids or ((ctx.current,) if ctx.current is not None else ())
    base = None
    kept = []
    for node_id in ids:
        node = doc.get(node_id)
        if not isinstance(node, WidgetNode) or node.id == doc.root.id or node.class_name in _SKIPPED:
            return (), None
        declared = doc.custom_widget(node.class_name)
        own = declared.field("extends") if isinstance(declared, CustomWidgetNode) else None
        shown = own if isinstance(own, str) and own else node.class_name
        if base is not None and shown != base:
            return (), None
        base = shown
        kept.append(node_id)
    return tuple(kept), base


def build(ctx: MenuContext) -> None:
    ids, base = _targets(ctx)
    if not ids or base is None:
        return
    doc = ctx.session.document
    action = ctx.menu.addAction(ROW)
    action.setToolTip(TOOLTIP)
    # After the menu has closed: closing it hands focus back to the canvas, which would
    # take it from the popover.
    action.triggered.connect(lambda _checked=False: QTimer.singleShot(0, lambda: _open(ctx, ids)))
    using = [
        doc.get(node_id).class_name  # type: ignore[union-attr]
        for node_id in ids
        if doc.custom_widget(doc.get(node_id).class_name) is not None  # type: ignore[union-attr]
    ]
    if using and len(using) == len(ids):
        friendly = friendly_of(base).lower()
        names = tuple(doc.get(node_id).object_name for node_id in ids)  # type: ignore[union-attr]
        back = ctx.menu.addAction("Back to %s" % friendly)
        back.triggered.connect(lambda _checked=False: ctx.run(UseBaseClass(ids, friendly, names)))


def _open(ctx: MenuContext, ids: Tuple[NodeId, ...]) -> None:
    live = ctx.live(ids[0])
    beside = None
    if live is not None:
        rect = live.rect()
        beside = QRect(live.mapToGlobal(rect.topLeft()), rect.size())
    parent = None if live is None else live.window()
    registry = registry_of(ctx.session)
    open_popover(ctx.session, ids, registry, parent, beside=beside)
