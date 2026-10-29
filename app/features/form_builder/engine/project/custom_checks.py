"""FB035: your own class comes from a module that is not in this project (UX-CUST-010).

Qt-free. It reads the form's declarations and looks for the module's file
under the project root; it never opens the file. A header that is not a Python
module path stays FB504 (codegen). A ``global`` header and a C++ ``::`` class
name name a library, not a project file, and are left alone.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.diagnostic_codes import fb03x_custom as _codes
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic
from app.features.form_builder.engine.project.custom_widgets import module_file, module_for_header
from app.features.form_builder.engine.ui4.nodes import CustomWidgetNode, WidgetNode
from app.features.form_builder.engine.ui4.schema import HeaderDecl

del _codes

SOURCE = "custom"


def missing_module_message(class_name: str, module: str) -> str:
    """The FB035 sentence (UX_SPEC 13.2.10)."""
    return "%s comes from %s, which isn't in this project." % (class_name, module)


def custom_diagnostics(document: object, project_root: Optional[str]) -> Tuple[FormDiagnostic, ...]:
    if not project_root:
        return ()
    declared: Dict[str, str] = {}
    for node in document.ui.children("customwidgets"):  # type: ignore[attr-defined]
        if not isinstance(node, CustomWidgetNode) or not node.class_name or "::" in node.class_name:
            continue
        header = node.field("header")
        if not isinstance(header, HeaderDecl) or header.location == "global":
            continue
        module = module_for_header(header.text)
        if module and not module_file(project_root, module):
            declared[node.class_name] = module
    if not declared:
        return ()
    first: Dict[str, WidgetNode] = {}
    for widget in document.iter_widgets():  # type: ignore[attr-defined]
        if widget.class_name in declared and widget.class_name not in first:
            first[widget.class_name] = widget
    info = CODES["FB035"]
    found: List[FormDiagnostic] = []
    for class_name, module in declared.items():
        user = first.get(class_name)
        found.append(
            FormDiagnostic(
                code=info.code,
                severity=info.severity,
                message=missing_module_message(class_name, module),
                location=DiagnosticLocation(
                    node_id=user.id if user is not None else None,
                    object_name=user.object_name if user is not None else None,
                    property="class",
                    rule_path=(class_name,),
                ),
                source=SOURCE,
            )
        )
    return tuple(found)


__all__ = ["SOURCE", "custom_diagnostics", "missing_module_message"]
