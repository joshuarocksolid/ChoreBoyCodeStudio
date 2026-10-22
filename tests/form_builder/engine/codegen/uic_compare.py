"""Compare one .ui file: our setupUi widget tree against uic -g python."""
from __future__ import annotations

import hashlib
import os
import re
import struct
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.form_builder.engine.codegen.uic_status import same_failure
from PySide6.QtCore import QByteArray, QLocale, QMetaMethod, QObject, QPointF, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QCursor, QFont, QIcon, QPalette, QPixmap, QRegion
from PySide6.QtWidgets import QApplication, QButtonGroup, QSizePolicy, QWidget

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.qtmap import class_module
from app.features.form_builder.engine.codegen.resources import (
    compile_resource_tree,
    read_qrc,
    render_rc_module,
)
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui

SKIP_PROPS = {
    "childrenRegion",
    "visibleRegion",
    "frameGeometry",
    "normalGeometry",
    "layoutDirection",
    # QMainWindow exposes this, and PySide raises until QTabWidget is imported.
    "tabShape",
}

# Current pixel geometry. Offscreen headers pick up a font height on one side
# only. The form's geometry property is already excluded as ``.props.geometry``.
# setSizes changes the same fields. The oracle checks splitter.sizes() instead.
_PIXEL_GEOMETRY = (
    ".props.frameRect",
    ".props.frameSize",
    ".props.rect",
    ".props.childrenRect",
    ".props.height",
    ".props.width",
    ".props.x",
    ".props.y",
    ".props.size",
)


def _strip_uic(text: str) -> str:
    """Drop C preprocessor lines uic still emits, and fill empty ``if`` bodies."""
    kept = []
    skip = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#ifndef") or stripped.startswith("#if "):
            continue
        if stripped.startswith("#ifdef"):
            skip = True
            continue
        if stripped.startswith("#else") or stripped.startswith("#elif"):
            skip = not skip
            continue
        if stripped.startswith("#endif"):
            skip = False
            continue
        if skip:
            continue
        kept.append(line)
    fixed = []
    for index, line in enumerate(kept):
        fixed.append(line)
        body = line.strip()
        if not body.endswith(":") or not (body.startswith("if ") or body.startswith("elif ") or body.startswith("else")):
            continue
        indent = len(line) - len(line.lstrip(" "))
        follower = None
        for later in kept[index + 1 :]:
            if later.strip():
                follower = later
                break
        next_indent = len(follower) - len(follower.lstrip(" ")) if follower is not None else 0
        if follower is None or next_indent <= indent:
            fixed.append(" " * (indent + 4) + "pass")
    return _pythonize_uic("\n".join(fixed) + "\n")


def _pythonize_uic(text: str) -> str:
    """uic still emits tokens Python 3 will not run.

    ``4294967295u`` is a C++ unsigned suffix. ``static_cast`` and
    ``QPalette::Active`` are C++. ``Q_UINT64_C`` of a value past signed 64-bit
    overflows PySide, and this generator omits that literal.
    """
    lines = []
    for line in text.splitlines():
        line = re.sub(r"(\d+)[uU]\b", r"\1", line)
        line = re.sub(r"static_cast<Qt::(\w+)>\(([^)]*)\)", r"Qt.\1(\2)", line)
        line = line.replace("QPalette::", "QPalette.ColorGroup.")
        line = re.sub(r"Q_INT64_C\((\d+)\)", r"\1", line)
        line = re.sub(r"QChar\((\d+)\)", lambda match: repr(chr(int(match.group(1)))), line)
        line = line.replace(".setPos(", ".move(")
        match = re.search(r"Q_UINT64_C\((\d+)\)", line)
        if match is not None:
            if int(match.group(1)) > 2**63 - 1:
                continue
            line = line.replace(match.group(0), match.group(1))
        lines.append(line)
    grids = set()
    for line in lines:
        found = re.search(r"(\w+)\.setRowStretch\(", line)
        if found is not None:
            grids.add(found.group(1))
    kept = []
    for line in lines:
        found = re.search(r"(\w+)\.setStretch\(", line)
        if found is not None and found.group(1) in grids:
            continue
        kept.append(line)
    return "\n".join(kept) + "\n"


_IMPORT_FROM = re.compile(r"^from ([\w.]+) import ([^\n]+)$", re.M)


def _install_import_stubs(source: str) -> None:
    """Give a missing promoted import a QWidget so both modules can run.

    The stub is a QWidget subclass with the imported name. PySide imports
    are left alone.
    """
    from PySide6.QtWidgets import QWidget as _QWidget

    for match in _IMPORT_FROM.finditer(source):
        module_name = match.group(1)
        if module_name.startswith("PySide6"):
            continue
        parent = None
        parts = module_name.split(".")
        for index, part in enumerate(parts):
            qual = ".".join(parts[: index + 1])
            module = sys.modules.get(qual)
            if module is None:
                module = types.ModuleType(qual)
                sys.modules[qual] = module
            if parent is not None and not hasattr(parent, part):
                setattr(parent, part, module)
            parent = module
        if parent is None:
            continue
        for raw in match.group(2).replace("(", " ").replace(")", " ").split(","):
            piece = raw.strip()
            if not piece or piece == "\\":
                continue
            imported = piece.split(" as ")[0].strip()
            if not imported.isidentifier() or hasattr(parent, imported):
                continue
            setattr(parent, imported, type(imported, (_QWidget,), {}))


def _load(source: str, name: str):
    module = types.ModuleType(name)
    module.__file__ = name + ".py"
    # id-based forms call qtTrId. uic 6.8.3 does not import it.
    module.__dict__["qtTrId"] = lambda text: text
    module.__dict__["cbcsPixmap"] = lambda path: path
    module.__dict__["qPixmapFromMimeSource"] = lambda path: path
    module.__dict__["cbcsSpacing"] = lambda: 6
    module.__dict__["cbcsMargin"] = lambda: 11
    module.__dict__["QPointF"] = QPointF
    module.__dict__["QRectF"] = QRectF
    module.__dict__["QSizeF"] = QSizeF
    exec(compile(source, name + ".py", "exec"), module.__dict__)
    return module


