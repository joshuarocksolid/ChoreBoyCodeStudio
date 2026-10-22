"""Walk a ui4 document and emit a uic-shaped PySide6 module body.

The body is a list of statements. ``setupUi`` builds the widget tree.
``retranslateUi`` assigns every string that still needs a translator.
No Qt library is imported here.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.features.form_builder.engine.codegen.api_types import CodegenOptions
from app.features.form_builder.engine.codegen.literals import py_float, py_string
from app.features.form_builder.engine.codegen.logic_hooks import (
    HELPER_TABLE,
    CodegenContext,
    Contribution,
    Method,
    load_expanders,
)
from app.features.form_builder.engine.codegen.names import (
    check_cpp_name,
    check_enum_set,
    check_py_attr,
    header_module,
    python_attr,
    python_class_stem,
    unusable_reason,
)
from app.features.form_builder.engine.codegen.qt_signals import known_class, signal_names
from app.features.form_builder.engine.codegen.qtmap import (
    class_module,
    enum_expr,
    qt_symbol,
    is_box,
    is_form,
    is_grid,
    layout_basename,
    policy_expr,
    set_expr,
    widget_basename,
)
from app.features.form_builder.engine.diagnostic_codes import fb5xx as _fb5xx
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import (
    ActionGroupNode,
    ActionNode,
    ButtonGroupNode,
    ConnectionNode,
    CustomWidgetNode,
    LayoutItemNode,
    LayoutNode,
    Node,
    ResourceNode,
    SpacerNode,
    WidgetNode,
)
from app.features.form_builder.engine.ui4.opaque import OpaqueElement
from app.features.form_builder.engine.ui4.schema import HeaderDecl, LayoutDefault, SlotsDecl
from app.features.form_builder.engine.ui4.spec import PropertyEntry
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    BrushValue,
    CStringValue,
    CharValue,
    ColorValue,
    CursorShapeValue,
    CursorValue,
    DateTimeValue,
    DateValue,
    DoubleValue,
    EnumValue,
    FloatValue,
    FontValue,
    GradientValue,
    IconSetValue,
    LocaleValue,
    LongLongValue,
    NumberValue,
    OpaqueValue,
    PaletteValue,
    PointFValue,
    PointValue,
    RectFValue,
    RectValue,
    ResourcePixmap,
    SetValue,
    SizeFValue,
    SizePolicyValue,
    SizeValue,
    StringListValue,
    StringValue,
    TimeValue,
    UIntValue,
    ULongLongValue,
    UrlValue,
    Value,
)

del _fb5xx

_TOKEN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_STRING_LITERAL = re.compile(r'u"(?:\\.|[^"\\])*"|"(?:\\.|[^"\\])*"')
_SKIP_TOKENS = frozenset({"True", "False", "None", "self"})
_LEGACY_FONT_WEIGHT = {25: "Light", 50: "Normal", 63: "DemiBold", 75: "Bold", 87: "Black"}
_QT6_FONT_WEIGHT = {
    100: "Thin",
    200: "ExtraLight",
    300: "Light",
    400: "Normal",
    500: "Medium",
    600: "DemiBold",
    700: "Bold",
    800: "ExtraBold",
    900: "Black",
}
_KEY_SEQUENCE = frozenset({"shortcut", "keySequence"})
_ICON_STATE = (
    ("normaloff", "Normal", "Off"),
    ("normalon", "Normal", "On"),
    ("disabledoff", "Disabled", "Off"),
    ("disabledon", "Disabled", "On"),
    ("activeoff", "Active", "Off"),
    ("activeon", "Active", "On"),
    ("selectedoff", "Selected", "Off"),
    ("selectedon", "Selected", "On"),
)
_DOCK_AREA = {
    0: "Qt.DockWidgetArea.LeftDockWidgetArea",
    1: "Qt.DockWidgetArea.LeftDockWidgetArea",
    2: "Qt.DockWidgetArea.RightDockWidgetArea",
    4: "Qt.DockWidgetArea.TopDockWidgetArea",
    8: "Qt.DockWidgetArea.BottomDockWidgetArea",
}
_GRADIENT = {
    "LinearGradient": "QLinearGradient",
    "RadialGradient": "QRadialGradient",
    "ConicalGradient": "QConicalGradient",
    "Linear": "QLinearGradient",
    "Radial": "QRadialGradient",
    "Conical": "QConicalGradient",
}
_FREECAD_HELPER = """
def _cbcs_widget(class_name, parent, object_name, fallback):
    widget = None
    if _cbcs_FreeCADGui is not None:
        loader = getattr(_cbcs_FreeCADGui, "UiLoader", None)
        if loader is not None:
            widget = loader().createWidget(class_name, parent, object_name)
    if widget is None:
        widget = fallback(parent)
        widget.setObjectName(object_name)
    return widget
