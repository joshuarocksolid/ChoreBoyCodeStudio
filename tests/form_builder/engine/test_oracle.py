# pyright: reportAttributeAccessIssue=false
"""Designer files load, save, and load again to the same widget tree."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.writer import write_ui

_CORPUS = Path(__file__).resolve().parents[1] / "corpus"
_FREECAD = Path("/Applications/FreeCAD.app")


def _ui_files() -> list[Path]:
    found: list[Path] = []
    if _CORPUS.is_dir():
        found.extend(_CORPUS.rglob("*.ui"))
    if _FREECAD.is_dir():
        found.extend(path for path in _FREECAD.rglob("*.ui") if path.is_file())
    return sorted(set(found))


_FILES = _ui_files()


def _load_tree(text: str, qapp: object):
    del qapp
    from app.qt.QtCore import QBuffer, QIODevice
    from app.qt.QtUiTools import QUiLoader

    buffer = QBuffer()
    buffer.setData(text.encode("utf-8"))
    buffer.open(QIODevice.ReadOnly)
    loader = QUiLoader()
    widget = loader.load(buffer)
    error = loader.errorString()
    return widget, error


def _snapshot(widget: object) -> object:
    from app.qt.QtWidgets import QGridLayout, QWidget

    if widget is None or not isinstance(widget, QWidget):
        return None

    def walk(current: QWidget) -> dict:
        layout = current.layout()
        return {
            "class": current.metaObject().className(),
            "name": current.objectName(),
            "properties": _properties(current),
            "layout": None if layout is None else _layout(layout),
            "children": [
                walk(child)
                for child in current.children()
                if isinstance(child, QWidget) and child.parent() is current
            ],
        }

    def _layout(layout: object) -> dict:
        items = []
        count = layout.count()
        grid = isinstance(layout, QGridLayout)
        for index in range(count):
            item = layout.itemAt(index)
            row = column = 0
            if grid:
                row, column, _row_span, _col_span = layout.getItemPosition(index)
            else:
                column = index
            child = item.widget()
            nested = item.layout()
            items.append(
                {
                    "row": row,
                    "column": column,
                    "spacer": item.spacerItem() is not None,
                    "widget": walk(child) if isinstance(child, QWidget) else None,
                    "layout": _layout(nested) if nested is not None else None,
                }
            )
        return {"class": layout.metaObject().className(), "items": items}

    return walk(widget)


def _properties(widget: object) -> dict:
    meta = widget.metaObject()
    found = {}
    for index in range(meta.propertyCount()):
        prop = meta.property(index)
        name = prop.name()
        if name in ("objectName", "windowIcon"):
            continue
        found[name] = _norm(widget.property(name))
    for name in widget.dynamicPropertyNames():
        key = bytes(name).decode("utf-8", errors="replace")
        if key.startswith("_"):
            continue
        try:
            found["dyn:" + key] = _norm(widget.property(key))
        except (RuntimeError, TypeError):
            continue
    return found


def _as_int(value: object) -> int:
    from app.qt.qt_compat import enum_value

    return enum_value(value)


def _norm(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    name = type(value).__name__
    if name == "QByteArray":
        return bytes(value.data())
    if name == "QTextDocument":
        return value.toPlainText()
    if name == "QRegion":
        rect = value.boundingRect()
        return (value.isEmpty(), rect.x(), rect.y(), rect.width(), rect.height(), value.rectCount())
    if name in ("QSize", "QSizeF"):
        return (value.width(), value.height())
    if name in ("QPoint", "QPointF"):
        return (value.x(), value.y())
    if name in ("QRect", "QRectF"):
        return (value.x(), value.y(), value.width(), value.height())
    if name == "QColor":
        return None if not value.isValid() else value.name()
    if name == "QFont":
        return (
            value.family(),
            value.pointSize(),
            _as_int(value.weight()),
            value.bold(),
            value.italic(),
            value.underline(),
            value.strikeOut(),
        )
    if name == "QSizePolicy":
        return (
            _as_int(value.horizontalPolicy()),
            _as_int(value.verticalPolicy()),
            value.horizontalStretch(),
            value.verticalStretch(),
        )
    if name == "QIcon":
        return (value.isNull(), value.name(), value.themeName())
    if name == "QPixmap":
        return (value.isNull(), value.width(), value.height())
    if name in ("QDate", "QTime", "QDateTime"):
        return value.toString()
    if name == "QLocale":
        return value.name()
    if name == "QUrl":
        return value.toString()
    if name == "QCursor":
        return _as_int(value.shape())
    if name == "QBrush":
        return (_as_int(value.style()), _norm(value.color()))
    if name == "QPalette":
        from app.qt.QtGui import QPalette

        groups = (QPalette.ColorGroup.Active, QPalette.ColorGroup.Disabled, QPalette.ColorGroup.Inactive)
        roles = [role for role in QPalette.ColorRole if role.name not in ("NColorRoles", "NoRole")]
        return tuple(_norm(value.color(group, role)) for group in groups for role in roles)
    try:
        return _as_int(value)
    except (TypeError, ValueError):
        return repr(value)


@pytest.mark.oracle
@pytest.mark.skipif(not _FILES, reason="no Designer .ui files on this machine")
@pytest.mark.parametrize("path", _FILES, ids=[str(path) for path in _FILES])
def test_designer_file_widget_tree_matches_after_save(path: Path, qapp) -> None:  # type: ignore[no-untyped-def]
    original = path.read_text(encoding="utf-8")
    try:
        loaded = read_ui(original, allocator=IdAllocator())
    except UiReadError as exc:
        pytest.fail("%s refused by the reader: %s %s" % (path, exc.code, exc))
    saved = write_ui(loaded.document).text
    again = write_ui(read_ui(saved, allocator=IdAllocator()).document).text
    assert again == saved
    before, before_error = _load_tree(original, qapp)
    after, after_error = _load_tree(saved, qapp)
    if before is None or after is None:
        assert (before is None) == (after is None), "%s load mismatch %r vs %r" % (path, before_error, after_error)
        return
    assert _snapshot(before) == _snapshot(after), path.name
    before.deleteLater()
    after.deleteLater()
