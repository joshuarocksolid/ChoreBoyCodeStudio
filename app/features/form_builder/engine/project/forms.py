"""Project forms: generation scope and file naming (CONTRACTS.md section 9.5 and 9.6).

Codegen imports ``FormScope`` from here. The path rules are the ones the
generator needs. M1.4 can extend this module; the fields below stay.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Optional, Tuple

FormScopeKind = Literal["project", "adopted", "external"]


@dataclass(frozen=True)
class FormScope:
    """``project``: the ``.ui`` is under ``<project>/forms/``. ``adopted``: listed in
    project settings by "Adopt this form". ``external``: anything else (FreeCAD
    workbench forms, forms an app loads with QUiLoader); edited, never generated
    beside (FB506 Info explains).

    Paths are absolute. ``generated_path`` is ``<dir>/ui_<stem>.py``;
    ``window_path`` is ``<dir>/<stem>_window.py``; ``module_name`` is the import
    path from the project root (``forms.ui_invoice``); all None for external.
    """

    kind: FormScopeKind
    ui_path: str
    project_root: Optional[str] = None
    generated_path: Optional[str] = None
    window_path: Optional[str] = None
    module_name: Optional[str] = None
    window_module_name: Optional[str] = None

    @property
    def generates(self) -> bool:
        """True for project and adopted forms."""
        return self.kind in ("project", "adopted")


def _inside(child: str, parent: str) -> bool:
    child_abs = os.path.abspath(child)
    parent_abs = os.path.abspath(parent)
    try:
        return os.path.commonpath((child_abs, parent_abs)) == parent_abs
    except ValueError:
        return False


def _module_name(project_root: str, py_path: str) -> str:
    rel = os.path.relpath(py_path, project_root).replace(os.sep, "/")
    if rel.endswith(".py"):
        rel = rel[:-3]
    return ".".join(part for part in rel.split("/") if part)


def classify_form(
    ui_path: str,
    *,
    project_root: Optional[str],
    adopted: Tuple[str, ...] = (),
) -> FormScope:
    """Pure path logic (no I/O except ``os.path``). ``adopted``: project-relative
    POSIX paths from project settings. Stems that are not Python identifiers
    still classify; codegen reports FB507 and writes nothing."""
    ui_abs = os.path.abspath(ui_path)
    stem = os.path.splitext(os.path.basename(ui_abs))[0]
    directory = os.path.dirname(ui_abs)
    generated = os.path.join(directory, "ui_%s.py" % stem)
    window = os.path.join(directory, "%s_window.py" % stem)
    root = os.path.abspath(project_root) if project_root else None
    kind: FormScopeKind = "external"
    if root is not None:
        rel = os.path.relpath(ui_abs, root).replace(os.sep, "/")
        if _inside(ui_abs, os.path.join(root, "forms")):
            kind = "project"
        elif rel in adopted:
            kind = "adopted"
    if kind == "external":
        return FormScope(kind="external", ui_path=ui_abs, project_root=root)
    return FormScope(
        kind=kind,
        ui_path=ui_abs,
        project_root=root,
        generated_path=generated,
        window_path=window,
        module_name=_module_name(root, generated) if root else None,
        window_module_name=_module_name(root, window) if root else None,
    )
