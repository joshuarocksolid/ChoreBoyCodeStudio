"""Settings > Form designer (UX-TMPL-006, R3 182).

A page of the CBCS settings dialog with the form builder's per-user choices:
Preview style and screen defaults, whether the preview process starts when a
form opens, how Insert shows, Qt names in the inspector, where new templates
go, and a link to the Keyboard tab filtered to "Form designer".

Where the values live. All of them are in the ``form_builder`` object of the
global settings file, next to the workbench widths:

* ``preview_style`` (a style name, absent means "Fusion · as on ChoreBoy"),
* ``preview_screen`` (``small`` or ``full_hd``; absent means the ChoreBoy screen),
* ``preview_prewarm`` (bool, default true),
* ``insert.view`` (``icons``, ``list``, absent means Automatic),
* ``qt_names`` (bool), and
* ``template_scope`` (``user`` or ``project``).

The page reads them on ``load`` and writes them on ``apply`` in one update
that keeps every other key.

How it gets into the dialog. ``install`` registers the page with the shell's
settings-page registry (``app.shell.settings_pages``). The dialog builds the
page from the global payload it opened with, and after OK hands the page the
payload it is about to save (re-read from disk, with its own values in); the
page writes its keys into that payload and the shell saves once. Nothing races
the shell's save.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, cast

from app.qt.QtCore import Qt, QTimer
from app.qt.QtGui import QShowEvent
from app.qt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyleFactory,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.features.form_builder.engine.project import user_templates as ut
from app.features.form_builder.integration import insert_memory, template_store
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.memory import reread_qt_names
from app.features.form_builder.qtside.theme.chrome import link_ink
from app.persistence.settings_service import SettingsService
from app.shell.settings_pages import SettingsPage, register_settings_page
from app.shell.theme_tokens import tokens_from_palette

SETTINGS_KEY = "form_builder"
TAB_TITLE = "Form designer"
KEYBOARD_FILTER = "Form designer"

DEFAULT_STYLE_LABEL = "Fusion · as on ChoreBoy"
DEFAULT_STYLE = ""
SCREENS = (
    ("", "ChoreBoy screen · 1366 × 768"),
    ("small", "Small screen · 1024 × 600"),
    ("full_hd", "Full HD · 1920 × 1080"),
)
INSERT_CHOICES = (("icons", "Icons"), ("list", "List"), ("", "Automatic"))
TEMPLATE_CHOICES = ((ut.SCOPE_USER, "All my projects"), (ut.SCOPE_PROJECT, "This project only"))


def values_from_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """The page's six values from a settings payload, with defaults for anything missing or odd."""
    section = payload.get(SETTINGS_KEY)
    block: Mapping[str, Any] = section if isinstance(section, Mapping) else {}
    insert = block.get("insert")
    view = insert.get("view") if isinstance(insert, Mapping) else ""
    style = block.get("preview_style")
    screen = block.get("preview_screen")
    return {
        "preview_style": style if isinstance(style, str) else DEFAULT_STYLE,
        "preview_screen": screen if isinstance(screen, str) else "",
        "preview_prewarm": block.get("preview_prewarm") is not False,
        "insert_view": view if view in ("icons", "list") else "",
        "qt_names": block.get("qt_names") is True,
        "template_scope": ut.SCOPE_PROJECT if block.get("template_scope") == ut.SCOPE_PROJECT else ut.SCOPE_USER,
    }


def payload_with_values(payload: Mapping[str, Any], values: Mapping[str, Any]) -> Dict[str, Any]:
    """``payload`` with the page's values written; every other key stays."""
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    _put(section, "preview_style", values["preview_style"] or None)
    _put(section, "preview_screen", values["preview_screen"] or None)
    section["preview_prewarm"] = bool(values["preview_prewarm"])
    section["qt_names"] = bool(values["qt_names"])
    section["template_scope"] = ut.SCOPE_PROJECT if values["template_scope"] == ut.SCOPE_PROJECT else ut.SCOPE_USER
    insert_raw = section.get("insert")
    insert = dict(insert_raw) if isinstance(insert_raw, Mapping) else {}
    _put(insert, "view", values["insert_view"] or None)
    if insert:
        section["insert"] = insert
    else:
        section.pop("insert", None)
    updated[SETTINGS_KEY] = section
    return updated


def _put(target: Dict[str, Any], key: str, value: Optional[Any]) -> None:
    if value is None:
        target.pop(key, None)
    else:
        target[key] = value


