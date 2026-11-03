"""Settings › Team. The line summary is on. Everything else is off."""

from __future__ import annotations

from dataclasses import dataclass

from app.qt.QtWidgets import QCheckBox, QGroupBox, QVBoxLayout, QWidget


@dataclass
class TeamUiSettings:
    line_summary: bool = True
    git_names: bool = False
    change_ids: bool = False
    copy_into_experiment: bool = False
    find_broke: bool = False
    tidy_before_send: bool = False


class TeamSettingsGroup(QGroupBox):
    def __init__(self, settings: TeamUiSettings, on_change, parent: QWidget | None = None) -> None:  # type: ignore[no-untyped-def]
        super().__init__("Team", parent)
        self.setObjectName("shell.teamSync.settingsGroup")
        self._settings = settings
        self._on_change = on_change
        layout = QVBoxLayout(self)
        self._line = self._box("Show who changed the current line", settings.line_summary, "line_summary")
        self._git = self._box("Show git names", settings.git_names, "git_names")
        self._ids = self._box("Show change IDs", settings.change_ids, "change_ids")
        advanced = QGroupBox("Advanced", self)
        advanced.setObjectName("shell.teamSync.settingsAdvanced")
        advanced_layout = QVBoxLayout(advanced)
        self._copy = self._box(
            "Copy a change into an experiment",
            settings.copy_into_experiment,
            "copy_into_experiment",
            advanced,
        )
        self._find = self._box(
            "Find when something broke",
            settings.find_broke,
            "find_broke",
            advanced,
        )
        self._tidy = self._box(
            "Tidy changes before sending",
            settings.tidy_before_send,
            "tidy_before_send",
            advanced,
        )
        for box in (self._copy, self._find, self._tidy):
            advanced_layout.addWidget(box)
        layout.addWidget(self._line)
        layout.addWidget(self._git)
        layout.addWidget(self._ids)
        layout.addWidget(advanced)

    def _box(self, label: str, checked: bool, key: str, parent: QWidget | None = None) -> QCheckBox:
        box = QCheckBox(label, parent or self)
        box.setObjectName(f"shell.teamSync.settings.{key}")
        box.setChecked(checked)
        box.toggled.connect(lambda value, key=key: self._toggle(key, value))
        return box

    def _toggle(self, key: str, value: bool) -> None:
        setattr(self._settings, key, bool(value))
        self._on_change(self._settings)


__all__ = ["TeamSettingsGroup", "TeamUiSettings"]
