"""Wire Team Sync into the shell. The UI stays dormant until a service exists."""

from __future__ import annotations

import importlib
import os

from app.features.team_sync.ui.controller import IdleTeamSync, TeamSyncController
from app.features.team_sync.ui.ports import SchedulerPorts, SyncPorts
from app.features.team_sync.ui.send_sheet import SendToolbarButton
from app.features.team_sync.ui.team_view import TeamView
from app.qt.QtGui import QColor
from app.shell.contributions import ExplorerMenuAction, ShellContributions, SidebarContribution, ToolbarContribution
from app.shell.events import ProjectOpenedEvent
from app.shell.icons.activity_bar import team_icon
from app.shell.shell_composition_context import ShellCompositionContext, bind_private_attrs


def _team_icon(normal: QColor, active: QColor):
    return team_icon(color_normal=normal, color_active=active)


def make_team_sync_service() -> tuple[object, bool, bool]:
    """Return ``(service, dormant, fake)``. The env var selects the fake.

    The real engine is built per open project, not at shell startup.
    """
    scenario = os.environ.get("CBCS_TEAM_SYNC_FAKE", "").strip()
    if scenario:
        from app.features.team_sync.core.fake import InMemoryTeamSync

        service = InMemoryTeamSync()
        service.scenario(scenario)
        return service, False, True
    try:
        importlib.import_module("app.features.team_sync.core.service")
    except ImportError:
        from app.features.team_sync.core.fake import InMemoryTeamSync

        service = InMemoryTeamSync()
        service.scenario("not_shared")
        return service, True, True
    return IdleTeamSync(), False, False


def _project_service(project_root: str) -> object:
    from app.features.shop_sharing.model import Machine
    from app.features.team_sync.core.service import TeamSyncService

    return TeamSyncService(project_root, machine=Machine.current())


class TeamSyncShell:
    """Registered at install time. Widgets and the service appear once the shell exists."""

    def __init__(self) -> None:
        self._view: TeamView | None = None
        self._send: SendToolbarButton | None = None
        self._controller: TeamSyncController | None = None

    def register(self, contributions: ShellContributions) -> None:
        contributions.sidebar.append(
            SidebarContribution(
                view_id="team",
                tooltip="Team",
                icon_factory=_team_icon,
                widget_factory=self._make_view,
            )
        )
        contributions.toolbar.append(ToolbarContribution(factory=self._make_send))
        contributions.explorer_decorations.append(self._lookup)
        contributions.explorer_menu_actions.append(ExplorerMenuAction("File History", self._file_history))
        contributions.editor_page_hooks.append(self._editor_page)
        contributions.finalize_hooks.append(self.build)
        contributions.file_saved_hooks.append(self._file_saved)
        contributions.theme_hooks.append(self._theme)
        contributions.package_extras.append(self._package_extra)
        contributions.packaged_hooks.append(self._packaged)
        contributions.settings_group_factories.append(self._settings_group)

    def build(self, window: object) -> None:
        service, dormant, fake = make_team_sync_service()
        if os.environ.get("CBCS_TEAM_SYNC_SHOTS"):
            ports: object = SyncPorts()
        else:
            ports = SchedulerPorts(window._background_tasks)  # type: ignore[attr-defined]
        self._controller = TeamSyncController(  # type: ignore[arg-type]
            window,
            service,
            ports,
            dormant=dormant,
            fake=fake,
            watch_invites=not fake and not dormant,
            project_factory=None if fake else _project_service,
        )
        if self._view is None or self._send is None:
            return
        self._controller.attach(self._view, self._send)

    def on_project(self, event: object) -> None:
        if self._controller is None:
            return
        self._controller.on_project_opened(
            getattr(event, "project_root", ""),
            getattr(event, "project_name", ""),
        )

    def _make_view(self, parent):  # type: ignore[no-untyped-def]
        self._view = TeamView(parent)
        return self._view

    def _make_send(self, parent):  # type: ignore[no-untyped-def]
        self._send = SendToolbarButton(parent)
        return self._send

    def _lookup(self, relative_path: str):
        if self._controller is None:
            return None
        return self._controller.letters.lookup(relative_path)

    def _file_history(self, relative_path: str) -> None:
        if self._controller is not None:
            self._controller.open_history(relative_path)

    def _editor_page(self, page, path: str) -> None:  # type: ignore[no-untyped-def]
        if self._controller is not None:
            self._controller.attach_editor_page(page, path)

    def _file_saved(self, path: str) -> None:
        if self._controller is not None:
            self._controller.on_file_saved(path)

    def _theme(self, tokens: object) -> None:
        if self._controller is not None:
            self._controller.apply_theme(tokens)

    def _package_extra(self, wizard: object) -> None:
        if self._controller is not None:
            self._controller.package_extra(wizard)

    def _packaged(self, wizard: object, version: str) -> None:
        if self._controller is not None:
            self._controller.on_packaged(wizard, version)

    def _settings_group(self, parent):  # type: ignore[no-untyped-def]
        if self._controller is None:
            from app.qt.QtWidgets import QWidget

            return QWidget(parent)
        return self._controller.settings_group(parent)


def install_team_sync(ctx: ShellCompositionContext) -> None:
    shell = TeamSyncShell()
    bind_private_attrs(ctx.w, {"_team_sync": shell})
    shell.register(ctx.w._shell_contributions)
    ctx.w._event_bus.subscribe(ProjectOpenedEvent, shell.on_project)


__all__ = ["TeamSyncShell", "install_team_sync", "make_team_sync_service"]
