"""Import diagnostics helpers for Python projects."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportDiagnostic:
    """Unresolved import diagnostic record."""

    file_path: str
    line_number: int
    message: str


def find_unresolved_imports(project_root: str) -> list[ImportDiagnostic]:
    """Find unresolved project-local imports in Python files."""
    root = Path(project_root).expanduser().resolve()
    diagnostics: list[ImportDiagnostic] = []
    for file_path in sorted(root.rglob("*.py")):
        if ".cbcs" in file_path.parts:
            continue
        diagnostics.extend(_diagnostics_for_file(root, file_path))
    return diagnostics


def _diagnostics_for_file(project_root: Path, file_path: Path) -> list[ImportDiagnostic]:
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    diagnostics: list[ImportDiagnostic] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_project_import_resolvable(project_root, alias.name):
                    diagnostics.append(
                        ImportDiagnostic(
                            file_path=str(file_path.resolve()),
                            line_number=int(node.lineno),
                            message=f"Unresolved import: {alias.name}",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            if node.level > 0:
                continue
            if not _is_project_import_resolvable(project_root, node.module):
                diagnostics.append(
                    ImportDiagnostic(
                        file_path=str(file_path.resolve()),
                        line_number=int(node.lineno),
                        message=f"Unresolved import: {node.module}",
                    )
                )
    return diagnostics


def _is_project_import_resolvable(project_root: Path, module_name: str) -> bool:
    module_path = Path(*module_name.split("."))
    if (project_root / module_path).with_suffix(".py").exists():
        return True
    if (project_root / module_path / "__init__.py").exists():
        return True
    return False