def _ui_class(module):
    for key, value in module.__dict__.items():
        if key.startswith("Ui_") and isinstance(value, type):
            return value
    raise RuntimeError("no Ui_ class")


def _root_type(class_name: str):
    from PySide6 import QtWidgets
    return getattr(QtWidgets, class_name, QWidget)


def _as_int(value):
    if hasattr(value, "value"):
        try:
            return int(value.value)
        except Exception:
            pass
    return int(value)


_PALETTE_GROUPS = (
    QPalette.ColorGroup.Active,
    QPalette.ColorGroup.Inactive,
    QPalette.ColorGroup.Disabled,
)
_PALETTE_ROLES = tuple(
    role
    for name in (
        "WindowText",
        "Button",
        "Light",
        "Midlight",
        "Dark",
        "Mid",
        "Text",
        "BrightText",
        "ButtonText",
        "Base",
        "Window",
        "Shadow",
        "Highlight",
        "HighlightedText",
        "Link",
        "LinkVisited",
        "AlternateBase",
        "ToolTipBase",
        "ToolTipText",
        "PlaceholderText",
        "Accent",
    )
    if (role := getattr(QPalette.ColorRole, name, None)) is not None
)
_ICON_MODES = (QIcon.Mode.Normal, QIcon.Mode.Disabled, QIcon.Mode.Active, QIcon.Mode.Selected)
_ICON_STATES = (QIcon.State.Off, QIcon.State.On)
_ACTION_CLASSES = ("QMenu", "QToolBar", "QMenuBar")
_BOX_LAYOUTS = ("QBoxLayout", "QHBoxLayout", "QVBoxLayout")
_CONNECT = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)\.connect\(")
_SKIP_SIGNAL = frozenset(
    {"destroyed", "deleteLater", "close", "accept", "reject", "finished", "done"}
)


def _image_digest(image) -> str:
    if image is None or image.isNull():
        return ""
    size = image.sizeInBytes()
    if size <= 0:
        return ""
    return hashlib.sha256(bytes(image.constBits())[:size]).hexdigest()


def _icon_norm(icon: QIcon):
    if icon.isNull():
        return ("icon", True, icon.name())
    rows = []
    for mode in _ICON_MODES:
        for state in _ICON_STATES:
            pix = icon.pixmap(32, 32, mode, state)
            rows.append((pix.isNull(), pix.width(), pix.height(), _image_digest(pix.toImage())))
    return ("icon", False, icon.name(), tuple(rows))


def _policy_norm(value: QSizePolicy):
    return (
        "policy",
        _as_int(value.horizontalPolicy()),
        _as_int(value.verticalPolicy()),
        int(value.horizontalStretch()),
        int(value.verticalStretch()),
        bool(value.hasHeightForWidth()),
    )


def _palette_norm(value: QPalette):
    colors = []
    for group in _PALETTE_GROUPS:
        for role in _PALETTE_ROLES:
            colors.append(value.color(group, role).name(QColor.NameFormat.HexArgb))
    return ("palette", int(value.resolveMask()), tuple(colors))


def _focus_chain(widget: QWidget) -> List[str]:
    """Object names inside this window, in nextInFocusChain order."""
    names = []
    node = widget
    seen = set()
    for _ in range(400):
        try:
            node = node.nextInFocusChain()
        except RuntimeError:
            break
        if node is None or node is widget or id(node) in seen:
            break
        seen.add(id(node))
        try:
            if not isinstance(node, QWidget):
                continue
            owner = node
            inside = False
            while owner is not None:
                if owner is widget:
                    inside = True
                    break
                owner = owner.parentWidget()
        except RuntimeError:
            continue
        if not inside:
            continue
        name = node.objectName()
        if not name or name.startswith("qt_"):
            continue
        # Containers sit in the chain even when they are not tab stops.
        # Their position follows creation order, which is not the tab order.
        try:
            if _as_int(node.focusPolicy()) == 0:
                continue
        except Exception:
            pass
        names.append(name)
    return names


def _read_string(text: str, index: int):
    if text.startswith("u", index) or text.startswith("U", index) or text.startswith("r", index):
        index += 1
    if index >= len(text) or text[index] not in ("'", '"'):
        return None, index
    quote = text[index]
    index += 1
    chars = []
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 1
            if index >= len(text):
                break
            escaped = text[index]
            mapping = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "'": "'", "\\": "\\"}
            if escaped in mapping:
                chars.append(mapping[escaped])
                index += 1
                continue
            if escaped == "x" and index + 2 < len(text):
                chars.append(chr(int(text[index + 1 : index + 3], 16)))
                index += 3
                continue
            if escaped == "u" and index + 4 < len(text):
                chars.append(chr(int(text[index + 1 : index + 5], 16)))
                index += 5
                continue
            chars.append(escaped)
            index += 1
            continue
        if char == quote:
            return "".join(chars), index + 1
        chars.append(char)
        index += 1
    return None, index


def _decode_arg(text: str):
    stripped = text.strip()
    if stripped == "None":
        return None
    index = 0
    parts = []
    saw_string = False
    while index < len(stripped):
        while index < len(stripped) and stripped[index] in " \t\r\n":
            index += 1
        if index >= len(stripped):
            break
        if stripped[index] in ("u", "U", "r", "'", '"'):
            literal, index = _read_string(stripped, index)
            if literal is None:
                return stripped
            parts.append(literal)
            saw_string = True
            continue
        return stripped
    if not saw_string:
        return stripped
    return "".join(parts)


def _read_call_args(source: str, start: int):
    args = []
    buf = []
    depth = 0
    quote = ""
    escape = False
    index = start
    while index < len(source):
        char = source[index]
        if quote:
            buf.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            buf.append(char)
            index += 1
            continue
        if char in "([{":
            depth += 1
            buf.append(char)
            index += 1
            continue
        if char in ")]}":
            if depth == 0 and char == ")":
                args.append("".join(buf).strip())
                return args, index + 1
            depth = max(0, depth - 1)
            buf.append(char)
            index += 1
            continue
        if char == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
            index += 1
            continue
        buf.append(char)
        index += 1
    return None, index


