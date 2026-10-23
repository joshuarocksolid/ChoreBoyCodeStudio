"""F5 on a form tab: run the project entry, or preview when that cannot happen.

The shell calls this and then uses its existing run-project action. Shift+F5
and Ctrl+F5 stay on the shell. This module does not import Qt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

FormRunAction = Literal["run_project", "preview"]

_OUTSIDE = "This form isn't part of a project, so F5 previews it."
_UNLISTED = "This form isn't in forms/ or adopted, so F5 previews it."
_NO_ENTRY = "This project has no entry point, so F5 previews the form."


@dataclass(frozen=True)
class FormRunPlan:
    """What F5 does for one open form.

    ``save`` is true when the form belongs to the project. Saving writes the
    ``.ui`` and the generated Python before the run or the preview.
    """

    action: FormRunAction
    status: str
    save: bool


def decide_form_run(
    *,
    generates: bool,
    in_project: bool,
    entry: str,
    ui_name: str,
) -> FormRunPlan:
    """Choose run or preview from the form's scope and the project entry.

    ``in_project`` is true when the ``.ui`` file sits inside the open project.
    A file there that is not under ``forms/`` and is not adopted still previews,
    with a different status from a form that has no project at all.
    """
    entry_name = os.path.basename(entry.strip()) if entry and entry.strip() else ""
    if not generates:
        status = _UNLISTED if in_project else _OUTSIDE
        return FormRunPlan(action="preview", status=status, save=False)
    if not entry_name:
        return FormRunPlan(action="preview", status=_NO_ENTRY, save=True)
    return FormRunPlan(
        action="run_project",
        status="Saved %s · Running %s" % (ui_name, entry_name),
        save=True,
    )
