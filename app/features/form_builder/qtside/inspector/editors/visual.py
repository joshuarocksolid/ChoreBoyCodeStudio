
from __future__ import annotations

from dataclasses import replace

from app.features.form_builder.engine.ui4.values import ColorValue, FontValue
from app.features.form_builder.qtside.inspector.api import (
    MIXED_TEXT,
    NOT_SET_TEXT,
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
from app.qt.QtGui import QColor
from app.qt.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QFontComboBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

class ColorEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QHBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        self._hex = QLineEdit(self._root)
        self._hex.setPlaceholderText("#RRGGBB")
        self._hex.editingFinished.connect(self._commit_hex)
        self._swatch = QPushButton(self._root)
        self._swatch.setFixedWidth(28)
        self._swatch.clicked.connect(self._pick)
        layout.addWidget(self._hex, 1)
        layout.addWidget(self._swatch)

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        mark(self._hex, value)
        color = _color(value)
        text = "" if color is None else _hex(color)
        self._hex.blockSignals(True)
        self._hex.setText(text)
        self._hex.blockSignals(False)
        self._paint_swatch(color)

    def _commit_hex(self) -> None:
        try:
            color = _parse_hex(self._hex.text())
        except ValueError:
            self._host.invalid("Enter a color like #1A2B3C.")
            return
        self._paint_swatch(color)
        self._host.commit(color)

    def _pick(self) -> None:
        current = ColorValue(0, 0, 0)
        if self._hex.text().strip():
            try:
                current = _parse_hex(self._hex.text())
            except ValueError:
                current = ColorValue(0, 0, 0)
        picked = QColorDialog.getColor(_qcolor(current), self._root, "Color")
        if not picked.isValid():
            return
        alpha = picked.alpha()
        color = ColorValue(picked.red(), picked.green(), picked.blue(), None if alpha == 255 else alpha)
        self._hex.setText(_hex(color))
        self._paint_swatch(color)
        self._host.commit(color)

    def _paint_swatch(self, color: object) -> None:
        if isinstance(color, ColorValue):
            self._swatch.setStyleSheet("background: %s; border: 1px solid palette(mid);" % _hex(color))
            return
        self._swatch.setStyleSheet("background: palette(button); border: 1px solid palette(mid);")

class FontEditor:

    def __init__(self, spec: ValueSpec, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._root = QWidget(parent)
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QWidget(self._root)
        fields = QHBoxLayout(row)
        fields.setContentsMargins(0, 0, 0, 0)
        self._family = QFontComboBox(row)
        self._family.setMinimumContentsLength(10)
        self._family.setSizeAdjustPolicy(
            getattr(
                getattr(QFontComboBox, "SizeAdjustPolicy", QFontComboBox),
                "AdjustToMinimumContentsLengthWithIcon",
            )
        )
        self._family.setSizePolicy(_font_policy("Ignored"), _font_policy("Fixed"))
        self._family.setMinimumWidth(0)
        self._family.setEditable(True)
        family_edit = self._family.lineEdit()
        if family_edit is not None:
            family_edit.setPlaceholderText("Default")
            family_edit.textEdited.connect(self._mark_family)
            family_edit.editingFinished.connect(self._commit_typed_family)
        self._size = QSpinBox(row)
        self._size.setRange(0, 256)
        self._size.setSpecialValueText(NOT_SET_TEXT)
        self._shown_size = ""
        # Commit on Enter, focus-out or a step, not on every typed digit.
        self._size.setKeyboardTracking(False)
        fields.addWidget(self._family, 1)
        fields.addWidget(self._size)
        layout.addWidget(row)
        flags = QWidget(self._root)
        flag_row = QHBoxLayout(flags)
        flag_row.setContentsMargins(0, 0, 0, 0)
        self._bold = QCheckBox("Bold", flags)
        self._bold.setAccessibleName("Font: Bold")
        self._italic = QCheckBox("Italic", flags)
        self._italic.setAccessibleName("Font: Italic")
        flag_row.addWidget(self._bold)
        flag_row.addWidget(self._italic)
        layout.addWidget(flags)
        self._base = FontValue()
        self._family_touched = False
        self._family.activated.connect(self._commit_picked_family)
        self._size.valueChanged.connect(self._commit_size)
        self._bold.clicked.connect(self._commit_bold)
        self._italic.clicked.connect(self._commit_italic)

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        written = value.value if isinstance(value, Written) and isinstance(value.value, FontValue) else None
        self._base = written if written is not None else FontValue()
        self._family_touched = False
        family = "" if written is None or not written.family else written.family
        point = None if written is None else written.pointsize
        mark(self._family, value)
        mark(self._size, value)
        mark(self._bold, value)
        mark(self._italic, value)
        self._family.blockSignals(True)
        self._size.blockSignals(True)
        self._bold.blockSignals(True)
        self._italic.blockSignals(True)
        line = self._family.lineEdit()
        if line is not None:
            line.blockSignals(True)
        if family:
            self._family.setCurrentText(family)
        else:
            self._family.setCurrentIndex(-1)
            if line is not None:
                line.clear()
                line.setPlaceholderText(MIXED_TEXT if isinstance(value, Mixed) else "Default")
        if point is None:
            self._size.setSpecialValueText(MIXED_TEXT if isinstance(value, Mixed) else NOT_SET_TEXT)
            self._size.setValue(0)
        else:
            self._size.setSpecialValueText("")
            self._size.setValue(point)
        self._bold.setChecked(bool(written is not None and written.bold))
        self._italic.setChecked(bool(written is not None and written.italic))
        if line is not None:
            line.blockSignals(False)
        self._family.blockSignals(False)
        self._size.blockSignals(False)
        self._bold.blockSignals(False)
        self._italic.blockSignals(False)
        self._shown_size = self._size.text()

    def is_dirty(self) -> bool:
        """Digits typed but not committed. Esc reverts them by re-showing the value."""
        return self._size.text() != self._shown_size

    def _mark_family(self, _text: str) -> None:
        self._family_touched = True

    def _commit_picked_family(self, index: int) -> None:
        if index < 0:
            return
        self._apply_family(self._family.currentText())

    def _commit_typed_family(self) -> None:
        if not self._family_touched:
            return
        self._family_touched = False
        self._apply_family(self._family.currentText())

    def _apply_family(self, text: str) -> None:
        family = text.strip()
        if not family or family == "Default":
            return
        if self._base.family == family:
            return
        self._base = replace(self._base, family=family)
        self._host.commit(self._base)

    def _commit_size(self, number: int) -> None:
        point = int(number) or None
        if self._base.pointsize == point:
            return
        self._base = replace(self._base, pointsize=point)
        self._host.commit(self._base)

    def _commit_bold(self, checked: bool) -> None:
        flag = bool(checked)
        if self._base.bold == flag:
            return
        self._base = replace(self._base, bold=flag)
        self._host.commit(self._base)

    def _commit_italic(self, checked: bool) -> None:
        flag = bool(checked)
        if self._base.italic == flag:
            return
        self._base = replace(self._base, italic=flag)
        self._host.commit(self._base)

def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(ColorValue.ELEMENT), ColorEditor, baseline=True)
    registrar.editor(EditorKey(FontValue.ELEMENT), FontEditor, baseline=True)

def _font_policy(name: str) -> QSizePolicy.Policy:
    return getattr(getattr(QSizePolicy, "Policy", QSizePolicy), name)

def _color(value: RowValue) -> object:
    found = _payload(value)
    return found if isinstance(found, ColorValue) else None

def _payload(value: RowValue) -> object:
    if isinstance(value, Written):
        return value.value
    if isinstance(value, Unset):
        return value.default
    return None

def _hex(color: ColorValue) -> str:
    if color.alpha is None:
        return "#%02X%02X%02X" % (color.red, color.green, color.blue)
    return "#%02X%02X%02X%02X" % (color.alpha, color.red, color.green, color.blue)

def _parse_hex(text: str) -> ColorValue:
    raw = text.strip().lstrip("#")
    if len(raw) == 6:
        return ColorValue(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    if len(raw) == 8:
        return ColorValue(int(raw[2:4], 16), int(raw[4:6], 16), int(raw[6:8], 16), int(raw[0:2], 16))
    raise ValueError(text)

def _qcolor(color: ColorValue) -> QColor:
    if color.alpha is None:
        return QColor(color.red, color.green, color.blue)
    return QColor(color.red, color.green, color.blue, color.alpha)
