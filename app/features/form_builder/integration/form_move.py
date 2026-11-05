"""When the project tree renames or moves a form, the companions move with it."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError, inside_project
from app.features.form_builder.engine.project.rename import apply, plan_rename
from app.project.path_rename import MoveDone, MoveOutcome, MoveRefusal, set_path_move_handler


_PLAIN_MOVE = (
    "That form is outside the project.",
    "There is no form at that path.",
)
_NOT_A_FORM = "A form file has to end with .ui."


def install_form_move(window: object) -> None:
    """Register the tree's move handler. The shell does not import this module."""

    def on_move(source: str, destination: str) -> Optional[MoveOutcome]:
        project = getattr(window, "_loaded_project", None)
        root = getattr(project, "project_root", None)
        if not root:
            return None
        if not str(source).lower().endswith(".ui"):
            return None
        fs = OsFileSystem()
        if not fs.is_file(source) or not inside_project(source, str(root)):
            return None
        plan = plan_rename(str(root), source, destination, fs)
        if plan.reason in _PLAIN_MOVE or (
            plan.reason == _NOT_A_FORM and not str(source).endswith(".ui")
        ):
            return None
        if plan.reason:
            return MoveRefusal(plan.reason)
        try:
            apply(plan, fs)
        except ProjectOpError as exc:
            return MoveRefusal(str(exc))
        return MoveDone(tuple((move.source, move.destination) for move in plan.moves))

    set_path_move_handler(on_move)