""".strip()
_MODULE_RANK = {
    "PySide6.QtCore": 0,
    "PySide6.QtGui": 1,
    "PySide6.QtWidgets": 2,
}


@dataclass
class ModulePieces:
    """Rendered module body (no banner) plus the facts the header and result need."""

    body: str
    attribute_names: Tuple[str, ...]
    resource_modules: Tuple[str, ...]
    uses_freecadgui: bool
    has_logic: bool
    diagnostics: Tuple[FormDiagnostic, ...]
    refused: bool
    ui_class_name: str
    form_param: str


def emit_module(doc: UiDocument, scope: FormScope, options: CodegenOptions) -> ModulePieces:
    """Generate the module body, or refuse when a name cannot be emitted."""
    emitter = _Emitter(doc, scope, options)
    return emitter.build()


class _Emitter:
    def __init__(self, doc: UiDocument, scope: FormScope, options: CodegenOptions) -> None:
        self.doc = doc
        self.scope = scope
        self.options = options
        self.lines: List[str] = []
        self.retranslate: List[str] = []
        self.splitter_lines: List[str] = []
        self.imports: Dict[str, Set[str]] = {}
        self.attributes: List[str] = []
        self._seen_attrs: Set[str] = set()
        self.diagnostics: List[FormDiagnostic] = []
        self.custom: Dict[str, CustomWidgetNode] = {}
        self.promoted_modules: Dict[str, str] = {}
        self.names: Dict[int, str] = {}
        self.kinds: Dict[str, str] = {}
        self.used: Set[str] = set()
        self.buddies: List[Tuple[str, str]] = []
        self.group_buttons: Dict[str, List[str]] = {}
        self.menu_binds: List[Tuple[str, str]] = []
        self.resource_modules: List[str] = []
        self.uses_freecadgui = False
        self.refused = False
        self._deferred: List[List[str]] = []
        self._central: Set[int] = set()
        raw_class = doc.form_class_name() or "Form"
        # uic's translate() context is the C++ class, colons included.
        # The Python class stem still turns ``::`` into one underscore.
        self.context = raw_class
        self.form_param = python_attr(doc.root.object_name or "Form")
        self._xml_to_py: Dict[str, str] = {}
        self._xml_nodes: Dict[str, Node] = {}
        self.ui_class = "Ui_%s%s" % (python_class_stem(raw_class), options.postfix)
        self.id_based = self._flag("idbasedtr", options.id_based)
        translate = options.translate_function or "QCoreApplication.translate"
        self.translate_function = translate
        self.root_id = doc.root.id

    def build(self) -> ModulePieces:
        self._prepare_custom()
        self._check_names()
        if self.refused:
            return self._pieces("")
        self._assign_names()
        self._collect_resources()
        self.emit_widget(self.doc.root, "", is_root=True, skip_attrs=frozenset())
        self._emit_buddies()
        self._emit_tab_order()
        self._emit_button_groups()
        self._emit_menu_binds()
        self._emit_connections()
        contributions = self._expand()
        body = self._render(contributions)
        # ``_note`` skips the form parameter, so a root named ``QLabel`` is called
        # as the class (``QLabel(...)``) and never imported.
        if class_module(self.form_param) and re.search(
            r"(?<![\w.])%s\s*\(" % re.escape(self.form_param), body
        ):
            self.diag(
                "FB502",
                'The name "%s" can\'t be used in the generated Python. Rename it, then save the form again.'
                % self.form_param,
                node=self.doc.root,
                object_name=self.form_param,
            )
        return self._pieces(body, has_logic=self._has_logic(contributions))

    def _pieces(self, body: str, has_logic: bool = False) -> ModulePieces:
        return ModulePieces(
            body=body,
            attribute_names=tuple(self.attributes),
            resource_modules=tuple(self.resource_modules),
            uses_freecadgui=self.uses_freecadgui,
            has_logic=has_logic,
            diagnostics=tuple(self.diagnostics),
            refused=self.refused,
            ui_class_name=self.ui_class,
            form_param=self.form_param,
        )

    def diag(self, code: str, message: str, *, node: Optional[Node] = None, object_name: Optional[str] = None) -> None:
        info = CODES.get(code)
        severity = info.severity if info is not None else Severity.ERROR
        if severity is Severity.ERROR:
            self.refused = True
        self.diagnostics.append(self._diagnostic(code, severity, message, node, object_name))

    def warn(self, code: str, message: str, *, node: Optional[Node] = None, object_name: Optional[str] = None) -> None:
        """A warning does not refuse the module. Unknown references use this."""
        self.diagnostics.append(self._diagnostic(code, Severity.WARNING, message, node, object_name))

    def _diagnostic(
        self,
        code: str,
        severity: Severity,
        message: str,
        node: Optional[Node],
        object_name: Optional[str],
    ) -> FormDiagnostic:
        return FormDiagnostic(
            code=code,
            severity=severity,
            message=message,
            location=DiagnosticLocation(
                node_id=None if node is None else node.id,
                object_name=object_name,
            ),
            source="codegen",
        )

    def _flag(self, field_name: str, override: Optional[bool]) -> bool:
        if override is not None:
            return override
        raw = self.doc.ui.field(field_name)
        return isinstance(raw, str) and raw.strip().lower() == "true"

    def _prepare_custom(self) -> None:
        for node in self.doc.ui.children("customwidgets"):
            if not isinstance(node, CustomWidgetNode) or not node.class_name:
                continue
            self.custom[node.class_name] = node
            # ``Gui::`` is created through FreeCADGui. Other ``::`` classes are
            # C++ types. uic spells them ``A_B`` and does not import the header.
            # Importing that header makes the module a syntax or import error
            # before setupUi runs.
            if "::" in node.class_name:
                continue
            header = node.field("header")
            text = header.text if isinstance(header, HeaderDecl) else ""
            module = header_module(text) if isinstance(text, str) else None
            if module:
                self.promoted_modules[node.class_name] = module
                continue
            shown = text if isinstance(text, str) and text else "(empty)"
            self.diag(
                "FB504",
                'The promoted class "%s" has header "%s", which is not a Python module path. The generated form uses %s instead.'
                % (node.class_name, shown, self._fallback(node.class_name)),
                node=node,
                object_name=node.class_name,
            )

    def _check_names(self) -> None:
        if not self.ui_class.isidentifier():
            self.diag(
                "FB502",
                'The class name "%s" can\'t be used in the generated Python. Rename it, then save the form again.'
                % self.context,
                node=self.doc.ui,
                object_name=self.context,
            )
        if unusable_reason(self.form_param) or not self.form_param or _parameter_clash(self.form_param):
            self.diag(
                "FB502",
                'The name "%s" can\'t be used in the generated Python. Rename it, then save the form again.'
                % self.form_param,
                node=self.doc.root,
                object_name=self.form_param,
            )
        seen = set()
        for node in self.doc.iter_preorder():
            name = _explicit_name(node)
            if not name or not unusable_reason(python_attr(name)):
                continue
            key = (node.id, name)
            if key in seen:
                continue
            seen.add(key)
            self.diag(
                "FB502",
                'The name "%s" can\'t be used in the generated Python. Rename it, then save the form again.'
                % name,
                node=node,
                object_name=name,
            )
        self._reject_emit_names()

    def _reject_name(self, text: str, node: Optional[Node] = None) -> None:
        if text and check_cpp_name(text):
            return
        if not text:
            return
        self.diag(
            "FB502",
            'The name "%s" can\'t be used in the generated Python. Rename it, then save the form again.'
            % text,
            node=node,
            object_name=text,
        )

    def _diag_unusable(self, text: str, node: Optional[Node] = None) -> None:
        self.diag(
            "FB502",
            'The name "%s" can\'t be used in the generated Python. Rename it, then save the form again.'
            % text,
            node=node,
            object_name=text,
        )

    def _reject_enum(self, text: str, node: Optional[Node] = None) -> None:
        if check_enum_set(text):
            return
        self.diag(
            "FB502",
            'The name "%s" can\'t be used in the generated Python. Rename it, then save the form again.'
            % text,
            node=node,
            object_name=text,
        )

    def _reject_emit_names(self) -> None:
        """Every token pasted into Python as a name has to be a C++ identifier."""
        raw_class = self.doc.form_class_name()
        if raw_class:
            self._reject_name(raw_class, self.doc.ui)
        for node in self.doc.iter_preorder():
            if isinstance(node, (WidgetNode, LayoutNode, CustomWidgetNode)):
                self._reject_name(node.class_name, node)
            if isinstance(node, CustomWidgetNode) and node.extends:
                self._reject_name(node.extends, node)
            if isinstance(node, LayoutItemNode) and node.alignment:
                self._reject_enum(node.alignment, node)
            if isinstance(node, ConnectionNode):
                signal = node.signal.split("(", 1)[0].strip()
                slot = node.slot.split("(", 1)[0].strip()
                self._reject_name(signal, node)
                self._reject_name(slot, node)
            if isinstance(node, ResourceNode) and node.location:
                module = _resource_module(node.location, self.scope, self.options)
                if not module or any(not part.isidentifier() for part in module.split(".")):
                    self.diag(
                        "FB502",
                        'The resource "%s" can\'t be imported from the generated Python.' % node.location,
                        node=node,
                        object_name=node.location,
                    )
            for entry in node.properties() + node.attributes():
                self._reject_name(entry.name, node)
                self._reject_value(entry.value, node)

    def _reject_value(self, value: Value, node: Optional[Node]) -> None:
        if isinstance(value, (EnumValue, SetValue)):
            self._reject_enum(value.text, node)
            return
        if isinstance(value, CursorShapeValue):
            self._reject_name(value.name, node)
            return
        if isinstance(value, SizePolicyValue):
            self._reject_name(value.hsizetype, node)
            self._reject_name(value.vsizetype, node)
            return
        if isinstance(value, LocaleValue):
            self._reject_name(value.language, node)
            if value.country:
                self._reject_name(value.country, node)
            return
        if isinstance(value, FontValue):
            for part in (value.stylestrategy, value.hintingpreference, value.fontweight):
                if part:
                    self._reject_name(part, node)
            return
        if isinstance(value, BrushValue):
            if value.brushstyle:
                self._reject_name(value.brushstyle, node)
            if value.gradient is not None:
                self._reject_gradient(value.gradient, node)
            return
        if isinstance(value, PaletteValue):
            for group in (value.active, value.inactive, value.disabled):
                for role in group:
                    if role.role:
                        self._reject_name(role.role, node)
                    self._reject_value(role.brush, node)
            return

    def _reject_gradient(self, value: GradientValue, node: Optional[Node]) -> None:
        for part in (value.type, value.spread, value.coordinatemode):
            if part:
                self._reject_name(part, node)

    def _assign_names(self) -> None:
        # uic reserves the form parameter, then names each object in document
        # order. A later explicit name that collides gets a numeric suffix.
        self.used.add(self.form_param)
        self.names[self.root_id] = self.form_param
        self.kinds[self.form_param] = "widget"
        root_xml = self.doc.root.object_name
        if root_xml:
            self._xml_to_py[root_xml] = self.form_param
            self._xml_nodes[root_xml] = self.doc.root
        for node in self.doc.iter_preorder():
            if node.id == self.root_id:
                continue
            if not isinstance(
                node, (WidgetNode, LayoutNode, SpacerNode, ActionNode, ActionGroupNode, ButtonGroupNode)
            ):
                continue
            raw = _explicit_name(node)
            explicit = python_attr(raw) if raw else ""
            if explicit:
                if unusable_reason(explicit):
                    assigned = explicit
                    self.used.add(explicit)
                elif explicit in self.used:
                    assigned = _unique(explicit, self.used)
                else:
                    assigned = explicit
                    self.used.add(explicit)
            else:
                assigned = _unique(_invented_base(node), self.used)
            self.names[node.id] = assigned
            self.kinds[assigned] = _kind_of(node)
            if raw:
                self._xml_to_py[raw] = assigned
                self._xml_nodes.setdefault(raw, node)

    def _collect_resources(self) -> None:
        for node in self.doc.ui.children("resources"):
            location = node.field("location") if hasattr(node, "field") else None
            if not isinstance(location, str) or not location:
                continue
            module = _resource_module(location, self.scope, self.options)
            if module not in self.resource_modules:
                self.resource_modules.append(module)

    def add(self, line: str) -> None:
        self._note(line)
        self.lines.append(line)

    def later(self, line: str) -> None:
        self._note(line)
        self.retranslate.append(line)

    def need(self, module: str, name: str) -> None:
        self.imports.setdefault(module, set()).add(name)

    def note_class(self, class_name: str) -> None:
        module = class_module(class_name)
        if module:
            self.need(module, class_name)

    def _note(self, line: str) -> None:
        # String literals are text, not classes. The form parameter is a value.
        code = _STRING_LITERAL.sub(" ", line)
        for token in _TOKEN.findall(code):
            if token in _SKIP_TOKENS or token == self.form_param or not class_module(token):
                continue
            self.note_class(token)

    def remember(self, name: str) -> None:
        if name not in self._seen_attrs:
            self._seen_attrs.add(name)
            self.attributes.append(name)

    def ref_widget(self, widget: WidgetNode) -> str:
        if widget.id == self.root_id:
            return self.form_param
        return "self.%s" % self.names[widget.id]

    def ref_name(self, name: str) -> str:
        """Python expression for an XML object name.

        Only names assigned in this form are emitted. An unknown target is a
        warning and an empty string, never the raw XML text.
        """
        mapped = self._xml_to_py.get(name)
        if mapped is None:
            self.warn(
                "FB502",
                'The name "%s" isn\'t on this form, so it was left out of the generated Python.' % name,
                object_name=name,
            )
            return ""
        if mapped == self.form_param:
            return self.form_param
        return "self.%s" % mapped

    def base(self, class_name: str) -> str:
        if class_name.startswith("Gui::"):
            return self._fallback(class_name)
        custom = self.custom.get(class_name)
        if custom is not None and custom.extends and class_module(custom.extends.split("::")[-1]):
            return custom.extends.split("::")[-1]
        return class_name.split("::")[-1]

    def _fallback(self, class_name: str) -> str:
        custom = self.custom.get(class_name)
        if custom is not None and custom.extends:
            name = custom.extends.split("::")[-1]
            if name and class_module(name):
                return name
        return "QWidget"

    def tr(self, text: str, comment: Optional[str], ident: Optional[str]) -> str:
        # uic writes an empty translation as "" and never calls translate(ctx, "", None).
        if text == "":
            return py_string("")
        source = py_string(ident or "") if self.id_based else py_string(text)
        disambiguation = "None" if not comment else py_string(comment)
        return "%s(%s, %s, %s)" % (
            self.translate_function,
            py_string(self.context),
            source,
            disambiguation,
        )

    def string_expr(self, value: StringValue) -> str:
        if value.notr is True:
            return py_string(value.text)
        return self.tr(value.text, value.comment, value.id)

    def emit_widget(
        self,
        widget: WidgetNode,
        parent_expr: str,
        *,
        is_root: bool,
        skip_attrs: frozenset,
    ) -> None:
        name = self.names[widget.id]
        ref = self.form_param if is_root else "self.%s" % name
        shown = _qobject_name(widget, name)
        if not is_root:
            self.remember(name)
            self.add("%s = %s" % (ref, self._construct(widget.class_name, parent_expr, name)))
            self.add("%s.setObjectName(%s)" % (ref, py_string(shown)))
        else:
            self.add("if not %s.objectName():" % ref)
            self.add("    %s.setObjectName(%s)" % (ref, py_string(name)))
            if shown != name:
                self.add("%s.setObjectName(%s)" % (ref, py_string(shown)))
        deferred: List[str] = []
        self._deferred.append(deferred)
        self._emit_members(widget, ref, skip_attrs)
        self._emit_actions(widget, ref)
        layout = widget.layout
        # A widget can own a layout and still have direct children that are
        # not items of that layout (Designer leaves them absolutely placed).
        # uic's tree walker visits those children before the layout, and the
        # creation order sets the focus chain.
        if layout is None or widget.child_widgets:
            self._emit_children(widget)
        if layout is not None:
            self.emit_layout(layout, ref, nested=False, owner=widget)
        self._emit_headers_and_items(widget, ref)
        self._deferred.pop()
        for line in deferred:
            self.add(line)
        self._emit_zorder(widget)
        self._emit_add_actions(widget)
        group = _attr_text(widget, "buttonGroup")
        if group:
            self.group_buttons.setdefault(group, []).append(ref)

    def _construct(self, class_name: str, parent_expr: str, object_name: str) -> str:
        if class_name.startswith("Gui::"):
            self.uses_freecadgui = True
            fallback = self._fallback(class_name)
            self.note_class(fallback)
            parent = parent_expr or "None"
            return "_cbcs_widget(%s, %s, %s, %s)" % (
                py_string(class_name),
                parent,
                py_string(object_name),
                fallback,
            )
        if not check_cpp_name(class_name):
            self._reject_name(class_name)
            used = "QWidget"
            self.note_class(used)
        elif class_name in self.promoted_modules:
            used = class_name
        elif "::" in class_name:
            used = class_name.replace("::", "_")
        elif class_name in self.custom:
            used = self._fallback(class_name)
            self.note_class(used)
        elif class_name == "Line":
            # Designer writes a horizontal or vertical line as class ``Line``.
            # uic builds a QFrame and turns orientation into the frame shape.
            used = "QFrame"
            self.note_class(used)
        else:
            used = class_name.split("::")[-1]
            self.note_class(used)
        if parent_expr:
            return "%s(%s)" % (used, parent_expr)
        return "%s()" % used

    def _emit_children(self, widget: WidgetNode) -> None:
        parent_base = self.base(widget.class_name)
        skip = _structural_attrs(parent_base)
        for child in widget.child_widgets:
            parent_expr = self._parent_expr(widget, child)
            self.emit_widget(child, parent_expr, is_root=False, skip_attrs=skip)
            self._attach(widget, child)

    def _parent_expr(self, parent: WidgetNode, child: WidgetNode) -> str:
        parent_base = self.base(parent.class_name)
        if parent_base in ("QTabWidget", "QStackedWidget", "QToolBox", "QScrollArea", "QWizard", "QMdiArea", "QDockWidget"):
            return ""
        return self.ref_widget(parent)

    def _attach(self, parent: WidgetNode, child: WidgetNode) -> None:
        parent_base = self.base(parent.class_name)
        child_base = self.base(child.class_name)
        parent_ref = self.ref_widget(parent)
        child_ref = self.ref_widget(child)
        if parent_base == "QMainWindow":
            self._attach_main(parent, child, parent_ref, child_ref, child_base)
            return
        if parent_base == "QTabWidget":
            self._attach_page(parent_ref, child, child_ref, "addTab", "setTabText", "title")
            return
        if parent_base == "QToolBox":
            label = "label" if child.attr("label") is not None else "title"
            self._attach_page(parent_ref, child, child_ref, "addItem", "setItemText", label)
            return
        if parent_base == "QStackedWidget":
            self.add("%s.addWidget(%s)" % (parent_ref, child_ref))
            return
        if parent_base == "QSplitter":
            self.add("%s.addWidget(%s)" % (parent_ref, child_ref))
            return
        if parent_base == "QScrollArea":
            self.add("%s.setWidget(%s)" % (parent_ref, child_ref))
            return
        if parent_base == "QDockWidget":
            self.add("%s.setWidget(%s)" % (parent_ref, child_ref))
            return
        if parent_base == "QWizard" and child_base == "QWizardPage":
            self.add("%s.addPage(%s)" % (parent_ref, child_ref))
            return
        if parent_base == "QMdiArea":
            self.add("%s.addSubWindow(%s)" % (parent_ref, child_ref))

    def _attach_main(
        self,
        parent: WidgetNode,
        child: WidgetNode,
        parent_ref: str,
        child_ref: str,
        child_base: str,
    ) -> None:
        if child_base == "QMenuBar":
            self.add("%s.setMenuBar(%s)" % (parent_ref, child_ref))
        elif child_base == "QStatusBar":
            self.add("%s.setStatusBar(%s)" % (parent_ref, child_ref))
        elif child_base == "QToolBar":
            area = self._toolbar_area(child)
            if _attr_bool(child, "toolBarBreak"):
                self.add("%s.addToolBarBreak(%s)" % (parent_ref, area))
            self.add("%s.addToolBar(%s, %s)" % (parent_ref, area, child_ref))
        elif child_base == "QDockWidget":
            self.add("%s.addDockWidget(%s, %s)" % (parent_ref, self._dock_area(child), child_ref))
        elif parent.id not in self._central:
            self._central.add(parent.id)
            self.add("%s.setCentralWidget(%s)" % (parent_ref, child_ref))

    def _attach_page(
        self,
        parent_ref: str,
        child: WidgetNode,
        child_ref: str,
        add_name: str,
        text_name: str,
        label_attr: str,
    ) -> None:
        label = self._attr_expr(child, label_attr)
        if label is None or label[0]:
            self.add("%s.%s(%s, %s)" % (parent_ref, add_name, child_ref, py_string("")))
            if label is not None:
                self.later(
                    "%s.%s(%s.indexOf(%s), %s)" % (parent_ref, text_name, parent_ref, child_ref, label[1])
                )
        else:
            self.add("%s.%s(%s, %s)" % (parent_ref, add_name, child_ref, label[1]))
        icon = child.attr("icon")
        if icon is not None:
            lines, expr = self._lower(icon.value, child_ref, copy_hfw=False)
            self.lines.extend(lines)
            for line in lines:
                self._note(line)
            self.add("%s.setTabIcon(%s.indexOf(%s), %s)" % (parent_ref, parent_ref, child_ref, expr))
        for attr_name, method in (("toolTip", "setTabToolTip"), ("whatsThis", "setTabWhatsThis")):
            tip = self._attr_expr(child, attr_name)
            if tip is None:
                continue
            statement = "%s.%s(%s.indexOf(%s), %s)" % (parent_ref, method, parent_ref, child_ref, tip[1])
            if tip[0]:
                self.later(statement)
            else:
                self.add(statement)

    def _toolbar_area(self, widget: WidgetNode) -> str:
        attr = widget.attr("toolBarArea")
        if attr is not None and isinstance(attr.value, EnumValue):
            return enum_expr(attr.value.text)
        return "Qt.ToolBarArea.TopToolBarArea"

    def _dock_area(self, widget: WidgetNode) -> str:
        attr = widget.attr("dockWidgetArea")
        if attr is None:
            return "Qt.DockWidgetArea.LeftDockWidgetArea"
        value = attr.value
        if isinstance(value, EnumValue):
            return enum_expr(value.text)
        if isinstance(value, NumberValue):
            return _DOCK_AREA.get(value.value, "Qt.DockWidgetArea.LeftDockWidgetArea")
        return "Qt.DockWidgetArea.LeftDockWidgetArea"

    def _attr_expr(self, widget: WidgetNode, name: str) -> Optional[Tuple[bool, str]]:
        attr = widget.attr(name)
        if attr is None or not isinstance(attr.value, StringValue):
            return None
        return (attr.value.notr is not True, self.string_expr(attr.value))

    def emit_layout(
        self,
        layout: LayoutNode,
        owner_ref: str,
        *,
        nested: bool,
        owner: Optional[WidgetNode] = None,
    ) -> None:
        name = self.names[layout.id]
        ref = "self.%s" % name
        self.remember(name)
        cls = layout.class_name
        if not check_cpp_name(cls):
            self._reject_name(cls, layout)
            used = "QVBoxLayout"
            self.note_class(used)
        elif cls in self.promoted_modules:
            used = cls
        else:
            used = cls.split("::")[-1]
            self.note_class(used)
        ctor = "%s()" % used if nested else "%s(%s)" % (used, owner_ref)
        self.add("%s = %s" % (ref, ctor))
        self.add("%s.setObjectName(%s)" % (ref, py_string(_qobject_name(layout, name))))
        self._emit_layout_props(layout, ref, owner if not nested else None)
        for item in layout.items:
            self._emit_layout_item(layout, ref, owner_ref, item)
        self._emit_stretches(layout, ref)

    def _emit_layout_item(self, layout: LayoutNode, layout_ref: str, owner_ref: str, item: Node) -> None:
        content = item.content if hasattr(item, "content") else None
        if content is None:
            return
        if isinstance(content, WidgetNode):
            self.emit_widget(content, owner_ref, is_root=False, skip_attrs=frozenset())
            target = self.ref_widget(content)
            self._place(layout, layout_ref, item, target, "widget")
        elif isinstance(content, LayoutNode):
            self.emit_layout(content, owner_ref, nested=True)
            target = "self.%s" % self.names[content.id]
            self._place(layout, layout_ref, item, target, "layout")
        elif isinstance(content, SpacerNode):
            self._emit_spacer(content)
            target = "self.%s" % self.names[content.id]
            self._place(layout, layout_ref, item, target, "spacer")

    def _place(self, layout: LayoutNode, layout_ref: str, item: Node, target: str, kind: str) -> None:
        cls = layout.class_name
        row = item.row if isinstance(getattr(item, "row", None), int) else 0
        column = item.column if isinstance(getattr(item, "column", None), int) else 0
        rowspan = item.rowspan if isinstance(getattr(item, "rowspan", None), int) else 1
        colspan = item.colspan if isinstance(getattr(item, "colspan", None), int) else 1
        alignment = item.alignment if isinstance(getattr(item, "alignment", None), str) else ""
        align = set_expr(alignment) if alignment else ""
        if is_form(cls):
            role = "QFormLayout.ItemRole.LabelRole"
            if colspan > 1:
                role = "QFormLayout.ItemRole.SpanningRole"
            elif column == 1:
                role = "QFormLayout.ItemRole.FieldRole"
            if kind == "layout":
                self.add("%s.setLayout(%s, %s, %s)" % (layout_ref, row, role, target))
            else:
                method = "setWidget" if kind == "widget" else "setItem"
                self.add("%s.%s(%s, %s, %s)" % (layout_ref, method, row, role, target))
            return
        if is_grid(cls) or (not is_box(cls) and (item.row is not None or item.column is not None)):
            method = {"widget": "addWidget", "layout": "addLayout"}.get(kind, "addItem")
            args = [layout_ref, target, row, column, rowspan, colspan]
            if align:
                args.append(align)
            self.add("%s.%s(%s)" % (args[0], method, ", ".join(str(arg) for arg in args[1:])))
            return
        if kind == "widget":
            if align:
                self.add("%s.addWidget(%s, 0, %s)" % (layout_ref, target, align))
            else:
                self.add("%s.addWidget(%s)" % (layout_ref, target))
        elif kind == "layout":
            self.add("%s.addLayout(%s)" % (layout_ref, target))
        else:
            self.add("%s.addItem(%s)" % (layout_ref, target))

    def _emit_stretches(self, layout: LayoutNode, ref: str) -> None:
        mapping = (
            ("stretch", "setStretch"),
            ("rowstretch", "setRowStretch"),
            ("columnstretch", "setColumnStretch"),
            ("rowminimumheight", "setRowMinimumHeight"),
            ("columnminimumwidth", "setColumnMinimumWidth"),
        )
        for field_name, method in mapping:
            raw = layout.field(field_name)
            if not isinstance(raw, str) or not raw:
                continue
            # setStretch is a box-layout method. A grid's stretch attribute is
            # already carried by columnstretch, and calling setStretch raises.
            if method == "setStretch" and not is_box(layout.class_name.split("::")[-1]):
                continue
            for index, piece in enumerate(raw.split(",")):
                piece = piece.strip()
                if piece.lstrip("-").isdigit():
                    self.add("%s.%s(%s, %s)" % (ref, method, index, int(piece)))

    def _emit_spacer(self, spacer: SpacerNode) -> None:
        name = self.names[spacer.id]
        self.remember(name)
        width, height, horizontal, vertical = _spacer_spec(spacer)
        self.note_class("QSpacerItem")
        self.add(
            "self.%s = QSpacerItem(%s, %s, %s, %s)"
            % (name, width, height, policy_expr(horizontal), policy_expr(vertical))
        )

    def _emit_actions(self, widget: WidgetNode, owner_ref: str) -> None:
        for group in widget.children("action_groups"):
            if isinstance(group, ActionGroupNode):
                self._emit_action_group(group, owner_ref)
        for action in widget.children("actions"):
            if isinstance(action, ActionNode):
                self._emit_action(action, owner_ref)

    def _emit_action_group(self, group: ActionGroupNode, owner_ref: str) -> None:
        name = self.names[group.id]
        ref = "self.%s" % name
        self.remember(name)
        self.note_class("QActionGroup")
        self.add("%s = QActionGroup(%s)" % (ref, owner_ref))
        self.add("%s.setObjectName(%s)" % (ref, py_string(_qobject_name(group, name))))
        self._emit_members(group, ref, frozenset(), attributes=False)
        for action in group.children("actions"):
            if isinstance(action, ActionNode):
                self._emit_action(action, ref)
                self.add("%s.addAction(self.%s)" % (ref, self.names[action.id]))
        for nested in group.children("action_groups"):
            if isinstance(nested, ActionGroupNode):
                self._emit_action_group(nested, ref)

    def _emit_action(self, action: ActionNode, owner_ref: str) -> None:
        name = self.names[action.id]
        ref = "self.%s" % name
        self.remember(name)
        self.note_class("QAction")
        self.add("%s = QAction(%s)" % (ref, owner_ref))
        self.add("%s.setObjectName(%s)" % (ref, py_string(_qobject_name(action, name))))
        self._emit_members(action, ref, frozenset(), attributes=False)
        if action.menu:
            self.menu_binds.append((name, action.menu))

    def _emit_add_actions(self, widget: WidgetNode) -> None:
        ref = self.ref_widget(widget)
        for action_ref in widget.children("add_actions"):
            name = action_ref.name if hasattr(action_ref, "name") else ""
            if not isinstance(name, str) or not name:
                continue
            if name == "separator":
                self.add("%s.addSeparator()" % ref)
                continue
            target = self.ref_name(name)
            if not target:
                continue
            mapped = self._xml_to_py.get(name, "")
            if self.kinds.get(mapped) == "menu":
                self.add("%s.addAction(%s.menuAction())" % (ref, target))
            else:
                self.add("%s.addAction(%s)" % (ref, target))

    def _emit_zorder(self, widget: WidgetNode) -> None:
        for name in widget.zorder:
            if not name:
                continue
            target = self.ref_name(name)
            if target:
                self.add("%s.raise_()" % target)

    def _emit_headers_and_items(self, widget: WidgetNode, ref: str) -> None:
        base = self.base(widget.class_name)
        columns = widget.children("columns")
        rows = widget.children("rows")
        items = widget.children("items")
        if not columns and not rows and not items:
            return
        if base == "QTreeWidget":
            if columns:
                self.add("%s.setColumnCount(%s)" % (ref, len(columns)))
            for index, header in enumerate(columns):
                self._emit_item_properties(header, "%s.headerItem()" % ref, tree=True, column=index)
            self._emit_tree_items(widget, ref, items, ())
            return
        if base == "QTableWidget":
            self.note_class("QTableWidgetItem")
            if columns:
                self.add("%s.setColumnCount(%s)" % (ref, len(columns)))
            if rows:
                self.add("%s.setRowCount(%s)" % (ref, len(rows)))
            for index, header in enumerate(columns):
                self.add("item = QTableWidgetItem()")
                self.add("%s.setHorizontalHeaderItem(%s, item)" % (ref, index))
                self._emit_item_properties(
                    header,
                    "item",
                    tree=False,
                    column=0,
                    fallback_ref="%s.horizontalHeaderItem(%s)" % (ref, index),
                )
            for index, header in enumerate(rows):
                self.add("item = QTableWidgetItem()")
                self.add("%s.setVerticalHeaderItem(%s, item)" % (ref, index))
                self._emit_item_properties(
                    header,
                    "item",
                    tree=False,
                    column=0,
                    fallback_ref="%s.verticalHeaderItem(%s)" % (ref, index),
                )
            for item in items:
                row = item.row if isinstance(getattr(item, "row", None), int) else 0
                column = item.column if isinstance(getattr(item, "column", None), int) else 0
                self.add("item = QTableWidgetItem()")
                self.add("%s.setItem(%s, %s, item)" % (ref, row, column))
                self._emit_item_properties(
                    item,
                    "item",
                    tree=False,
                    column=0,
                    fallback_ref="%s.item(%s, %s)" % (ref, row, column),
                )
            return
        if base in ("QListWidget",):
            self.note_class("QListWidgetItem")
            for index, item in enumerate(items):
                self.add("item = QListWidgetItem(%s)" % ref)
                self._emit_item_properties(item, "item", tree=False, column=0, fallback_ref="%s.item(%s)" % (ref, index))
            return
        if base in ("QComboBox", "QFontComboBox"):
            for index, item in enumerate(items):
                text = item.prop("text")
                icon = item.prop("icon")
                icon_expr = ""
                if icon is not None:
                    lines, icon_expr = self._lower(icon.value, ref, copy_hfw=False)
                    for line in lines:
                        self.add(line)
                literal = py_string("")
                if text is not None and isinstance(text.value, StringValue):
                    if text.value.notr is True:
                        literal = self.string_expr(text.value)
                    else:
                        self.later(
                            "%s.setItemText(%s, %s)" % (ref, index, self.string_expr(text.value))
                        )
                if icon_expr:
                    self.add("%s.addItem(%s, %s)" % (ref, icon_expr, literal))
                else:
                    self.add("%s.addItem(%s)" % (ref, literal))
            return
        for item in items:
            self._emit_item_properties(item, ref, tree=False, column=0)

    def _emit_tree_items(self, widget: WidgetNode, ref: str, items: Sequence[Node], path: Tuple[int, ...]) -> None:
        self.note_class("QTreeWidgetItem")
        for index, item in enumerate(items):
            parent_expr = ref if not path else "item"
            if not path:
                self.add("item = QTreeWidgetItem(%s)" % ref)
            else:
                self.add("item = QTreeWidgetItem(item)")
            item_path = path + (index,)
            lookup = _tree_lookup(ref, item_path)
            self._emit_item_properties(item, "item", tree=True, column=None, fallback_ref=lookup)
            self._emit_tree_items(widget, ref, item.children("subitems"), item_path)
            del parent_expr

    def _emit_item_properties(
        self,
        item: Node,
        ref: str,
        *,
        tree: bool,
        column: Optional[int],
        fallback_ref: str = "",
    ) -> None:
        texts = _text_values(item)
        for index, value in enumerate(texts):
            if not isinstance(value, StringValue):
                continue
            expr = self.string_expr(value)
            if tree:
                statement = "%s.setText(%s, %s)" % (ref, index if column is None else column + index, expr)
                later_ref = fallback_ref or ref
                later = "%s.setText(%s, %s)" % (later_ref, index if column is None else column + index, expr)
            else:
                statement = "%s.setText(%s)" % (ref, expr)
                later = "%s.setText(%s)" % (fallback_ref or ref, expr)
            if value.notr is True:
                self.add(statement)
            else:
                self.later(later)
        for prop in item.properties():
            if prop.name == "text":
                continue
            self._emit_one_property(item, ref, prop, copy_hfw=False)

    def _emit_members(
        self, node: Node, ref: str, skip_attrs: frozenset, *, attributes: bool = True
    ) -> None:
        """Properties, then attributes. uic writes no code for the
        ``<attribute>`` children of ``<action>`` and ``<actiongroup>``, so their
        callers pass ``attributes=False``."""
        if isinstance(node, LayoutNode):
            self._emit_layout_props(node, ref)
            return
        for prop in node.properties():
            self._emit_one_property(node, ref, prop, copy_hfw=True)
        if not attributes:
            return
        for attr in node.attributes():
            if attr.name in skip_attrs or attr.name == "buttonGroup":
                continue
            self._emit_one_property(node, ref, attr, copy_hfw=False)

    def _layout_default(self) -> Tuple[Optional[int], Optional[int]]:
        raw = self.doc.ui.field("layoutdefault")
        if not isinstance(raw, LayoutDefault):
            return None, None
        return raw.margin, raw.spacing

    def _emit_layout_props(self, layout: LayoutNode, ref: str, owner: Optional[WidgetNode]) -> None:
        margin: Optional[int] = None
        sides = {"leftMargin": None, "topMargin": None, "rightMargin": None, "bottomMargin": None}
        spacing: Optional[int] = None
        horizontal: Optional[int] = None
        vertical: Optional[int] = None
        for prop in layout.properties():
            if prop.name == "objectName":
                continue
            if prop.name == "margin" and isinstance(prop.value, NumberValue):
                margin = prop.value.value
                continue
            if prop.name in sides and isinstance(prop.value, NumberValue):
                sides[prop.name] = prop.value.value
                continue
            if prop.name == "spacing" and isinstance(prop.value, NumberValue):
                spacing = prop.value.value
                continue
            if prop.name == "horizontalSpacing" and isinstance(prop.value, NumberValue):
                horizontal = prop.value.value
                continue
            if prop.name == "verticalSpacing" and isinstance(prop.value, NumberValue):
                vertical = prop.value.value
                continue
            self._emit_one_property(layout, ref, prop, copy_hfw=False)
        default_margin, default_spacing = self._layout_default()
        # Designer names the holder of a broken-out layout layoutWidget. uic
        # clears that layout's margins instead of applying the form default.
        holder = owner is not None and owner.object_name.startswith("layoutWidget")
        if holder and margin is None and all(value is None for value in sides.values()):
            self.add("%s.setContentsMargins(0, 0, 0, 0)" % ref)
        elif any(value is not None for value in sides.values()) or margin is not None:
            def pick(side: str) -> int:
                if sides[side] is not None:
                    return int(sides[side])
                if margin is not None:
                    return int(margin)
                # -1 keeps the side Qt already applied (the layoutdefault or the style).
                return -1

            self.add(
                "%s.setContentsMargins(%s, %s, %s, %s)"
                % (ref, pick("leftMargin"), pick("topMargin"), pick("rightMargin"), pick("bottomMargin"))
            )
        elif default_margin is not None:
            self.add(
                "%s.setContentsMargins(%s, %s, %s, %s)"
                % (ref, default_margin, default_margin, default_margin, default_margin)
            )
        if spacing is None:
            spacing = default_spacing
        if spacing is not None:
            self.add("%s.setSpacing(%s)" % (ref, spacing))
        if horizontal is not None:
            self.add("%s.setHorizontalSpacing(%s)" % (ref, horizontal))
        if vertical is not None:
            self.add("%s.setVerticalSpacing(%s)" % (ref, vertical))

    def _emit_one_property(self, node: Node, ref: str, prop: PropertyEntry, *, copy_hfw: bool) -> None:
        if prop.name == "objectName":
            return
        if prop.name == "pos" and isinstance(prop.value, PointValue):
            # QWidget has move(), not setPos(). uic still writes setPos, and setupUi raises.
            self.add("%s.move(%s, %s)" % (ref, prop.value.x, prop.value.y))
            return
        if isinstance(node, WidgetNode) and node.class_name == "Line" and prop.name == "orientation":
            text = prop.value.text if isinstance(prop.value, EnumValue) else ""
            shape = "VLine" if "Vertical" in text else "HLine"
            self.note_class("QFrame")
            self.add("%s.setFrameShape(QFrame.Shape.%s)" % (ref, shape))
            self.add("%s.setFrameShadow(QFrame.Shadow.Sunken)" % ref)
            return
        if prop.name == "headerVisible" and isinstance(prop.value, BoolValue):
            self.note_class("QHeaderView")
            shown = "True" if prop.value.value else "False"
            self.add("%s.header().setVisible(%s)" % (ref, shown))
            return
        accessor = _header_accessor(prop.name)
        if accessor is not None:
            lines, expr = self._lower(prop.value, ref, copy_hfw=False)
            for line in lines:
                self.add(line)
            self.note_class("QHeaderView")
            rest = prop.name[len(accessor) :]
            method = _HEADER_METHODS.get(rest)
            if method:
                self.add("%s.%s().%s(%s)" % (ref, accessor, method, expr))
            else:
                prop_name = rest[:1].lower() + rest[1:]
                self.add("%s.%s().setProperty(%s, %s)" % (ref, accessor, py_string(prop_name), expr))
            return
        if prop.name == "buddy":
            target = _plain_text(prop.value)
            if target:
                self.buddies.append((ref, target))
            return
        if prop.name == "geometry" and isinstance(prop.value, RectValue):
            if ref == self.form_param:
                self.add("%s.resize(%s, %s)" % (ref, prop.value.width, prop.value.height))
            else:
                self.add(
                    "%s.setGeometry(QRect(%s, %s, %s, %s))"
                    % (ref, prop.value.x, prop.value.y, prop.value.width, prop.value.height)
                )
            return
        if prop.name == "cbcsSplitterSizes" and isinstance(node, WidgetNode) and self.base(node.class_name) == "QSplitter":
            rendered = _sizes_literal(prop.value)
            if rendered:
                self.splitter_lines.append("%s.setSizes(%s)" % (ref, rendered))
        if prop.name == "currentIndex" and not _translated(prop.value):
            line = self._apply(node, ref, prop, copy_hfw=False)
            if line and self._deferred:
                self._deferred[-1].append(line)
            return
        line = self._apply(node, ref, prop, copy_hfw=copy_hfw)
        if not line:
            return
        if _translated(prop.value):
            self.later(line)
        else:
            self.add(line)

    def _apply(self, node: Node, ref: str, prop: PropertyEntry, *, copy_hfw: bool) -> str:
        lines, expr = self._lower(prop.value, ref, copy_hfw=copy_hfw and prop.name == "sizePolicy" and not prop.is_dynamic)
        for line in lines:
            self.add(line)
        if prop.name in _KEY_SEQUENCE and isinstance(prop.value, (StringValue, CStringValue)):
            expr = "QKeySequence(%s)" % expr
            self.note_class("QKeySequence")
        if prop.is_dynamic or prop.name == "cbcsSplitterSizes":
            # PySide's setProperty takes a signed 64-bit integer. An unsigned
            # 64-bit max raises OverflowError and setupUi stops.
            if isinstance(prop.value, ULongLongValue) and prop.value.value > 9223372036854775807:
                return ""
            return "%s.setProperty(%s, %s)" % (ref, py_string(prop.name), expr)
        # The name becomes part of a method name, so a keyword is fine (setClass)
        # but a scope is not (setA::b).
        if not (prop.name.isidentifier() and prop.name.isascii()):
            self._diag_unusable(prop.name, node)
            return ""
        method = "set" + prop.name[:1].upper() + prop.name[1:]
        return "%s.%s(%s)" % (ref, method, expr)

    def _lower(self, value: Value, ref: str, *, copy_hfw: bool) -> Tuple[List[str], str]:
        if isinstance(value, StringValue):
            return [], self.string_expr(value)
        if isinstance(value, CStringValue):
            return [], py_string(value.text)
        if isinstance(value, StringListValue):
            return [], self._string_list(value)
        if isinstance(value, BoolValue):
            return [], "True" if value.value else "False"
        if isinstance(value, (NumberValue, UIntValue, LongLongValue, ULongLongValue)):
            return [], str(value.value)
        if isinstance(value, (FloatValue, DoubleValue)):
            return [], py_float(value.value)
        if isinstance(value, EnumValue):
            return [], enum_expr(value.text)
        if isinstance(value, SetValue):
            return [], set_expr(value.text)
        if isinstance(value, CharValue):
            return [], py_string(chr(value.unicode))
        if isinstance(value, PointValue):
            return [], "QPoint(%s, %s)" % (value.x, value.y)
        if isinstance(value, PointFValue):
            return [], "QPointF(%s, %s)" % (py_float(value.x), py_float(value.y))
        if isinstance(value, SizeValue):
            return [], "QSize(%s, %s)" % (value.width, value.height)
        if isinstance(value, OpaqueValue):
            boxed = _opaque_box(value.element)
            if boxed:
                return [], boxed
        if isinstance(value, SizeFValue):
            return [], "QSizeF(%s, %s)" % (py_float(value.width), py_float(value.height))
        if isinstance(value, RectValue):
            return [], "QRect(%s, %s, %s, %s)" % (value.x, value.y, value.width, value.height)
        if isinstance(value, RectFValue):
            return [], "QRectF(%s, %s, %s, %s)" % (
                py_float(value.x),
                py_float(value.y),
                py_float(value.width),
                py_float(value.height),
            )
        if isinstance(value, DateValue):
            return [], "QDate(%s, %s, %s)" % (value.year, value.month, value.day)
        if isinstance(value, TimeValue):
            return [], "QTime(%s, %s, %s)" % (value.hour, value.minute, value.second)
        if isinstance(value, DateTimeValue):
            return [], "QDateTime(QDate(%s, %s, %s), QTime(%s, %s, %s))" % (
                value.year,
                value.month,
                value.day,
                value.hour,
                value.minute,
                value.second,
            )
        if isinstance(value, LocaleValue):
            language = value.language if check_cpp_name(value.language) else "C"
            if value.country and check_cpp_name(value.country):
                return [], "QLocale(QLocale.Language.%s, QLocale.Country.%s)" % (language, value.country)
            return [], "QLocale(QLocale.Language.%s)" % language
        if isinstance(value, UrlValue):
            # uic writes the URL as a literal. It does not pass it through translate.
            return [], "QUrl(%s)" % py_string(value.string.text)
        if isinstance(value, CursorShapeValue):
            return [], "QCursor(%s)" % enum_expr(value.name if "::" in value.name else "Qt::CursorShape::" + value.name)
        if isinstance(value, CursorValue):
            return [], "QCursor(Qt.CursorShape(%s))" % value.value
        if isinstance(value, ColorValue):
            return [], _color(value)
        if isinstance(value, ResourcePixmap):
            return [], "QPixmap(%s)" % py_string(value.path)
        if isinstance(value, SizePolicyValue):
            return self._size_policy(value, ref, copy_hfw=copy_hfw), "sizePolicy"
        if isinstance(value, FontValue):
            return self._font(value), "font"
        if isinstance(value, IconSetValue):
            return self._icon(value), "icon"
        if isinstance(value, PaletteValue):
            return self._palette(value), "palette"
        if isinstance(value, BrushValue):
            return self._brush(value), "brush"
        return [], "None"

    def _string_list(self, value: StringListValue) -> str:
        parts = []
        for item in value.items:
            if value.notr is True:
                parts.append(py_string(item))
            else:
                parts.append(self.tr(item, value.comment, value.id))
        return "[" + ", ".join(parts) + "]"

    def _size_policy(self, value: SizePolicyValue, ref: str, *, copy_hfw: bool) -> List[str]:
        lines = [
            "sizePolicy = QSizePolicy(%s, %s)" % (policy_expr(value.hsizetype), policy_expr(value.vsizetype)),
            "sizePolicy.setHorizontalStretch(%s)" % value.horstretch,
            "sizePolicy.setVerticalStretch(%s)" % value.verstretch,
        ]
        if copy_hfw:
            lines.append("sizePolicy.setHeightForWidth(%s.sizePolicy().hasHeightForWidth())" % ref)
        return lines

    def _font(self, value: FontValue) -> List[str]:
        lines = ["font = QFont()"]
        if value.family is not None:
            lines.append("font.setFamily(%s)" % py_string(value.family))
        if value.pointsize is not None:
            lines.append("font.setPointSize(%s)" % value.pointsize)
        if value.weight is not None:
            lines.extend(_font_weight_lines(value.weight))
        if value.fontweight:
            lines.append("font.setWeight(%s)" % _scoped("QFont", "Weight", value.fontweight))
        if value.italic is not None:
            lines.append("font.setItalic(%s)" % ("True" if value.italic else "False"))
        if value.bold is not None:
            lines.append("font.setBold(%s)" % ("True" if value.bold else "False"))
        if value.underline is not None:
            lines.append("font.setUnderline(%s)" % ("True" if value.underline else "False"))
        if value.strikeout is not None:
            lines.append("font.setStrikeOut(%s)" % ("True" if value.strikeout else "False"))
        if value.kerning is not None:
            lines.append("font.setKerning(%s)" % ("True" if value.kerning else "False"))
        if value.stylestrategy:
            lines.append("font.setStyleStrategy(%s)" % _scoped("QFont", "StyleStrategy", value.stylestrategy))
        if value.hintingpreference:
            lines.append(
                "font.setHintingPreference(%s)" % _scoped("QFont", "HintingPreference", value.hintingpreference)
            )
        return lines

    def _icon(self, value: IconSetValue) -> List[str]:
        lines: List[str] = []
        states = []
        for name, mode, state in _ICON_STATE:
            pixmap = getattr(value, name)
            if isinstance(pixmap, ResourcePixmap) and pixmap.path:
                states.append((pixmap.path, mode, state))
        if value.theme and not states:
            lines.append("icon = QIcon.fromTheme(%s)" % py_string(value.theme))
            return lines
        if value.theme:
            lines.append("icon = QIcon.fromTheme(%s)" % py_string(value.theme))
        else:
            lines.append("icon = QIcon()")
        if not states and value.text:
            states.append((value.text, "Normal", "Off"))
        for path, mode, state in states:
            lines.append(
                "icon.addFile(%s, QSize(), QIcon.Mode.%s, QIcon.State.%s)"
                % (py_string(path), mode, state)
            )
        return lines

    def _palette(self, value: PaletteValue) -> List[str]:
        lines = ["palette = QPalette()"]
        for group, roles in (("Active", value.active), ("Inactive", value.inactive), ("Disabled", value.disabled)):
            for role in roles:
                lines.extend(self._brush(role.brush))
                lines.append(
                    "palette.setBrush(QPalette.ColorGroup.%s, QPalette.ColorRole.%s, brush)"
                    % (group, role.role.split("::")[-1] if check_cpp_name(role.role) else "Window")
                )
        return lines

    def _brush(self, value: BrushValue) -> List[str]:
        lines: List[str] = []
        if value.gradient is not None:
            lines.extend(self._gradient(value.gradient))
            lines.append("brush = QBrush(gradient)")
        elif value.texture is not None:
            lines.append("brush = QBrush(QPixmap(%s))" % py_string(value.texture.path))
        elif value.color is not None:
            lines.append("brush = QBrush(%s)" % _color(value.color))
        else:
            lines.append("brush = QBrush()")
        if value.brushstyle:
            lines.append("brush.setStyle(%s)" % enum_expr("Qt::BrushStyle::" + value.brushstyle.split("::")[-1]))
        return lines

    def _gradient(self, value: GradientValue) -> List[str]:
        kind = (value.type or "LinearGradient").split("::")[-1]
        cls = _GRADIENT.get(kind, "QLinearGradient")
        if cls == "QRadialGradient":
            ctor = "%s(%s, %s, %s)" % (
                cls,
                _num(value.centralx),
                _num(value.centraly),
                _num(value.radius),
            )
        elif cls == "QConicalGradient":
            ctor = "%s(%s, %s, %s)" % (cls, _num(value.centralx), _num(value.centraly), _num(value.angle))
        else:
            ctor = "%s(%s, %s, %s, %s)" % (
                cls,
                _num(value.startx),
                _num(value.starty),
                _num(value.endx),
                _num(value.endy),
            )
        lines = ["gradient = %s" % ctor]
        if value.spread:
            lines.append("gradient.setSpread(%s)" % _scoped("QGradient", "Spread", value.spread))
        if value.coordinatemode:
            lines.append(
                "gradient.setCoordinateMode(%s)" % _scoped("QGradient", "CoordinateMode", value.coordinatemode)
            )
        for stop in value.stops:
            lines.append("gradient.setColorAt(%s, %s)" % (py_float(stop.position), _color(stop.color)))
        return lines

    def _emit_buddies(self) -> None:
        for ref, target in self.buddies:
            expr = self.ref_name(target)
            if expr:
                self.add("%s.setBuddy(%s)" % (ref, expr))

    def _emit_tab_order(self) -> None:
        stops = self.doc.ui.field("tabstops")
        if not isinstance(stops, tuple) or len(stops) < 2:
            return
        self.note_class("QWidget")
        previous = None
        for name in stops:
            if not isinstance(name, str) or not name:
                continue
            target = self.ref_name(name)
            if not target:
                continue
            if previous is not None:
                self.add("QWidget.setTabOrder(%s, %s)" % (previous, target))
            previous = target

    def _emit_button_groups(self) -> None:
        for node in self.doc.ui.children("buttongroups"):
            if not isinstance(node, ButtonGroupNode):
                continue
            name = self.names.get(node.id) or node.name
            if not name:
                continue
            ref = "self.%s" % name
            self.remember(name)
            self.note_class("QButtonGroup")
            self.add("%s = QButtonGroup(%s)" % (ref, self.form_param))
            self.add("%s.setObjectName(%s)" % (ref, py_string(_qobject_name(node, name))))
            self._emit_members(node, ref, frozenset())
            for button in self.group_buttons.get(node.name or name, ()):
                self.add("%s.addButton(%s)" % (ref, button))

    def _emit_menu_binds(self) -> None:
        for action_name, menu_name in self.menu_binds:
            target = self.ref_name(menu_name)
            if target:
                self.add("self.%s.setMenu(%s)" % (action_name, target))

    def _emit_connections(self) -> None:
        for node in self.doc.ui.children("connections"):
            sender = node.field("sender") if hasattr(node, "field") else ""
            signal = node.field("signal") if hasattr(node, "field") else ""
            receiver = node.field("receiver") if hasattr(node, "field") else ""
            slot = node.field("slot") if hasattr(node, "field") else ""
            if not all(isinstance(part, str) and part for part in (sender, signal, receiver, slot)):
                continue
            signal_name = signal.split("(", 1)[0].strip()
            slot_name = slot.split("(", 1)[0].strip()
            if not signal_name or not slot_name:
                continue
            if not check_py_attr(signal_name) or not check_py_attr(slot_name):
                self._diag_unusable(signal_name if not check_py_attr(signal_name) else slot_name, node)
                continue
            sender_ref = self.ref_name(sender)
            receiver_ref = self.ref_name(receiver)
            if not sender_ref or not receiver_ref:
                continue
            if not self._signal_line_kept(node, sender, signal_name):
                continue
            # uic's own line. A wrong signal raises in setupUi, never silently.
            self.add("%s.%s.connect(%s.%s)" % (sender_ref, signal_name, receiver_ref, slot_name))

    def _signal_line_kept(self, connection: Node, sender: str, signal_name: str) -> bool:
        """Check a connection's signal against the sender's class.

        A plain Qt class has a closed signal set. A signal it lacks gets FB508
        and the line is left out, because the connect could only raise.
        FreeCAD ``Gui::`` classes, promoted Python classes and C++ ``::`` classes
        are real classes at run time, so their line is kept as uic writes it.
        A signal not declared for them gets FB508 too.
        """
        found = self._sender_class(sender)
        if found is None:
            return True
        class_name, open_class = found
        custom = self.custom.get(class_name)
        declared: Set[str] = set()
        if custom is not None:
            slots = custom.field("slots")
            if isinstance(slots, SlotsDecl):
                declared = {item.split("(", 1)[0].strip() for item in slots.signals}
        if open_class:
            base = self.base(class_name)
        elif custom is not None:
            base = self._fallback(class_name)
        else:
            base = class_name
        if not known_class(base):
            return True
        names = signal_names(base) or frozenset()
        if signal_name in names or (open_class and signal_name in declared):
            return True
        if open_class:
            self.warn(
                "FB508",
                'The class "%s" of "%s" has no "%s" signal that the form knows about. '
                "The generated connection raises an error if the class doesn't define it."
                % (class_name, sender, signal_name),
                node=connection,
                object_name=sender,
            )
            return True
        self.warn(
            "FB508",
            'The class "%s" of "%s" has no "%s" signal, so that connection was left out of the generated Python. '
            "Define the signal and connect it in the window class instead."
            % (class_name, sender, signal_name),
            node=connection,
            object_name=sender,
        )
        return False

    def _sender_class(self, sender: str) -> Optional[Tuple[str, bool]]:
        """(class name, open class) for a connection sender, or None."""
        node = self._xml_nodes.get(sender)
        if isinstance(node, ActionNode):
            return ("QAction", False)
        if isinstance(node, ActionGroupNode):
            return ("QActionGroup", False)
        if isinstance(node, ButtonGroupNode):
            return ("QButtonGroup", False)
        if not isinstance(node, (WidgetNode, LayoutNode)):
            return None
        class_name = node.class_name
        if not isinstance(class_name, str) or not class_name:
            return None
        if class_name == "Line":
            return ("QFrame", False)
        open_class = "::" in class_name or class_name in self.promoted_modules
        return (class_name, open_class)

    def _expand(self) -> List[Contribution]:
        ctx = CodegenContext(
            ui_class_name=self.ui_class,
            form_param=self.form_param,
            attribute_names=tuple(self.attributes),
        )
        found = []
        for expander in load_expanders():
            try:
                found.append(expander.contribute(self.doc, ctx))
            except Exception:
                # A broken expander adds no lines. The rest of the form still generates.
                name = getattr(expander, "expander_id", type(expander).__name__)
                self.warn(
                    "FB504",
                    'Logic expander "%s" failed and added nothing.' % name,
                )
        return found

    def _has_logic(self, contributions: Sequence[Contribution]) -> bool:
        for item in contributions:
            if item.setup_lines or item.methods or item.helpers:
                return True
        return False

    def _render(self, contributions: Sequence[Contribution]) -> str:
        for item in contributions:
            self.diagnostics.extend(item.diagnostics)
            for module, name in item.imports:
                self.need(module, name)
        connect = self._connect_slots()
        if connect:
            self.note_class("QMetaObject")
        chunks: List[str] = []
        imports = _format_imports(self.imports)
        if imports:
            chunks.append(imports)
        resource_lines = [_resource_import(module, self.scope, self.options) for module in self.resource_modules]
        if resource_lines:
            chunks.append("\n".join(resource_lines))
        promoted = _format_promoted(self.promoted_modules)
        if promoted:
            chunks.append(promoted)
        if self.uses_freecadgui:
            chunks.append(
                "try:\n    import FreeCADGui as _cbcs_FreeCADGui\nexcept ImportError:\n    _cbcs_FreeCADGui = None"
            )
            chunks.append(_FREECAD_HELPER)
        methods = [
            self._method("setupUi", self._setup_body(connect, contributions)),
            self._method("retranslateUi", self.retranslate or ["pass"]),
        ]
        for item in contributions:
            for method in item.methods:
                methods.append(_render_method(method))
        setup_lines: List[str] = []
        for item in contributions:
            setup_lines.extend(item.setup_lines)
        if setup_lines:
            methods.append(self._method("_cbcs_setup", setup_lines))
        chunks.append("class %s(object):\n%s" % (self.ui_class, "\n\n".join(methods)))
        helper_ids = []
        for item in contributions:
            for helper_id in item.helpers:
                if helper_id not in helper_ids:
                    helper_ids.append(helper_id)
        known = {helper_id: source for helper_id, source in HELPER_TABLE}
        for helper_id in helper_ids:
            source = known.get(helper_id)
            if source:
                chunks.append(source.rstrip())
        return "\n\n".join(chunks) + "\n"

    def _connect_slots(self) -> bool:
        if self.options.connect_slots_by_name is False:
            return False
        if self.options.connect_slots_by_name is True:
            return True
        raw = self.doc.ui.field("connectslotsbyname")
        if isinstance(raw, str) and raw.strip().lower() == "false":
            return False
        return True

    def _setup_body(self, connect: bool, contributions: Sequence[Contribution]) -> List[str]:
        body = list(self.lines)
        body.extend(self.splitter_lines)
        body.append("self.retranslateUi(%s)" % self.form_param)
        if connect:
            body.append("QMetaObject.connectSlotsByName(%s)" % self.form_param)
        if any(item.setup_lines for item in contributions):
            body.append("self._cbcs_setup(%s)" % self.form_param)
        return body

    def _method(self, name: str, statements: Sequence[str]) -> str:
        lines = ["    def %s(self, %s):" % (name, self.form_param)]
        if not statements:
            lines.append("        pass")
        else:
            for statement in statements:
                if statement == "":
                    lines.append("")
                    continue
                lines.append("        %s" % statement)
        return "\n".join(lines)


def _parameter_clash(name: str) -> bool:
    """True when the form parameter would hide an import or an emitter local."""
    if name in {"sizePolicy", "font", "palette", "gradient", "__sortingEnabled"}:
        return True
    if name == "icon" or (name.startswith("icon") and name[4:].isdigit()):
        return True
    if name == "brush" or (name.startswith("brush") and name[5:].isdigit()):
        return True
    if name.startswith("___q") and "item" in name:
        return True
    return qt_symbol(name)


def _explicit_name(node: Node) -> str:
    if isinstance(node, WidgetNode):
        return node.object_name
    if isinstance(node, LayoutNode):
        return node.object_name
    if isinstance(node, (SpacerNode, ActionNode, ActionGroupNode, ButtonGroupNode)):
        return node.name
    return ""


def _kind_of(node: Node) -> str:
    if isinstance(node, WidgetNode) and node.class_name.split("::")[-1] == "QMenu":
        return "menu"
    if isinstance(node, ActionNode):
        return "action"
    if isinstance(node, WidgetNode):
        return "widget"
    return node.kind


def _unique(base: str, used: Set[str]) -> str:
    """uic's suffix: ``name``, ``name1``, ``name2`` (no underscore)."""
    stem = base or "object"
    candidate = stem
    number = 1
    while candidate in used or unusable_reason(candidate):
        candidate = "%s%s" % (stem, number)
        number += 1
    used.add(candidate)
    return candidate


