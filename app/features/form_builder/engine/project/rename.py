"""Preview and apply a form rename or move.

``ui_<stem>.py`` is regenerated for the new path. The window file is moved
and its import of the generated module is edited. Other files in the project
that import the old module paths get the same edit. ``apply`` restores the
previous bytes when a later step fails.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import (
    adopted_forms,
    retarget_adoption,
    write_adopted,
)
from app.features.form_builder.engine.project.cache import clear_inference_cache
from app.features.form_builder.engine.project.forms import FormScope, classify_form
from app.features.form_builder.engine.project.fs import (
    OsFileSystem,
    ProjectOpError,
    inside_project,
    restore,
    same_path,
    snapshot,
)
from app.features.form_builder.engine.project.imports import package_of, python_files, rewrite_imports
from app.features.form_builder.engine.project.names import explain_form_name
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui


@dataclass(frozen=True)
class FileMove:
    source: str
    destination: str


@dataclass(frozen=True)
class TextEdit:
    """Replace the whole file. ``path`` is where the file is after the moves."""

    path: str
    old: str
    new: str


@dataclass(frozen=True)
class RegeneratedFile:
    """``ui_<stem>.py`` written from the generator, not from a text edit."""

    path: str
    text: str


@dataclass(frozen=True)
class RenamePlan:
    """A preview of one rename. ``reason`` is set when nothing should change.

    ``adopted`` is the new adopted list, or None when the list stays as it is.
    """

    project_root: str
    reason: Optional[str]
    moves: Tuple[FileMove, ...]
    edits: Tuple[TextEdit, ...]
    regenerated: Tuple[RegeneratedFile, ...]
    removed: Tuple[str, ...]
    adopted: Optional[Tuple[str, ...]]

    def preview(self) -> Tuple[str, ...]:
        """One line per move, regeneration, edit and removal."""
        if self.reason:
            return (self.reason,)
        lines = ["move %s -> %s" % (item.source, item.destination) for item in self.moves]
        lines.extend("regenerate %s" % item.path for item in self.regenerated)
        lines.extend("edit %s" % item.path for item in self.edits)
        lines.extend("remove %s" % path for path in self.removed)
        return tuple(lines)


def plan_rename(project_root: str, old_ui: str, new_ui: str, fs: OsFileSystem) -> RenamePlan:
    """Build the moves and edits. Does not touch the filesystem except to read."""
    root = os.path.abspath(project_root)
    old_abs = os.path.abspath(old_ui)
    new_abs = os.path.abspath(new_ui)
    if not inside_project(old_abs, root):
        return _refused(root, "That form is outside the project.")
    if not inside_project(new_abs, root):
        return _refused(root, "The new location is outside the project.")
    if same_path(old_abs, new_abs):
        return _refused(root, "That is already the form's path.")
    if not fs.is_file(old_abs):
        return _refused(root, "There is no form at that path.")
    if not old_abs.endswith(".ui") or not new_abs.endswith(".ui"):
        return _refused(root, "A form file has to end with .ui.")
    if fs.is_file(new_abs):
        return _refused(root, "A file named %s is already in that folder." % os.path.basename(new_abs))
    new_stem = os.path.splitext(os.path.basename(new_abs))[0]
    reason = explain_form_name(new_stem, folder=os.path.dirname(new_abs), fs=fs)
    if reason is not None:
        return _refused(root, reason)
    occupied = _occupied(old_abs, new_abs, fs)
    if occupied is not None:
        return _refused(root, "A file named %s is already in that folder." % os.path.basename(occupied))
    try:
        ui_bytes = fs.read_bytes(old_abs)
        document = read_ui(ui_bytes.decode("utf-8"), allocator=IdAllocator()).document
    except (OSError, UnicodeError, UiReadError) as exc:
        return _refused(root, str(exc))
    old_scope = classify_form(old_abs, project_root=root, adopted=adopted_forms(root, fs))
    adopted = retarget_adoption(root, old_abs, new_abs, fs)
    new_list = adopted if adopted is not None else adopted_forms(root, fs)
    new_scope = classify_form(new_abs, project_root=root, adopted=new_list)
    if not new_scope.generates or not new_scope.generated_path:
        return _refused(root, "The new location is outside the project.")
    generated = generate_form_module(document, scope=new_scope, source_bytes=ui_bytes)
    if generated.text is None:
        message = generated.diagnostics[0].message if generated.diagnostics else "The form could not be generated."
        return _refused(root, message)
    moves = [FileMove(source=old_abs, destination=new_abs)]
    window_exists = bool(old_scope.window_path and fs.is_file(old_scope.window_path))
    if window_exists and old_scope.window_path and new_scope.window_path:
        moves.append(FileMove(source=old_scope.window_path, destination=new_scope.window_path))
    removed = []
    if old_scope.generated_path and not same_path(old_scope.generated_path, new_scope.generated_path):
        if fs.is_file(old_scope.generated_path):
            removed.append(old_scope.generated_path)
    mapping = _mapping(old_scope, new_scope, window_exists)
    skip = {os.path.abspath(path) for path in (old_scope.generated_path, new_scope.generated_path) if path}
    edits = _edits(root, fs, mapping, skip, old_scope.window_path if window_exists else None, new_scope.window_path)
    return RenamePlan(
        project_root=root,
        reason=None,
        moves=tuple(moves),
        edits=tuple(edits),
        regenerated=(RegeneratedFile(path=new_scope.generated_path, text=generated.text),),
        removed=tuple(removed),
        adopted=adopted,
    )


def apply(plan: RenamePlan, fs: OsFileSystem) -> None:
    """Run the plan. On failure, put back every file the plan had started to change."""
    if plan.reason:
        raise ProjectOpError(plan.reason)
    _require_inside(plan)
    paths = [_manifest(plan.project_root)]
    for move in plan.moves:
        paths.append(move.source)
        paths.append(move.destination)
    for item in plan.regenerated:
        paths.append(item.path)
    for edit in plan.edits:
        paths.append(edit.path)
    for path in plan.removed:
        paths.append(path)
    originals = snapshot(fs, tuple(path for path in paths if path))
    try:
        for move in plan.moves:
            fs.replace(move.source, move.destination)
        for item in plan.regenerated:
            fs.write_text(item.path, item.text if item.text.endswith("\n") else item.text + "\n")
        for path in plan.removed:
            if fs.is_file(path):
                fs.remove(path)
        for edit in plan.edits:
            current = fs.read_text(edit.path)
            if current != edit.old:
                raise ProjectOpError("A file changed before the rename could update it.")
            fs.write_text(edit.path, edit.new)
        if plan.adopted is not None:
            write_adopted(plan.project_root, fs, plan.adopted)
    except Exception:
        restore(fs, originals)
        raise
    clear_inference_cache()


def _occupied(old_ui: str, new_ui: str, fs: OsFileSystem) -> Optional[str]:
    old_dir = os.path.dirname(old_ui)
    new_dir = os.path.dirname(new_ui)
    old_stem = os.path.splitext(os.path.basename(old_ui))[0]
    new_stem = os.path.splitext(os.path.basename(new_ui))[0]
    candidates = (
        new_ui,
        os.path.join(new_dir, "ui_%s.py" % new_stem),
        os.path.join(new_dir, "%s_window.py" % new_stem),
    )
    old_set = {
        os.path.abspath(old_ui),
        os.path.abspath(os.path.join(old_dir, "ui_%s.py" % old_stem)),
        os.path.abspath(os.path.join(old_dir, "%s_window.py" % old_stem)),
    }
    for path in candidates:
        if os.path.abspath(path) in old_set:
            continue
        if fs.is_file(path):
            return path
    return None


def _mapping(old: FormScope, new: FormScope, window_exists: bool) -> Dict[str, str]:
    mapping = {}
    if old.module_name and new.module_name and old.module_name != new.module_name:
        mapping[old.module_name] = new.module_name
    if (
        window_exists
        and old.window_module_name
        and new.window_module_name
        and old.window_module_name != new.window_module_name
    ):
        mapping[old.window_module_name] = new.window_module_name
    return mapping


def _edits(
    root: str,
    fs: OsFileSystem,
    mapping: Dict[str, str],
    skip: set,
    old_window: Optional[str],
    new_window: Optional[str],
) -> List[TextEdit]:
    if not mapping:
        return []
    edits = []
    old_window_abs = os.path.abspath(old_window) if old_window else None
    for path in python_files(root, fs):
        if os.path.abspath(path) in skip:
            continue
        try:
            text = fs.read_text(path)
        except (OSError, UnicodeError):
            continue
        rewritten = rewrite_imports(text, mapping, package_of(root, path))
        if rewritten == text:
            continue
        dest = path
        if old_window_abs is not None and os.path.abspath(path) == old_window_abs and new_window:
            dest = new_window
        edits.append(TextEdit(path=dest, old=text, new=rewritten))
    return edits


def _require_inside(plan: RenamePlan) -> None:
    paths = []
    for move in plan.moves:
        paths.extend((move.source, move.destination))
    for item in plan.regenerated:
        paths.append(item.path)
    for edit in plan.edits:
        paths.append(edit.path)
    for path in plan.removed:
        paths.append(path)
    for path in paths:
        if not inside_project(path, plan.project_root):
            raise ProjectOpError("That path is outside the project.")


def _refused(root: str, reason: str) -> RenamePlan:
    return RenamePlan(
        project_root=root,
        reason=reason,
        moves=(),
        edits=(),
        regenerated=(),
        removed=(),
        adopted=None,
    )


def _manifest(root: str) -> str:
    return os.path.join(root, "cbcs", "project.json")
