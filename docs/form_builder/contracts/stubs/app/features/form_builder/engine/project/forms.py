"""Project forms: generation scope and file naming (CONTRACTS.md section 9.6).
[M1.4]
"""

from __future__ import annotations

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
        ...


def classify_form(ui_path: str, *, project_root: Optional[str], adopted: Tuple[str, ...] = ()) -> FormScope:
    """Pure path logic (no I/O except ``os.path``). ``adopted``: project-relative
    POSIX paths from project settings. Stems that are not Python identifiers
    still classify; codegen reports FB507 and writes nothing."""
    ...