def _invented_base(node: Node) -> str:
    if isinstance(node, LayoutNode):
        return layout_basename(node.class_name)
    if isinstance(node, SpacerNode):
        return "spacerItem"
    if isinstance(node, WidgetNode):
        return widget_basename(node.class_name)
    if isinstance(node, ActionNode):
        return "action"
    if isinstance(node, ActionGroupNode):
        return "actionGroup"
    if isinstance(node, ButtonGroupNode):
        return "buttonGroup"
    return "object"


def _font_weight_lines(weight: int) -> List[str]:
    """Qt 4 ``<weight>75</weight>`` is bold. Qt 6 ``setWeight`` takes the enum."""
    if weight == 75:
        return ["font.setBold(True)"]
    if weight == 50:
        return []
    name = _LEGACY_FONT_WEIGHT.get(weight) or _QT6_FONT_WEIGHT.get(weight)
    if name is None or name == "Normal":
        return [] if name == "Normal" else ["font.setWeight(QFont.Weight(%s))" % int(weight)]
    return ["font.setWeight(QFont.Weight.%s)" % name]


def _qobject_name(node: Node, python_name: str) -> str:
    """Object name uic leaves on the QObject.

    uic writes the pythonized identifier (``::`` becomes ``__``). An explicit
    ``objectName`` property overwrites that, including when the property is empty.
    """
    prop = node.prop("objectName")
    if prop is not None:
        return _plain_text(prop.value)
    return python_name


