"""Font popover (UX-PED-080). Registered as an override of the baseline font editor."""

from __future__ import annotations

from dataclasses import replace
from typing import List, Optional, Tuple

from app.features.form_builder.engine.ui4.values import FontValue
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    Mixed,
    Registrar,
    RowValue,
    ValueSpec,
    Written,
)
from app.features.form_builder.qtside.inspector.editors._popover import RowPopover
from app.features.form_builder.qtside.visual.common import (
    RowSummary,
    begin_popover,
    owner_name,
    part_name,
    refit,
    refit_widget,
)
from app.qt.QtCore import Qt, QTimer
from app.qt.QtGui import QFont, QFontDatabase
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSpinBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_ROW = "Font"
_PRESETS = (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 36, 48)
_STYLES = (
    ("bold", "B", "bold"),
    ("italic", "I", "italic"),
    ("underline", "U", "underline"),
    ("strikeout", "S", "strikeout"),
)
_WEIGHTS = (
    ("Thin", "Thin"),
    ("Extra light", "ExtraLight"),
    ("Light", "Light"),
    ("Normal", "Normal"),
    ("Medium", "Medium"),
    ("Demi bold", "DemiBold"),
    ("Bold", "Bold"),
    ("Extra bold", "ExtraBold"),
    ("Black", "Black"),
)
_SMOOTHING = (
    ("Default", ""),
    ("Prefer smooth", "PreferAntialias"),
    ("No smoothing", "NoAntialias"),
)
_HINTING = (
    ("Default", ""),
    ("None", "PreferNoHinting"),
    ("Vertical", "PreferVerticalHinting"),
    ("Full", "PreferFullHinting"),
)
_FAMILY_ROLE = getattr(getattr(Qt, "ItemDataRole", Qt), "UserRole")


def _focus(name: str) -> object:
    return getattr(getattr(Qt, "FocusPolicy", Qt), name)


def _policy(name: str) -> object:
    return getattr(getattr(QComboBox, "InsertPolicy", QComboBox), name)


def app_point_size() -> int:
    font = QApplication.font()
    size = font.pointSize()
    if size > 0:
        return size
    return 13


def font_summary(font: Optional[FontValue], *, mixed: bool) -> str:
    if mixed:
        return "Mixed"
    if font is None or not _any_part(font):
        return "Default (%d pt)" % app_point_size()
    parts: List[str] = []
    if font.family:
        parts.append(font.family)
    if font.pointsize:
        parts.append("%d pt" % font.pointsize)
    style = []
    if font.bold:
        style.append("Bold")
    if font.italic:
        style.append("Italic")
    if font.underline:
        style.append("Underline")
    if font.strikeout:
        style.append("Strikeout")
    if font.fontweight:
        style.append(_weight_label(font.fontweight))
    if style:
        parts.append(", ".join(style))
    return ", ".join(parts)


def _weight_label(stored: str) -> str:
    for label, name in _WEIGHTS:
        if name == stored:
            return label
    return stored


def _any_part(font: FontValue) -> bool:
    return any(
        getattr(font, name) is not None
        for name in (
            "family",
            "pointsize",
            "bold",
            "italic",
            "underline",
            "strikeout",
            "fontweight",
            "kerning",
            "stylestrategy",
            "hintingpreference",
        )
    )


class _FamilyDelegate(QStyledItemDelegate):
    """The drop-down draws each family in its own face. The closed field does not."""

    def paint(self, painter: object, option: object, index: object) -> None:  # type: ignore[override]
        family = index.data(_FAMILY_ROLE)  # type: ignore[attr-defined]
        if isinstance(family, str) and family:
            try:
                styled = QStyleOptionViewItem(option)
                current = styled.font
                font = QFont(current() if callable(current) else current)
                font.setFamily(family)
                styled.font = font
            except (TypeError, RuntimeError):
                super().paint(painter, option, index)  # type: ignore[arg-type]
                return
            super().paint(painter, styled, index)  # type: ignore[arg-type]
            return
        super().paint(painter, option, index)  # type: ignore[arg-type]


_FAMILY_NAMES: Optional[List[str]] = None


def _family_names() -> List[str]:
    """QFontDatabase.families is expensive the first time. Keep one list per process."""
    global _FAMILY_NAMES
    if _FAMILY_NAMES is None:
        _FAMILY_NAMES = [name for name in QFontDatabase.families() if name]
    return _FAMILY_NAMES


