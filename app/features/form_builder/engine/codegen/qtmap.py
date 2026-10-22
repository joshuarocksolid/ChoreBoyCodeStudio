"""Qt class modules and enumerator spellings for generated PySide6.

The maps are the public Qt 6 type names. Two-part ``.ui`` enumerators
(``Qt::AlignCenter``) pick the scoped PySide6 form (``Qt.AlignmentFlag.AlignCenter``).
Three-part spellings already name the scope.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

_QT_CORE = frozenset(
    {
        "Qt",
        "QCoreApplication",
        "QObject",
        "QMetaObject",
        "QPoint",
        "QPointF",
        "QRect",
        "QRectF",
        "QSize",
        "QSizeF",
        "QDate",
        "QTime",
        "QDateTime",
        "QLocale",
        "QUrl",
        "QByteArray",
        "QEasingCurve",
        "QModelIndex",
        "QItemSelectionModel",
    }
)

_QT_GUI = frozenset(
    {
        "QAction",
        "QActionGroup",
        "QIcon",
        "QPixmap",
        "QImage",
        "QFont",
        "QFontDatabase",
        "QFontInfo",
        "QColor",
        "QBrush",
        "QPen",
        "QPalette",
        "QCursor",
        "QKeySequence",
        "QGradient",
        "QLinearGradient",
        "QRadialGradient",
        "QConicalGradient",
        "QTransform",
        "QPainter",
        "QPolygon",
        "QRegion",
        "QShortcut",
    }
)

_EXTRA_MODULES = {
    "QPdfView": "PySide6.QtPdfWidgets",
    "QWebEngineView": "PySide6.QtWebEngineWidgets",
    "QVideoWidget": "PySide6.QtMultimediaWidgets",
    "QChartView": "PySide6.QtCharts",
    "QSvgWidget": "PySide6.QtSvgWidgets",
    "QOpenGLWidget": "PySide6.QtOpenGLWidgets",
    "QQuickWidget": "PySide6.QtQuickWidgets",
}

# (scope, enumerator) -> scoped attribute path. Corpus two-part names plus the
# flags those forms combine. Unknown pairs fall back to ``Scope.Name``.
_ENUM_SCOPE: Dict[Tuple[str, str], str] = {}


def _fill_enum_scope() -> None:
    def add(scope: str, enum: str, names: Tuple[str, ...]) -> None:
        for name in names:
            _ENUM_SCOPE[(scope, name)] = "%s.%s.%s" % (scope, enum, name)

    add(
        "Qt",
        "AlignmentFlag",
        (
            "AlignLeft",
            "AlignRight",
            "AlignHCenter",
            "AlignJustify",
            "AlignTop",
            "AlignBottom",
            "AlignVCenter",
            "AlignBaseline",
            "AlignCenter",
            "AlignAbsolute",
            "AlignLeading",
            "AlignTrailing",
            "AlignHorizontal_Mask",
            "AlignVertical_Mask",
        ),
    )
    add("Qt", "Orientation", ("Horizontal", "Vertical"))
    add(
        "Qt",
        "FocusPolicy",
        ("NoFocus", "TabFocus", "ClickFocus", "StrongFocus", "WheelFocus"),
    )
    add("Qt", "LayoutDirection", ("LeftToRight", "RightToLeft", "LayoutDirectionAuto"))
    add(
        "Qt",
        "ScrollBarPolicy",
        (
            "ScrollBarAsNeeded",
            "ScrollBarAlwaysOff",
            "ScrollBarAlwaysOn",
        ),
    )
    add(
        "Qt",
        "ContextMenuPolicy",
        (
            "NoContextMenu",
            "DefaultContextMenu",
            "ActionsContextMenu",
            "CustomContextMenu",
            "PreventContextMenu",
        ),
    )
    add(
        "Qt",
        "WindowModality",
        ("NonModal", "WindowModal", "ApplicationModal"),
    )
    add(
        "Qt",
        "ToolBarArea",
        (
            "LeftToolBarArea",
            "RightToolBarArea",
            "TopToolBarArea",
            "BottomToolBarArea",
            "AllToolBarAreas",
            "NoToolBarArea",
        ),
    )
    add(
        "Qt",
        "DockWidgetArea",
        (
            "LeftDockWidgetArea",
            "RightDockWidgetArea",
            "TopDockWidgetArea",
            "BottomDockWidgetArea",
            "AllDockWidgetAreas",
            "NoDockWidgetArea",
        ),
    )
    add(
        "Qt",
        "CursorShape",
        (
            "ArrowCursor",
            "UpArrowCursor",
            "CrossCursor",
            "WaitCursor",
            "IBeamCursor",
            "SizeVerCursor",
            "SizeHorCursor",
            "SizeBDiagCursor",
            "SizeFDiagCursor",
            "SizeAllCursor",
            "BlankCursor",
            "SplitVCursor",
            "SplitHCursor",
            "PointingHandCursor",
            "ForbiddenCursor",
            "OpenHandCursor",
            "ClosedHandCursor",
            "WhatsThisCursor",
            "BusyCursor",
            "BitmapCursor",
        ),
    )
    add(
        "Qt",
        "ItemFlag",
        (
            "NoItemFlags",
            "ItemIsSelectable",
            "ItemIsEditable",
            "ItemIsDragEnabled",
            "ItemIsDropEnabled",
            "ItemIsUserCheckable",
            "ItemIsEnabled",
            "ItemIsAutoTristate",
            "ItemNeverHasChildren",
            "ItemIsUserTristate",
        ),
    )
    add("Qt", "CheckState", ("Unchecked", "PartiallyChecked", "Checked"))
    add("Qt", "BrushStyle", ("NoBrush", "SolidPattern", "Dense1Pattern", "Dense7Pattern", "HorPattern", "VerPattern", "CrossPattern", "BDiagPattern", "FDiagPattern", "DiagCrossPattern", "LinearGradientPattern", "RadialGradientPattern", "ConicalGradientPattern", "TexturePattern"))
    add(
        "QSizePolicy",
        "Policy",
        (
            "Fixed",
            "Minimum",
            "Maximum",
            "Preferred",
            "Expanding",
            "MinimumExpanding",
            "Ignored",
        ),
    )
    add("QFrame", "Shape", ("NoFrame", "Box", "Panel", "StyledPanel", "HLine", "VLine", "WinPanel"))
    add("QFrame", "Shadow", ("Plain", "Raised", "Sunken"))
    add(
        "QLayout",
        "SizeConstraint",
        (
            "SetDefaultConstraint",
            "SetNoConstraint",
            "SetMinimumSize",
            "SetFixedSize",
            "SetMaximumSize",
            "SetMinAndMaxSize",
        ),
    )
    add("QLineEdit", "EchoMode", ("Normal", "NoEcho", "Password", "PasswordEchoOnEdit"))
    add(
        "QAbstractItemView",
        "SelectionBehavior",
        ("SelectItems", "SelectRows", "SelectColumns"),
    )
    add(
        "QAbstractItemView",
        "SelectionMode",
        ("NoSelection", "SingleSelection", "MultiSelection", "ExtendedSelection", "ContiguousSelection"),
    )
    add("QAbstractItemView", "ScrollMode", ("ScrollPerItem", "ScrollPerPixel"))
    add(
        "QAbstractItemView",
        "EditTrigger",
        (
            "NoEditTriggers",
            "CurrentChanged",
            "DoubleClicked",
            "SelectedClicked",
            "EditKeyPressed",
            "AnyKeyPressed",
            "AllEditTriggers",
        ),
    )
    add("QListView", "Movement", ("Static", "Free", "Snap"))
    add("QListView", "ViewMode", ("ListMode", "IconMode"))
    add(
        "QFormLayout",
        "FieldGrowthPolicy",
        ("FieldsStayAtSizeHint", "ExpandingFieldsGrow", "AllNonFixedFieldsGrow"),
    )
    add("QFormLayout", "ItemRole", ("LabelRole", "FieldRole", "SpanningRole"))
    add(
        "QTabWidget",
        "TabPosition",
        ("North", "South", "West", "East"),
    )
    add("QTabWidget", "TabShape", ("Rounded", "Triangular"))
    add(
        "QSlider",
        "TickPosition",
        ("NoTicks", "TicksAbove", "TicksLeft", "TicksBelow", "TicksRight", "TicksBothSides"),
    )
    add("QAbstractSpinBox", "StepType", ("DefaultStepType", "AdaptiveDecimalStepType"))
    add("QTextEdit", "LineWrapMode", ("NoWrap", "WidgetWidth", "FixedPixelWidth", "FixedColumnWidth"))
    add(
        "QDialogButtonBox",
        "StandardButton",
        (
            "NoButton",
            "Ok",
            "Save",
            "SaveAll",
            "Open",
            "Yes",
            "YesToAll",
            "No",
            "NoToAll",
            "Abort",
            "Retry",
            "Ignore",
            "Close",
            "Cancel",
            "Discard",
            "Help",
            "Apply",
            "Reset",
            "RestoreDefaults",
        ),
    )
    add(
        "QDockWidget",
        "DockWidgetFeature",
        ("DockWidgetClosable", "DockWidgetMovable", "DockWidgetFloatable", "NoDockWidgetFeatures"),
    )
    add("QComboBox", "InsertPolicy", ("NoInsert", "InsertAtTop", "InsertAtCurrent", "InsertAtBottom", "InsertAfterCurrent", "InsertBeforeCurrent", "InsertAlphabetically"))
    add("QFont", "Weight", ("Thin", "ExtraLight", "Light", "Normal", "Medium", "DemiBold", "Bold", "ExtraBold", "Black"))


_fill_enum_scope()

_UNQUALIFIED = {
    "LeftToolBarArea": "Qt.ToolBarArea.LeftToolBarArea",
    "RightToolBarArea": "Qt.ToolBarArea.RightToolBarArea",
    "TopToolBarArea": "Qt.ToolBarArea.TopToolBarArea",
    "BottomToolBarArea": "Qt.ToolBarArea.BottomToolBarArea",
    "AllToolBarAreas": "Qt.ToolBarArea.AllToolBarAreas",
    "NoToolBarArea": "Qt.ToolBarArea.NoToolBarArea",
    "LeftDockWidgetArea": "Qt.DockWidgetArea.LeftDockWidgetArea",
    "RightDockWidgetArea": "Qt.DockWidgetArea.RightDockWidgetArea",
    "TopDockWidgetArea": "Qt.DockWidgetArea.TopDockWidgetArea",
    "BottomDockWidgetArea": "Qt.DockWidgetArea.BottomDockWidgetArea",
    "AllDockWidgetAreas": "Qt.DockWidgetArea.AllDockWidgetAreas",
    "NoDockWidgetArea": "Qt.DockWidgetArea.NoDockWidgetArea",
}

_POLICY = {
    "Fixed": "QSizePolicy.Policy.Fixed",
    "Minimum": "QSizePolicy.Policy.Minimum",
    "Maximum": "QSizePolicy.Policy.Maximum",
    "Preferred": "QSizePolicy.Policy.Preferred",
    "Expanding": "QSizePolicy.Policy.Expanding",
    "MinimumExpanding": "QSizePolicy.Policy.MinimumExpanding",
    "Ignored": "QSizePolicy.Policy.Ignored",
}

_LAYOUT_BASENAME = {
    "QVBoxLayout": "vboxLayout",
    "QHBoxLayout": "hboxLayout",
    "QGridLayout": "gridLayout",
    "QFormLayout": "formLayout",
}

_BOX = frozenset({"QVBoxLayout", "QHBoxLayout"})
_GRID = frozenset({"QGridLayout"})
_FORM = frozenset({"QFormLayout"})


def base_qt_class(class_name: str, extends: str) -> str:
    """Qt class a window or a FreeCAD fallback should subclass."""
    if extends:
        name = extends.split("::")[-1]
        if name and class_module(name):
            return name
    name = class_name.split("::")[-1]
    if class_module(name):
        return name
    return "QWidget"


def class_module(class_name: str) -> Optional[str]:
    """PySide6 module that defines ``class_name``, or None for a non-Qt name."""
    if class_name in _EXTRA_MODULES:
        return _EXTRA_MODULES[class_name]
    if class_name in _QT_CORE:
        return "PySide6.QtCore"
    if class_name in _QT_GUI:
        return "PySide6.QtGui"
    if class_name.startswith("Q") and class_name[1:2].isupper():
        return "PySide6.QtWidgets"
    return None


def enum_expr(text: str) -> str:
    """One enumerator token as a PySide6 attribute path."""
    token = text.strip()
    if not token or token == "0":
        return "0"
    parts = token.split("::")
    if len(parts) >= 3:
        return ".".join(parts)
    if len(parts) == 2:
        mapped = _ENUM_SCOPE.get((parts[0], parts[1]))
        if mapped:
            return mapped
        return "%s.%s" % (parts[0], parts[1])
    mapped_one = _UNQUALIFIED.get(token)
    if mapped_one:
        return mapped_one
    mapped_policy = _POLICY.get(token)
    if mapped_policy:
        return mapped_policy
    matches = [value for (scope, name), value in _ENUM_SCOPE.items() if name == token]
    if len(matches) == 1:
        return matches[0]
    for (scope, name), value in _ENUM_SCOPE.items():
        if name == token and scope == "Qt":
            return value
    return token


def set_expr(text: str) -> str:
    """A ``|`` flag set. Empty and ``0`` become ``0``."""
    parts = []
    for piece in text.split("|"):
        name = piece.strip()
        if not name or name == "0":
            continue
        parts.append(enum_expr(name))
    if not parts:
        return "0"
    return "|".join(parts)


def policy_expr(text: str) -> str:
    """A size-policy name (``Preferred`` or ``QSizePolicy::Policy::Preferred``)."""
    return enum_expr(text) if "::" in text else _POLICY.get(text, "QSizePolicy.Policy.%s" % text)


def layout_basename(class_name: str) -> str:
    mapped = _LAYOUT_BASENAME.get(class_name)
    if mapped:
        return mapped
    if class_name.startswith("Q") and len(class_name) > 1:
        rest = class_name[1:]
        return rest[0].lower() + rest[1:]
    if not class_name:
        return "layout"
    return class_name[0].lower() + class_name[1:]


def widget_basename(class_name: str) -> str:
    name = class_name.split("::")[-1]
    if name.startswith("Q") and len(name) > 1:
        rest = name[1:]
        return rest[0].lower() + rest[1:]
    if not name:
        return "widget"
    return name[0].lower() + name[1:]


def is_box(class_name: str) -> bool:
    return class_name in _BOX


def is_grid(class_name: str) -> bool:
    return class_name in _GRID


def is_form(class_name: str) -> bool:
    return class_name in _FORM
