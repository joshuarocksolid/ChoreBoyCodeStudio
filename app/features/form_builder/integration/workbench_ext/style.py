"""Opens the style sheet drawer under the canvas (M5.3, UX-STYLE-001, UX-STYLE-002).

The drawer is made the first time something asks for it (the Style sheet row,
the context menu, Form > Style sheet of the form, a Problems button) and kept
for the life of the workbench.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.integration.workbench_ext._style_memory import DrawerHeight
from app.features.form_builder.qtside.style import gateway
from app.features.form_builder.qtside.style.drawer import DrawerHooks, StyleDrawer
from app.features.form_builder.qtside.theme.chrome import default_chrome
from app.qt.QtCore import QTimer
from app.qt.QtWidgets import QPlainTextEdit, QWidget

logger = logging.getLogger(__name__)

KEY = "style"
LAYER = "style_matches"


def register(slots: Any) -> None:
    slots.on_workbench(attach, module=__name__)


def attach(workbench: Any) -> None:
    try:
        session = workbench.outline.session()
    except (AssertionError, AttributeError):
        return
    controller = _Controller(workbench, session)
    gateway.register_opener(session, controller.open)
    workbench.destroyed.connect(lambda *_args: controller.dispose())


def make_editor(parent: QWidget) -> QPlainTextEdit:
    """The shell's code editor with CSS highlighting, or a plain text edit when the shell's is unavailable."""
    try:
        from app.editors.code_editor_widget import CodeEditorWidget

        editor = CodeEditorWidget(parent)
        editor.set_language_for_path("style.css")
        window = parent.window()
        workflow = getattr(window, "_shell_theme_workflow", None)
        if workflow is not None:
            editor.apply_theme(workflow.resolve_theme_tokens())
        return editor
    except Exception:
        logger.exception("style sheet drawer could not make the code editor")
        return QPlainTextEdit(parent)


class _Controller:
    def __init__(self, workbench: Any, session: Any) -> None:
        self._workbench = workbench
        self._session = session
        self._drawer: Optional[StyleDrawer] = None
        self._memory: Optional[DrawerHeight] = None

    def dispose(self) -> None:
        gateway.forget_opener(self._session)
        drawer, self._drawer = self._drawer, None
        if drawer is not None:
            drawer.dispose()

    def _height(self) -> DrawerHeight:
        if self._memory is None:
            root = getattr(self._workbench.window(), "_state_root", None)
            self._memory = DrawerHeight(str(root) if root else None)
        return self._memory

    def open(self, node_id: Optional[NodeId]) -> bool:
        workbench = self._workbench
        drawer = self._ensure()
        target = node_id if node_id is not None else self._selected()
        if workbench.under_canvas_key() != KEY:
            if not workbench.open_under_canvas(KEY, drawer, height=self._height().load()):
                return False
            workbench.set_under_canvas_listener(self._height().save)
        drawer.show_for(target)
        return True

    def _selected(self) -> NodeId:
        document = self._session.document
        ids = [i for i in self._session.selection.state.ids if isinstance(document.get(i), WidgetNode)]
        return ids[0] if len(ids) == 1 else document.root.id

    def _ensure(self) -> StyleDrawer:
        if self._drawer is not None:
            return self._drawer
        workbench = self._workbench
        editor = make_editor(workbench)
        hooks = DrawerHooks(
            chrome=self._chrome,
            show_matches=self._show_matches,
            narrate=self._narrate,
            closed=self._closed,
            pick_picture=self._pick_picture,
        )
        self._drawer = StyleDrawer(self._session, editor, hooks, workbench)
        return self._drawer

    def _chrome(self) -> Any:
        services = getattr(getattr(self._workbench, "inspector", None), "_services", None)
        chrome = getattr(services, "chrome", None)
        return chrome if chrome is not None else default_chrome()

    def _show_matches(self, ids: tuple) -> None:
        canvas = self._workbench.canvas
        if ids:
            canvas.show_layer(LAYER, tuple(ids))
        else:
            canvas.hide_layer(LAYER)

    def _narrate(self, sentence: str) -> None:
        widget: Optional[QWidget] = self._workbench
        while widget is not None:
            narrate = getattr(widget, "narrate", None)
            if callable(narrate) and widget is not self._workbench:
                narrate(sentence)
                return
            widget = widget.parentWidget()

    def _closed(self, target: Optional[NodeId]) -> None:
        del target
        workbench = self._workbench
        if workbench.under_canvas_key() == KEY:
            workbench.close_under_canvas()
        QTimer.singleShot(0, self._focus_row)

    def _focus_row(self) -> None:
        inspector = getattr(self._workbench, "inspector", None)
        button = inspector.findChild(QWidget, "formBuilder.styleEdit") if inspector is not None else None
        if button is not None and button.isVisible():
            button.setFocus()
        else:
            self._workbench.canvas.setFocus()

    def _pick_picture(self, parent: QWidget) -> str:
        from app.features.form_builder.integration.workbench_ext._style_picture import pick_picture

        return pick_picture(self._session, self._chrome(), parent)
