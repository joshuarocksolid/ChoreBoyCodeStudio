"""A banner when rules still name widgets that were renamed outside Code Studio."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.features.form_builder.engine.logic.repair import RepairFix, repair_edits, repair_references, widget_classes
from app.features.form_builder.qtside.dialogs.repair_refs import RepairDialog
from app.qt.QtCore import QTimer
from app.qt.qt_compat import exec_qt

def repair_sentence(count: int) -> str:
    """The banner line. One missing use is singular. The spec line is for more than one."""
    if count == 1:
        return "1 rule points at a widget that was renamed outside Code Studio."
    return "%d rules point at widgets that were renamed outside Code Studio." % count


def register(slots: Any) -> None:
    slots.on_workbench(attach, module=__name__)


def attach(workbench: Any) -> None:
    def later() -> None:
        previous = _previous(workbench)
        if previous is None:
            return
        offer_repair(workbench, previous)

    QTimer.singleShot(0, later)


def offer_repair(workbench: Any, previous: Mapping[str, str]) -> None:
    session = getattr(workbench, "_session", None)
    canvas = getattr(workbench, "canvas", None)
    if session is None or canvas is None or not hasattr(canvas, "show_banner"):
        return
    fixes = repair_references(session.document, previous)
    if not fixes:
        return
    sentence = repair_sentence(len(fixes))

    def repair() -> None:
        _repair(workbench, fixes)

    def done() -> None:
        hide = getattr(canvas, "hide_banner", None)
        if callable(hide):
            hide()

    canvas.show_banner("warning", "Repair", sentence, "Repair\u2026", repair, done)
    _style(workbench)


def _repair(workbench: Any, fixes: Sequence[RepairFix]) -> None:
    session = getattr(workbench, "_session", None)
    dialog = RepairDialog(fixes, workbench, getattr(session, "document", None))
    chrome = _chrome(workbench)
    if chrome is not None:
        dialog.apply_chrome(chrome)
    if not exec_qt(dialog):
        return
    session = getattr(workbench, "_session", None)
    canvas = getattr(workbench, "canvas", None)
    if session is None:
        return
    edits = repair_edits(session.document, fixes, dialog.chosen())
    if edits:
        with session.log.transaction("Repair references") as txn:
            for command in edits:
                txn.execute(command)
    hide = getattr(canvas, "hide_banner", None)
    if callable(hide):
        hide()


def _previous(workbench: Any) -> Optional[Mapping[str, str]]:
    session = getattr(workbench, "_session", None)
    scope = getattr(session, "scope", None)
    path = getattr(scope, "generated_path", None)
    if not path:
        return None
    file = Path(path)
    if not file.is_file():
        return None
    return widget_classes(file.read_text(encoding="utf-8"))


def _chrome(workbench: Any) -> object:
    widget = workbench
    while widget is not None:
        tokens = getattr(widget, "_tokens", None)
        if tokens is not None:
            from app.features.form_builder.integration.chrome import chrome_for

            return chrome_for(tokens)
        parent = getattr(widget, "parent", None)
        widget = parent() if callable(parent) else None
    return None


def _style(workbench: Any) -> None:
    widget = workbench
    while widget is not None:
        style = getattr(widget, "style_banner", None)
        if callable(style):
            style()
            return
        parent = getattr(widget, "parent", None)
        widget = parent() if callable(parent) else None
