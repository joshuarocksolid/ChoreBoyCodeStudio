"""UX-CAT-015: window kinds. Search rows only; they never insert (they open New form)."""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.qtside.insert.catalog._model import WINDOW, WINDOW_CATEGORY, Entry, Registry


def _kind(key: str, name: str, qt_class: str, synonyms: Tuple[str, ...], glyph: str, sentence: str) -> Entry:
    return Entry(
        "window:" + key, name + " · new form", qt_class, WINDOW_CATEGORY, "", sentence,
        synonyms, glyph, WINDOW, None,
    )


def entries() -> Tuple[Entry, ...]:
    return (
        _kind("main", "Main window", "QMainWindow", ("mainwindow", "main window form"), "window_main",
              "Opens a new main window form."),
        _kind("dialog", "Dialog", "QDialog", ("dialogform",), "window_dialog",
              "Opens a new dialog form."),
        _kind("widget", "Widget", "QWidget", ("widgetform", "widget form"), "window_widget",
              "Opens a new widget form."),
        _kind("wizard", "Wizard", "QWizard", ("wizardform",), "window_wizard",
              "Opens a new wizard form."),
    )


def register(registry: Registry) -> None:
    registry.family("QMainWindow", "Main window")
    registry.family("QDialog", "Dialog")
    registry.family("QWizard", "Wizard")
    for entry in entries():
        registry.add(entry)