def _translate_calls(source: str):
    """(context, source, disambiguation) for every translate() call, sorted."""
    found = []
    needle = ".translate("
    pos = 0
    while True:
        start = source.find(needle, pos)
        if start < 0:
            break
        args, pos = _read_call_args(source, start + len(needle))
        if not args:
            continue
        decoded = [_decode_arg(arg) for arg in args[:3]]
        while len(decoded) < 3:
            decoded.append(None)
        found.append(tuple(decoded))
    found.sort()
    return found


def _emit_args(method: QMetaMethod):
    args = []
    for index in range(method.parameterCount()):
        try:
            kind = bytes(method.parameterTypeName(index).data()).decode()
        except Exception:
            return None
        if kind in ("int", "qlonglong", "qint32", "uint", "short"):
            args.append(0)
        elif kind == "bool":
            args.append(False)
        elif kind in ("double", "float"):
            args.append(0.0)
        elif kind == "QString":
            args.append("")
        elif kind == "QByteArray":
            args.append(b"")
        else:
            return None
    return args


def _signal_state(root: QWidget):
    rows = []
    nodes: List[Any] = [root]
    nodes.extend(root.findChildren(QObject))
    for node in nodes:
        text = ""
        reader = getattr(node, "text", None)
        if callable(reader):
            try:
                text = reader()
            except Exception:
                text = ""
        try:
            class_name = node.metaObject().className()
            visible = bool(node.isVisible()) if isinstance(node, QWidget) else False
            enabled = bool(node.isEnabled()) if isinstance(node, QWidget) else True
            object_name = node.objectName()
        except RuntimeError:
            continue
        rows.append((object_name, class_name, visible, enabled, text))
    focus = ""
    focus_widget = root.focusWidget()
    if focus_widget is not None:
        focus = focus_widget.objectName()
    return (tuple(rows), focus)


def _fire(root: QWidget, sources: str):
    """Emit connected signals and record the ones that changed widget state."""
    names = set(_CONNECT.findall(sources))
    if not names:
        return []
    records = []
    nodes: List[Any] = [root]
    nodes.extend(root.findChildren(QObject))
    for node in nodes:
        try:
            meta = node.metaObject()
        except RuntimeError:
            continue
        seen = set()
        methods = []
        for index in range(meta.methodCount()):
            method = meta.method(index)
            if method.methodType() == QMetaMethod.MethodType.Signal:
                methods.append(method)
        methods.sort(key=lambda method: method.parameterCount())
        for method in methods:
            try:
                name = bytes(method.name()).decode()
            except Exception:
                continue
            if name not in names or name in _SKIP_SIGNAL or name in seen:
                continue
            signal = getattr(node, name, None)
            emit = getattr(signal, "emit", None)
            if not callable(emit):
                continue
            args = _emit_args(method)
            if args is None:
                continue
            before = _signal_state(root)
            try:
                emit(*args)
            except Exception:
                continue
            seen.add(name)
            after = _signal_state(root)
            if before == after:
                continue
            changes = []
            before_rows, before_focus = before
            after_rows, after_focus = after
            for left, right in zip(before_rows, after_rows):
                if left != right:
                    changes.append((left[0], left[2:], right[2:]))
            if before_focus != after_focus:
                changes.append(("focus", before_focus, after_focus))
            if len(before_rows) != len(after_rows):
                changes.append(("len", len(before_rows), len(after_rows)))
            records.append((node.objectName(), name, tuple(changes[:6])))
    return records


def _norm(value):
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, str) or value is None:
        return value
    if isinstance(value, float):
        # Dynamic float properties come back as doubles. uic's literal is the
        # float32 rounding of the same XML number.
        rounded = struct.unpack("f", struct.pack("f", value))[0]
        if rounded == 0.0:
            rounded = 0.0
        return rounded
    if isinstance(value, QSize):
        return ("size", value.width(), value.height())
    type_name = type(value).__name__
    if type_name in ("QPoint", "QPointF"):
        return (type_name, value.x(), value.y())
    if type_name in ("QRect", "QRectF"):
        return (type_name, value.x(), value.y(), value.width(), value.height())
    if isinstance(value, QColor):
        return ("color", value.name(QColor.NameFormat.HexArgb))
    if isinstance(value, QFont):
        return ("font", value.family(), value.pointSize(), value.weight(), value.italic(), value.bold())
    if isinstance(value, QCursor):
        return ("cursor", _as_int(value.shape()))
    if isinstance(value, QLocale):
        return ("locale", value.name(), value.bcp47Name())
    if isinstance(value, QRegion):
        rect = value.boundingRect()
        return ("region", value.isNull(), value.rectCount(), rect.x(), rect.y(), rect.width(), rect.height())
    if isinstance(value, QPalette):
        return _palette_norm(value)
    if isinstance(value, QBrush):
        color = value.color()
        return ("brush", _as_int(value.style()), color.name(QColor.NameFormat.HexArgb))
    if isinstance(value, QIcon):
        return _icon_norm(value)
    if isinstance(value, QSizePolicy):
        return _policy_norm(value)
    if isinstance(value, QPixmap):
        return ("pixmap", value.isNull(), value.width(), value.height(), value.cacheKey() if False else 0)
    if isinstance(value, QByteArray):
        return ("bytes", bytes(value.data()).hex())
    if hasattr(value, "value"):
        try:
            return ("enum", _as_int(value))
        except Exception:
            pass
    try:
        return ("enum", _as_int(value))
    except Exception:
        return ("repr", type(value).__name__)


def _props(obj):
    try:
        meta = obj.metaObject()
    except RuntimeError:
        return {}
    found = {}
    try:
        count = meta.propertyCount()
    except RuntimeError:
        return {}
    for index in range(count):
        try:
            prop = meta.property(index)
            name = prop.name()
            if not prop.isStored() or not prop.isReadable() or name in SKIP_PROPS:
                continue
            raw = obj.property(name)
            if _unsigned_overflow(raw):
                continue
            found[name] = _norm(raw)
        except Exception:
            continue
    for raw_name in obj.dynamicPropertyNames():
        try:
            name = bytes(raw_name).decode()
        except Exception:
            continue
        if not name or name in found or name in SKIP_PROPS:
            continue
        try:
            raw = obj.property(name)
            if _unsigned_overflow(raw):
                continue
            found[name] = _norm(raw)
        except Exception:
            continue
    return found


