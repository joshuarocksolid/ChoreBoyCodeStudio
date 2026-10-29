"""Add a screen: the dialog behind Aa > Screen > Add a screen… (M5.5a, UX-PREV-001).

Name, Width, Height, Font, Font size and Scale (100 to 200 %). Every number is a
spin box held to its range, so the dialog has no error sentences: the add button
is off until the name has a letter in it and is not a built-in screen's name.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.features.form_builder.engine.preview_options import (
    ADD_SCREEN,
    MAX_FONT,
    MAX_HEIGHT,
    MAX_SCALE,
    MAX_WIDTH,
    MIN_HEIGHT,
    MIN_SCALE,
    MIN_WIDTH,
    ScreenProfile,
    clean_profile,
    name_is_built_in,
)
from app.features.form_builder.qtside.theme.chrome import FormChrome, edge_on, field_qss
from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class ScreenDialog(QDialog):
    """Collects one ``ScreenProfile``. ``open()`` it; ``on_done`` gets the profile when the user adds it."""

    def __init__(
        self,
        parent: QWidget,
        on_done: Callable[[ScreenProfile], None],
        chrome: Optional[FormChrome] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.screenDialog")
        self.setWindowTitle(ADD_SCREEN.rstrip("…"))
        self.setAccessibleName("Add a screen")
        self.setModal(True)
        self._on_done = on_done
        form = QFormLayout()
        self.name = QLineEdit(self)
        self.name.setObjectName("formBuilder.screenName")
        self.name.setAccessibleName("Name")
        self.width_box = self._spin("formBuilder.screenWidth", "Width", MIN_WIDTH, MAX_WIDTH, 1366, " px")
        self.height_box = self._spin("formBuilder.screenHeight", "Height", MIN_HEIGHT, MAX_HEIGHT, 768, " px")
        self.font = QLineEdit(self)
        self.font.setObjectName("formBuilder.screenFont")
        self.font.setAccessibleName("Font")
        self.font.setPlaceholderText("ChoreBoy font")
        self.font_size = self._spin("formBuilder.screenFontSize", "Font size", 0, MAX_FONT, 0, " pt")
        self.font_size.setSpecialValueText("ChoreBoy size")
        self.scale = self._spin("formBuilder.screenScale", "Scale", MIN_SCALE, MAX_SCALE, 100, " %")
        for label, field in (
            ("Name", self.name),
            ("Width", self.width_box),
            ("Height", self.height_box),
            ("Font", self.font),
            ("Font size", self.font_size),
            ("Scale", self.scale),
        ):
            form.addRow(label, field)
        buttons = QDialogButtonBox(self)
        self._add = buttons.addButton("Add screen", QDialogButtonBox.AcceptRole)
        self._add.setObjectName("formBuilder.screenAdd")
        cancel = buttons.addButton("Cancel", QDialogButtonBox.RejectRole)
        cancel.setObjectName("formBuilder.screenCancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer = QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(buttons)
        self._add.setDefault(True)
        self.name.textChanged.connect(lambda _text: self._sync())
        self.accepted.connect(self._finish)
        self._sync()
        if chrome is not None:
            self._apply_chrome(chrome)
        self.setTabOrder(self.name, self.width_box)
        self.name.setFocus(Qt.OtherFocusReason)

    def _apply_chrome(self, chrome: FormChrome) -> None:
        """The shell theme: a top-level dialog does not inherit the main window's sheet."""
        edge = edge_on(chrome, chrome.window)
        self.setStyleSheet(
            "QDialog#formBuilder\\.screenDialog { background: %(window)s; color: %(text)s; }"
            "QDialog#formBuilder\\.screenDialog QLabel { color: %(text)s; }"
            "QDialog#formBuilder\\.screenDialog QPushButton {"
            " background: %(panel)s; color: %(text)s; border: 1px solid %(edge)s; border-radius: 4px; padding: 3px 12px; }"
            "QDialog#formBuilder\\.screenDialog QPushButton:default {"
            " background: %(accent)s; color: %(on_accent)s; border: 1px solid %(accent)s; }"
            "QDialog#formBuilder\\.screenDialog QPushButton:disabled { color: %(muted)s; background: %(panel)s; border: 1px dashed %(muted)s; }"
            "QDialog#formBuilder\\.screenDialog QPushButton:focus { border: %(focus)dpx solid %(accent)s; }"
            % {
                "window": chrome.window,
                "panel": chrome.panel,
                "text": chrome.text,
                "muted": chrome.muted,
                "edge": edge,
                "accent": chrome.accent,
                "on_accent": chrome.on_accent,
                "focus": max(1, chrome.focus_width),
            }
            + field_qss(chrome, "QDialog#formBuilder\\.screenDialog")
        )

    def _spin(self, name: str, label: str, low: int, high: int, value: int, suffix: str) -> QSpinBox:
        box = QSpinBox(self)
        box.setObjectName(name)
        box.setAccessibleName(label)
        box.setRange(low, high)
        box.setValue(value)
        box.setSuffix(suffix)
        return box

    def profile(self) -> Optional[ScreenProfile]:
        return clean_profile(
            self.name.text(),
            self.width_box.value(),
            self.height_box.value(),
            self.font.text(),
            self.font_size.value(),
            self.scale.value(),
        )

    def _sync(self) -> None:
        text = self.name.text()
        self._add.setEnabled(bool(text.strip()) and not name_is_built_in(text))

    def _finish(self) -> None:
        found = self.profile()
        if found is not None and not name_is_built_in(found.name):
            self._on_done(found)
