"""Color and font."""

from __future__ import annotations

from app.features.form_builder.engine.ui4.values import ColorValue, FontValue
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    Registrar,
    RowValue,
    Unset,
    ValueSpec,
    Written,
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
    """A hex field and a swatch that opens a color picker."""

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
    """Family, point size, bold, and italic."""

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
        self._size = QSpinBox(row)
        self._size.setRange(0, 256)
        fields.addWidget(self._family, 1)
        fields.addWidget(self._size)
        layout.addWidget(row)
        flags = QWidget(self._root)
        flag_row = QHBoxLayout(flags)
        flag_row.setContentsMargins(0, 0, 0, 0)
        self._bold = QCheckBox("Bold", flags)
        self._italic = QCheckBox("Italic", flags)
        flag_row.addWidget(self._bold)
        flag_row.addWidget(self._italic)
        layout.addWidget(flags)
        self._family.currentIndexChanged.connect(self._commit)
        self._size.valueChanged.connect(self._commit)
        self._bold.clicked.connect(self._commit)
        self._italic.clicked.connect(self._commit)

    @property
    def widget(self) -> QWidget:
        return self._root

    def show(self, value: RowValue) -> None:
        font = _font(value)
        self._family.blockSignals(True)
        self._size.blockSignals(True)
        self._bold.blockSignals(True)
        self._italic.blockSignals(True)
        if font is not None and font.family:
            self._family.setCurrentText(font.family)
        self._size.setValue(0 if font is None or font.pointsize is None else font.pointsize)
        self._bold.setChecked(bool(font is not None and font.bold))
        self._italic.setChecked(bool(font is not None and font.italic))
        self._family.blockSignals(False)
        self._size.blockSignals(False)
        self._bold.blockSignals(False)
        self._italic.blockSignals(False)

    def _commit(self, _value: object = None) -> None:
        point = self._size.value()
        self._host.commit(
            FontValue(
                family=self._family.currentText() or None,
                pointsize=point or None,
                bold=self._bold.isChecked(),
                italic=self._italic.isChecked(),
            )
        )


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey(ColorValue.ELEMENT), ColorEditor, baseline=True)
    registrar.editor(EditorKey(FontValue.ELEMENT), FontEditor, baseline=True)


def _font_policy(name: str) -> QSizePolicy.Policy:
    return getattr(getattr(QSizePolicy, "Policy", QSizePolicy), name)


def _color(value: RowValue) -> object:
    found = _payload(value)
    return found if isinstance(found, ColorValue) else None


def _font(value: RowValue) -> object:
    found = _payload(value)
    return found if isinstance(found, FontValue) else None


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
