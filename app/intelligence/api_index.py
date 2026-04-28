"""Trusted runtime API index used to improve static editor completions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from app.intelligence.completion_models import CompletionItem, CompletionKind

DEFAULT_RUNTIME_API_INDEX_PATH = Path(__file__).with_name("runtime_api_index.json")


@dataclass(frozen=True)
class ApiMember:
    """A documented member from a trusted runtime module."""

    name: str
    kind: CompletionKind
    detail: str = ""
    documentation: str = ""
    signature: str = ""


_CURATED_API_INDEX: dict[str, tuple[ApiMember, ...]] = {
    "FreeCAD": (
        ApiMember("ActiveDocument", CompletionKind.ATTRIBUTE, "FreeCAD active document"),
        ApiMember("Console", CompletionKind.ATTRIBUTE, "FreeCAD console"),
        ApiMember("GuiUp", CompletionKind.ATTRIBUTE, "FreeCAD GUI availability flag"),
        ApiMember("Version", CompletionKind.FUNCTION, "FreeCAD version information", signature="Version()"),
        ApiMember("addImportType", CompletionKind.FUNCTION, "Register an import type"),
        ApiMember("addExportType", CompletionKind.FUNCTION, "Register an export type"),
        ApiMember("closeDocument", CompletionKind.FUNCTION, "Close a FreeCAD document"),
        ApiMember("getDocument", CompletionKind.FUNCTION, "Return a document by name"),
        ApiMember("listDocuments", CompletionKind.FUNCTION, "Return open documents"),
        ApiMember("newDocument", CompletionKind.FUNCTION, "Create a new document", signature="newDocument(name='')"),
        ApiMember("openDocument", CompletionKind.FUNCTION, "Open a FreeCAD document"),
        ApiMember("setActiveDocument", CompletionKind.FUNCTION, "Set the active document"),
    ),
    "FreeCAD.ActiveDocument": (
        ApiMember("Objects", CompletionKind.ATTRIBUTE, "Objects in the active document"),
        ApiMember("Name", CompletionKind.ATTRIBUTE, "Document name"),
        ApiMember("Label", CompletionKind.ATTRIBUTE, "Document label"),
        ApiMember("addObject", CompletionKind.METHOD, "Add an object to the document"),
        ApiMember("getObject", CompletionKind.METHOD, "Return an object by name"),
        ApiMember("recompute", CompletionKind.METHOD, "Recompute document dependencies"),
        ApiMember("removeObject", CompletionKind.METHOD, "Remove an object by name"),
        ApiMember("save", CompletionKind.METHOD, "Save the document"),
        ApiMember("saveAs", CompletionKind.METHOD, "Save the document as a path"),
    ),
    "PySide2": (
        ApiMember("QtCore", CompletionKind.MODULE, "QtCore module"),
        ApiMember("QtGui", CompletionKind.MODULE, "QtGui module"),
        ApiMember("QtWidgets", CompletionKind.MODULE, "QtWidgets module"),
        ApiMember("QtPrintSupport", CompletionKind.MODULE, "Qt print support module"),
        ApiMember("QtUiTools", CompletionKind.MODULE, "Qt Designer UI loader module"),
    ),
    "QtWidgets": (
        ApiMember("QApplication", CompletionKind.CLASS, "Qt application object"),
        ApiMember("QDialog", CompletionKind.CLASS, "Dialog window"),
        ApiMember("QLabel", CompletionKind.CLASS, "Text/display label"),
        ApiMember("QLineEdit", CompletionKind.CLASS, "Single-line text input"),
        ApiMember("QListWidget", CompletionKind.CLASS, "List widget"),
        ApiMember("QMainWindow", CompletionKind.CLASS, "Main window shell"),
        ApiMember("QMessageBox", CompletionKind.CLASS, "Message dialog"),
        ApiMember("QPushButton", CompletionKind.CLASS, "Push button"),
        ApiMember("QTableWidget", CompletionKind.CLASS, "Table widget"),
        ApiMember("QTextEdit", CompletionKind.CLASS, "Rich/plain text editor widget"),
        ApiMember("QVBoxLayout", CompletionKind.CLASS, "Vertical box layout"),
        ApiMember("QWidget", CompletionKind.CLASS, "Base QWidget"),
    ),
    "PySide2.QtWidgets": (
        ApiMember("QApplication", CompletionKind.CLASS, "Qt application object"),
        ApiMember("QDialog", CompletionKind.CLASS, "Dialog window"),
        ApiMember("QLabel", CompletionKind.CLASS, "Text/display label"),
        ApiMember("QLineEdit", CompletionKind.CLASS, "Single-line text input"),
        ApiMember("QListWidget", CompletionKind.CLASS, "List widget"),
        ApiMember("QMainWindow", CompletionKind.CLASS, "Main window shell"),
        ApiMember("QMessageBox", CompletionKind.CLASS, "Message dialog"),
        ApiMember("QPushButton", CompletionKind.CLASS, "Push button"),
        ApiMember("QTableWidget", CompletionKind.CLASS, "Table widget"),
        ApiMember("QTextEdit", CompletionKind.CLASS, "Rich/plain text editor widget"),
        ApiMember("QVBoxLayout", CompletionKind.CLASS, "Vertical box layout"),
        ApiMember("QWidget", CompletionKind.CLASS, "Base QWidget"),
    ),
    "QtCore": (
        ApiMember("QDate", CompletionKind.CLASS, "Date value"),
        ApiMember("QDateTime", CompletionKind.CLASS, "Date/time value"),
        ApiMember("QObject", CompletionKind.CLASS, "Base QObject"),
        ApiMember("QPoint", CompletionKind.CLASS, "2D point"),
        ApiMember("QRect", CompletionKind.CLASS, "Rectangle"),
        ApiMember("QSize", CompletionKind.CLASS, "Size value"),
        ApiMember("QTimer", CompletionKind.CLASS, "Timer"),
        ApiMember("Qt", CompletionKind.CLASS, "Qt enum namespace"),
        ApiMember("Signal", CompletionKind.CLASS, "PySide signal descriptor"),
        ApiMember("Slot", CompletionKind.FUNCTION, "PySide slot decorator"),
    ),
    "PySide2.QtCore": (
        ApiMember("QDate", CompletionKind.CLASS, "Date value"),
        ApiMember("QDateTime", CompletionKind.CLASS, "Date/time value"),
        ApiMember("QObject", CompletionKind.CLASS, "Base QObject"),
        ApiMember("QPoint", CompletionKind.CLASS, "2D point"),
        ApiMember("QRect", CompletionKind.CLASS, "Rectangle"),
        ApiMember("QSize", CompletionKind.CLASS, "Size value"),
        ApiMember("QTimer", CompletionKind.CLASS, "Timer"),
        ApiMember("Qt", CompletionKind.CLASS, "Qt enum namespace"),
        ApiMember("Signal", CompletionKind.CLASS, "PySide signal descriptor"),
        ApiMember("Slot", CompletionKind.FUNCTION, "PySide slot decorator"),
    ),
    "QtGui": (
        ApiMember("QBrush", CompletionKind.CLASS, "Brush"),
        ApiMember("QColor", CompletionKind.CLASS, "Color"),
        ApiMember("QFont", CompletionKind.CLASS, "Font"),
        ApiMember("QIcon", CompletionKind.CLASS, "Icon"),
        ApiMember("QKeyEvent", CompletionKind.CLASS, "Key event"),
        ApiMember("QPainter", CompletionKind.CLASS, "Painter"),
        ApiMember("QPalette", CompletionKind.CLASS, "Palette"),
        ApiMember("QPixmap", CompletionKind.CLASS, "Pixmap"),
        ApiMember("QTextCursor", CompletionKind.CLASS, "Text cursor"),
    ),
    "PySide2.QtGui": (
        ApiMember("QBrush", CompletionKind.CLASS, "Brush"),
        ApiMember("QColor", CompletionKind.CLASS, "Color"),
        ApiMember("QFont", CompletionKind.CLASS, "Font"),
        ApiMember("QIcon", CompletionKind.CLASS, "Icon"),
        ApiMember("QKeyEvent", CompletionKind.CLASS, "Key event"),
        ApiMember("QPainter", CompletionKind.CLASS, "Painter"),
        ApiMember("QPalette", CompletionKind.CLASS, "Palette"),
        ApiMember("QPixmap", CompletionKind.CLASS, "Pixmap"),
        ApiMember("QTextCursor", CompletionKind.CLASS, "Text cursor"),
    ),
}


def provide_api_index_member_items(
    *,
    module_name: str,
    member_prefix: str,
    limit: int,
    index_path: str | None = None,
) -> list[CompletionItem]:
    """Return trusted runtime API completion items for a module/member context."""

    members = list(_CURATED_API_INDEX.get(module_name, ()))
    members.extend(_load_index_members(str(DEFAULT_RUNTIME_API_INDEX_PATH), module_name))
    if index_path and Path(index_path).expanduser() != DEFAULT_RUNTIME_API_INDEX_PATH:
        members.extend(_load_index_members(index_path, module_name))
    deduped_members = {member.name: member for member in members}
    filtered = [
        member
        for member in deduped_members.values()
        if not member_prefix or member.name.lower().startswith(member_prefix.lower())
    ]
    return [
        CompletionItem(
            label=member.name,
            insert_text=member.name,
            kind=member.kind,
            detail=member.detail or f"{module_name} API",
            documentation=member.documentation,
            signature=member.signature,
            engine="api_index",
            source="static_api_index",
            confidence="static",
        )
        for member in sorted(filtered, key=lambda item: item.name.lower())[: max(1, int(limit))]
    ]


def _load_index_members(index_path: str, module_name: str) -> list[ApiMember]:
    path = Path(index_path).expanduser()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    module_payload: object | None = None
    if isinstance(payload, dict):
        modules_payload = payload.get("modules")
        if isinstance(modules_payload, dict):
            module_payload = modules_payload.get(module_name)
        else:
            module_payload = payload.get(module_name)
    if not isinstance(module_payload, list):
        return []
    members: list[ApiMember] = []
    for entry in module_payload:
        if not isinstance(entry, dict):
            continue
        member = _member_from_payload(entry)
        if member is not None:
            members.append(member)
    return members


def _member_from_payload(payload: dict[str, Any]) -> ApiMember | None:
    name = payload.get("name")
    if not isinstance(name, str) or not name.isidentifier():
        return None
    kind_value = payload.get("kind", CompletionKind.ATTRIBUTE.value)
    try:
        kind = CompletionKind(str(kind_value))
    except ValueError:
        kind = CompletionKind.ATTRIBUTE
    return ApiMember(
        name=name,
        kind=kind,
        detail=str(payload.get("detail") or ""),
        documentation=str(payload.get("documentation") or ""),
        signature=str(payload.get("signature") or ""),
    )
