"""F5 for an open form tab. The shell calls ``FormSurface.run_active_file``."""

from __future__ import annotations

import os
from typing import Any, Optional

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.forms import classify_form
from app.features.form_builder.engine.project.fs import OsFileSystem, inside_project
from app.features.form_builder.engine.project.run_route import decide_form_run
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui


def run_open_form(surface: Any, workflow: Any) -> bool:
    """Save a project form, then run its entry point or request a preview."""
    path = str(surface.form_path())
    host = workflow._host
    project = _loaded_project(host)
    root = _project_root(project)
    entry = _entry_file(project)
    files = OsFileSystem()
    if root:
        scope = scope_for(path, root, files)
    else:
        scope = classify_form(path, project_root=None)
    plan = decide_form_run(
        generates=scope.generates,
        in_project=bool(root) and inside_project(path, root),
        entry=entry,
        ui_name=os.path.basename(path),
    )
    if plan.save:
        text = str(surface.current_text())
        saved = _persist_form(host, surface, path, text, files)
        if saved is None:
            return False
        if saved == "shell":
            # The shell's save already ran the form's after_save codegen.
            if not _shell_save_ok(host, surface):
                return False
        elif scope.generates:
            if not _generate(host, scope, path, files):
                return False
    if plan.action == "preview":
        surface.request_preview(path)
        _status(host, plan.status)
        return True
    started = bool(workflow.handle_run_project_action())
    if started:
        _status(host, plan.status)
    else:
        _status(host, "Saved %s." % os.path.basename(path))
    return started


def _loaded_project(host: Any) -> Any:
    getter = getattr(host, "loaded_project", None)
    if not callable(getter):
        return None
    return getter()


def _project_root(project: Any) -> Optional[str]:
    root = getattr(project, "project_root", None)
    if not root:
        return None
    return str(root)


def _entry_file(project: Any) -> str:
    metadata = getattr(project, "metadata", None)
    entry = getattr(metadata, "default_entry", "") if metadata is not None else ""
    return str(entry or "").strip()


def _persist_form(host: Any, surface: Any, path: str, text: str, files: OsFileSystem) -> Optional[str]:
    """``"shell"`` when the shell saved (and generated), ``"direct"`` when we wrote it, None on failure."""
    window = getattr(host, "_window", None)
    save_workflow = getattr(window, "_save_workflow", None) if window is not None else None
    save_tab = getattr(save_workflow, "save_tab", None) if save_workflow is not None else None
    if callable(save_tab):
        return "shell" if save_tab(path) else None
    try:
        files.write_text(path, text)
    except OSError:
        return None
    marker = getattr(surface, "mark_saved", None)
    if callable(marker):
        marker(text)
    return "direct"


def _shell_save_ok(host: Any, surface: Any) -> bool:
    """False when the save's codegen failed, so F5 never runs stale generated code."""
    source_getter = getattr(surface, "content_source", None)
    source = source_getter() if callable(source_getter) else None
    notice = getattr(source, "save_notice", None)
    if notice is not None and getattr(notice, "error", False):
        _status(host, str(getattr(notice, "text", "")) or "The form could not be generated.")
        return False
    return True


def _generate(host: Any, scope: Any, path: str, files: OsFileSystem) -> bool:
    try:
        ui_bytes = files.read_bytes(path)
        document = read_ui(ui_bytes.decode("utf-8"), allocator=IdAllocator()).document
    except (OSError, UnicodeError, UiReadError) as exc:
        _status(host, str(exc))
        return False
    written = write_generated(scope, document, ui_bytes, files)
    if written.text_written:
        return True
    if written.diagnostics:
        _status(host, written.diagnostics[0].message)
    else:
        _status(host, "The form could not be generated.")
    return False


def _status(host: Any, message: str) -> None:
    getter = getattr(host, "status_bar", None)
    bar = getter() if callable(getter) else None
    show = getattr(bar, "showMessage", None)
    if callable(show):
        show(message)
