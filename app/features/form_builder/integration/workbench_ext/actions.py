"""The Actions section of the left pane (UX-MAIN-010). Alt+5 focuses it."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.integration.workbench_ext import LeftSection
from app.features.form_builder.qtside.actions.pane import ActionsPane
from app.qt.QtWidgets import QMessageBox


def _shown(session: Any) -> bool:
    """On a main window, or on any form that already has an action."""
    doc = session.document
    return q.is_main_window(doc) or bool(q.all_actions(doc))


def _confirm(parent: Any, sentence: str, ok: str) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(sentence)
    accept = box.addButton(ok, QMessageBox.ButtonRole.AcceptRole)
    cancel = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.exec()
    return box.clickedButton() is accept


def _build(workbench: Any) -> ActionsPane:
    holder: dict = {}

    def say(sentence: str) -> None:
        status = getattr(workbench.outline, "_status", None)
        if callable(status):
            status(sentence)

    pane = ActionsPane(
        workbench._session,
        say,
        lambda sentence, ok: _confirm(holder.get("pane"), sentence, ok),
        None,
    )
    holder["pane"] = pane
    return pane


def _focus(widget: Any) -> None:
    widget.focus_tree()


def register(slots: Any) -> None:
    slots.add_left_section(
        LeftSection(
            "actions",
            "Actions",
            _build,
            order=30,
            weight=25,
            shown=_shown,
            keys="Alt+5",
            focus=_focus,
        )
    )