def _unsigned_overflow(value) -> bool:
    """True for an integer PySide cannot pass to setProperty.

    Unsigned 64-bit max round-trips through QUiLoader and raises OverflowError
    from Python. Both snapshots omit it.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value > 9223372036854775807


def _layout(layout: Any):
    """``layout`` is any QLayout. Grid, form and box methods are read by class name."""
    try:
        class_name = layout.metaObject().className()
        object_name = layout.objectName()
    except RuntimeError:
        return {"class": "deleted", "objectName": "", "items": []}
    info = {
        "class": class_name,
        "objectName": object_name,
        "margins": layout.contentsMargins().left()
        if False
        else (
            layout.contentsMargins().left(),
            layout.contentsMargins().top(),
            layout.contentsMargins().right(),
            layout.contentsMargins().bottom(),
        ),
        "spacing": layout.spacing(),
        "items": [],
    }
    if class_name == "QGridLayout":
        info["rowStretch"] = [layout.rowStretch(i) for i in range(layout.rowCount())]
        info["colStretch"] = [layout.columnStretch(i) for i in range(layout.columnCount())]
        info["rowMin"] = [layout.rowMinimumHeight(i) for i in range(layout.rowCount())]
        info["colMin"] = [layout.columnMinimumWidth(i) for i in range(layout.columnCount())]
    for index in range(layout.count()):
        item = layout.itemAt(index)
        entry: dict = {"index": index}
        if item is None:
            info["items"].append(entry)
            continue
        widget = item.widget()
        nested = item.layout()
        spacer = item.spacerItem()
        if widget is not None:
            entry["kind"] = "widget"
            try:
                entry["objectName"] = widget.objectName()
                entry["class"] = widget.metaObject().className()
            except RuntimeError:
                entry["objectName"] = ""
                entry["class"] = "deleted"
        elif nested is not None:
            entry["kind"] = "layout"
            try:
                entry["objectName"] = nested.objectName()
                entry["class"] = nested.metaObject().className()
            except RuntimeError:
                entry["objectName"] = ""
                entry["class"] = "deleted"
        elif spacer is not None:
            entry["kind"] = "spacer"
            hint = spacer.sizeHint()
            entry["hint"] = (hint.width(), hint.height())
            directions = spacer.expandingDirections()
            entry["policy"] = _as_int(directions)
        else:
            entry["kind"] = "other"
        geo = item.geometry()
        entry["geo"] = (geo.x(), geo.y(), geo.width(), geo.height())
        try:
            entry["alignment"] = _as_int(item.alignment())
        except Exception:
            entry["alignment"] = 0
        grid = class_name
        if grid == "QGridLayout":
            row, col, rs, cs = layout.getItemPosition(index)
            entry["cell"] = (row, col, rs, cs)
        elif grid == "QFormLayout":
            row, role = layout.getItemPosition(index)
            entry["form"] = (row, _as_int(role))
        elif grid in _BOX_LAYOUTS:
            entry["stretch"] = layout.stretch(index)
        info["items"].append(entry)
    return info


def _widget(widget: QWidget, depth=0):
    if depth > 30:
        return {"truncated": True}
    try:
        class_name = widget.metaObject().className()
        object_name = widget.objectName()
    except RuntimeError:
        return {"class": "deleted", "objectName": "", "props": {}, "children": []}
    info = {
        "class": class_name,
        "objectName": object_name,
        "props": _props(widget),
    }
    layout = widget.layout()
    if layout is not None:
        info["layout"] = _layout(layout)
    buddy_fn = getattr(widget, "buddy", None)
    if callable(buddy_fn):
        try:
            buddy = buddy_fn()
        except Exception:
            buddy = None
        name_fn = getattr(buddy, "objectName", None)
        info["buddy"] = name_fn() if callable(name_fn) else ""
    if class_name in _ACTION_CLASSES:
        info["actions"] = [action.objectName() for action in widget.actions()]
    if depth == 0:
        info["focus"] = _focus_chain(widget)
    children = []
    try:
        raw_children = list(widget.children())
    except RuntimeError:
        raw_children = []
    for child in raw_children:
        try:
            if isinstance(child, QWidget):
                if child.objectName().startswith("qt_"):
                    continue
                children.append(_widget(child, depth + 1))
            elif isinstance(child, QAction):
                children.append({"class": "QAction", "objectName": child.objectName(), "props": _props(child)})
            elif isinstance(child, QButtonGroup):
                children.append(
                    {
                        "class": "QButtonGroup",
                        "objectName": child.objectName(),
                        "buttons": sorted(b.objectName() for b in child.buttons()),
                    }
                )
        except RuntimeError:
            continue
    children.sort(key=lambda item: (item.get("class", ""), item.get("objectName", "")))
    info["children"] = children
    return info


_IGNORED_PROPS = frozenset(
    {
        "geo",
        "geometry",
        "pos",
        "size",
        "minimumSizeHint",
        "sizeHint",
        "frameRect",
        "frameSize",
        "rect",
        "childrenRect",
        "height",
        "width",
        "x",
        "y",
    }
)


def _ignored_diff(item: str) -> bool:
    path = item.split(" ", 1)[0]
    for part in path.split("."):
        name = part.split("[", 1)[0]
        if name in _IGNORED_PROPS:
            return True
    return False


def _diff(left, right, path="$"):
    diffs = []
    if type(left) is not type(right) and not (isinstance(left, (list, dict)) and isinstance(right, (list, dict))):
        diffs.append("%s type %s != %s" % (path, type(left).__name__, type(right).__name__))
        return diffs
    if isinstance(left, dict):
        keys = sorted(set(left) | set(right))
        for key in keys:
            if key not in left:
                diffs.append("%s missing left .%s" % (path, key))
            elif key not in right:
                diffs.append("%s missing right .%s" % (path, key))
            else:
                diffs.extend(_diff(left[key], right[key], path + "." + str(key)))
        return diffs
    if isinstance(left, list):
        if len(left) != len(right):
            diffs.append("%s len %s != %s" % (path, len(left), len(right)))
        for index, (a, b) in enumerate(zip(left, right)):
            diffs.extend(_diff(a, b, "%s[%s]" % (path, index)))
        return diffs
    if left != right:
        diffs.append("%s %r != %r" % (path, left, right))
    return diffs


def _resource_locations(document) -> List[str]:
    found: List[str] = []
    for node in document.ui.children("resources"):
        location = node.location if hasattr(node, "location") else ""
        if location:
            found.append(location)
    for node in document.ui.children("opaque"):
        element = node.element
        if element.tag != "resources":
            continue
        for child in element.children:
            if child.tag != "include":
                continue
            location = dict(child.attrs).get("location", "")
            if location:
                found.append(location)
    return found


def _load_resources(document, ui_path: Path, folder: Path) -> None:
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    for location in _resource_locations(document):
        _write_one_resource(ui_path, folder, location)


def _write_one_resource(ui_path: Path, folder: Path, location: str) -> None:
    qrc_path = (ui_path.parent / location).resolve()
    if not qrc_path.is_file():
        return
    qrc = read_qrc(qrc_path.read_text(encoding="utf-8"))

    def read_file(rel: str, base: Path = qrc_path.parent) -> bytes:
        return (base / rel).read_bytes()

    tree, _diagnostics = compile_resource_tree(qrc, read_file=read_file)
    text = render_rc_module(tree, qrc_file_name=qrc_path.name)
    module = qrc_path.stem + "_rc.py"
    (folder / module).write_text(text, encoding="utf-8")


def _drop_resources() -> None:
    """Unregister before the module object is freed.

    ``qRegisterResourceData`` keeps the byte pointers. Deleting the module
    first leaves Qt walking freed memory on the next ``setupUi``.
    """
    for key, module in list(sys.modules.items()):
        if not key.endswith("_rc"):
            continue
        cleanup = getattr(module, "qCleanupResources", None)
        if cleanup is not None:
            try:
                cleanup()
            except Exception:
                pass
        del sys.modules[key]


# FreeCAD Designer classes and the Qt widget both sides should build.
# These six override <extends>QWidget</extends>. Other custom classes follow
# <extends>, including Gui::FileChooser -> FileChooser -> QLineEdit.
_FREECAD_STANDINS = {
    "QuantitySpinBox": "QDoubleSpinBox",
    "InputField": "QLineEdit",
    "PrefCheckBox": "QCheckBox",
    "PrefRadioButton": "QRadioButton",
    "IntSpinBox": "QSpinBox",
    "FileChooser": "QLineEdit",
}
_ACTIVE_STANDINS = dict(_FREECAD_STANDINS)
# Python names (``Gui_InputField``, ``MatGui_MaterialTreeWidget``) of this
# form's ``::`` classes, mapped to their leaf in ``_ACTIVE_STANDINS``.
_ACTIVE_CPP_NAMES: dict = {}
# First ``::`` scope of each such class (``Gui``, ``MatGui``).
_ACTIVE_SCOPES: set = set()
_RECORDING_TYPES: dict = {}


class _CppName(str):
    """A C++ scope both modules spell the same, such as ``Gui.FileChooser.Directory``.

    uic and our generator write a FreeCAD enum value as a Python attribute
    path. Each step returns the longer ``::`` name, so the recorded property
    holds the same text on both sides.
    """

    def __getattr__(self, name: str) -> "_CppName":
        if name.startswith("__"):
            raise AttributeError(name)
        return _CppName("%s::%s" % (self, name))
_OPEN_WIDGETS: List[QWidget] = []


def _record_setter(self, name: str):
    """A ``set<X>`` the Qt class lacks stores its value as property ``x``.

    FreeCAD's real class has the setter (Gui::InputField.setSingleStep,
    Gui::FileChooser.setMode, ...). The stand-in keeps the call and its value,
    so both trees show what the form set instead of both raising.
    """
    if not (name.startswith("set") and name[3:4].isupper()):
        raise AttributeError(name)
    prop = name[3].lower() + name[4:]

    def record(*args):
        value = args[0] if len(args) == 1 else list(args)
        try:
            self.setProperty(prop, value)
        except Exception:
            self.setProperty(prop, repr(value))

    return record


def _recording_type(qt_name: str):
    """One subclass per Qt class, shared by our tree and uic's.

    It keeps the Qt class name, so its meta-object class matches the widget
    QUiLoader builds for the same element.
    """
    from PySide6 import QtWidgets

    found = _RECORDING_TYPES.get(qt_name)
    if found is None:
        base = getattr(QtWidgets, qt_name, None)
        if not isinstance(base, type):
            base = QWidget
        found = type(base.__name__, (base,), {"__getattr__": _record_setter})
        _RECORDING_TYPES[qt_name] = found
    return found


def _resolve_qt_leaf(name: str, extends_of: dict, seen: set) -> Optional[str]:
    if name in seen:
        return None
    seen.add(name)
    leaf = name.split("::")[-1]
    if leaf in _FREECAD_STANDINS:
        return _FREECAD_STANDINS[leaf]
    if class_module(leaf):
        return leaf
    extends = extends_of.get(name)
    if extends is None:
        extends = extends_of.get("Gui::" + leaf)
    if not extends:
        return None
    return _resolve_qt_leaf(extends, extends_of, seen)


def _activate_standins(document) -> None:
    """Map this form's custom classes onto one Qt class for both trees."""
    global _ACTIVE_STANDINS
    extends_of = {}
    for node in document.ui.children("customwidgets"):
        class_name = getattr(node, "class_name", "")
        if not class_name:
            continue
        extends_of[class_name] = getattr(node, "extends", "") or ""
    for node in document.iter_preorder():
        class_name = getattr(node, "class_name", "")
        if isinstance(class_name, str) and "::" in class_name:
            extends_of.setdefault(class_name, "")
    resolved = dict(_FREECAD_STANDINS)
    cpp_names = {}
    _ACTIVE_SCOPES.clear()
    for class_name in extends_of:
        qt_name = _resolve_qt_leaf(class_name, extends_of, set())
        leaf = class_name.split("::")[-1]
        resolved[leaf] = qt_name or "QWidget"
        if "::" in class_name:
            cpp_names[class_name.replace("::", "_")] = leaf
            _ACTIVE_SCOPES.add(class_name.split("::", 1)[0])
    _ACTIVE_STANDINS = resolved
    _ACTIVE_CPP_NAMES.clear()
    _ACTIVE_CPP_NAMES.update(cpp_names)


