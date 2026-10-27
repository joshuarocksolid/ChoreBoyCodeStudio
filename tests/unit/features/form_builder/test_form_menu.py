"""The Form menu comes from the command table and stays hidden off a form tab."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import Qt  # noqa: E402
from app.qt.QtWidgets import QMenu, QMenuBar, QShortcut, QTreeWidget, QTreeWidgetItem, QWidget  # noqa: E402
from app.shell.menus import build_menu_stubs, clear_menu_contributors  # noqa: E402
from app.shell.shortcut_preferences import (  # noqa: E402
    SHORTCUT_COMMANDS,
    ShortcutCommand,
    clear_extra_shortcut_commands,
    default_shortcut_map,
    parse_shortcut_overrides,
    register_shortcut_commands,
)

from app.features.form_builder.engine.shell_commands import shortcut_rows  # noqa: E402
from app.features.form_builder.integration.form_menu import register_form_menu  # noqa: E402
from app.intelligence.diagnostics_models import CodeDiagnostic  # noqa: E402
from app.shell.problems_panel import ProblemsPanel  # noqa: E402
from app.features.form_builder.integration.problems_bridge import code_diagnostics_for_form  # noqa: E402
from app.features.form_builder.engine.diagnostics import (  # noqa: E402
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from tests.unit.features.form_builder.test_workbench import _FORM, _open  # noqa: E402

pytestmark = pytest.mark.unit


def test_form_shortcuts_join_the_shell_table() -> None:
    register_shortcut_commands(
        tuple(
            ShortcutCommand(action_id, label, shortcut, category)
            for action_id, label, shortcut, category in shortcut_rows()
        )
    )
    try:
        assert default_shortcut_map()["form.action.zoomToFit"] == "Ctrl+9"
        parsed = parse_shortcut_overrides(
            {"keybindings": {"overrides": {"form.action.zoomToFit": "Ctrl+8"}}}
        )
        assert parsed["form.action.zoomToFit"] == "Ctrl+8"
    finally:
        clear_extra_shortcut_commands()


def test_form_menu_sits_after_view_and_stays_hidden(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    window = QWidget()
    register_form_menu(window)
    bar = QMenuBar(window)
    try:
        registry = build_menu_stubs(bar)
        titles = [action.text().replace("&", "") for action in bar.actions()]
        assert titles.index("Form") == titles.index("View") + 1
        assert titles.index("Tools") == titles.index("Form") + 1
        form = registry.menus["formBuilder.menu"]
        assert not form.menuAction().isVisible()
        assert not registry.actions["form.action.insert"].isEnabled()
    finally:
        clear_menu_contributors()
        window.deleteLater()


def test_widget_keys_are_menu_hints_and_not_window_shortcuts(qapp) -> None:  # type: ignore[no-untyped-def]
    """A window-scope form action must not share a key with a shell action."""
    del qapp
    shell_keys = {command.default_shortcut for command in SHORTCUT_COMMANDS if command.default_shortcut}
    window = QWidget()
    register_form_menu(window)
    bar = QMenuBar(window)
    try:
        registry = build_menu_stubs(bar)
        shortcut_context = getattr(Qt, "ShortcutContext", Qt)
        window_scope = {
            getattr(shortcut_context, "WindowShortcut"),
            getattr(shortcut_context, "ApplicationShortcut"),
        }
        shared = []
        for action_id, action in registry.actions.items():
            if not str(action_id).startswith("form.action."):
                continue
            key = action.shortcut().toString()
            if key and action.shortcutContext() in window_scope and key in shell_keys:
                shared.append("%s %s" % (action_id, key))
        assert shared == []
        horizontal = registry.actions["form.action.layoutHorizontal"]
        assert horizontal.shortcut().isEmpty()
        assert "Ctrl+1" in horizontal.text()
        insert = registry.actions["form.action.insert"]
        assert insert.shortcut().isEmpty()
        assert "/" in insert.text()
        goto = registry.actions["form.action.goToWidget"]
        assert goto.shortcut().isEmpty()
        assert "Ctrl+R" in goto.text()
        view_xml = registry.actions["form.action.viewXml"]
        assert view_xml.shortcut().isEmpty()
        assert "Ctrl+Shift+V" in view_xml.text()
        zoom_fit = registry.actions["form.action.zoomToFit"]
        assert zoom_fit.shortcut().isEmpty()
        assert "Ctrl+9" in zoom_fit.text()
    finally:
        clear_menu_contributors()
        window.deleteLater()


def test_the_layout_menu_lists_horizontal_before_vertical(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    window = QWidget()
    register_form_menu(window)
    bar = QMenuBar(window)
    try:
        build_menu_stubs(bar)
        layout = window.findChild(QMenu, "formBuilder.menu.Layout")
        assert layout is not None
        labels = [action.text().replace("&", "") for action in layout.actions()]
        horizontal = next(index for index, label in enumerate(labels) if label.startswith("Horizontal\t"))
        vertical = next(index for index, label in enumerate(labels) if label.startswith("Vertical\t"))
        assert horizontal < vertical
    finally:
        clear_menu_contributors()
        window.deleteLater()


def test_layout_horizontal_is_a_canvas_shortcut(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Ctrl+1 is bound on the canvas, not as a window action."""
    del qapp
    parent = QWidget()
    surface = _open(parent, _FORM, tmp_path / "invoice.ui")
    try:
        canvas = surface.findChild(QWidget, "formBuilder.canvas")
        assert canvas is not None
        matches = [
            shortcut
            for shortcut in canvas.findChildren(QShortcut)
            if shortcut.key().toString() == "Ctrl+1"
        ]
        assert matches
        context = getattr(Qt, "WidgetWithChildrenShortcut")
        assert all(shortcut.context() == context for shortcut in matches)
    finally:
        surface.release()
        parent.deleteLater()


