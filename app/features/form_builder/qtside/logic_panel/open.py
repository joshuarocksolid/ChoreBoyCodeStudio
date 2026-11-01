"""Open the Behavior row a Logic panel line names, or Uses of the focused name."""

from __future__ import annotations

import os
from typing import Any, Optional

from app.qt.QtWidgets import QApplication, QWidget

from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.uses import Use, collect, of_name
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.logic_panel.uses_view import UsesDialog, displays_for

_PLACE = "formBuilder.events.place"
_NEED = "Select a widget, a method, or a logic row first."


def open_use(surface: Any, use: Use) -> None:
    """Select the anchor widget and open the rule, check or step it names."""
    widget = use.widget
    if use.kind == "rule":
        surface.select_object(widget)
        from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row

        open_state_row(_inspector(surface), use.property_key)
        return
    if use.kind == "check":
        surface.select_object(widget)
        inspector = _inspector(surface)
        _focus_behavior(inspector)
        flush = getattr(inspector, "flush", None)
        if callable(flush):
            flush()
        body = inspector.findChild(QWidget, "formBuilder.checks") if inspector is not None else None
        focus = getattr(body, "focus_check", None)
        if callable(focus):
            focus(use.index)
        return
    if use.kind == "step":
        surface.open_logic(widget, (use.property_key, use.index))
        return
    if use.kind == "code":
        surface.select_object(widget)


def show_uses(surface: Any) -> None:
    """Shift+F12. The focused method, else the focused logic row, else the one selected widget."""
    name = _focused_method() or _focused_anchor() or _selected_name(surface)
    if not name:
        narrate = getattr(surface, "narrate", None)
        if callable(narrate):
            narrate(_NEED)
        return
    book = _book(surface)
    uses = of_name(book, name) if book is not None else ()
    source, _relative = _window_text(surface)
    shown = _display(surface, name)
    previous = getattr(surface, "_logic_uses", None)
    if previous is not None:
        # A closed dialog stays a child and would be the next findChild hit.
        rename = getattr(previous, "setObjectName", None)
        if callable(rename):
            rename("")
        close = getattr(previous, "close", None)
        if callable(close):
            close()
        later = getattr(previous, "deleteLater", None)
        if callable(later):
            later()
    parent = surface.window() if hasattr(surface, "window") else surface
    dialog = UsesDialog(
        name,
        shown,
        uses,
        source.splitlines(),
        displays_for(_env(surface)),
        _tokens(surface),
        parent,
        _code_family(surface),
    )
    surface._logic_uses = dialog  # type: ignore[attr-defined]
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


def arm_method_rename(widget: QWidget, method: str) -> None:
    """Arm the rename hook with this method, then open the shell preview."""
    if not method:
        return
    surface = widget
    while surface is not None and not (
        getattr(surface, "session", None) is not None and callable(getattr(surface, "logic_window_file", None))
    ):
        surface = surface.parentWidget()
    window = widget.window()
    hook = getattr(window, "_form_builder_method_rename", None)
    arm = getattr(hook, "arm", None)
    if surface is None or not callable(arm):
        return
    arm(surface, method)
    registry_of = getattr(window, "menu_registry", None)
    registry = registry_of() if callable(registry_of) else registry_of
    action_of = getattr(registry, "action", None)
    action = action_of("shell.action.edit.renameSymbol") if callable(action_of) else None
    if action is not None and action.isEnabled():
        action.trigger()
        return
    workflow = getattr(window, "_semantic_navigation_workflow", None)
    run = getattr(workflow, "handle_rename_symbol_action", None)
    if callable(run):
        run()
        return
    clear = getattr(hook, "clear", None)
    if callable(clear):
        clear()


def _display(surface: Any, name: str) -> str:
    return displays_for(_env(surface)).get(name) or name


def _env(surface: Any) -> object:
    session = getattr(surface, "session", None)
    document = getattr(session, "document", None) if session is not None else None
    if document is None:
        return None
    return env_for(document, None, QtClassTable.shared())


def _code_family(surface: Any) -> str:
    from app.core.constants import UI_EDITOR_FONT_FAMILY_DEFAULT

    window = surface.window() if hasattr(surface, "window") else None
    family = getattr(window, "_editor_font_family", "") if window is not None else ""
    if isinstance(family, str) and family.strip():
        return family.strip()
    return UI_EDITOR_FONT_FAMILY_DEFAULT


def _book(surface: Any) -> object:
    panel = surface.findChild(QWidget, "formBuilder.logic") if hasattr(surface, "findChild") else None
    ready = getattr(panel, "book", None)
    if callable(ready):
        found = ready()
        if found is not None:
            return found
    session = getattr(surface, "session", None)
    document = getattr(session, "document", None) if session is not None else None
    if document is None:
        return None
    source, relative = _window_text(surface)
    env = env_for(document, None, QtClassTable.shared())
    return collect(document, env, source, relative)


def _window_text(surface: Any) -> tuple:
    ask = getattr(surface, "logic_window_file", None)
    base = ask() if callable(ask) else ""
    if not isinstance(base, str):
        base = ""
    folder = os.path.dirname(str(getattr(surface, "_path", "") or ""))
    if not base or not folder:
        return "", base or ""
    path = os.path.join(folder, base)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read(), base
    except OSError:
        return "", base


def _tokens(surface: Any) -> object:
    panel = surface.findChild(QWidget, "formBuilder.logic") if hasattr(surface, "findChild") else None
    tokens = getattr(panel, "tokens", None)
    if tokens is not None:
        return tokens
    return getattr(surface, "_tokens", None)


def _inspector(surface: Any) -> Any:
    workbench = getattr(surface, "workbench", None)
    if workbench is None:
        workbench = getattr(surface, "_workbench", None)
    return getattr(workbench, "inspector", None)


def _focus_behavior(inspector: Any) -> None:
    if inspector is None:
        return
    from app.features.form_builder.qtside.inspector.pane import TabId

    focus = getattr(inspector, "focus_tab", None)
    if callable(focus):
        focus(TabId.BEHAVIOR)


def _focused_method() -> str:
    widget: Optional[QWidget] = QApplication.focusWidget()
    while widget is not None:
        method = getattr(widget, "method_name", "") or ""
        if method and widget.objectName() != _PLACE:
            return str(method)
        widget = widget.parentWidget()
    return ""


def _focused_anchor() -> str:
    widget: Optional[QWidget] = QApplication.focusWidget()
    while widget is not None:
        use = getattr(widget, "use", None)
        if isinstance(use, Use):
            return use.widget
        widget = widget.parentWidget()
    return ""


def _selected_name(surface: Any) -> str:
    session = getattr(surface, "session", None)
    if session is None:
        return ""
    ids = session.selection.state.ids
    if len(ids) != 1:
        return ""
    node = session.document.get(ids[0])
    name = getattr(node, "object_name", "") or ""
    return name if isinstance(name, str) else ""