class _StandInLoader:
    """UiLoader stand-in. createWidget returns the Qt class the oracle maps."""

    def createWidget(self, class_name, parent, object_name):
        leaf = str(class_name).split("::")[-1]
        qt_name = _ACTIVE_STANDINS.get(leaf)
        if qt_name is None:
            return None
        widget = _recording_type(qt_name)(parent)
        if object_name:
            widget.setObjectName(str(object_name))
        return widget


def _push_fake_freecadgui() -> bool:
    if "FreeCADGui" in sys.modules:
        return False
    module = types.ModuleType("FreeCADGui")
    setattr(module, "UiLoader", _StandInLoader)
    sys.modules["FreeCADGui"] = module
    return True


def _pop_fake_freecadgui(pushed: bool) -> None:
    if pushed:
        sys.modules.pop("FreeCADGui", None)


def _install_gui_classes(module) -> None:
    """Give a module this form's ``Gui_*`` and other ``A_B`` class names.

    uic spells ``Gui::InputField`` and ``MatGui::MaterialTreeWidget`` as
    ``Gui_InputField`` and ``MatGui_MaterialTreeWidget``. Each name is the
    recording stand-in that ``_StandInLoader`` builds for our module.
    """
    for leaf, qt_name in _ACTIVE_STANDINS.items():
        setattr(module, "Gui_" + leaf, _recording_type(qt_name))
    for python_name, leaf in _ACTIVE_CPP_NAMES.items():
        qt_name = _ACTIVE_STANDINS.get(leaf, "QWidget")
        setattr(module, python_name, _recording_type(qt_name))
    for scope in _ACTIVE_SCOPES:
        if scope.isidentifier() and not hasattr(module, scope):
            setattr(module, scope, _CppName(scope))