def _spacer_orientation(spacer: SpacerNode) -> str:
    prop = spacer.prop("orientation")
    if prop is not None and isinstance(prop.value, EnumValue):
        if prop.value.text.endswith("Vertical"):
            return "Vertical"
    return "Horizontal"


def _spacer_spec(spacer: SpacerNode) -> Tuple[int, int, str, str]:
    orientation = _spacer_orientation(spacer)
    # uic passes 0, 0 when the spacer has no sizeHint. The 40 by 20 figure is
    # only Designer's on-canvas default, and it shows up in QSpacerItem.sizeHint.
    width = 0
    height = 0
    expanding = "Expanding"
    hint = spacer.prop("sizeHint")
    if hint is not None and isinstance(hint.value, SizeValue):
        width = hint.value.width
        height = hint.value.height
    size_type = spacer.prop("sizeType")
    if size_type is not None and isinstance(size_type.value, EnumValue):
        expanding = size_type.value.text.split("::")[-1]
    if orientation == "Vertical":
        return width, height, "Minimum", expanding
    return width, height, expanding, "Minimum"


def _structural_attrs(parent_base: str) -> frozenset:
    if parent_base == "QTabWidget":
        return frozenset({"title", "icon", "toolTip", "whatsThis"})
    if parent_base == "QToolBox":
        return frozenset({"label", "title", "icon", "toolTip", "whatsThis"})
    if parent_base == "QMainWindow":
        return frozenset({"toolBarArea", "toolBarBreak", "dockWidgetArea"})
    if parent_base == "QWizard":
        return frozenset({"title", "subTitle", "icon"})
    return frozenset()


