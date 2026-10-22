# pyright: reportAttributeAccessIssue=false
"""Designer files load, save, and load again to the same widget tree."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.writer import write_ui

_CORPUS = Path(__file__).resolve().parents[1] / "corpus"
_FREECAD = Path("/Applications/FreeCAD.app")

# uic calls these malformed. The ui4 contract still accepts them: language is
# stored, a missing class becomes "", and any widget class string is legal.
# They must not raise. They also have no diagnostic code in section 7.
_ACCEPTED_MALFORMED = frozenset(
    {
        "language_python.ui",
        "missing_widget_class.ui",
        "refused_QColorDialog.ui",
        "refused_QErrorMessage.ui",
        "refused_QFileDialog.ui",
        "refused_QFocusFrame.ui",
        "refused_QFontDialog.ui",
        "refused_QInputDialog.ui",
        "refused_QMdiSubWindow.ui",
        "refused_QMessageBox.ui",
        "refused_QProgressDialog.ui",
        "refused_QRhiWidget.ui",
        "refused_QSplashScreen.ui",
        "refused_QTabBar.ui",
    }
)


def _manifest_files(*folders: str) -> list[Path]:
    manifest = _CORPUS / "MANIFEST.json"
    if not manifest.is_file():
        return []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    wanted = set(folders)
    found = []
    for item in data["files"]:
        if item.get("folder") not in wanted:
            continue
        path = _CORPUS / item["path"]
        if path.is_file():
            found.append(path)
    return sorted(found)


def _oracle_files() -> list[Path]:
    found = _manifest_files("qt_examples", "synthetic")
    if _FREECAD.is_dir():
        found.extend(path for path in _FREECAD.rglob("*.ui") if path.is_file())
    return sorted(set(found))


_ORACLE_FILES = _oracle_files()
_MALFORMED_FILES = _manifest_files("malformed")


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


def _connection_list(document: object) -> tuple:
    rows = []
    for node in document.connections():
        rows.append(
            (
                node.field("sender"),
                node.field("signal"),
                node.field("receiver"),
                node.field("slot"),
                node.field("hints"),
            )
        )
    return tuple(rows)


def _same_form(original: str, saved: str, qapp: object) -> bool:
    loaded = read_ui(original, allocator=IdAllocator()).document
    rewritten = read_ui(saved, allocator=IdAllocator()).document
    if loaded.structure_fingerprint() != rewritten.structure_fingerprint():
        return False
    if _connection_list(loaded) != _connection_list(rewritten):
        return False
    before, _before_error = _load_tree(original, qapp)
    after, _after_error = _load_tree(saved, qapp)
    try:
        if before is None or after is None:
            return (before is None) == (after is None)
        return _snapshot(before) == _snapshot(after)
    finally:
        if before is not None and hasattr(before, "deleteLater"):
            before.deleteLater()
        if after is not None and hasattr(after, "deleteLater"):
            after.deleteLater()


def test_writer_that_drops_connections_fails_the_oracle(qapp: object) -> None:
    text = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="lay">
   <property name="spacing"><number>7</number></property>
   <item>
    <spacer name="gap">
     <property name="orientation"><enum>Qt::Vertical</enum></property>
     <property name="sizeType"><enum>QSizePolicy::Expanding</enum></property>
     <property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property>
    </spacer>
   </item>
  </layout>
 </widget>
 <connections>
  <connection>
   <sender>Form</sender>
   <signal>customContextMenuRequested(QPoint)</signal>
   <receiver>Form</receiver>
   <slot>update()</slot>
  </connection>
 </connections>
</ui>
"""
    from app.features.form_builder.engine.ui4 import writer as writer_module

    loaded = read_ui(text, allocator=IdAllocator())
    original = writer_module._Writer._group

    def drop(self: object, node: object, group: str, indent: int, buckets: object) -> None:
        if getattr(node, "kind", "") == "ui" and group == "connections":
            return None
        return original(self, node, group, indent, buckets)  # type: ignore[arg-type]

    writer_module._Writer._group = drop
    try:
        saved = write_ui(loaded.document).text
    finally:
        writer_module._Writer._group = original
    assert saved != write_ui(loaded.document).text
    assert not _same_form(text, saved, qapp)