def test_form_menu_enables_only_commands_that_exist(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    parent = QWidget()
    surface = _open(parent, _FORM, tmp_path / "invoice.ui")

    class _Tab:
        def __init__(self, path: str) -> None:
            self.file_path = path

    class _Manager:
        def active_tab(self) -> _Tab:
            return _Tab(surface.form_path())

    class _Registry:
        def surface_for_path(self, path: str) -> object:
            del path
            return surface

    window = QWidget()
    window._editor_manager = _Manager()  # type: ignore[attr-defined]
    window._tab_content_registry = _Registry()  # type: ignore[attr-defined]
    register_form_menu(window)
    bar = QMenuBar(window)
    try:
        registry = build_menu_stubs(bar)
        form = registry.menus["formBuilder.menu"]
        assert form.menuAction().isVisible()
        assert registry.actions["form.action.viewXml"].isEnabled()
        assert registry.actions["form.action.viewXml"].shortcut().isEmpty()
        assert not registry.actions["form.action.insert"].isEnabled()
        for action in form.actions():
            label = action.text()
            assert "M2" not in label
            assert "M3" not in label
            assert "M5" not in label
            assert "M6" not in label
        out = Path(os.environ.get("CBCS_FB_SCREENSHOT_DIR") or tmp_path)
        out.mkdir(parents=True, exist_ok=True)
        window.resize(900, 40)
        window.show()
        form.popup(bar.mapToGlobal(bar.rect().bottomLeft()))
        qapp.processEvents()
        form.grab().save(str(out / "form-menu.png"))
        form.hide()
    finally:
        clear_menu_contributors()
        surface.release()
        window.deleteLater()


def test_problems_panel_shows_a_form_row(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    diagnostic = FormDiagnostic(
        code="FB003",
        severity=Severity.ERROR,
        message="This name is already used.",
        location=DiagnosticLocation(object_name="email", line=4),
        source="reader",
    )
    rows = code_diagnostics_for_form("/work/invoice.ui", (diagnostic,))
    assert rows and isinstance(rows[0], CodeDiagnostic)
    panel = ProblemsPanel()
    panel.resize(720, 180)
    panel.show()
    panel.set_diagnostics(rows)
    qapp.processEvents()
    tree = panel.findChild(QTreeWidget)
    assert tree is not None
    labels = []

    def walk(item: QTreeWidgetItem) -> None:
        labels.append(item.text(1))
        labels.append(item.text(2))
        for index in range(item.childCount()):
            child = item.child(index)
            if child is not None:
                walk(child)

    root = tree.invisibleRootItem()
    assert root is not None
    walk(root)
    assert any("email: This name is already used." in label for label in labels)
    assert "email" in labels
    out = Path(os.environ.get("CBCS_FB_SCREENSHOT_DIR") or tmp_path)
    out.mkdir(parents=True, exist_ok=True)
    panel.grab().save(str(out / "problems-form-row.png"))
    panel.deleteLater()
