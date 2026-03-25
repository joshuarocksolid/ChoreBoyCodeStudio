"""Help/about/log action orchestration extracted from MainWindow."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from PySide2.QtCore import QUrl
from PySide2.QtGui import QDesktopServices
from PySide2.QtWidgets import QMessageBox, QWidget

from app.bootstrap.paths import global_app_log_path, global_logs_dir
from app.core import constants
from app.shell.shortcut_preferences import SHORTCUT_COMMANDS
from app.ui.help.help_dialog import show_help_file, show_help_markdown

if TYPE_CHECKING:
    from app.shell.theme_tokens import ShellThemeTokens


class ShellHelpController:
    """Coordinates Help menu actions and log visibility helpers."""

    def __init__(
        self,
        *,
        state_root: str | None,
        resolve_theme_tokens: Callable[[], ShellThemeTokens],
        reveal_path_in_file_manager: Callable[[str], None],
        get_effective_shortcuts: Callable[[], Mapping[str, str]],
    ) -> None:
        self._state_root = state_root
        self._resolve_theme_tokens = resolve_theme_tokens
        self._reveal_path_in_file_manager = reveal_path_in_file_manager
        self._get_effective_shortcuts = get_effective_shortcuts

    def open_app_log(self, *, parent: QWidget) -> None:
        log_path = global_app_log_path(self._state_root)
        if not log_path.exists():
            QMessageBox.information(
                parent,
                "Application Log",
                f"No log file found at:\n{log_path}",
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path)))

    def open_log_folder(self, *, parent: QWidget) -> None:
        log_dir = global_logs_dir(self._state_root)
        if not log_dir.exists():
            QMessageBox.information(
                parent,
                "Log Folder",
                f"Log folder does not exist yet:\n{log_dir}",
            )
            return
        self._reveal_path_in_file_manager(str(log_dir))

    def show_getting_started(self, *, parent: QWidget) -> None:
        self._show_help_file("Getting Started", "getting_started.md", parent=parent)

    def show_shortcuts(self, *, parent: QWidget) -> None:
        self._show_help_markdown(
            "Keyboard Shortcuts",
            self.build_shortcuts_help_markdown(),
            parent=parent,
        )

    def show_headless_notes(self, *, parent: QWidget) -> None:
        self._show_help_file("FreeCAD Headless Notes", "headless_notes.md", parent=parent)

    def show_packaging_backup(self, *, parent: QWidget) -> None:
        self._show_help_file("Packaging, Sharing, and Backup", "packaging_backup.md", parent=parent)

    def show_about(self, *, parent: QWidget) -> None:
        QMessageBox.information(
            parent,
            "About",
            (
                f"ChoreBoy Code Studio v{constants.APP_VERSION}\n"
                "Project-first editor + runner for constrained systems.\n"
                "\n"
                "Licensed under the MIT License.\n"
                "\n"
                "Developed by Joshua Aguilar\n"
                "RockSolid Data Solutions\n"
                "620-888-7050\n"
                "sales@rocksoliddata.solutions"
            ),
        )

    def build_shortcuts_help_markdown(self) -> str:
        lines: list[str] = ["# Keyboard Shortcuts", ""]
        grouped: dict[str, list[tuple[str, str]]] = {}
        effective_shortcuts = self._get_effective_shortcuts()
        for command in SHORTCUT_COMMANDS:
            shortcut = effective_shortcuts.get(command.action_id, "")
            if not shortcut:
                continue
            grouped.setdefault(command.category, []).append((command.label, shortcut))
        for category in sorted(grouped.keys()):
            lines.append(f"## {category}")
            lines.append("")
            for label, shortcut in sorted(grouped[category], key=lambda item: item[0].lower()):
                lines.append(f"- **{shortcut}**: {label}")
            lines.append("")
        if len(lines) <= 2:
            lines.extend(["No shortcuts are currently assigned.", ""])
        lines.extend(
            [
                "_Customize shortcuts in **File > Settings > Keybindings**._",
                "",
            ]
        )
        return "\n".join(lines)

    def _show_help_file(self, title: str, file_name: str, *, parent: QWidget) -> None:
        show_help_file(title, file_name, self._resolve_theme_tokens(), parent=parent)

    def _show_help_markdown(self, title: str, markdown_text: str, *, parent: QWidget) -> None:
        show_help_markdown(title, markdown_text, self._resolve_theme_tokens(), parent=parent)