def _track(widget):
    if widget is not None:
        _OPEN_WIDGETS.append(widget)
    return widget


def _close_widgets() -> None:
    """Destroy top-level forms before the next file walks Qt's object tree.

    deleteLater leaves the C++ object alive until the event loop. The next
    file then reads a wrapper whose meta-object is already gone.
    """
    try:
        import shiboken6

        destroy = getattr(shiboken6, "delete", None)
    except ImportError:
        destroy = None
    while _OPEN_WIDGETS:
        widget = _OPEN_WIDGETS.pop()
        if destroy is not None:
            try:
                destroy(widget)
                continue
            except Exception:
                pass
        try:
            widget.deleteLater()
        except RuntimeError:
            pass
    app = QApplication.instance()
    if app is not None:
        try:
            app.processEvents()
        except RuntimeError:
            pass


def _exc_text(exc: BaseException) -> str:
    return "%s: %s" % (type(exc).__name__, exc)


def _qui_widget(path: Path, *, id_based: bool = False):
    from PySide6.QtCore import QBuffer, QFile, QIODevice
    from PySide6.QtUiTools import QUiLoader

    rewritten = None
    if id_based:
        import xml.etree.ElementTree as ET

        try:
            rewritten = _id_based_xml(path.read_bytes())
        except ET.ParseError:
            rewritten = None
    if rewritten is not None:
        buffer = QBuffer()
        buffer.setData(QByteArray(rewritten))
        if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
            return None
        try:
            return QUiLoader().load(buffer)
        finally:
            buffer.close()
    handle = QFile(str(path))
    if not handle.open(QIODevice.OpenModeFlag.ReadOnly):
        return None
    try:
        return QUiLoader().load(handle)
    finally:
        handle.close()


# Differences the QUiLoader fallback shows where uic's own code agrees with
# ours. The fallback runs only when uic's module cannot build a tree, so
# QUiLoader stands in for uic. Each entry says why QUiLoader differs from uic
# there. Every other difference still fails.
_QUILOADER_IGNORES = (
    (
        "id-based text",
        'idbasedtr="true": our module and uic\'s both call qtTrId(id), and with no '
        'catalog loaded that returns the id ("" when there is none). QUiLoader shows '
        "the source text, so it loads a copy whose translatable strings hold the id.",
    ),
    (
        "replaced status bar",
        "QStatusBar(w) followed by setStatusBar leaves two QStatusBar children until "
        "deleteLater runs, exactly as uic's code does. QUiLoader builds one, so the "
        "unnamed bar is dropped from our root.",
    ),
    (
        "layout function",
        "<layoutfunction> names Python functions. uic's code calls them (this harness "
        "defines cbcsMargin() = 11 and cbcsSpacing() = 6). QUiLoader cannot call them "
        "and keeps Qt's default, so a margin or spacing equal to the function's value "
        "on our side is not compared.",
    ),
    (
        "z-order property",
        "QUiLoader records <zorder> as the dynamic property _q_zOrder. uic writes "
        "raise_() calls and sets no property.",
    ),
    (
        "float property",
        "QUiLoader cannot read <float> (Designer: Reading properties of the type 20 is "
        "not supported yet) and drops the property. uic writes setProperty.",
    ),
    (
        "grid item alignment on layouts and spacers",
        "uic passes an <item alignment> to addLayout/addItem on a grid. QUiLoader "
        "applies it to widgets only and leaves nested layouts and spacers at 0, so "
        "our alignment on those items is not compared.",
    ),
)

# The values this harness's layout functions return (see ``_load``).
_LAYOUT_FUNCTION_VALUES = {"margin": 11, "spacing": 6}
_LAYOUT_VALUE = re.compile(r"^\S+\.layout\.(margins|spacing) (\([^)]*\)|-?\d+) != ")