def _snapshot(widget: object) -> object:
    from app.qt.QtWidgets import QGridLayout, QWidget

    if widget is None or not isinstance(widget, QWidget):
        return None

    def walk(current: QWidget) -> dict:
        layout = current.layout()
        # A laid-out child is also in children(). Walking both is 2^depth
        # snapshots, and the 15-deep corpus form then exceeds the 30s timeout.
        placed: set = set()
        layout_snapshot = _layout(layout, placed) if layout is not None else None
        return {
            "class": current.metaObject().className(),
            "name": current.objectName(),
            "properties": _properties(current),
            "layout": layout_snapshot,
            "children": [
                walk(child)
                for child in current.children()
                if isinstance(child, QWidget) and child.parent() is current and child not in placed
            ],
        }

    def _layout(layout: object, placed: set) -> dict:
        from app.qt.QtWidgets import QBoxLayout

        items = []
        count = layout.count()
        grid = isinstance(layout, QGridLayout)
        margins = layout.contentsMargins()
        for index in range(count):
            item = layout.itemAt(index)
            row = column = row_span = col_span = 0
            if grid:
                row, column, row_span, col_span = layout.getItemPosition(index)
            else:
                column = index
            child = item.widget()
            if isinstance(child, QWidget):
                placed.add(child)
            nested = item.layout()
            spacer = item.spacerItem()
            spacer_info = None
            if spacer is not None:
                hint = spacer.sizeHint()
                policy = spacer.sizePolicy()
                spacer_info = {
                    "size": (hint.width(), hint.height()),
                    "policy": (_as_int(policy.horizontalPolicy()), _as_int(policy.verticalPolicy())),
                }
            items.append(
                {
                    "row": row,
                    "column": column,
                    "row_span": row_span,
                    "col_span": col_span,
                    "spacer": spacer_info,
                    "widget": walk(child) if isinstance(child, QWidget) else None,
                    "layout": _layout(nested, placed) if nested is not None else None,
                }
            )
        stretch = None
        if isinstance(layout, QBoxLayout):
            stretch = tuple(layout.stretch(index) for index in range(count))
        elif grid:
            stretch = (
                tuple(layout.rowStretch(index) for index in range(layout.rowCount())),
                tuple(layout.columnStretch(index) for index in range(layout.columnCount())),
            )
        return {
            "class": layout.metaObject().className(),
            "margins": (margins.left(), margins.top(), margins.right(), margins.bottom()),
            "spacing": layout.spacing(),
            "stretch": stretch,
            "items": items,
        }

    return walk(widget)


def _properties(widget: object) -> dict:
    meta = widget.metaObject()
    found = {}
    for index in range(meta.propertyCount()):
        prop = meta.property(index)
        name = prop.name()
        if name == "objectName":
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


_GRADIENT_BRUSH_STYLES: object = None


def _gradient_brush_styles() -> frozenset:
    global _GRADIENT_BRUSH_STYLES
    if isinstance(_GRADIENT_BRUSH_STYLES, frozenset):
        return _GRADIENT_BRUSH_STYLES
    from app.qt.QtCore import Qt

    styles = frozenset(
        _as_int(style)
        for style in (
            Qt.BrushStyle.LinearGradientPattern,
            Qt.BrushStyle.RadialGradientPattern,
            Qt.BrushStyle.ConicalGradientPattern,
        )
    )
    _GRADIENT_BRUSH_STYLES = styles
    return styles


def _norm_gradient(gradient: object) -> object:
    if gradient is None:
        return None
    kind = type(gradient).__name__
    if kind == "QLinearGradient":
        start = gradient.start()
        end = gradient.finalStop()
        coords = (start.x(), start.y(), end.x(), end.y())
    elif kind == "QRadialGradient":
        center = gradient.center()
        focal = gradient.focalPoint()
        coords = (center.x(), center.y(), focal.x(), focal.y(), gradient.radius())
    elif kind == "QConicalGradient":
        center = gradient.center()
        coords = (center.x(), center.y(), gradient.angle())
    else:
        coords = ()
    stops = tuple((position, _norm(color)) for position, color in gradient.stops())
    return (
        _as_int(gradient.type()),
        _as_int(gradient.spread()),
        _as_int(gradient.coordinateMode()),
        coords,
        stops,
    )


