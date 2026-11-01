"""One logic row: a name line, faint words, and a wrapped second line."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.qt.QtCore import QSize, Qt
from app.qt.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QPainter, QPalette, QTextCharFormat, QTextCursor, QTextDocument, QTextOption
from app.qt.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value

from app.core.constants import UI_EDITOR_FONT_FAMILY_DEFAULT
from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.theme.chrome import FALLBACK_TEXT, on_accent_for

_PLAIN = getattr(getattr(Qt, "TextFormat", Qt), "PlainText")
_FOCUS = getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus")
_CLICK = getattr(getattr(Qt, "FocusPolicy", Qt), "ClickFocus")
_NO_FOCUS = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
_TRANSPARENT = getattr(Qt, "WA_TransparentForMouseEvents")


@dataclass(frozen=True)
class PaintRoles:
    faint: str
    border: str
    row_hover: str
    selected: str
    warning: str
    on_accent: str


def paint_roles(tokens: object) -> PaintRoles:
    """Shell token fields the rows paint with. qtside does not import integration chrome."""
    accent = str(getattr(tokens, "accent", "") or "")
    text = str(getattr(tokens, "text_primary", "") or "")
    return PaintRoles(
        faint=str(getattr(tokens, "gutter_text", "") or text),
        border=str(getattr(tokens, "border", "") or text),
        row_hover=str(getattr(tokens, "tree_hover_bg", "") or ""),
        selected=str(getattr(tokens, "tree_selected_bg", "") or ""),
        warning=str(getattr(tokens, "diag_warning_color", "") or ""),
        on_accent=on_accent_for(accent) if accent else text,
    )


@dataclass(frozen=True)
class RowFace:
    """What one row shows. ``body`` wraps. It is never cut with an ellipsis."""

    title: str
    aside: str
    body: str
    code: bool
    warning: bool
    tooltip: str
    accessible: str


class WrapLabel(QWidget):
    """A second line whose height grows, breaking a long source line as well as words."""

    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._text = text
        self._color = QColor(FALLBACK_TEXT)
        self._doc = QTextDocument(self)
        self._doc.setDocumentMargin(0)
        option = QTextOption()
        mode = getattr(QTextOption, "WrapAtWordBoundaryOrAnywhere")
        option.setWrapMode(mode)
        self._doc.setDefaultTextOption(option)
        self._doc.setPlainText(text)
        self.setMinimumWidth(0)
        self.setFocusPolicy(_NO_FOCUS)
        self.setAttribute(_TRANSPARENT, True)
        ignored, preferred = _policies()
        policy = QSizePolicy(ignored, preferred)  # type: ignore[arg-type]
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def text(self) -> str:
        return self._text

    def wordWrap(self) -> bool:  # noqa: N803
        return True

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        cursor = QTextCursor(self._doc)
        cursor.select(getattr(QTextCursor, "Document"))  # type: ignore[arg-type]
        fmt = QTextCharFormat()
        fmt.setForeground(self._color)
        cursor.mergeCharFormat(fmt)
        self.update()

    def setFont(self, font: QFont) -> None:  # noqa: N802
        super().setFont(font)
        self._doc.setDefaultFont(font)
        self.updateGeometry()

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        self._doc.setTextWidth(max(1, width))
        return int(self._doc.size().height()) + 1

    def sizeHint(self) -> QSize:  # noqa: N802
        width = self.width() if self.width() > 20 else 160
        return QSize(0, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, self.heightForWidth(max(1, self.width() or 160)))

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._doc.setTextWidth(max(1, self.width()))
        self.updateGeometry()

    def paintEvent(self, event: object) -> None:  # noqa: N802
        del event
        self._doc.setTextWidth(max(1, self.width()))
        painter = QPainter(self)
        painter.setPen(self._color)
        self._doc.drawContents(painter)
        painter.end()


class LogicRow(QWidget):
    """The whole row takes hover, focus, click and Enter."""

    def __init__(
        self,
        face: RowFace,
        parent: QWidget,
        on_activate: Optional[Callable[[], None]] = None,
        *,
        takes_focus: bool = True,
    ) -> None:
        super().__init__(parent)
        self._face = face
        self._on_activate = on_activate
        self._hover = False
        self._text = ""
        self._faint = ""
        self._hover_bg = ""
        self._selected_bg = ""
        self._warning = ""
        self._panel_bg = ""
        self._code_family = UI_EDITOR_FONT_FAMILY_DEFAULT
        self.setFocusPolicy(_FOCUS if takes_focus else _CLICK)
        self.setMinimumWidth(0)
        self.setAccessibleName(face.accessible)
        self.setToolTip(face.tooltip)
        self.setMouseTracking(True)
        column = QVBoxLayout(self)
        column.setContentsMargins(4, 4, 4, 4)
        column.setSpacing(0)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self._glyph = QLabel(self)
        self._glyph.setFixedSize(16, 16)
        self._glyph.setFocusPolicy(_NO_FOCUS)
        self._glyph.setAttribute(_TRANSPARENT, True)
        self._glyph.setVisible(face.warning)
        line.addWidget(self._glyph)
        self._title = QLabel(face.title, self)
        self._title.setObjectName("formBuilder.logic.rowTitle")
        self._title.setTextFormat(_PLAIN)
        self._title.setFocusPolicy(_NO_FOCUS)
        self._title.setAttribute(_TRANSPARENT, True)
        self._title.setMinimumWidth(0)
        line.addWidget(self._title, 0)
        self._aside = QLabel(face.aside, self)
        self._aside.setObjectName("formBuilder.logic.rowAside")
        self._aside.setTextFormat(_PLAIN)
        self._aside.setFocusPolicy(_NO_FOCUS)
        self._aside.setAttribute(_TRANSPARENT, True)
        self._aside.setMinimumWidth(0)
        self._aside.setVisible(bool(face.aside))
        line.addWidget(self._aside, 1)
        self._title.setVisible(bool(face.title))
        column.addLayout(line)
        body_line = QHBoxLayout()
        body_line.setContentsMargins(0, 0, 0, 0)
        body_line.setSpacing(0)
        indent = QWidget(self)
        indent.setFixedWidth(12)
        indent.setAttribute(_TRANSPARENT, True)
        body_line.addWidget(indent)
        self._body = WrapLabel(face.body, self)
        self._body.setObjectName("formBuilder.logic.formula")
        self._body.setVisible(bool(face.body))
        body_line.addWidget(self._body, 1)
        column.addLayout(body_line)
        ignored, preferred = _policies()
        self.setSizePolicy(ignored, preferred)  # type: ignore[arg-type]

    def face(self) -> RowFace:
        return self._face

    def formula(self) -> WrapLabel:
        return self._body

    def apply_colors(
        self,
        text: str,
        faint: str,
        hover: str,
        selected: str,
        warning: str,
        panel: str,
        code_family: str,
    ) -> None:
        self._text = text
        self._faint = faint
        self._hover_bg = hover
        self._selected_bg = selected
        self._warning = warning
        self._panel_bg = panel
        self._code_family = code_family or UI_EDITOR_FONT_FAMILY_DEFAULT
        self._title.setStyleSheet("color: %s; background: transparent;" % text)
        self._aside.setStyleSheet("color: %s; background: transparent;" % faint)
        body_color = faint if not self._face.code and self._face.warning else text
        self._body.set_color(body_color)
        if self._face.code:
            # Start from the row's font so the code line keeps the body size.
            font = QFont(self.font())
            font.setFamily(self._code_family)
            font.setStyleHint(QFont.TypeWriter)  # type: ignore[attr-defined]
            font.setFixedPitch(True)
            if not QFontInfo(font).fixedPitch():
                font.setFamily(QFontDatabase.systemFont(QFontDatabase.FixedFont).family())
            self._body.setFont(font)
        if self._face.warning and warning:
            ratio = float(getattr(self, "devicePixelRatioF", lambda: 1.0)())
            self._glyph.setPixmap(paint_glyph("warning", warning, 16, ratio))
        self._paint()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        # The second line has to wrap inside the row. A layout will otherwise
        # keep the label as wide as the unwrapped source line and clip it.
        available = max(1, self.contentsRect().width() - 12)
        if self._body.maximumWidth() != available:
            self._body.setMaximumWidth(available)

    def enterEvent(self, event: object) -> None:  # noqa: N802
        self._hover = True
        self._paint()
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        self._hover = False
        self._paint()
        super().leaveEvent(event)  # type: ignore[arg-type]

    def focusInEvent(self, event: object) -> None:  # noqa: N802
        self._paint()
        super().focusInEvent(event)  # type: ignore[arg-type]

    def focusOutEvent(self, event: object) -> None:  # noqa: N802
        self._paint()
        super().focusOutEvent(event)  # type: ignore[arg-type]

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        key = enum_value(event.key())  # type: ignore[attr-defined]
        if key in (int(enum_value(Qt.Key.Key_Return)), int(enum_value(Qt.Key.Key_Enter))):
            event.accept()  # type: ignore[attr-defined]
            self._activate()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]

    def mouseReleaseEvent(self, event: object) -> None:  # noqa: N802
        self._activate()
        super().mouseReleaseEvent(event)  # type: ignore[arg-type]

    def _activate(self) -> None:
        if self._on_activate is None:
            return
        from app.qt.QtCore import QTimer

        run = self._on_activate
        QTimer.singleShot(0, run)

    def _paint(self) -> None:
        if self.hasFocus() and self._selected_bg:
            fill = self._selected_bg
        elif self._hover and self._hover_bg:
            fill = self._hover_bg
        else:
            fill = ""
        self.setAutoFillBackground(bool(fill))
        if not fill:
            return
        palette = self.palette()
        role = getattr(QPalette, "ColorRole", QPalette)
        palette.setColor(getattr(role, "Window"), QColor(fill))
        self.setPalette(palette)


def _policies() -> tuple:
    names = getattr(QSizePolicy, "Policy", QSizePolicy)
    return getattr(names, "Ignored"), getattr(names, "Preferred")