def _drop_replaced_status_bar(tree: dict) -> dict:
    """Ours, root only: the unnamed QStatusBar setStatusBar replaced."""
    children = tree.get("children") or []
    bars = [child for child in children if child.get("class") == "QStatusBar"]
    if len(bars) < 2 or not any(child.get("objectName") for child in bars):
        return tree
    kept = [
        child
        for child in children
        if not (child.get("class") == "QStatusBar" and not child.get("objectName"))
    ]
    return dict(tree, children=kept)


def _drop_non_widget_item_alignment(node):
    """Ours: the grid-item alignment QUiLoader never sets on nested layouts and spacers."""
    if isinstance(node, list):
        return [_drop_non_widget_item_alignment(child) for child in node]
    if not isinstance(node, dict):
        return node
    copied = {key: _drop_non_widget_item_alignment(value) for key, value in node.items()}
    # Only grid items carry "cell"; box and form items are compared as they are.
    if copied.get("kind") in ("layout", "spacer") and "cell" in copied and "alignment" in copied:
        copied["alignment"] = 0
    return copied


def _id_based_xml(data: bytes) -> bytes:
    """The form as qtTrId with no catalog shows it: each translatable string is its id."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(data)
    strings = []
    for holder in root.iter():
        if holder.tag == "property":
            strings.extend(holder.findall("string"))
            for listed in holder.findall("stringlist"):
                strings.extend(listed.findall("string"))
        elif holder.tag == "attribute" and holder.get("name") in _TRANSLATED_ATTRIBUTES:
            strings.extend(holder.findall("string"))
    for element in strings:
        if element.get("notr") == "true":
            continue
        element.text = element.get("id", "")
    return ET.tostring(root, encoding="utf-8")


# Page attributes uic writes through the translate function.
_TRANSLATED_ATTRIBUTES = frozenset({"title", "label", "toolTip", "whatsThis"})


class _QuiLoaderRules:
    """The ``_QUILOADER_IGNORES`` entries, read from one form's XML."""

    def __init__(self, data: bytes) -> None:
        import xml.etree.ElementTree as ET

        self.layout_values = {}
        self.float_names = frozenset()
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return
        functions = root.find("layoutfunction")
        if functions is not None:
            if functions.get("margin"):
                self.layout_values["margins"] = str((_LAYOUT_FUNCTION_VALUES["margin"],) * 4)
            if functions.get("spacing"):
                self.layout_values["spacing"] = str(_LAYOUT_FUNCTION_VALUES["spacing"])
        self.float_names = frozenset(
            prop.get("name", "")
            for prop in root.iter("property")
            if prop.find("float") is not None
        )

    def ignored(self, item: str) -> bool:
        match = _LAYOUT_VALUE.match(item)
        if match is not None:
            return self.layout_values.get(match.group(1)) == match.group(2)
        if item.endswith(".props missing left ._q_zOrder"):
            return True
        marker = ".props missing right ."
        if marker in item:
            return item.rsplit(marker, 1)[1] in self.float_names
        return False


def _tree_result(
    left,
    right,
    source: str,
    other_source: Optional[str],
    *,
    quiloader_xml: Optional[bytes] = None,
):
    left_tree = _widget(left)
    if quiloader_xml is not None:
        left_tree = _drop_non_widget_item_alignment(_drop_replaced_status_bar(left_tree))
    diffs = _diff(left_tree, _widget(right))
    if quiloader_xml is not None:
        rules = _QuiLoaderRules(quiloader_xml)
        diffs = [item for item in diffs if not rules.ignored(item)]
    if other_source is not None:
        diffs.extend(_diff(_translate_calls(source), _translate_calls(other_source), "$.translate"))
        fired = source + "\n" + other_source
    else:
        fired = source
    diffs.extend(_diff(_fire(left, fired), _fire(right, fired), "$.fired"))
    interesting = [item for item in diffs if not _ignored_diff(item)]
    return ("ok" if not interesting else "diff", interesting[:12], len(interesting), len(diffs))


def compare(path: Path, rewrite: Optional[Callable[[str], str]] = None) -> Tuple[object, ...]:
    _close_widgets()
    _drop_resources()
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    try:
        read = read_ui(text, allocator=IdAllocator())
    except UiReadError as exc:
        return "reader", str(exc)
    scope = FormScope(
        kind="project",
        ui_path=str(path.resolve()),
        project_root=str(path.resolve().parent),
        generated_path=str(path.with_name("ui_%s.py" % path.stem)),
        window_path=str(path.with_name("%s_window.py" % path.stem)),
        module_name="ui_" + path.stem,
    )
    generated = generate_form_module(read.document, scope=scope, source_bytes=data)
    if generated.text is None:
        return "refused", [(d.code, d.message) for d in generated.diagnostics]
    source = rewrite(generated.text) if rewrite is not None else generated.text
    uic = os.environ["CBCS_FB_UIC"]
    proc = subprocess.run([uic, "-g", "python", str(path)], capture_output=True, text=True)
    uic_text = _strip_uic(proc.stdout) if proc.returncode == 0 else None
    _activate_standins(read.document)
    with tempfile.TemporaryDirectory(prefix="fbgen-rc-") as folder:
        _load_resources(read.document, path, Path(folder))
        pushed = _push_fake_freecadgui()
        try:
            return _compare_loaded(path, read, source, uic_text, proc.stderr, data)
        finally:
            _close_widgets()
            _pop_fake_freecadgui(pushed)