def _icon_signature(icon: object) -> object:
    """Pixels per mode and state. cacheKey is unique per pixmap instance.

    A null icon has no pixmap to hash. Rendering one for every default
    windowIcon blows the oracle timeout on the 15-deep nested form.
    """
    from app.qt.QtGui import QIcon, QImage

    if icon.isNull():
        return (True, icon.name(), icon.themeName(), ())
    modes = (QIcon.Mode.Normal, QIcon.Mode.Disabled, QIcon.Mode.Active, QIcon.Mode.Selected)
    states = (QIcon.State.Off, QIcon.State.On)
    cells = []
    for mode in modes:
        for state in states:
            sizes = tuple(sorted((size.width(), size.height()) for size in icon.availableSizes(mode, state)))
            pixmap = icon.pixmap(16, 16, mode, state)
            if pixmap.isNull():
                cells.append((sizes, None))
                continue
            image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
            bits = bytes(image.constBits())
            cells.append((sizes, image.width(), image.height(), hashlib.sha256(bits).hexdigest()))
    return (False, icon.name(), icon.themeName(), tuple(cells))


def _norm(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_norm(item) for item in value)
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
        from app.qt.QtGui import QColor

        return None if not value.isValid() else value.name(QColor.NameFormat.HexArgb)
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
        return _icon_signature(value)
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
    if name == "QTimeZone":
        zone_id = value.id()
        return (bytes(zone_id.data()) if hasattr(zone_id, "data") else bytes(zone_id), value.isValid())
    if name == "QKeySequence":
        return value.toString()
    if name == "QKeyCombination":
        return (_as_int(value.keyboardModifiers()), _as_int(value.key()))
    if name == "QBrush":
        style = _as_int(value.style())
        # Solid and other non-gradient styles have no gradient. Asking for one
        # on every palette role of every widget blows the nested-form timeout.
        gradient = _norm_gradient(value.gradient()) if style in _gradient_brush_styles() else None
        return (style, _norm(value.color()), gradient)
    if name == "QPalette":
        from app.qt.QtGui import QPalette

        groups = (QPalette.ColorGroup.Active, QPalette.ColorGroup.Disabled, QPalette.ColorGroup.Inactive)
        roles = [role for role in QPalette.ColorRole if role.name not in ("NColorRoles", "NoRole")]
        return tuple(_norm(value.brush(group, role)) for group in groups for role in roles)
    try:
        return _as_int(value)
    except (TypeError, ValueError):
        return repr(value)


def _oracle_id(path: Path) -> str:
    try:
        return path.relative_to(_CORPUS).as_posix()
    except ValueError:
        return "freecad/" + path.name


@pytest.mark.oracle
@pytest.mark.skipif(not _ORACLE_FILES, reason="no Designer .ui files on this machine")
@pytest.mark.parametrize(
    "path",
    _ORACLE_FILES,
    ids=[_oracle_id(path) for path in _ORACLE_FILES],
)
def test_designer_file_widget_tree_matches_after_save(path: Path, qapp) -> None:  # type: ignore[no-untyped-def]
    original = path.read_text(encoding="utf-8")
    try:
        loaded = read_ui(original, allocator=IdAllocator())
    except UiReadError as exc:
        pytest.fail("%s refused by the reader: %s %s" % (path, exc.code, exc))
        raise  # fail() does not return; without this, pyright treats loaded as unbound
    saved = write_ui(loaded.document).text
    rewritten = read_ui(saved, allocator=IdAllocator())
    again = write_ui(rewritten.document).text
    assert again == saved
    assert rewritten.document.structure_fingerprint() == loaded.document.structure_fingerprint()
    assert _connection_list(rewritten.document) == _connection_list(loaded.document)
    before, before_error = _load_tree(original, qapp)
    after, after_error = _load_tree(saved, qapp)
    if before is None or after is None:
        assert (before is None) == (after is None), "%s load mismatch %r vs %r" % (path, before_error, after_error)
        return
    assert _snapshot(before) == _snapshot(after), path.name
    before.deleteLater()
    after.deleteLater()


def _palette_ui(active_body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0"><widget class="QWidget" name="Form">\n'
        ' <property name="palette"><palette>\n'
        "  <active>\n%s\n  </active>\n"
        "  <inactive/>\n  <disabled/>\n"
        " </palette></property>\n"
        "</widget></ui>\n" % active_body
    )


