"""UX-CAT-015: window kinds. Search rows only; they never insert (they open New form).

UX-MAIN-002: the three main-window parts are search rows too. They add the part to the
current main window (key ``part:…``); on a form that is not a main window they say why.
"""

from __future__ import annotations

from typing import Tuple

from app.features.form_builder.qtside.insert.catalog._model import WINDOW, WINDOW_CATEGORY, Entry, Registry


def _kind(key: str, name: str, qt_class: str, synonyms: Tuple[str, ...], glyph: str, sentence: str) -> Entry:
    return Entry(
        "window:" + key, name + " · new form", qt_class, WINDOW_CATEGORY, "", sentence,
        synonyms, glyph, WINDOW, None,
    )


PART_PREFIX = "part:"


def _part(key: str, name: str, qt_class: str, synonyms: Tuple[str, ...], glyph: str, sentence: str) -> Entry:
    return Entry(
        PART_PREFIX + key, name + " · add to this window", qt_class, WINDOW_CATEGORY, "", sentence,
        synonyms, glyph, WINDOW, None,
    )


def parts() -> Tuple[Entry, ...]:
    return (
        _part("menubar", "Menu bar", "QMenuBar", ("menubar", "menus"), "part_menubar",
              "Adds a menu bar to this main window."),
        _part("toolbar", "Toolbar", "QToolBar", ("toolbar", "tool bar", "buttons"), "part_toolbar",
              "Adds a toolbar to this main window."),
        _part("statusbar", "Status bar", "QStatusBar", ("statusbar", "status line"), "part_statusbar",
              "Adds a status bar to this main window."),
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
    ) + parts()


def register(registry: Registry) -> None:
    registry.family("QMainWindow", "Main window")
    registry.family("QDialog", "Dialog")
    registry.family("QWizard", "Wizard")
    registry.family("QMenuBar", "Menu bar")
    registry.family("QToolBar", "Toolbar")
    registry.family("QStatusBar", "Status bar")
    for entry in entries():
        registry.add(entry)
