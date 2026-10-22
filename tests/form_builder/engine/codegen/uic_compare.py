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
from typing import Callable, List, Optional, Tuple

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QLocale, QMetaMethod, QObject, QSize, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QCursor, QFont, QIcon, QPalette, QPixmap, QRegion
from PySide6.QtWidgets import QApplication, QButtonGroup, QLayout, QSizePolicy, QWidget

from app.features.form_builder.engine.codegen.api import generate_form_module
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
    return "\n".join(fixed) + "\n"


def _load(source: str, name: str):
    module = types.ModuleType(name)
    module.__file__ = name + ".py"
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
_SKIP_SIGNAL = frozenset({"destroyed", "deleteLater"})


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
        node = node.nextInFocusChain()
        if node is None or node is widget or id(node) in seen:
            break
        seen.add(id(node))
        if not isinstance(node, QWidget):
            continue
        owner = node
        inside = False
        while owner is not None:
            if owner is widget:
                inside = True
                break
            owner = owner.parentWidget()
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
            kind = bytes(method.parameterTypeName(index)).decode()
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
    nodes = [root]
    nodes.extend(root.findChildren(QObject))
    for node in nodes:
        text = ""
        reader = getattr(node, "text", None)
        if callable(reader):
            try:
                text = reader()
            except Exception:
                text = ""
        visible = bool(node.isVisible()) if isinstance(node, QWidget) else False
        enabled = bool(node.isEnabled()) if isinstance(node, QWidget) else True
        rows.append((node.objectName(), node.metaObject().className(), visible, enabled, text))
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
    nodes = [root]
    nodes.extend(root.findChildren(QObject))
    for node in nodes:
        meta = node.metaObject()
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
            if not callable(getattr(signal, "emit", None)):
                continue
            args = _emit_args(method)
            if args is None:
                continue
            before = _signal_state(root)
            try:
                signal.emit(*args)
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
        return ("bytes", bytes(value).hex())
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
    meta = obj.metaObject()
    found = {}
    for index in range(meta.propertyCount()):
        prop = meta.property(index)
        name = prop.name()
        if not prop.isStored() or not prop.isReadable() or name in SKIP_PROPS:
            continue
        try:
            value = obj.property(name)
            found[name] = _norm(value)
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
            found[name] = _norm(obj.property(name))
        except Exception:
            continue
    return found


def _layout(layout: QLayout):
    info = {
        "class": layout.metaObject().className(),
        "objectName": layout.objectName(),
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
    class_name = layout.metaObject().className()
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
            entry["objectName"] = widget.objectName()
            entry["class"] = widget.metaObject().className()
        elif nested is not None:
            entry["kind"] = "layout"
            entry["objectName"] = nested.objectName()
            entry["class"] = nested.metaObject().className()
        elif spacer is not None:
            entry["kind"] = "spacer"
            hint = spacer.sizeHint()
            entry["hint"] = (hint.width(), hint.height())
            directions = spacer.expandingDirections()
            entry["policy"] = int(directions.value) if hasattr(directions, "value") else int(directions)
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
    info = {
        "class": widget.metaObject().className(),
        "objectName": widget.objectName(),
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
        info["buddy"] = buddy.objectName() if buddy is not None else ""
    class_name = info["class"]
    if class_name in _ACTION_CLASSES:
        info["actions"] = [action.objectName() for action in widget.actions()]
    if depth == 0:
        info["focus"] = _focus_chain(widget)
    children = []
    for child in widget.children():
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


def _load_resources(document, ui_path: Path, folder: Path) -> None:
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    for node in document.ui.children("resources"):
        location = node.field("location") if hasattr(node, "field") else None
        if not isinstance(location, str) or not location:
            continue
        qrc_path = (ui_path.parent / location).resolve()
        if not qrc_path.is_file():
            continue
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


def compare(path: Path, rewrite: Optional[Callable[[str], str]] = None) -> Tuple[object, ...]:
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
    if proc.returncode != 0:
        return "uic-fail", proc.stderr[:400]
    with tempfile.TemporaryDirectory(prefix="fbgen-rc-") as folder:
        _load_resources(read.document, path, Path(folder))
        try:
            ours = _load(source, "ours_" + path.stem)
        except Exception as exc:
            ours_error = "%s: %s" % (type(exc).__name__, exc)
            try:
                _load(_strip_uic(proc.stdout), "uic_" + path.stem)
            except Exception as other:
                return "env", "%s | uic %s: %s" % (ours_error, type(other).__name__, other)
            return "ours-exec", ours_error
        try:
            theirs = _load(_strip_uic(proc.stdout), "uic_" + path.stem)
        except Exception as exc:
            return "uic-exec", "%s: %s" % (type(exc).__name__, exc)
        root_name = read.document.root.class_name.split("::")[-1]
        factory = _root_type(root_name)
        try:
            left = factory()
            _ui_class(ours)().setupUi(left)
        except Exception as exc:
            ours_error = "%s: %s" % (type(exc).__name__, exc)
            try:
                right = factory()
                _ui_class(theirs)().setupUi(right)
            except Exception as other:
                if type(other).__name__ == type(exc).__name__:
                    return "same-error", ours_error
                # uic did not build a tree either. The forms cannot be compared.
                return "uic-setup", "uic %s: %s | ours %s" % (type(other).__name__, other, ours_error)
            return "ours-setup", ours_error
        try:
            right = factory()
            _ui_class(theirs)().setupUi(right)
        except Exception as exc:
            return "uic-setup", "%s: %s" % (type(exc).__name__, exc)
        uic_text = _strip_uic(proc.stdout)
        diffs = _diff(_widget(left), _widget(right))
        diffs.extend(_diff(_translate_calls(source), _translate_calls(uic_text), "$.translate"))
        diffs.extend(_diff(_fire(left, source + "\n" + uic_text), _fire(right, source + "\n" + uic_text), "$.fired"))
        interesting = [item for item in diffs if not _ignored_diff(item)]
        if b"cbcsSplitterSizes" in data:
            _assert_splitter_sizes(left, source or "")
        return ("ok" if not interesting else "diff", interesting[:12], len(interesting), len(diffs))


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
