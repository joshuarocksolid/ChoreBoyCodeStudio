"""View Python code: the read-only split beside the canvas (M5.5a, UX-PREV-004, D22, R3 181).

Form > View Python code and Ctrl+K, C toggle the split. The text is the module
the preview and Save generate (``generate_form_module``), built in memory from
the current, unsaved form 300 ms after the last change. Selecting a widget
scrolls the code to the line that creates it and marks its lines; a click on a
code line that names a widget selects that widget. Nothing here writes a file or
a command to the undo stack.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from typing import Any, Optional, Tuple

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.names import ui_basename_ok
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.qtside.code_view.lines import CodeIndex
from app.features.form_builder.qtside.code_view.panel import CodeViewPanel
from app.qt.QtCore import QTimer
from app.qt.QtWidgets import QWidget

logger = logging.getLogger(__name__)

KEY = "code"
CHANGE_MS = 300
TOO_NARROW = "Make the window wider to see the code beside the form."
NOT_GENERATED = "The code can't be shown for this form."


def register(slots: Any) -> None:
    slots.on_workbench(attach, module=__name__)


def attach(workbench: Any) -> None:
    try:
        session = workbench.outline.session()
    except (AssertionError, AttributeError):
        return
    controller = CodeViewController(workbench, session)
    workbench.code_view = controller
    workbench.destroyed.connect(lambda *_args: controller.dispose())


def view_scope(scope: FormScope, form_path: str) -> FormScope:
    """The scope to generate for. A form that is not in a project is shown as it would be written beside it."""
    if scope.generates:
        return scope
    path = os.path.abspath(scope.ui_path or form_path or "form.ui")
    stem = os.path.splitext(os.path.basename(path))[0]
    folder = os.path.dirname(path)
    return dataclasses.replace(
        scope,
        kind="project",
        ui_path=path,
        generated_path=os.path.join(folder, "ui_%s.py" % stem),
        window_path=os.path.join(folder, "%s_window.py" % stem),
        module_name="ui_%s" % stem,
        window_module_name="%s_window" % stem,
    )


def generate_view(session: Any, form_path: str) -> Tuple[Optional[str], str]:
    """``(text, "")`` for the current form, or ``(None, sentence)`` when it cannot be generated."""
    scope = view_scope(session.scope, form_path)
    basename = os.path.basename(scope.ui_path)
    if not ui_basename_ok(basename):
        stem_note = 'The file name "%s" can\'t be a Python module.' % basename
        return None, stem_note
    made = generate_form_module(session.document, scope=scope, source_bytes=None)
    if made.text is not None:
        return made.text, ""
    for diagnostic in made.diagnostics:
        if diagnostic.message:
            return None, diagnostic.message
    return None, NOT_GENERATED


class CodeViewController:
    def __init__(self, workbench: Any, session: Any) -> None:
        self._workbench = workbench
        self._session = session
        self._panel: Optional[CodeViewPanel] = None
        self._index = CodeIndex("")
        self._selecting = False
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(CHANGE_MS)
        self._timer.timeout.connect(self.refresh)
        self._log_sub = session.log.subscribe(self._changed, priority=960)
        self._selection_unsub = session.selection.subscribe(self._selection_changed)

    # ---- state

    @property
    def panel(self) -> Optional[CodeViewPanel]:
        return self._panel

    def is_open(self) -> bool:
        return self._workbench.beside_canvas_key() == KEY

    def dispose(self) -> None:
        try:
            self._timer.stop()
        except RuntimeError:
            pass
        self._log_sub.close()
        self._selection_unsub()

    # ---- open and close

    def toggle(self) -> bool:
        """Open or close the split. True when it is open afterwards."""
        if self.is_open():
            self.close()
            return False
        return self.open()

    def open(self) -> bool:
        if self.is_open():
            return True
        panel = self._ensure()
        if not self._workbench.open_beside_canvas(KEY, panel):
            self._say(TOO_NARROW)
            return False
        self._retheme(panel)
        self.refresh()
        self._mark_selection(scroll=True)
        panel.setFocus()
        return True

    def close(self, *, focus_canvas: bool = True) -> None:
        if not self.is_open():
            return
        self._timer.stop()
        self._workbench.close_beside_canvas()
        if focus_canvas:
            self._workbench.canvas.setFocus()

    # ---- content

    def refresh(self) -> None:
        panel = self._panel
        if panel is None or not self.is_open() or self._session.disposed:
            return
        path = self._form_path()
        text, problem = generate_view(self._session, path)
        scope = view_scope(self._session.scope, path)
        module_file = os.path.basename(scope.generated_path or "") or "ui_form.py"
        saved = bool(scope.generated_path) and self._session.scope.generates and os.path.isfile(scope.generated_path)
        panel.set_header(module_file, can_open=saved)
        if text is None:
            self._index = CodeIndex("")
            panel.show_error(problem)
            return
        self._index = CodeIndex(text)
        panel.show_code(text)
        self._mark_selection(scroll=False)

    def _changed(self, _change: object) -> None:
        if self.is_open():
            self._timer.start()

    def _form_path(self) -> str:
        surface = self._surface()
        getter = getattr(surface, "form_path", None)
        return str(getter()) if callable(getter) else str(getattr(self._session, "path", ""))

    # ---- selection and marks

    def _selection_changed(self, _change: object) -> None:
        if self.is_open():
            self._mark_selection(scroll=not self._selecting)

    def _selected_names(self) -> Tuple[str, ...]:
        document = self._session.document
        names = []
        for node_id in self._session.selection.state.ids:
            node = document.get(node_id)
            name = getattr(node, "object_name", "") or getattr(node, "name", "")
            if isinstance(name, str) and name:
                names.append(name)
        return tuple(names)

    def _mark_selection(self, *, scroll: bool) -> None:
        panel = self._panel
        if panel is None or panel.error_text():
            return
        lines = []
        target: Optional[int] = None
        for name in self._selected_names():
            lines.extend(self._index.lines_of(name))
            if target is None:
                target = self._index.first_line(name)
        panel.mark(tuple(sorted(set(lines))), target if scroll else None)

    def _line_clicked(self, line: int) -> None:
        name = self._index.name_on(line)
        if not name:
            return
        found = self._session.document.by_name(name)
        if not found or tuple(self._session.selection.state.ids) == (found[0],):
            return
        self._selecting = True
        try:
            self._session.selection.set((found[0],), source=SelectionSource.PROGRAM)
        finally:
            self._selecting = False

    # ---- plumbing

    def _ensure(self) -> CodeViewPanel:
        if self._panel is not None:
            return self._panel
        panel = CodeViewPanel(self._workbench)
        panel.close_requested.connect(self.close)
        panel.open_file_requested.connect(self._open_file)
        panel.line_clicked.connect(self._line_clicked)
        self._panel = panel
        return panel

    def _open_file(self) -> None:
        scope = self._session.scope
        path = scope.generated_path
        window = self._workbench.window()
        factory = getattr(window, "_editor_tab_factory", None)
        if path and factory is not None and os.path.isfile(path):
            factory.open_file_in_editor(path)

    def _surface(self) -> Optional[QWidget]:
        widget: Optional[QWidget] = self._workbench.parentWidget()
        while widget is not None:
            if callable(getattr(widget, "narrate", None)):
                return widget
            widget = widget.parentWidget()
        return None

    def _say(self, sentence: str) -> None:
        surface = self._surface()
        if surface is not None:
            surface.narrate(sentence)  # type: ignore[attr-defined]

    def _retheme(self, panel: CodeViewPanel) -> None:
        tokens = getattr(self._surface(), "_tokens", None)
        if tokens is not None:
            try:
                panel.apply_theme(tokens)
            except Exception:
                logger.exception("the code view could not apply the theme")

    def apply_theme(self, tokens: Any) -> None:
        if self._panel is not None:
            self._panel.apply_theme(tokens)


__all__ = ["CHANGE_MS", "CodeViewController", "TOO_NARROW", "generate_view", "view_scope"]
