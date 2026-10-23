"""Find runtime ``.ui`` loaders and describe the ``setupUi`` replacement.

The scan uses the stdlib ``ast`` module. It does not rewrite user files.
Importing a form that was built only in code is out of scope.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from app.features.form_builder.engine.codegen.names import python_class_stem
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.fs import ProjectOpError, relative_posix
from app.features.form_builder.engine.ui4.reader import read_ui

_SKIP_DIRS = frozenset({"cbcs", "__pycache__", ".git", "vendor", "node_modules"})

LOADER_KIND_LABEL = {
    "qui_loader": "QUiLoader.load",
    "load_ui": "loadUi",
    "pyside_uic": "PySideUic.loadUi",
}


def loader_kind_label(kind: str) -> str:
    """User-facing name for one loader kind. Unknown kinds stay as stored."""
    return LOADER_KIND_LABEL.get(kind, kind)
LoadKind = str


@dataclass(frozen=True)
class UiLoadSite:
    """One call that loads a ``.ui`` file at runtime."""

    path: str
    line: int
    kind: LoadKind
    ui_literal: Optional[str]
    before: str


def scan_ui_loaders(root: str) -> Tuple[UiLoadSite, ...]:
    """Every ``QUiLoader.load``, ``loadUi``, and ``PySideUic.loadUi`` under ``root``."""
    found: List[UiLoadSite] = []
    base = os.path.abspath(root)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(
            name for name in dirnames if name not in _SKIP_DIRS and not name.startswith(".")
        )
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            if name.startswith("ui_") or name.endswith("_rc.py"):
                continue
            found.extend(_scan_file(os.path.join(dirpath, name)))
    return tuple(found)


def suggestion_text(
    project_root: str,
    ui_path: str,
    scope: FormScope,
) -> Tuple[str, str]:
    """Before and after text for adopting ``ui_path``. Neither side is written."""
    root = os.path.abspath(project_root)
    sites = _sites_for_form(root, ui_path)
    class_name = _ui_class_name(ui_path)
    module = scope.module_name or ""
    after = (
        "# At the top of the file\n"
        "from %s import %s\n"
        "\n"
        "# In __init__\n"
        "self.ui = %s()\n"
        "self.ui.setupUi(self)\n"
    ) % (module, class_name, class_name)
    if not sites:
        before = "No QUiLoader, loadUi, or PySideUic.loadUi call was found.\n"
        return before, after
    chunks: List[str] = []
    for site in sites:
        rel = relative_posix(site.path, root)
        literal = site.ui_literal if site.ui_literal else "a path that is not a literal"
        chunks.append(
            "# %s:%s (%s, %s)\n%s" % (rel, site.line, loader_kind_label(site.kind), literal, site.before)
        )
    return "\n\n".join(chunks) + "\n", after


def _sites_for_form(root: str, ui_path: str) -> List[UiLoadSite]:
    ui_name = os.path.basename(ui_path)
    try:
        rel = relative_posix(ui_path, root)
    except ProjectOpError:
        rel = ui_name
    matched: List[UiLoadSite] = []
    variable: List[UiLoadSite] = []
    for site in scan_ui_loaders(root):
        literal = (site.ui_literal or "").replace("\\", "/")
        if not literal:
            variable.append(site)
            continue
        if literal == rel or literal.endswith("/" + ui_name) or os.path.basename(literal) == ui_name:
            matched.append(site)
    return matched or variable


def _ui_class_name(ui_path: str) -> str:
    with open(ui_path, "r", encoding="utf-8") as handle:
        text = handle.read()
    document = read_ui(text, allocator=IdAllocator()).document
    return "Ui_%s" % python_class_stem(document.form_class_name())


def _scan_file(path: str) -> List[UiLoadSite]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source, filename=path)
    except (OSError, UnicodeError, SyntaxError):
        return []
    sites: List[UiLoadSite] = []
    loaders: Set[str] = set()

    class _Visitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            if _is_loader_ctor(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        loaders.add(target.id)
            self.generic_visit(node)

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            if node.value is not None and _is_loader_ctor(node.value) and isinstance(node.target, ast.Name):
                loaders.add(node.target.id)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            kind = _call_kind(node, loaders)
            if kind is not None:
                segment = ast.get_source_segment(source, node) or ""
                sites.append(
                    UiLoadSite(
                        path=path,
                        line=int(node.lineno or 0),
                        kind=kind,
                        ui_literal=_first_string(node),
                        before=segment,
                    )
                )
            self.generic_visit(node)

    _Visitor().visit(tree)
    return sites


def _is_loader_ctor(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "QUiLoader"
    return isinstance(func, ast.Attribute) and func.attr == "QUiLoader"


def _call_kind(node: ast.Call, loaders: Set[str]) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "load":
        value = func.value
        if isinstance(value, ast.Call) and _is_loader_ctor(value):
            return "qui_loader"
        if isinstance(value, ast.Name) and value.id in loaders:
            return "qui_loader"
    if isinstance(func, ast.Attribute) and func.attr == "loadUi":
        if _chain_has(func.value, "PySideUic"):
            return "pyside_uic"
        return "load_ui"
    if isinstance(func, ast.Name) and func.id == "loadUi":
        return "load_ui"
    return None


def _chain_has(node: ast.AST, name: str) -> bool:
    current: Optional[ast.AST] = node
    while isinstance(current, ast.Attribute):
        if current.attr == name:
            return True
        current = current.value
    return isinstance(current, ast.Name) and current.id == name


def _first_string(node: ast.Call) -> Optional[str]:
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None