class _FamilyBox(QComboBox):
    def __init__(self, parent: QWidget, on_pick: object) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.fontFamily")
        self.setAccessibleName(part_name(_ROW, "family"))
        self.setEditable(True)
        self.setInsertPolicy(_policy("NoInsert"))  # type: ignore[arg-type]
        self.setItemDelegate(_FamilyDelegate(self))
        self._on_pick = on_pick
        self._all: List[str] = []
        line = self.lineEdit()
        if line is not None:
            line.setAccessibleName(part_name(_ROW, "family"))
            line.setProperty("fbEnterStays", True)
            line.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
            line.setPlaceholderText("Default (the app's font)")
            line.textEdited.connect(self._filter)
            line.returnPressed.connect(self._enter)
        self._fill("")

    def _fill(self, needle: str) -> None:
        if not self._all:
            self._all = list(_family_names())
        self.blockSignals(True)
        self.clear()
        self.addItem("Default (the app's font)")
        self.setItemData(0, "", _FAMILY_ROLE)
        folded = needle.strip().lower()
        for name in self._all:
            if folded and folded not in name.lower():
                continue
            self.addItem(name)
            self.setItemData(self.count() - 1, name, _FAMILY_ROLE)
        self.blockSignals(False)

    def _filter(self, text: str) -> None:
        self._fill(text)
        self.showPopup()
        line = self.lineEdit()
        if line is not None:
            line.setText(text)
            line.setFocus()

    def _enter(self) -> None:
        self.hidePopup()
        line = self.lineEdit()
        text = "" if line is None else line.text().strip()
        if not text or text == "Default (the app's font)":
            self._on_pick("")
            return
        for index in range(1, self.count()):
            family = self.itemData(index, _FAMILY_ROLE)
            if isinstance(family, str) and family and text.lower() in family.lower():
                self._on_pick(family)
                self._refocus(line)
                return
        self._refocus(line)

    def _refocus(self, line: object) -> None:
        def _back() -> None:
            if not isinstance(line, QWidget):
                return
            window = line.window()
            if window is not None:
                window.activateWindow()
            line.setFocus()
        QTimer.singleShot(0, _back)

    def show_family(self, family: str) -> None:
        self._fill("")
        self.blockSignals(True)
        line = self.lineEdit()
        if not family:
            self.setCurrentIndex(0)
            if line is not None:
                line.clear()
        else:
            index = self.findText(family)
            if index < 0:
                self.addItem(family)
                index = self.count() - 1
                self.setItemData(index, family, _FAMILY_ROLE)
            self.setCurrentIndex(index)
        self.blockSignals(False)