def _attr_text(widget: WidgetNode, name: str) -> str:
    attr = widget.attr(name)
    if attr is None:
        return ""
    return _plain_text(attr.value)


def _attr_bool(widget: WidgetNode, name: str) -> bool:
    attr = widget.attr(name)
    if attr is None or not isinstance(attr.value, BoolValue):
        return False
    return attr.value.value


def _plain_text(value: Value) -> str:
    if isinstance(value, StringValue):
        return value.text
    if isinstance(value, CStringValue):
        return value.text
    return ""


def _translated(value: Value) -> bool:
    if isinstance(value, StringValue):
        return value.notr is not True
    if isinstance(value, StringListValue):
        return value.notr is not True
    if isinstance(value, UrlValue):
        return value.string.notr is not True
    return False


# Remainder after ``horizontalHeader`` / ``verticalHeader`` that QHeaderView
# implements as a method. Anything else is a dynamic property. uic writes
# ``horizontalHeader().setProperty("showSortIndicator", ...)``.
_HEADER_METHODS = {
    "CascadingSectionResizes": "setCascadingSectionResizes",
    "DefaultAlignment": "setDefaultAlignment",
    "DefaultSectionSize": "setDefaultSectionSize",
    "HighlightSections": "setHighlightSections",
    "MaximumSectionSize": "setMaximumSectionSize",
    "MinimumSectionSize": "setMinimumSectionSize",
    "SortIndicatorShown": "setSortIndicatorShown",
    "StretchLastSection": "setStretchLastSection",
    "Visible": "setVisible",
}