class FormDesignerSettingsPage(QWidget):
    """The page. ``load`` fills it from the settings file; ``apply`` writes it back."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        service: Optional[SettingsService] = None,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.settingsPage")
        self._service = service
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 12, 16, 12)
        column.setSpacing(10)
        form = QFormLayout()
        form.setSpacing(8)

        self.style_combo = QComboBox(self)
        self.style_combo.setObjectName("formBuilder.settings.previewStyle")
        self.style_combo.addItem(DEFAULT_STYLE_LABEL, DEFAULT_STYLE)
        for name in QStyleFactory.keys():
            if name.casefold() != "fusion":
                self.style_combo.addItem(name, name)
        self.screen_combo = QComboBox(self)
        self.screen_combo.setObjectName("formBuilder.settings.previewScreen")
        for value, label in SCREENS:
            self.screen_combo.addItem(label, value)
        self.prewarm = QCheckBox("Start the preview process when a form opens", self)
        self.prewarm.setObjectName("formBuilder.settings.prewarm")
        self.insert_combo = QComboBox(self)
        self.insert_combo.setObjectName("formBuilder.settings.insertShows")
        for value, label in INSERT_CHOICES:
            self.insert_combo.addItem(label, value)
        self.qt_names = QCheckBox("Show Qt names in the inspector", self)
        self.qt_names.setObjectName("formBuilder.settings.qtNames")
        self.template_combo = QComboBox(self)
        self.template_combo.setObjectName("formBuilder.settings.templateScope")
        for value, label in TEMPLATE_CHOICES:
            self.template_combo.addItem(label, value)

        for text, widget in (
            ("Preview style", self.style_combo),
            ("Preview screen", self.screen_combo),
            ("Insert shows", self.insert_combo),
            ("Where new templates go", self.template_combo),
        ):
            label = QLabel(text, self)
            label.setBuddy(widget)
            form.addRow(label, widget)
        column.addLayout(form)
        column.addWidget(self.prewarm)
        column.addWidget(self.qt_names)

        self.keyboard_link = QPushButton("Keyboard shortcuts…", self)
        self.keyboard_link.setObjectName("formBuilder.settings.keyboardLink")
        self.keyboard_link.setFlat(True)
        self.keyboard_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.keyboard_link.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.keyboard_link.clicked.connect(self.show_keyboard_shortcuts)
        column.addWidget(self.keyboard_link, 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)
        if payload is None:
            self.load()
        else:
            self.set_values(values_from_payload(payload))

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._style_link()

    def _style_link(self) -> None:
        """The link reads as a link: underlined, in the builder's link colour for the dialog's theme."""
        tokens = getattr(self.window(), "_tokens", None) or tokens_from_palette(self.palette())
        colour = link_ink(chrome_for(tokens))
        self.keyboard_link.setStyleSheet(
            "QPushButton#formBuilder\\.settings\\.keyboardLink { border: none; background: transparent;"
            " padding: 2px 0; text-align: left; text-decoration: underline; font-weight: normal; color: %s; }" % colour
        )

    # -- values ---------------------------------------------------------
    def values(self) -> Dict[str, Any]:
        return {
            "preview_style": str(self.style_combo.currentData() or ""),
            "preview_screen": str(self.screen_combo.currentData() or ""),
            "preview_prewarm": self.prewarm.isChecked(),
            "insert_view": str(self.insert_combo.currentData() or ""),
            "qt_names": self.qt_names.isChecked(),
            "template_scope": str(self.template_combo.currentData() or ut.SCOPE_USER),
        }

    def set_values(self, values: Mapping[str, Any]) -> None:
        self._select(self.style_combo, values["preview_style"], add_missing=True)
        self._select(self.screen_combo, values["preview_screen"], add_missing=True)
        self._select(self.insert_combo, values["insert_view"])
        self._select(self.template_combo, values["template_scope"])
        self.prewarm.setChecked(bool(values["preview_prewarm"]))
        self.qt_names.setChecked(bool(values["qt_names"]))

    def load(self) -> None:
        try:
            payload = self._settings().load_global(force_refresh=True)
        except OSError:
            payload = {}
        self.set_values(values_from_payload(payload))

    def write_into(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """``payload`` with the page's values written (what the settings dialog saves after OK)."""
        return payload_with_values(payload, self.values())

    def apply(self) -> None:
        """Write the page's values to the settings file on its own, keeping every other key."""
        values = self.values()
        try:
            self._settings().update_global(lambda payload: payload_with_values(payload, values))
        except OSError:
            return
        insert_memory.forget_cached()

    def show_keyboard_shortcuts(self) -> bool:
        """Go to the dialog's Keyboard tab with its search box reading "Form designer"."""
        dialog = self.window()
        tabs = cast(Optional[QTabWidget], getattr(dialog, "_tabs_widget", None))
        index = getattr(dialog, "_keybindings_tab_index", None)
        search = getattr(dialog, "_shortcut_search_input", None)
        if tabs is None:
            return False
        if index is None:
            return False
        tabs.setCurrentIndex(int(index))
        if search is not None:
            search.setText(KEYBOARD_FILTER)
            search.setFocus()
        return True

    # -- helpers --------------------------------------------------------
    def _settings(self) -> SettingsService:
        return self._service or SettingsService(state_root=template_store.settings_root())

    @staticmethod
    def _select(combo: QComboBox, value: Any, *, add_missing: bool = False) -> None:
        index = combo.findData(value)
        if index < 0 and add_missing and value:
            combo.addItem(str(value), value)
            index = combo.count() - 1
        combo.setCurrentIndex(max(0, index))


def _build(parent: QWidget, payload: Mapping[str, Any]) -> QWidget:
    return FormDesignerSettingsPage(parent, payload=payload)


def _apply(page: QWidget, payload: Dict[str, Any]) -> Mapping[str, Any]:
    if not isinstance(page, FormDesignerSettingsPage):
        return payload
    # The Insert pane caches its state; it reads "Insert shows" again after the shell saves.
    insert_memory.forget_cached()
    # Open inspectors read "Show Qt names" again once the shell has saved the payload.
    QTimer.singleShot(0, reread_qt_names)
    return page.write_into(payload)


PAGE = SettingsPage(key=SETTINGS_KEY, title=TAB_TITLE, build=_build, apply=_apply)


def install() -> None:
    """Register the page with the shell's Settings dialog. Safe to call twice."""
    register_settings_page(PAGE)
