"""Packaging view of form-builder generated files.

The engine report stays free of ``RuntimeIssue``. This module is the boundary
that turns it into packaging problems.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.bootstrap.qt_binding_choice import select_binding
from app.core.models import RuntimeIssue
from app.features.form_builder.engine.project.fs import ProjectOpError, relative_posix
from app.features.form_builder.engine.project.loaders import loader_kind_label, scan_ui_loaders
from app.features.form_builder.engine.project.packaging import (
    GeneratedFile,
    adopt_pictures_now,
    inspect_forms,
    save_form_now,
)
from app.features.form_builder.engine.ui4.reader import UiReadError

_FIX_LABEL = "Save the form now"
_PYSIDE2_NEXT = "Open this project in FreeCAD 1.1 or later and save the form."


def _form_save_available() -> bool:
    """True when this process can run the form builder saver."""
    try:
        return select_binding() == "PySide6"
    except ImportError:
        return False


def form_packaging_issues(project_root: str) -> list[RuntimeIssue]:
    """Blocking problems for stale or missing output, plus degraded loader calls."""
    report = inspect_forms(project_root)
    issues = [_issue_for_file(project_root, item) for item in report.files if item.state != "current"]
    issues.extend(_loader_issues(project_root))
    return [issue for issue in issues if issue is not None]


def form_lines(project_root: str) -> list[str]:
    """One line per generated file, for the package wizard."""
    lines: list[str] = []
    for item in inspect_forms(project_root).files:
        if item.state == "current":
            if item.source_relative:
                lines.append("%s    %s" % (item.source_relative, item.relative_path))
            else:
                lines.append(item.relative_path)
        else:
            lines.append(item.message)
    return lines


def form_report_dict(project_root: str) -> dict[str, Any]:
    """``forms`` entry for ``package_report.json``."""
    report = inspect_forms(project_root)
    return {"forms": [_file_dict(item) for item in report.files]}


def save_packaged_form(project_root: str, ui_path: str) -> str:
    """Regenerate one form from disk.

    An empty string means the Python files were written. Otherwise the string
    is the reason, including an FB code when the generator reported one.
    """
    try:
        written = save_form_now(project_root, ui_path)
    except (OSError, UnicodeError, ProjectOpError, UiReadError, ValueError) as exc:
        text = str(exc).strip()
        return text or "The form could not be saved."
    if written.text_written:
        return ""
    if written.diagnostics:
        return written.diagnostics[0].message
    return "The form could not be saved."


def add_packaged_pictures(project_root: str, ui_path: str) -> str:
    """The "Add to project pictures" fix for one form. An empty string means every picture was fixed."""
    try:
        fixed, reason = adopt_pictures_now(project_root, ui_path)
    except (OSError, UnicodeError, ProjectOpError, UiReadError, ValueError) as exc:
        return str(exc).strip() or "The pictures could not be added."
    if reason:
        return reason
    return "" if fixed else "No picture in this form uses a file path."


def _issue_for_file(project_root: str, item: GeneratedFile) -> RuntimeIssue | None:
    if item.state == "current":
        return None
    ui_path = ""
    if item.source_relative:
        ui_path = _abs(project_root, item.source_relative)
    if item.state == "raw_path":
        return _picture_path_issue(item, ui_path)
    fixable = item.role in {"ui_module", "resource"} and item.state in {"stale", "missing"}
    if item.state == "missing":
        issue_id = "package.form.missing"
        title = "Generated form file is missing"
    elif item.state == "unreadable":
        issue_id = "package.form.unreadable"
        title = "Form file could not be read"
    else:
        issue_id = "package.form.stale"
        title = "Generated form file is out of date"
    evidence: dict[str, Any] = {
        "ui_path": ui_path,
        "ui_relative": item.source_relative,
        "generated_relative": item.relative_path,
        "source_file": item.source_relative,
        "line_number": 1,
        "report_row": item.message,
        "role": item.role,
    }
    can_save = bool(fixable and ui_path and _form_save_available())
    severity = "blocking"
    next_steps = ["Open the form and save it so the Python files match."]
    if can_save:
        evidence["fix_action"] = "save_form"
        evidence["fix_label"] = _FIX_LABEL
        next_steps = [_FIX_LABEL]
    elif fixable and ui_path:
        severity = "degraded"
        next_steps = [_PYSIDE2_NEXT]
    return RuntimeIssue(
        issue_id=issue_id,
        workflow="package",
        severity=severity,
        title=title,
        summary=item.message,
        why_it_happened=(
            "The packaged app imports the generated Python. "
            "It does not load the .ui file at runtime."
        ),
        next_steps=next_steps,
        help_topic="packaging_backup",
        evidence=evidence,
    )


def _picture_path_issue(item: GeneratedFile, ui_path: str) -> RuntimeIssue:
    """A picture stored as a file path (UX-RES-005). Save is never blocked; packaging is."""
    return RuntimeIssue(
        issue_id="package.form.picture_path",
        workflow="package",
        severity="blocking",
        title="A picture uses a file path",
        summary=item.message,
        why_it_happened=(
            "The packaged app does not carry the picture file, so the picture or icon is blank when it runs."
        ),
        next_steps=["Open the form, select the widget and choose Add to project pictures."],
        help_topic="packaging_backup",
        evidence={
            "ui_path": ui_path,
            "ui_relative": item.source_relative,
            "picture_path": item.relative_path,
            "source_file": item.source_relative,
            "line_number": 1,
            "report_row": item.message,
            "role": item.role,
            "fix_action": "add_pictures",
            "fix_label": "Add to project pictures",
        },
    )


def _loader_issues(project_root: str) -> list[RuntimeIssue]:
    issues: list[RuntimeIssue] = []
    for site in scan_ui_loaders(project_root):
        try:
            rel = relative_posix(site.path, project_root)
        except ProjectOpError:
            continue
        kind = loader_kind_label(site.kind)
        summary = "%s loads a .ui file with %s." % (rel, kind)
        issues.append(
            RuntimeIssue(
                issue_id="package.form.runtime_loader",
                workflow="package",
                severity="degraded",
                title="The app still loads a .ui file at runtime",
                summary=summary,
                why_it_happened=(
                    "A packaged app should call setupUi on the generated class. "
                    "Loading the .ui file skips that Python."
                ),
                next_steps=["Use Adopt this form, then paste the setupUi suggestion into the window class."],
                help_topic="packaging_backup",
                evidence={
                    "source_file": rel,
                    "line_number": site.line,
                    "report_row": summary,
                    "kind": site.kind,
                },
            )
        )
    return issues


def _file_dict(item: GeneratedFile) -> dict[str, str]:
    return {
        "path": item.relative_path,
        "role": item.role,
        "state": item.state,
        "source": item.source_relative,
        "message": item.message,
    }


def _abs(project_root: str, relative: str) -> str:
    return str((Path(project_root) / relative).resolve())
