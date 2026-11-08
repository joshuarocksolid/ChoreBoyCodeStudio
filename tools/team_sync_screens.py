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
    window.resize(1400, 860)
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
        for name, painter in _SHOTS + _WINDOW_SHOTS:
            _close_popups()
            if name.startswith("window_"):
                _quiet(window)
            try:
                target = painter(window, app)
                _pump(app)
                whole = name.startswith("window_")
                widget = window if whole or target is None else target
                path = OUT / f"{name}_{theme}.png"
                pixmap = _grab(window, widget) if whole else widget.grab()
                if pixmap.isNull():
                    missing.append(path.name)
                    continue
                pixmap.save(str(path), "PNG")
                print(path.name, pixmap.width(), pixmap.height(), flush=True)
            except Exception as exc:  # noqa: BLE001 - one shot must not hide the rest
                missing.append(f"{name}_{theme}.png ({exc})")
                print("FAIL", name, theme, exc, flush=True)
    missing.extend(_capture_real(app))
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


def _pump(app, times: int = 4) -> None:  # type: ignore[no-untyped-def]
    for _ in range(times):
        app.processEvents()


def _grab(window, widget):  # type: ignore[no-untyped-def]
    """Grab the window and paint any Team Sync popup that lives in its own window."""
    from app.qt.QtCore import QPoint
    from app.qt.QtGui import QPainter
    from app.qt.QtWidgets import QApplication

    window.repaint()
    base = widget.grab()
    app = QApplication.instance()
    if app is None:
        return base
    painter = QPainter(base)
    origin = window.mapToGlobal(QPoint(0, 0))
    for popup in app.topLevelWidgets():
        if popup is window or not popup.isVisible():
            continue
        name = popup.objectName()
        if not (name.startswith("shell.teamSync") or name.startswith("shell.toast")):
            continue
        pos = popup.mapToGlobal(QPoint(0, 0))
        painter.drawPixmap(pos.x() - origin.x(), pos.y() - origin.y(), popup.grab())
    painter.end()
    return base


def _theme(window, theme: str) -> None:  # type: ignore[no-untyped-def]
    from app.core import constants
    from app.qt.QtWidgets import QApplication

    window._theme_mode = constants.UI_THEME_MODE_DARK if theme == "dark" else constants.UI_THEME_MODE_LIGHT
    window._shell_theme_workflow.apply_theme_styles()
    app = QApplication.instance()
    if app is not None:
        _pump(app)
    window.repaint()


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


def _delivered_popover(window, app):  # type: ignore[no-untyped-def]
    del app
    _scenario(window, "delivered")
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
        from app.shell.diff_view import DIFF_VIEW_MODE_INLINE

        chosen = DIFF_VIEW_MODE_SIDE_BY_SIDE if mode == "side" else DIFF_VIEW_MODE_INLINE
        tab._mode.set_selected(chosen)
        tab._diff.set_mode(chosen)
        _pump(app)
        if mode == "form":
            for row, diff in enumerate(tab._diffs):
                if diff.path.endswith(".ui"):
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
        local = QPoint(4, 30)
        callback(5, editor.mapToGlobal(local) if editor is not None else window.mapToGlobal(local), local)
    _pump(app)
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
    dialog.setObjectName("shell.teamSync.settingsDialog")
    dialog.setWindowTitle("Settings")
    dialog.resize(520, 420)
    dialog.setStyleSheet(window.styleSheet())
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


def _quiet(window) -> None:  # type: ignore[no-untyped-def]
    from app.qt.QtWidgets import QWidget

    for name in (
        "shell.teamSync.toast",
        "shell.toast",
        "shell.teamSync.gutterPeek",
        "shell.teamSync.hoverCard",
        "shell.teamSync.infoBar",
        "shell.teamSync.statusPopover",
        "shell.teamSync.sendSheet",
    ):
        for found in window.findChildren(QWidget, name):
            found.hide()
    tabs = getattr(window, "_editor_tabs_widget", None)
    if tabs is None:
        return
    for index in range(tabs.count() - 1, -1, -1):
        if tabs.tabText(index).startswith(("Review", "Combine", "History")):
            page = tabs.widget(index)
            tabs.removeTab(index)
            if page is not None:
                page.hide()


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