def _window_text_hex(text: str, qapp: object) -> str:
    from app.qt.QtGui import QColor, QPalette

    widget, error = _load_tree(text, qapp)
    assert widget is not None, error
    try:
        color = widget.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText)
        return color.name(QColor.NameFormat.HexArgb)
    finally:
        widget.deleteLater()


def _resave(text: str) -> str:
    return write_ui(read_ui(text, allocator=IdAllocator()).document).text


@pytest.mark.oracle
def test_legacy_color_alpha_loads_opaque_red_before_and_after(qapp: object) -> None:
    text = _palette_ui('   <color alpha="10"><red>255</red><green>0</green><blue>0</blue></color>')
    before = _window_text_hex(text, qapp)
    after = _window_text_hex(_resave(text), qapp)
    assert before == "#ffff0000"
    assert after == "#ffff0000"


@pytest.mark.oracle
def test_colorrole_then_legacy_loads_the_same_after_save(qapp: object) -> None:
    text = _palette_ui(
        '   <colorrole role="WindowText"><brush brushstyle="SolidPattern">'
        '<color alpha="255"><red>0</red><green>255</green><blue>0</blue></color>'
        "</brush></colorrole>\n"
        "   <color><red>255</red><green>0</green><blue>0</blue></color>"
    )
    before = _window_text_hex(text, qapp)
    after = _window_text_hex(_resave(text), qapp)
    assert before == "#ff00ff00"
    assert after == before


def _gradient_blocks(text: str) -> list[str]:
    return re.findall(r"<gradient\b.*?</gradient>", text, re.S)


def _qformbuilder_save(widget: object) -> str:
    from app.qt.QtCore import QBuffer, QIODevice
    from PySide6.QtDesigner import QFormBuilder

    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    QFormBuilder().save(buffer, widget)
    return bytes(buffer.data()).decode("utf-8")


@pytest.mark.oracle
def test_gradient_attribute_order_matches_qformbuilder(qapp: object) -> None:
    """QFormBuilder writes coordinates, then type, spread, and coordinatemode."""
    del qapp
    from app.qt.QtGui import QBrush, QColor, QConicalGradient, QLinearGradient, QPalette, QRadialGradient
    from app.qt.QtWidgets import QWidget

    linear = QLinearGradient(0.0, 0.0, 1.0, 1.0)
    linear.setColorAt(0.0, QColor(255, 0, 0, 255))
    linear.setColorAt(1.0, QColor(0, 0, 255, 128))
    radial = QRadialGradient(0.5, 0.5, 0.5, 0.25, 0.75)
    radial.setColorAt(0.0, QColor(255, 0, 0))
    radial.setColorAt(1.0, QColor(0, 0, 255))
    conical = QConicalGradient(0.5, 0.5, 45.0)
    conical.setColorAt(0.0, QColor(255, 0, 0))
    conical.setColorAt(1.0, QColor(0, 0, 255))

    for gradient in (linear, radial, conical):
        widget = QWidget()
        palette = widget.palette()
        palette.setBrush(QPalette.ColorGroup.Active, QPalette.ColorRole.Window, QBrush(gradient))
        widget.setPalette(palette)
        qt_text = _qformbuilder_save(widget)
        saved = write_ui(read_ui(qt_text, allocator=IdAllocator()).document).text
        qt_blocks = _gradient_blocks(qt_text)
        saved_blocks = _gradient_blocks(saved)
        assert qt_blocks, qt_text
        assert saved_blocks == qt_blocks
        widget.deleteLater()


@pytest.mark.oracle
@pytest.mark.skipif(not _MALFORMED_FILES, reason="malformed corpus is not checked out")
@pytest.mark.parametrize("path", _MALFORMED_FILES, ids=[path.name for path in _MALFORMED_FILES])
def test_malformed_corpus_produces_a_diagnostic(path: Path) -> None:
    """Malformed fixtures never raise an unexpected exception.

    ``UiReadError`` is the diagnostic for FB001/FB002/FB004/FB008. A returned
    document must carry at least one diagnostic, except the files section 7
    still accepts (see ``_ACCEPTED_MALFORMED``).
    """
    text = path.read_text(encoding="utf-8")
    try:
        loaded = read_ui(text, allocator=IdAllocator())
    except UiReadError as exc:
        assert exc.code
        return
    if path.name in _ACCEPTED_MALFORMED:
        return
    assert loaded.diagnostics, path.name