def _header_accessor(name: str) -> Optional[str]:
    """Designer writes ``horizontalHeaderVisible`` for ``horizontalHeader().setVisible``."""
    for prefix in ("horizontalHeader", "verticalHeader"):
        if name.startswith(prefix) and len(name) > len(prefix) and name[len(prefix)].isupper():
            return prefix
    return None


def _opaque_box(element: OpaqueElement) -> str:
    """A ``<size>`` (or point/rect) the reader kept because a field was missing.

    uic fills the missing field with 0. ``<size><width>100</width></size>`` is
    ``QSize(100, 0)``. An empty ``<number/>`` is 0 the same way.
    """
    if element.tag == "number":
        text = "".join(part for part in element.children if isinstance(part, str)).strip()
        return "0" if not text and not element.children else ""
    boxes = {
        "size": ("QSize", ("width", "height")),
        "point": ("QPoint", ("x", "y")),
        "rect": ("QRect", ("x", "y", "width", "height")),
    }
    spec = boxes.get(element.tag)
    if spec is None:
        return ""
    ctor, fields = spec
    found = {}
    for child in element.children:
        if not isinstance(child, OpaqueElement) or child.tag not in fields:
            continue
        text = "".join(part for part in child.children if isinstance(part, str)).strip()
        if not text.lstrip("-").isdigit():
            return ""
        found[child.tag] = int(text)
    if not found:
        return ""
    return "%s(%s)" % (ctor, ", ".join(str(found.get(field, 0)) for field in fields))


