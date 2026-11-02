"""Save light and dark screenshots of every Team Sync surface.

Launch the real main window offscreen against the in-memory fake.
Run: ``CBCS_APPRUN=$HOME/opt/freecad/AppRun python3 tools/team_sync_screens.py``
or through AppRun the same way ``run_tests.py`` launches the editor.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CBCS_TEAM_SYNC_SHOTS"] = "1"
os.environ["CBCS_TEAM_SYNC_FAKE"] = "idle"
os.environ.setdefault("CBCS_DISABLE_BACKGROUND_RUNTIME", "1")

OUT = ROOT / "docs" / "team_sync" / "screens"


def main() -> int:
    from app.qt.QtCore import QPoint
    from app.qt.QtWidgets import QApplication, QDialog

    from app.core import constants
    from app.features.team_sync.core.fake import InMemoryTeamSync
    from app.project.project_service import create_blank_project
    from app.shell.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    state = ROOT / ".screenshot_state"
    state.mkdir(parents=True, exist_ok=True)
    window = MainWindow(state_root=str(state))
    window.resize(1280, 800)
    window.show()
    app.processEvents()
    project = _project(window)
    window._file_project_commands_workflow.open_project_by_path(str(project))
    app.processEvents()
    OUT.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    for theme in ("light", "dark"):
        _theme(window, theme)
        app.processEvents()
        for name, painter in _SHOTS:
            _close_popups()
            try:
                target = painter(window, app)
                app.processEvents()
                widget = target if target is not None else window
                path = OUT / f"{name}_{theme}.png"
                pixmap = widget.grab()
                if pixmap.isNull():
                    missing.append(path.name)
                    continue
                pixmap.save(str(path), "PNG")
                print(path.name, pixmap.width(), pixmap.height(), flush=True)
            except Exception as exc:  # noqa: BLE001 - one shot must not hide the rest
                missing.append(f"{name}_{theme}.png ({exc})")
                print("FAIL", name, theme, exc, flush=True)
    window.close()
    if missing:
        print("Missing screenshots:")
        for item in missing:
            print(" -", item)
        return 1
    print(f"Wrote {len(list(OUT.glob('*.png')))} screenshots to {OUT}")
    os._exit(0)


def _find(window, name: str):  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QApplication, QWidget

    found = window.findChild(QWidget, name)
    if found is not None:
        return found
    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        if widget.objectName() == name:
            return widget
        child = widget.findChild(QWidget, name)
        if child is not None:
            return child
    return None


def _project(window) -> Path:  # type: ignore[no-untyped-def]
    import shutil

    from app.features.team_sync.core.fake import InMemoryTeamSync
    from app.project.project_service import create_blank_project

    root = ROOT / ".screenshot_project"
    if root.exists():
        shutil.rmtree(root)
    create_blank_project(root, project_name="Invoice App")
    service = window._team_sync._controller.service
    files = service.project_files() if isinstance(service, InMemoryTeamSync) else {}
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _theme(window, theme: str) -> None:  # type: ignore[no-untyped-def]
    from app.core import constants

    window._theme_mode = constants.UI_THEME_MODE_DARK if theme == "dark" else constants.UI_THEME_MODE_LIGHT
    window._shell_theme_workflow.apply_theme_styles()


def _service(window):  # type: ignore[no-untyped-def]
    return window._team_sync._controller.service


def _scenario(window, name: str):  # type: ignore[no-untyped-def]
    service = _service(window)
    service.scenario(name)
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def _team(window):  # type: ignore[no-untyped-def]
    window._activity_bar.set_active_view("team")
    window._project_tree_ui_workflow.handle_sidebar_view_changed("team")
    return window.findChild(type(window._team_sync._view), "shell.teamSync.teamView") or window._team_sync._view


def _shot_team(name: str):  # type: ignore[no-untyped-def]
    def paint(window, app):  # type: ignore[no-untyped-def]
        del app
        _scenario(window, name)
        return _team(window)

    return paint


def _send_sheet(window, app):  # type: ignore[no-untyped-def]
    del app
    _scenario(window, "pending")
    window._team_sync._controller.open_send_sheet()
    return _find(window, "shell.teamSync.sendSheet")


def _popover(window, app):  # type: ignore[no-untyped-def]
    del app
    _scenario(window, "incoming")
    window._team_sync._controller.open_status_popover()
    return _find(window, "shell.teamSync.statusPopover")


def _experiment_menu(window, app):  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QMenu

    _scenario(window, "experiments")
    window._team_sync._controller.open_experiment_menu()
    app.processEvents()
    for widget in window.findChildren(QMenu):
        if widget.objectName() == "shell.teamSync.experimentMenu" and widget.isVisible():
            return widget
    return window.findChild(QMenu, "shell.teamSync.experimentMenu")


def _explorer(window, app):  # type: ignore[no-untyped-def]
    del app
    _scenario(window, "pending")
    window._activity_bar.set_active_view("explorer")
    window._project_tree_ui_workflow.handle_sidebar_view_changed("explorer")
    return window._project_tree_widget


def _open_invoice(window):  # type: ignore[no-untyped-def]
    path = str(Path(window._loaded_project.project_root) / "invoice.py")
    window._editor_tab_factory.open_file_in_editor(path)
    return path


def _info_incoming(window, app):  # type: ignore[no-untyped-def]
    del app
    _scenario(window, "incoming")
    _open_invoice(window)
    return _find(window, "shell.teamSync.infoBar") or window._editor_tabs_widget


def _info_clash(window, app):  # type: ignore[no-untyped-def]
    del app
    _scenario(window, "combine_one")
    _open_invoice(window)
    return _find(window, "shell.teamSync.infoBar") or window._editor_tabs_widget


def _toast(window, app):  # type: ignore[no-untyped-def]
    del app
    _scenario(window, "incoming")
    return _find(window, "shell.teamSync.toast") or window


def _review(mode: str):  # type: ignore[no-untyped-def]
    def paint(window, app):  # type: ignore[no-untyped-def]
        from app.shell.diff_view import DIFF_VIEW_MODE_SIDE_BY_SIDE

        _scenario(window, "incoming")
        window._team_sync._controller.open_review()
        app.processEvents()
        tab = window._team_sync._controller._review
        if mode == "side":
            tab._mode.set_selected(DIFF_VIEW_MODE_SIDE_BY_SIDE)
            tab._set_mode(DIFF_VIEW_MODE_SIDE_BY_SIDE)
        if mode == "form":
            for row in range(tab._files.count()):
                if tab._files.item(row).text().endswith(".ui"):
                    tab._files.setCurrentRow(row)
                    break
        return tab

    return paint


def _combine(name: str):  # type: ignore[no-untyped-def]
    def paint(window, app):  # type: ignore[no-untyped-def]
        _scenario(window, name)
        state = _service(window).combine_state()
        window._team_sync._controller._open_combine(state)
        app.processEvents()
        if name == "combine_deleted":
            dialog = _find(window, "shell.teamSync.deletedClashDialog")
            if dialog is not None and dialog.isVisible():
                return dialog
        return window._team_sync._controller._combine

    return paint


def _history(kind: str):  # type: ignore[no-untyped-def]
    def paint(window, app):  # type: ignore[no-untyped-def]
        from app.qt.QtCore import QPoint
        from app.qt.QtWidgets import QMenu

        scenario = "experiments" if kind == "lanes" else "milestones"
        _scenario(window, scenario)
        window._team_sync._controller.open_history()
        app.processEvents()
        tab = window._team_sync._controller._history
        if kind == "menu" and tab._list.count():
            tab._list.setCurrentRow(0)
            tab._menu(QPoint(20, 20))
            app.processEvents()
            menu = window.findChild(QMenu, "shell.teamSync.historyMenu")
            if menu is not None:
                return menu
        return tab

    return paint


def _hover(window, app):  # type: ignore[no-untyped-def]
    from app.qt.QtCore import QPoint

    _scenario(window, "idle")
    _open_invoice(window)
    app.processEvents()
    editor = _find(window, "shell.editorTabs.textEditor")
    callback = getattr(editor, "_line_hover_callback", None) if editor is not None else None
    if callback is not None:
        callback(5, window.mapToGlobal(QPoint(420, 180)))
    return _find(window, "shell.teamSync.hoverCard") or window


def _peek(window, app):  # type: ignore[no-untyped-def]
    _scenario(window, "pending")
    _open_invoice(window)
    app.processEvents()
    editor = _find(window, "shell.editorTabs.textEditor")
    callback = getattr(editor, "_change_mark_callback", None) if editor is not None else None
    if callback is not None:
        callback(5)
    return _find(window, "shell.teamSync.gutterPeek") or editor or window


def _share(window, app):  # type: ignore[no-untyped-def]
    del app
    _scenario(window, "not_shared")
    window._team_sync._controller._dormant = False
    window._team_sync._controller.open_share()
    return _visible_named("shell.teamSync.shareDialog") or window


def _invite(window, app):  # type: ignore[no-untyped-def]
    del app
    _scenario(window, "invite")
    window._team_sync._controller.open_invite()
    return _visible_named("shell.teamSync.inviteDialog") or window


def _members(window, app):  # type: ignore[no-untyped-def]
    del app
    _scenario(window, "idle")
    window._team_sync._controller.open_members()
    return _visible_named("shell.teamSync.membersDialog") or window


def _settings(window, app):  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QDialog, QVBoxLayout

    del app
    dialog = QDialog(window)
    dialog.setWindowTitle("Settings")
    dialog.resize(480, 420)
    layout = QVBoxLayout(dialog)
    layout.addWidget(window._team_sync._controller.settings_group(dialog))
    dialog.show()
    return dialog


def _package(window, app):  # type: ignore[no-untyped-def]
    from app.packaging.config import resolve_project_package_config
    from app.shell.package_wizard_dialog import PackageProjectWizard

    del app
    _scenario(window, "idle")
    loaded = window._loaded_project
    config = resolve_project_package_config(
        project_root=loaded.project_root,
        project_metadata=loaded.metadata,
    )
    wizard = PackageProjectWizard(
        project_root=loaded.project_root,
        project_metadata=loaded.metadata,
        package_config=config,
        parent=window,
        tokens=window._shell_theme_workflow.resolve_theme_tokens(),
    )
    wizard._current_page = 1
    wizard._update_page_chrome()
    wizard.show()
    return wizard


def _visible_named(name: str):  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        if widget.objectName() == name and widget.isVisible():
            return widget
    return None


def _close_popups() -> None:
    from app.qt.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        name = widget.objectName()
        if name.startswith("shell.teamSync") or name.startswith("shell.toast"):
            widget.hide()


_SHOTS = [
    ("team_not_shared", _shot_team("not_shared")),
    ("team_idle", _shot_team("idle")),
    ("team_pending", _shot_team("pending")),
    ("team_delivered", _shot_team("delivered")),
    ("team_incoming", _shot_team("incoming")),
    ("send_sheet", _send_sheet),
    ("status_popover", _popover),
    ("experiment_menu", _experiment_menu),
    ("explorer_letters", _explorer),
    ("info_bar_incoming", _info_incoming),
    ("info_bar_clash", _info_clash),
    ("toast", _toast),
    ("review_inline", _review("inline")),
    ("review_side_by_side", _review("side")),
    ("review_form", _review("form")),
    ("combine_one", _combine("combine_one")),
    ("combine_several", _combine("combine_several")),
    ("combine_form", _combine("combine_form")),
    ("combine_deleted", _combine("combine_deleted")),
    ("history_plain", _history("plain")),
    ("history_lanes", _history("lanes")),
    ("history_menu", _history("menu")),
    ("hover_card", _hover),
    ("gutter_peek", _peek),
    ("share", _share),
    ("invite", _invite),
    ("members", _members),
    ("settings_team", _settings),
    ("package_milestone", _package),
]


if __name__ == "__main__":
    raise SystemExit(main())