def _compare_loaded(path, read, source: str, uic_text: Optional[str], uic_stderr: str, data: bytes):
    """Compare setupUi to uic, or to QUiLoader when uic cannot build a tree."""
    ours_exc = None
    try:
        ours = _load(source, "ours_" + path.stem)
    except ModuleNotFoundError as exc:
        # A missing promoted module would skip the QUiLoader comparison.
        _install_import_stubs(source)
        try:
            ours = _load(source, "ours_" + path.stem)
        except Exception as retry_exc:
            ours = None
            ours_exc = retry_exc
    except Exception as exc:
        ours = None
        ours_exc = exc
    if ours is not None:
        _install_gui_classes(ours)
    theirs = None
    theirs_exc = None
    if uic_text is not None:
        try:
            theirs = _load(uic_text, "uic_" + path.stem)
            _install_gui_classes(theirs)
        except ModuleNotFoundError:
            _install_import_stubs(uic_text)
            try:
                theirs = _load(uic_text, "uic_" + path.stem)
                _install_gui_classes(theirs)
            except Exception as exc:
                theirs_exc = exc
        except Exception as exc:
            theirs_exc = exc
    if ours is None and theirs is None:
        if uic_text is None:
            return "uic-fail", (uic_stderr or "")[:400]
        if (
            ours_exc is not None
            and theirs_exc is not None
            and same_failure(ours_exc, theirs_exc)
        ):
            return "env", "%s | uic %s" % (_exc_text(ours_exc), _exc_text(theirs_exc))
        return "env-mismatch", "%s | uic %s" % (
            _exc_text(ours_exc) if ours_exc is not None else "load failed",
            _exc_text(theirs_exc) if theirs_exc is not None else "load failed",
        )
    if ours is None:
        return "ours-exec", _exc_text(ours_exc) if ours_exc is not None else "load failed"
    root_name = read.document.root.class_name.split("::")[-1]
    factory = _root_type(root_name)
    try:
        left = _track(factory())
        _ui_class(ours)().setupUi(left)
    except Exception as exc:
        if theirs is None:
            return "ours-setup", _exc_text(exc)
        try:
            right = _track(factory())
            _ui_class(theirs)().setupUi(right)
        except Exception as other:
            if same_failure(other, exc):
                return "same-error", _exc_text(exc)
            return "setup-mismatch", "uic %s | ours %s" % (_exc_text(other), _exc_text(exc))
        return "ours-setup", _exc_text(exc)
    if theirs is not None:
        try:
            right = _track(factory())
            _ui_class(theirs)().setupUi(right)
        except Exception as exc:
            loaded = _track(_qui_widget(path, id_based=_id_based(read.document)))
            if loaded is None:
                return "loader", _exc_text(exc)
            result = _tree_result(left, loaded, source, None, quiloader_xml=data)
            if b"cbcsSplitterSizes" in data:
                _assert_splitter_sizes(left, source or "")
            return result
        if b"cbcsSplitterSizes" in data:
            _assert_splitter_sizes(left, source or "")
        return _tree_result(left, right, source, uic_text)
    loaded = _track(_qui_widget(path, id_based=_id_based(read.document)))
    if loaded is None:
        detail = (uic_stderr or "uic produced no Python")[:400]
        return "loader", detail
    if b"cbcsSplitterSizes" in data:
        _assert_splitter_sizes(left, source or "")
    return _tree_result(left, loaded, source, None, quiloader_xml=data)


def _id_based(document) -> bool:
    raw = document.ui.field("idbasedtr")
    return isinstance(raw, str) and raw.strip().lower() == "true"


_SET_SIZES = re.compile(r"\.setSizes\(\[([0-9,\s-]*)\]\)")


def _splitters(widget):
    found = []
    nodes = [widget]
    nodes.extend(widget.findChildren(QWidget))
    for node in nodes:
        if node.metaObject().className() == "QSplitter":
            found.append(node)
    return found


def _assert_splitter_sizes(root, generated_text: str) -> None:
    """The stored sizes are what QSplitter.sizes() reports after setupUi.

    Qt redistributes a list whose sum is not the widget's current length.
    The check then compares the pane count and that every stored pane is positive
    when the call asked for a positive pane.
    """
    requested = []
    for match in _SET_SIZES.finditer(generated_text):
        body = match.group(1).strip()
        if not body:
            requested.append([])
            continue
        requested.append([int(part.strip()) for part in body.split(",")])
    assert requested, "cbcsSplitterSizes is set but setupUi never calls setSizes"
    splitters = _splitters(root)
    actuals = [list(splitter.sizes()) for splitter in splitters]
    assert splitters, "cbcsSplitterSizes is set but setupUi built no QSplitter"
    for sizes in requested:
        if sizes in actuals:
            continue
        same_count = [actual for actual in actuals if len(actual) == len(sizes)]
        assert same_count, "setSizes(%s) did not land; splitter sizes are %s" % (sizes, actuals)
        matched = False
        for actual in same_count:
            if sum(sizes) <= 0 or sum(actual) <= 0:
                continue
            if all((wanted > 0) == (got > 0) for wanted, got in zip(sizes, actual)):
                matched = True
                break
        assert matched, "setSizes(%s) did not land; splitter sizes are %s" % (sizes, actuals)


def main():
    app = QApplication.instance() or QApplication([])
    del app
    paths = [Path(arg) for arg in sys.argv[1:]]
    counts = {}
    diff_rows = []
    for path in paths:
        result: Tuple[object, ...]
        try:
            result = compare(path)
        except Exception as exc:
            result = ("crash", "%s: %s" % (type(exc).__name__, exc))
        status = result[0]
        counts[status] = counts.get(status, 0) + 1
        detail = result[1] if len(result) > 1 else ""
        if status != "ok":
            if status == "diff":
                samples = detail if isinstance(detail, list) else []
                diff_rows.append((str(path), result[2] if len(result) > 2 else 0, samples[:4]))
            else:
                diff_rows.append((str(path), status, detail))
        if len(paths) <= 20 or status not in ("ok",):
            print(status, path)
            if status == "diff" and isinstance(detail, list):
                for line in detail[:8]:
                    print("   ", line[:220])
            elif status != "ok":
                print("   ", detail)
    print("COUNTS", counts)
    if len(paths) > 20:
        print("--- failures", len(diff_rows))
        for row in diff_rows[:80]:
            print(row[0], row[1])
            payload = row[2]
            if isinstance(payload, list):
                for line in payload[:3]:
                    print("   ", str(line)[:200])
            else:
                print("   ", str(payload)[:200])


if __name__ == "__main__":
    main()