def _window_history(window, app):  # type: ignore[no-untyped-def]
    from app.qt.QtCore import QPoint

    _scenario(window, "experiments")
    window._team_sync._controller.open_history()
    _pump(app)
    tab = window._team_sync._controller._history
    if tab is not None and tab._list.count():
        tab._list.setCurrentRow(0)
        tab._menu(QPoint(24, 36))
        _pump(app)
    return window


def _window_incoming(window, app):  # type: ignore[no-untyped-def]
    _scenario(window, "incoming")
    _open_invoice(window)
    _pump(app)
    return window


def _window_review(window, app):  # type: ignore[no-untyped-def]
    return _review("side")(window, app) or window


def _window_hover(window, app):  # type: ignore[no-untyped-def]
    _hover(window, app)
    return window


_WINDOW_SHOTS = [
    ("window_team_idle", _shot_team("idle")),
    ("window_pending_send", _send_sheet),
    ("window_delivered_popover", _delivered_popover),
    ("window_incoming", _window_incoming),
    ("window_review_side", _window_review),
    ("window_combine", _combine("combine_several")),
    ("window_history", _window_history),
    ("window_hover", _window_hover),
    ("window_settings", _settings),
]


def _capture_real(app) -> list[str]:  # type: ignore[no-untyped-def]
    """Light and dark grabs of a real two-shop flow. The fake shots stay above."""
    import logging
    from types import SimpleNamespace

    from app.features.team_sync.api import RESOLVE_THEIRS, Invite, ShareRequest
    from app.features.team_sync.core.service import TeamSyncService
    from app.features.team_sync.ui.combine_tab import CombineTab
    from app.features.team_sync.ui.controller import TeamSyncController
    from app.features.team_sync.ui.copy import status_view
    from app.features.team_sync.ui.dialogs import InviteDialog
    from app.features.team_sync.ui.ports import SyncPorts
    from app.features.team_sync.ui.send_sheet import SendToolbarButton
    from app.features.team_sync.ui.status_segment import TeamStatusSegment
    from app.features.team_sync.ui.team_view import TeamView
    from app.qt.QtWidgets import QLabel, QStatusBar, QWidget
    from app.shell.style_sheet_sections_team_sync import shell_section_team_sync
    from app.shell.theme_tokens import tokens_from_palette
    from tests.unit.features.team_sync.conftest import machine, touch_watchdog, write_account
    from tests.unit.features.team_sync.faxmail_sim import FaxMailSim

    missing: list[str] = []
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="cbcs-team-sync-shots-"))
    mails = root / ".Mails"
    sam_account = write_account(mails, "default", "sam@example.test")
    ana_account = write_account(mails, "cedar", "ana@example.test")
    touch_watchdog(mails, "sam-pc")
    touch_watchdog(mails, "ana-pc")
    sam_root = root / "sam"
    ana_root = root / "ana"
    sam_root.mkdir()
    ana_root.mkdir()
    (sam_root / "invoice.py").write_text("def total(x):\n    return x\n", encoding="utf-8")
    sam = TeamSyncService(str(sam_root), machine=machine(root / "sam-box", "sam-pc"), mail_roots=[str(sam_account)])
    ana = TeamSyncService(str(ana_root), machine=machine(root / "ana-box", "ana-pc"), mail_roots=[str(ana_account)])
    sim = FaxMailSim(mails)
    host = QWidget()
    host._status_controller = SimpleNamespace(status_bar=QStatusBar(host))  # type: ignore[attr-defined]
    host._status_controller.status_bar.addPermanentWidget(QLabel("Python", host))
    host._activity_bar = SimpleNamespace(set_badge=lambda *_a: None, set_active_view=lambda *_a: None, counts={})  # type: ignore[attr-defined]
    host._logger = logging.getLogger("cbcs.team_sync.shots")  # type: ignore[attr-defined]
    sam_view = TeamView()
    sam_ui = TeamSyncController(host, sam, SyncPorts(), dormant=False)
    sam_ui._project_root = str(sam_root)
    sam_ui.attach(sam_view, SendToolbarButton())
    ana_view = TeamView()
    ana_ui = TeamSyncController(host, ana, SyncPorts(), dormant=False)
    ana_ui._project_root = str(ana_root)
    ana_ui.attach(ana_view, SendToolbarButton())
    sam.share(
        ShareRequest(
            project_name="Invoice",
            my_name="Sam Brenneman",
            my_shop="Maple",
            invites=[Invite("Ana Kurtz", "Cedar", "ana@example.test")],
            message="Invoice for the shop",
        )
    )
    sam_ui.refresh_status()
    sim.tick()
    ana.poll()
    invite = ana.pending_invites()[0]
    detail = ana.invite_detail(invite.id)
    ana.accept_invite(invite.id, str(ana_root), my_name="Ana Kurtz", my_shop="Cedar")
    sim.tick()
    sam.poll()
    (sam_root / "invoice.py").write_text("def total(x):\n    return x + 2\n", encoding="utf-8")
    sam.save_only("sam total")
    (ana_root / "invoice.py").write_text("def total(x):\n    return x * 2\n", encoding="utf-8")
    ana_ui.refresh_status()
    ana.send("ana total")
    sim.tick()
    sam.poll()
    state = sam.accept(sam.incoming()[0].id)
    assert state is not None

    def _paint(widget, tokens, name: str, theme: str) -> None:  # type: ignore[no-untyped-def]
        widget.setStyleSheet(shell_section_team_sync(tokens))
        if hasattr(widget, "apply_theme"):
            widget.apply_theme(tokens)
        widget.resize(widget.sizeHint().expandedTo(widget.size()))
        widget.show()
        _pump(app)
        path = OUT / f"real_{name}_{theme}.png"
        pixmap = widget.grab()
        if pixmap.isNull():
            missing.append(path.name)
            return
        pixmap.save(str(path), "PNG")
        print(path.name, pixmap.width(), pixmap.height(), flush=True)
        widget.hide()

    for theme in ("light", "dark"):
        tokens = tokens_from_palette(app.palette(), force_mode=theme)
        sam_view.apply(sam.status(), sam.feed(), git_names=False, dormant=False, tidy=False)
        sam_view.apply_theme(tokens)
        sam_view.resize(420, 640)
        _paint(sam_view, tokens, "shared", theme)
        ana_view.apply(ana.status(), ana.feed(), git_names=False, dormant=False, tidy=False)
        ana_view.apply_theme(tokens)
        ana_view.resize(420, 640)
        _paint(ana_view, tokens, "pending", theme)
        dialog = InviteDialog(
            invite,
            lambda *_args: None,
            project_name=detail.get("project_name") or "Invoice",
            default_location=str(Path.home() / "Projects" / "Invoice"),
            author_name=detail.get("sender_name") or "Sam Brenneman",
            tokens=tokens,
        )
        dialog.resize(520, 260)
        _paint(dialog, tokens, "invite", theme)
        dialog.deleteLater()
        segment = TeamStatusSegment()
        segment.apply(status_view(sam.status(), waiting_name="Ana"), tokens)
        segment.resize(segment.sizeHint())
        _paint(segment, tokens, "status", theme)
        segment.deleteLater()
        combine = CombineTab()
        combine.resize(860, 560)
        ana_me = ana.status().me
        sam_me = sam.status().me
        combine.open_state(
            sam,
            SyncPorts(),
            on_finished=lambda: None,
            on_deleted=lambda _clash: None,
            tokens=tokens,
            theirs_label="Ana's",
            theirs_id=ana_me.id if ana_me is not None else "",
            theirs_name="Ana Kurtz",
            mine_name="Sam Brenneman",
            mine_id=sam_me.id if sam_me is not None else "",
        )
        combine.settle(state.clashes[0].id, RESOLVE_THEIRS)
        _paint(combine, tokens, "combine", theme)
        combine.deleteLater()
        _pump(app)
    sam_view.deleteLater()
    ana_view.deleteLater()
    host.deleteLater()
    return missing


if __name__ == "__main__":
    raise SystemExit(main())
