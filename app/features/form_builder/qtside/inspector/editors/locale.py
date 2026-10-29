"""A language list that filters as you type, and the territories Qt pairs with it."""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.features.form_builder.engine.ui4.values import LocaleValue
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    Unset,
    ValueSpec,
    Written,
    mark,
)
from app.features.form_builder.qtside.inspector.editors._editor_kit import change_label, name_part, payload
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover, SummaryButton
from app.qt.QtCore import QLocale, Qt
from app.qt.QtWidgets import QComboBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QWidget


class _LanguageFilter(QLineEdit):
    """Down leaves the filter and lands on the first visible language."""

    def __init__(self, parent: QWidget, on_down) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._on_down = on_down

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        keys = getattr(Qt, "Key", Qt)
        if event.key() == getattr(keys, "Key_Down"):  # type: ignore[attr-defined]
            self._on_down()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


class _LanguageList(QListWidget):
    """Up from the first visible row returns to the filter."""

    def __init__(self, parent: QWidget, on_up) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._on_up = on_up

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        keys = getattr(Qt, "Key", Qt)
        if event.key() == getattr(keys, "Key_Up") and self._at_first():  # type: ignore[attr-defined]
            self._on_up()
            event.accept()  # type: ignore[attr-defined]
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def _at_first(self) -> bool:
        current = self.currentRow()
        for index in range(self.count()):
            item = self.item(index)
            if item is not None and not item.isHidden():
                return current <= index
        return True


def _languages() -> List[Tuple[str, str]]:
    rows = []
    for language in QLocale.Language:
        key = str(getattr(language, "name", "") or "")
        if not key or key == "AnyLanguage":
            continue
        label = str(QLocale.languageToString(language))
        rows.append((key, label or key))
    rows.sort(key=lambda item: item[1].lower())
    return rows


def _language(key: str) -> object:
    return getattr(QLocale.Language, key)


def _territories(language_key: str) -> List[Tuple[str, str]]:
    try:
        language = _language(language_key)
    except AttributeError:
        return []
    any_script = getattr(QLocale, "AnyScript")
    any_territory = getattr(QLocale, "AnyTerritory", None) or getattr(QLocale, "AnyCountry")
    matches = QLocale.matchingLocales(language, any_script, any_territory)
    seen = []
    found = []
    display = getattr(QLocale, "territoryToString", None) or getattr(QLocale, "countryToString")
    for locale in matches:
        territory = locale.territory() if hasattr(locale, "territory") else locale.country()
        key = str(getattr(territory, "name", "") or "")
        if not key or key in seen or key in ("AnyTerritory", "AnyCountry"):
            continue
        seen.append(key)
        label = str(display(territory))
        found.append((key, label or key))
    found.sort(key=lambda item: item[1].lower())
    return found


class LocaleEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._button = SummaryButton(host.label or "Locale", parent)
        self._button.set_opener(self._open)
        self._popover: Optional[RowPopover] = None
        self._language = ""
        self._country = ""
        self._can_reset = False
        self._resetting = False
        self._filling = False
        self._filter: Optional[QLineEdit] = None
        self._list: Optional[QListWidget] = None
        self._countries: Optional[QComboBox] = None

    @property
    def widget(self) -> QWidget:
        return self._button

    def show(self, value: RowValue) -> None:
        self._button.set_row_label(self._host.label or "Locale")
        self._can_reset = isinstance(value, Written) or (isinstance(value, Unset) and value.default is not None)
        found = payload(value)
        mark(self._button, value)
        if isinstance(value, Mixed):
            self._button.set_summary("Mixed")
            return
        if not isinstance(found, LocaleValue) or not found.language:
            self._language = ""
            self._country = ""
            self._button.set_summary("Same as the app")
            self._button.setAccessibleName("%s: same as the app" % (self._host.label or "Locale"))
            return
        self._language = found.language
        self._country = found.country
        self._button.set_summary("%s (%s)" % (_language_label(found.language), _country_label(found.country)))
        self._button.setAccessibleName(
            "%s: %s, %s" % (self._host.label or "Locale", _language_label(found.language), _country_label(found.country))
        )

    def _open(self) -> None:
        if self._popover is not None and not self._popover.closed:
            return
        popover = RowPopover(
            self._host.row_widget,
            self._host,
            row_label=self._host.label or "Locale",
            session_label=change_label(self._host.label),
            qt_name=self._host.qt_name,
            anchor=self._button,
        )
        self._popover = popover
        body = popover.body()
        field = _LanguageFilter(popover, self._focus_list)
        self._filter = field
        field.setPlaceholderText("Language")
        name_part(field, self._host, "language filter")
        field.textChanged.connect(self._apply_filter)
        listing = _LanguageList(popover, self._focus_filter)
        self._list = listing
        listing.setMaximumHeight(220)
        for key, label in _languages():
            item = QListWidgetItem(label, listing)
            item.setData(getattr(Qt, "UserRole"), key)
            item.setToolTip(key)
        listing.currentItemChanged.connect(lambda _cur, _prev: self._language_picked())
        countries = QComboBox(popover)
        self._countries = countries
        name_part(countries, self._host, "territory")
        countries.currentIndexChanged.connect(self._country_picked)
        body.addWidget(QLabel("Language", popover))
        body.addWidget(field)
        body.addWidget(listing)
        body.addWidget(QLabel("Country or region", popover))
        body.addWidget(countries)
        self._filling = True
        self._select_current()
        self._filling = False
        if self._can_reset:
            popover.set_reset(self._reset)
        popover.open_popover()

    def _focus_list(self) -> None:
        listing = self._list
        if listing is None:
            return
        current = listing.currentItem()
        if current is not None and not current.isHidden():
            listing.setFocus()
            return
        for index in range(listing.count()):
            item = listing.item(index)
            if item is not None and not item.isHidden():
                listing.setCurrentRow(index)
                listing.setFocus()
                return

    def _focus_filter(self) -> None:
        field = self._filter
        if field is not None:
            field.setFocus()

    def _apply_filter(self, text: str) -> None:
        listing = self._list
        if listing is None:
            return
        needle = text.strip().lower()
        for index in range(listing.count()):
            item = listing.item(index)
            item.setHidden(needle not in item.text().lower())

    def _select_current(self) -> None:
        listing = self._list
        if listing is None:
            return
        target = self._language or "English"
        for index in range(listing.count()):
            item = listing.item(index)
            if item.data(getattr(Qt, "UserRole")) == target:
                listing.setCurrentItem(item)
                return
        if listing.count():
            listing.setCurrentRow(0)

    def _language_picked(self) -> None:
        listing = self._list
        combo = self._countries
        if listing is None or combo is None or self._resetting:
            return
        item = listing.currentItem()
        if item is None or item.isHidden():
            return
        language = str(item.data(getattr(Qt, "UserRole")) or "")
        if not language:
            return
        self._language = language
        territories = _territories(language)
        if not any(key == self._country for key, _label in territories) and territories:
            self._country = _usual_territory(language, territories)
        combo.blockSignals(True)
        combo.clear()
        for key, label in territories:
            combo.addItem(label, key)
            if key == self._country:
                combo.setCurrentIndex(combo.count() - 1)
        combo.blockSignals(False)
        if self._filling:
            return
        self._commit()

    def _country_picked(self, index: int) -> None:
        combo = self._countries
        if combo is None or index < 0 or self._resetting:
            return
        data = combo.itemData(index)
        if isinstance(data, str) and data:
            self._country = data
            self._commit()

    def _commit(self) -> None:
        if self._resetting or self._popover is None or not self._language or not self._country:
            return
        value = LocaleValue(self._language, self._country)
        self._host.commit(value, session=self._popover.session)
        self._button.set_summary("%s (%s)" % (_language_label(self._language), _country_label(self._country)))
        self._button.setAccessibleName(
            "%s: %s, %s" % (self._host.label or "Locale", _language_label(self._language), _country_label(self._country))
        )

    def _reset(self) -> None:
        self._resetting = True
        popover = self._popover
        if popover is not None and popover.session.has_step():
            popover.session.revert()
        self._host.reset()
        self._resetting = False


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(LocaleValue.ELEMENT), LocaleEditor)


def _usual_territory(language_key: str, territories: List[Tuple[str, str]]) -> str:
    """The territory Qt picks for the bare language (English: United States), else the first."""
    try:
        usual = QLocale(_language(language_key))
    except (AttributeError, TypeError):
        return territories[0][0]
    territory = usual.territory() if hasattr(usual, "territory") else usual.country()
    key = str(getattr(territory, "name", "") or "")
    if any(key == found for found, _label in territories):
        return key
    return territories[0][0]


def _language_label(key: str) -> str:
    try:
        return str(QLocale.languageToString(_language(key))) or key
    except AttributeError:
        return key


def _country_label(key: str) -> str:
    country_type = getattr(QLocale, "Territory", None) or getattr(QLocale, "Country")
    try:
        country = getattr(country_type, key)
    except AttributeError:
        return key
    display = getattr(QLocale, "territoryToString", None) or getattr(QLocale, "countryToString")
    return str(display(country)) or key