def _sizes_literal(value: Value) -> str:
    text = _plain_text(value)
    if not text:
        return ""
    numbers = []
    for part in text.split(","):
        part = part.strip()
        if not part or not part.lstrip("-").isdigit():
            return ""
        numbers.append(str(int(part)))
    if not numbers:
        return ""
    return "[" + ", ".join(numbers) + "]"


def _color(value: ColorValue) -> str:
    if value.alpha is None:
        return "QColor(%s, %s, %s)" % (value.red, value.green, value.blue)
    return "QColor(%s, %s, %s, %s)" % (value.red, value.green, value.blue, value.alpha)


def _num(value: Optional[float]) -> str:
    if value is None:
        return "0.0"
    return py_float(value)


def _scoped(owner: str, enum: str, text: str) -> str:
    if "::" in text:
        return enum_expr(text)
    leaf = text.split("::")[-1]
    if not check_cpp_name(leaf):
        return "0"
    return "%s.%s.%s" % (owner, enum, leaf)


def _text_values(node: Node) -> List[Value]:
    found: List[Value] = []
    for opaque in node.opaque():
        element = opaque.element
        if element.tag != "property":
            continue
        if dict(element.attrs).get("name") != "text":
            continue
        text = _opaque_string(element)
        if text is None:
            continue
        found.append(StringValue(text=text[0], notr=text[1]))
    prop = node.prop("text")
    if prop is not None:
        found.append(prop.value)
    return found