class FontEditor:
    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        self._summary = RowSummary(host.label or _ROW, self._root)
        self._summary.set_opener(self._open)
        layout.addWidget(self._summary, 1)
        self._font = FontValue()
        self._written = False
        self._popover: Optional[RowPopover] = None
        self._family: Optional[_FamilyBox] = None
        self._size: Optional[QSpinBox] = None
        self._toggles = {}
        self._resets = {}
        self._weight: Optional[QComboBox] = None
        self._kerning: Optional[QCheckBox] = None
        self._smoothing: Optional[QComboBox] = None
        self._hinting: Optional[QComboBox] = None

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mixed = isinstance(value, Mixed)
        self._written = isinstance(value, Written) and isinstance(value.value, FontValue)
        self._font = value.value if self._written else FontValue()  # type: ignore[assignment]
        text = font_summary(self._font if self._written else None, mixed=mixed)
        self._summary.set_summary(text)
        self._summary.show_state(value, self._host.chrome.faint)
        if self._popover is not None and not self._popover.closed:
            self._push()

    def _open(self) -> None:
        if self._popover is not None and not self._popover.closed:
            return
        popover = begin_popover(
            self._host,
            self._summary,
            "Change font of %s" % owner_name(self._host),
        )
        body = QWidget(popover)
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        self._family = _FamilyBox(body, self._pick_family)
        form.addWidget(QLabel("Family", body))
        form.addWidget(self._family)
        caption = QLabel("The computer that runs your app needs this font too.", body)
        caption.setWordWrap(True)
        caption.setStyleSheet("color: %s;" % self._host.chrome.faint)
        form.addWidget(caption)
        size_row = QWidget(body)
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size = QSpinBox(size_row)
        self._size = size
        size.setObjectName("formBuilder.fontSize")
        size.setAccessibleName(part_name(_ROW, "size"))
        size.setRange(1, 200)
        size.setKeyboardTracking(False)
        size.valueChanged.connect(self._size_changed)
        size_line = size.lineEdit()
        if size_line is not None:
            size_line.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
        size.setFocusPolicy(_focus("StrongFocus"))  # type: ignore[arg-type]
        presets = QToolButton(size_row)
        presets.setText("\u25be")
        presets.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
        presets.setAccessibleName(part_name(_ROW, "size presets"))
        menu = QMenu(presets)
        for preset in _PRESETS:
            menu.addAction(str(preset), lambda _checked=False, number=preset: self._size_changed(number))
        presets.setMenu(menu)
        size_layout.addWidget(QLabel("Size", size_row))
        size_layout.addWidget(size, 1)
        size_layout.addWidget(presets)
        size_layout.addWidget(self._reset("pointsize", size_row))
        form.addWidget(size_row)
        toggles = QWidget(body)
        toggle_row = QHBoxLayout(toggles)
        toggle_row.setContentsMargins(0, 0, 0, 0)
        self._toggles = {}
        for key, glyph, accessible in _STYLES:
            button = QToolButton(toggles)
            button.setText(glyph)
            button.setCheckable(True)
            button.setFixedSize(24, 24)
            button.setObjectName("formBuilder.font" + key.capitalize())
            button.setAccessibleName(part_name(_ROW, accessible))
            button.clicked.connect(lambda _checked=False, name=key: self._toggle(name))
            self._toggles[key] = button
            toggle_row.addWidget(button)
            toggle_row.addWidget(self._reset(key, toggles))
        toggle_row.addStretch(1)
        form.addWidget(toggles)
        more = QToolButton(body)
        more.setText("More \u25b8")
        more.setCheckable(True)
        more.setAccessibleName(part_name(_ROW, "more"))
        box = QWidget(body)
        more_form = QVBoxLayout(box)
        more_form.setContentsMargins(0, 0, 0, 0)
        self._weight = self._choice(box, "weight", "Weight", _WEIGHTS)
        kerning = QCheckBox("Kerning", box)
        self._kerning = kerning
        kerning.setAccessibleName(part_name(_ROW, "kerning"))
        # The popover sheet styles labels, not check boxes; keep its text on the popover's colours.
        kerning.setStyleSheet("color: %s;" % self._host.chrome.text)
        kerning.clicked.connect(self._kerning_clicked)
        self._smoothing = self._choice(box, "smoothing", "Smoothing", _SMOOTHING)
        self._hinting = self._choice(box, "hinting", "Hinting", _HINTING)
        more_form.addWidget(self._labeled("Weight", self._weight, "fontweight", box))
        kerning_row = QWidget(box)
        kerning_layout = QHBoxLayout(kerning_row)
        kerning_layout.setContentsMargins(0, 0, 0, 0)
        kerning_layout.addWidget(kerning, 1)
        kerning_layout.addWidget(self._reset("kerning", kerning_row))
        more_form.addWidget(kerning_row)
        more_form.addWidget(self._labeled("Smoothing", self._smoothing, "stylestrategy", box))
        more_form.addWidget(self._labeled("Hinting", self._hinting, "hintingpreference", box))
        box.hide()
        more.toggled.connect(box.setVisible)
        more.toggled.connect(lambda _open: refit_widget(box))
        form.addWidget(more)
        form.addWidget(box)
        popover.body().addWidget(body)
        popover.set_reset(self._host.reset if self._written else None)
        self._popover = popover
        self._push()
        popover.open_popover()
        refit(popover)
        if self._family is not None:
            line = self._family.lineEdit()
            if line is not None:
                line.setFocus()
            else:
                self._family.setFocus()

    def _labeled(self, title: str, widget: QWidget, part: str, parent: QWidget) -> QWidget:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title, row))
        layout.addWidget(widget, 1)
        layout.addWidget(self._reset(part, row))
        return row

    def _choice(
        self,
        parent: QWidget,
        part: str,
        accessible: str,
        options: Tuple[Tuple[str, str], ...],
    ) -> QComboBox:
        combo = QComboBox(parent)
        combo.setObjectName("formBuilder.font" + part.capitalize())
        combo.setAccessibleName(part_name(_ROW, accessible.lower()))
        if not options or options[0][1] != "":
            combo.addItem("Default", "")
        for label, stored in options:
            combo.addItem(label, stored)
        combo.activated.connect(lambda _index, name=part: self._choice_changed(name))
        return combo

    def _reset(self, part: str, parent: QWidget) -> QToolButton:
        button = QToolButton(parent)
        button.setText("\u21ba")
        button.setAccessibleName(part_name(_ROW, "reset " + part))
        button.setFocusPolicy(_focus("NoFocus"))  # type: ignore[arg-type]
        button.clicked.connect(lambda _checked=False, name=part: self._unset(name))
        button.hide()
        self._resets[part] = button
        return button

    def _push(self) -> None:
        font = self._font
        if self._family is not None:
            self._family.show_family(font.family or "")
        if self._size is not None:
            self._size.blockSignals(True)
            self._size.setValue(font.pointsize or app_point_size())
            self._size.blockSignals(False)
        for key, button in self._toggles.items():
            own = getattr(font, key)
            button.setChecked(self._inherited(key) if own is None else bool(own))
        self._select(self._weight, font.fontweight or "")
        if self._kerning is not None:
            self._kerning.blockSignals(True)
            self._kerning.setChecked(bool(font.kerning))
            self._kerning.blockSignals(False)
        self._select(self._smoothing, font.stylestrategy or "")
        self._select(self._hinting, font.hintingpreference or "")
        for part, button in self._resets.items():
            button.setVisible(getattr(font, part) is not None)

    def _select(self, combo: Optional[QComboBox], stored: str) -> None:
        if combo is None:
            return
        combo.blockSignals(True)
        index = combo.findData(stored)
        combo.setCurrentIndex(0 if index < 0 else index)
        combo.blockSignals(False)

    def _commit(self) -> None:
        popover = self._popover
        if popover is None:
            return
        self._written = _any_part(self._font)
        self._host.commit(self._font, session=popover.session)
        self._summary.set_summary(font_summary(self._font if self._written else None, mixed=False))
        popover.set_reset(self._host.reset if self._written else None)
        for part, button in self._resets.items():
            button.setVisible(getattr(self._font, part) is not None)

    def _pick_family(self, family: str) -> None:
        self._font = replace(self._font, family=family or None)
        self._commit()

    def _size_changed(self, number: int) -> None:
        if self._size is not None and self._size.value() != number:
            self._size.setValue(number)
        self._font = replace(self._font, pointsize=int(number))
        self._commit()

    def _inherited(self, name: str) -> bool:
        """Whether a parent's font already sets ``name`` (bold, italic, ...) for this widget."""
        try:
            document = self._host.document()
            owner = self._host.owner_ids()[0]
            for ancestor in document.ancestors(owner):
                value = document.node(ancestor).value("font")
                if isinstance(value, FontValue) and getattr(value, name) is not None:
                    return bool(getattr(value, name))
        except (AttributeError, IndexError, KeyError, RuntimeError, TypeError):
            pass
        return False

    def _toggle(self, name: str) -> None:
        # Match the parent's setting by writing nothing; differ from it by writing the opposite,
        # so a bold parent's child can be made not bold.
        button = self._toggles[name]
        wanted = button.isChecked()
        self._font = replace(self._font, **{name: None if wanted == self._inherited(name) else wanted})
        self._commit()

    def _kerning_clicked(self, checked: bool) -> None:
        self._font = replace(self._font, kerning=True if checked else False)
        self._commit()

    def _choice_changed(self, part: str) -> None:
        combo = {"weight": self._weight, "smoothing": self._smoothing, "hinting": self._hinting}[part]
        if combo is None:
            return
        stored = combo.currentData()
        field = {"weight": "fontweight", "smoothing": "stylestrategy", "hinting": "hintingpreference"}[part]
        self._font = replace(self._font, **{field: stored or None})
        self._commit()

    def _unset(self, part: str) -> None:
        field = {"weight": "fontweight", "smoothing": "stylestrategy", "hinting": "hintingpreference"}.get(part, part)
        self._font = replace(self._font, **{field: None})
        self._push()
        self._commit()


def register(registrar: Registrar) -> None:
    # Baseline, not a second override. A later package replaces this editor
    # the way the catalog test does. Cursor and palette stay overrides
    # because choices.py and raw.py already own those baselines.
    registrar.editor(EditorKey(FontValue.ELEMENT), FontEditor, baseline=True)