def _opaque_string(element: OpaqueElement) -> Optional[Tuple[str, Optional[bool]]]:
    for child in element.children:
        if not isinstance(child, OpaqueElement) or child.tag != "string":
            continue
        parts = [part for part in child.children if isinstance(part, str)]
        notr = None
        raw = dict(child.attrs).get("notr")
        if raw == "true":
            notr = True
        elif raw == "false":
            notr = False
        return "".join(parts), notr
    return None


def _tree_lookup(ref: str, path: Tuple[int, ...]) -> str:
    expr = "%s.topLevelItem(%s)" % (ref, path[0])
    for index in path[1:]:
        expr = "%s.child(%s)" % (expr, index)
    return expr


def _resource_module(location: str, scope: FormScope, options: CodegenOptions) -> str:
    normalized = location.replace("\\", "/")
    stem = os.path.splitext(os.path.basename(normalized))[0] + "_rc"
    directory = os.path.dirname(normalized)
    parts = [part for part in directory.split("/") if part and part != "."]
    if options.python_paths and scope.ui_path:
        ui_dir = os.path.dirname(os.path.abspath(scope.ui_path))
        qrc_dir = os.path.abspath(os.path.join(ui_dir, directory))
        for raw in options.python_paths:
            base = os.path.abspath(raw)
            try:
                inside = os.path.commonpath((qrc_dir, base)) == base
            except ValueError:
                inside = False
            if not inside:
                continue
            rel = os.path.relpath(qrc_dir, base).replace(os.sep, "/")
            parts = [part for part in rel.split("/") if part and part != "."]
            break
    if (options.rc_prefix or options.python_paths) and parts and all(part.isidentifier() for part in parts):
        return ".".join(parts + [stem])
    return stem


def _resource_import(module: str, scope: FormScope, options: CodegenOptions) -> str:
    leaf = module.split(".")[-1]
    style = options.import_style
    if style == "from":
        return "from . import %s" % leaf
    if style == "star":
        return "from %s import *" % module
    if style == "absolute":
        package = ""
        if scope.module_name and "." in scope.module_name:
            package = scope.module_name.rsplit(".", 1)[0]
        if package:
            return "from %s import %s" % (package, leaf)
        return "import %s" % leaf
    return "import %s" % module


def _format_promoted(promoted: Dict[str, str]) -> str:
    by_module: Dict[str, List[str]] = {}
    for class_name, module in promoted.items():
        by_module.setdefault(module, []).append(class_name)
    lines = []
    for module in sorted(by_module):
        lines.append(_format_import(module, sorted(by_module[module])))
    return "\n".join(lines)


def _format_imports(imports: Dict[str, Set[str]]) -> str:
    modules = sorted(imports, key=lambda name: (_MODULE_RANK.get(name, 50), name))
    lines = []
    for module in modules:
        names = sorted(imports[module])
        if names:
            lines.append(_format_import(module, names))
    return "\n".join(lines)


def _format_import(module: str, names: Sequence[str]) -> str:
    if len(names) == 1:
        return "from %s import %s" % (module, names[0])
    single = "from %s import (%s)" % (module, ", ".join(names))
    if len(single) <= 88:
        return single
    rows = ["from %s import (" % module]
    current = "    "
    for index, name in enumerate(names):
        piece = name if index == len(names) - 1 else name + ", "
        if current != "    " and len(current) + len(piece) > 88:
            rows.append(current.rstrip())
            current = "    "
        current += piece
    current = current.rstrip() + ")"
    rows.append(current)
    return "\n".join(rows)


def _render_method(method: Method) -> str:
    lines = ["    def %s(self):" % method.name, "        # %s" % method.source_ref.replace("\n", " ")]
    body = method.body.strip("\n")
    if not body:
        lines.append("        pass")
    else:
        for line in body.split("\n"):
            lines.append("        %s" % line if line else "")
    return "\n".join(lines)
