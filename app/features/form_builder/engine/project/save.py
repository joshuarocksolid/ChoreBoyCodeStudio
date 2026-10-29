"""Save-side generation (CONTRACTS.md section 9.6 step 3).

A codegen failure returns diagnostics and leaves every existing file
byte-identical. A hand edit is copied aside before the generated file is
replaced. The window class is created once.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.api_types import CodegenOptions
from app.features.form_builder.engine.codegen.header import is_hand_edited, is_stale, split_generated
from app.features.form_builder.engine.codegen.resources import (
    compile_resource_tree,
    read_qrc,
    render_rc_module,
)
from app.features.form_builder.engine.codegen.window_template import render_window_class
from app.features.form_builder.engine.diagnostics import (
    CODES,
    DiagnosticLocation,
    FormDiagnostic,
    QuickFix,
    Severity,
)
from app.features.form_builder.engine.project.cache import clear_inference_cache
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.fs import Journal, OsFileSystem, inside_project
from app.features.form_builder.engine.ui4.document import UiDocument


@dataclass(frozen=True)
class WriteResult:
    """``files`` lists paths this call created or replaced. ``text_written`` is
    false when generation was refused and nothing was replaced."""

    diagnostics: Tuple[FormDiagnostic, ...]
    files: Tuple[str, ...]
    text_written: bool


def opening_diagnostics(
    scope: FormScope,
    ui_bytes: bytes,
    fs: OsFileSystem,
) -> Tuple[FormDiagnostic, ...]:
    """FB505 when a generated module is out of date with the form just opened."""
    if not scope.generates or not scope.generated_path or not fs.is_file(scope.generated_path):
        return ()
    text = fs.read_text(scope.generated_path)
    if not is_stale(text, ui_bytes):
        return ()
    name = os.path.basename(scope.generated_path)
    return (
        _diagnostic(
            "FB505",
            "%s is out of date with this form. Save the form to bring it up to date." % name,
        ),
    )


def write_generated(
    scope: FormScope,
    doc: UiDocument,
    ui_bytes: bytes,
    fs: OsFileSystem,
    *,
    options: CodegenOptions = CodegenOptions(),
) -> WriteResult:
    """Generate, keep a hand-edit copy, and atomically write the Python files.

    Does not write the ``.ui`` file. That is step 1 of the save pipeline.
    """
    if not scope.generates or not scope.generated_path or not scope.project_root:
        return WriteResult(
            diagnostics=(
                _diagnostic(
                    "FB506",
                    "This form is outside the project, so no Python file is written.",
                ),
            ),
            files=(),
            text_written=False,
        )
    result = generate_form_module(doc, scope=scope, source_bytes=ui_bytes, options=options)
    if result.text is None:
        return WriteResult(diagnostics=result.diagnostics, files=(), text_written=False)
    window_text = _window_text(scope, doc, fs)
    if isinstance(window_text, FormDiagnostic):
        return WriteResult(
            diagnostics=result.diagnostics + (window_text,),
            files=(),
            text_written=False,
        )
    diagnostics = list(result.diagnostics)  # type: List[FormDiagnostic]
    planned = []  # type: List[Tuple[str, bytes]]
    backup = _hand_edit_backup(scope.project_root, scope.generated_path, fs, diagnostics)
    if backup is not None:
        planned.append(backup)
    planned.append((scope.generated_path, result.text.encode("utf-8")))
    planned.extend(_resource_writes(scope, doc, result.resource_modules, fs, diagnostics))
    init_path = _forms_init(scope, fs)
    if init_path is not None:
        planned.append((init_path, b"\n"))
    if window_text is not None and scope.window_path:
        planned.append((scope.window_path, window_text.encode("utf-8")))
    outside = [path for path, _data in planned if not inside_project(path, scope.project_root)]
    if outside:
        return WriteResult(
            diagnostics=tuple(result.diagnostics)
            + (
                _diagnostic(
                    "FB506",
                    "This form would be written outside the project, so nothing was written.",
                ),
            ),
            files=(),
            text_written=False,
        )
    journal = Journal(fs)
    failed_name = "the generated file"
    try:
        for path, data in planned:
            failed_name = os.path.basename(path)
            journal.put(path, data)
    except OSError:
        try:
            journal.rollback()
        except OSError:
            pass
        return WriteResult(
            diagnostics=tuple(diagnostics)
            + (_diagnostic("FB509", "could not write %s." % failed_name),),
            files=(),
            text_written=False,
        )
    except Exception:
        journal.rollback()
        raise
    clear_inference_cache()
    return WriteResult(
        diagnostics=tuple(diagnostics),
        files=tuple(path for path, _data in planned),
        text_written=True,
    )


def _window_text(scope: FormScope, doc: UiDocument, fs: OsFileSystem):
    if not scope.window_path or fs.is_file(scope.window_path):
        return None
    try:
        text = render_window_class(doc, scope=scope)
    except ValueError as exc:
        return _diagnostic("FB502", str(exc))
    if not text.endswith("\n"):
        text += "\n"
    return text


def _forms_init(scope: FormScope, fs: OsFileSystem) -> Optional[str]:
    if scope.kind != "project" or not scope.project_root:
        return None
    path = os.path.join(scope.project_root, "forms", "__init__.py")
    if fs.is_file(path):
        return None
    return path


def _hand_edit_backup(
    project_root: str,
    path: str,
    fs: OsFileSystem,
    diagnostics: List[FormDiagnostic],
) -> Optional[Tuple[str, bytes]]:
    if not fs.is_file(path):
        return None
    data = fs.read_bytes(path)
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        text = None
    if text is not None and not is_hand_edited(text):
        return None
    backup = os.path.join(
        project_root,
        "cbcs",
        "form_builder",
        "hand_edits",
        _backup_name(path, data, text),
    )
    diagnostics.append(
        FormDiagnostic(
            code="FB501",
            severity=CODES["FB501"].severity,
            message="%s was edited by hand. A copy was saved before it was replaced."
            % os.path.basename(path),
            location=DiagnosticLocation(),
            source="project",
            fixes=(
                QuickFix(
                    fix_id="open-hand-edit",
                    title="Open the saved copy",
                    action="open-saved-copy",
                    args=(("path", backup),),
                ),
            ),
        )
    )
    return backup, data


def _backup_name(path: str, data: bytes, text: Optional[str]) -> str:
    base = os.path.basename(path)
    if base.endswith(".py"):
        base = base[:-3]
    if text is None:
        payload = data
        digest = hashlib.sha256(payload).hexdigest()[:8]
    else:
        parts = split_generated(text)
        body = parts[1] if parts is not None else text
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]
    return "%s.%s.py.txt" % (base, digest)


def _resource_writes(
    scope: FormScope,
    doc: UiDocument,
    modules: Tuple[str, ...],
    fs: OsFileSystem,
    diagnostics: List[FormDiagnostic],
) -> List[Tuple[str, bytes]]:
    if not scope.project_root or not scope.ui_path:
        return []
    locations = []
    for node in doc.ui.children("resources"):
        location = node.field("location")
        if isinstance(location, str) and location.strip():
            locations.append(location)
    planned = []
    for location, module in zip(locations, modules):
        qrc, dest = _rc_paths(scope.project_root, scope.ui_path, location, module)
        if not inside_project(qrc, scope.project_root) or not inside_project(dest, scope.project_root):
            diagnostics.append(
                _diagnostic(
                    "FB503",
                    'The resource file "%s" is outside the project.' % location,
                )
            )
            continue
        if not fs.is_file(qrc):
            diagnostics.append(
                _diagnostic("FB503", 'The resource file "%s" is missing.' % location)
            )
            continue
        try:
            qrc_text = fs.read_text(qrc)
            parsed = read_qrc(qrc_text)
        except (OSError, UnicodeError, ValueError) as exc:
            diagnostics.append(_diagnostic("FB502", str(exc)))
            continue
        qrc_dir = os.path.dirname(qrc)

        def read_file(rel: str, folder: str = qrc_dir, root: str = scope.project_root or "") -> bytes:
            target = os.path.normpath(os.path.join(folder, rel.replace("\\", "/")))
            if not inside_project(target, root):
                raise OSError(rel)
            return fs.read_bytes(target)

        tree, resource_diagnostics = compile_resource_tree(parsed, read_file=read_file)
        diagnostics.extend(resource_diagnostics)
        text = render_rc_module(tree, qrc_file_name=os.path.basename(qrc))
        data = text.encode("utf-8")
        if fs.is_file(dest) and fs.read_bytes(dest) == data:
            continue
        backup = _hand_edit_backup(scope.project_root, dest, fs, diagnostics)
        if backup is not None:
            planned.append(backup)
        planned.append((dest, data))
    return planned


_SKIP_DIRS = frozenset({"cbcs", "__pycache__", ".git", "vendor", "node_modules"})


def project_ui_files(root: str) -> Tuple[str, ...]:
    """Absolute paths of every ``.ui`` under ``root``, sorted, without tool and vendor folders."""
    found: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in _SKIP_DIRS and not name.startswith("."))
        found.extend(os.path.join(dirpath, name) for name in sorted(filenames) if name.endswith(".ui"))
    return tuple(found)


def forms_including(project_root: str, qrc_path: str, fs: Optional[OsFileSystem] = None) -> Tuple[str, ...]:
    """Absolute paths of the project's forms whose ``<resources>`` include ``qrc_path``."""
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui

    files = fs if fs is not None else OsFileSystem()
    target = os.path.normcase(os.path.abspath(qrc_path))
    found: List[str] = []
    for ui_path in project_ui_files(project_root):
        try:
            document = read_ui(files.read_text(ui_path), allocator=IdAllocator()).document
        except (OSError, UnicodeError, UiReadError):
            continue
        for node in document.ui.children("resources"):
            location = node.field("location")
            if not isinstance(location, str) or not location.strip():
                continue
            here = os.path.normcase(os.path.normpath(os.path.join(os.path.dirname(ui_path), location.replace("\\", "/"))))
            if here == target:
                found.append(ui_path)
                break
    return tuple(found)


def rewrite_resource_modules(
    project_root: str,
    qrc_path: str,
    fs: Optional[OsFileSystem] = None,
) -> WriteResult:
    """Write the ``*_rc.py`` of every form in the project that includes ``qrc_path`` (UX-RES-004).

    Only the resource modules are written, never a form's ``ui_*.py``. A module
    whose bytes already match is left alone. Files are written through a
    ``Journal``, so a failure leaves every one of them as it was.
    """
    from app.features.form_builder.engine.ids import IdAllocator
    from app.features.form_builder.engine.project.adoption import scope_for
    from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui

    files = fs if fs is not None else OsFileSystem()
    root = os.path.abspath(project_root)
    diagnostics: List[FormDiagnostic] = []
    planned: dict = {}
    for ui_path in forms_including(root, qrc_path, files):
        scope = scope_for(ui_path, root, files)
        if not scope.generates:
            continue
        try:
            ui_bytes = files.read_bytes(ui_path)
            document = read_ui(ui_bytes.decode("utf-8"), allocator=IdAllocator()).document
        except (OSError, UnicodeError, UiReadError):
            continue
        result = generate_form_module(document, scope=scope, source_bytes=ui_bytes)
        for path, data in _resource_writes(scope, document, result.resource_modules, files, diagnostics):
            planned.setdefault(path, data)
    outside = [path for path in planned if not inside_project(path, root)]
    if outside:
        return WriteResult(tuple(diagnostics), (), False)
    journal = Journal(files)
    try:
        for path, data in planned.items():
            journal.put(path, data)
    except OSError:
        try:
            journal.rollback()
        except OSError:
            pass
        diagnostics.append(_diagnostic("FB509", "could not write the picture module."))
        return WriteResult(tuple(diagnostics), (), False)
    clear_inference_cache()
    return WriteResult(tuple(diagnostics), tuple(planned), True)


def resource_destination(project_root: str, ui_path: str, location: str, module: str) -> str:
    """Absolute path of the ``*_rc.py`` written for one ``.qrc`` include."""
    _qrc, dest = _rc_paths(project_root, ui_path, location, module)
    return dest


def _rc_paths(project_root: str, ui_path: str, location: str, module: str) -> Tuple[str, str]:
    qrc = os.path.normpath(os.path.join(os.path.dirname(ui_path), location.replace("\\", "/")))
    parts = [part for part in module.split(".") if part]
    leaf = (parts[-1] if parts else "resources") + ".py"
    if len(parts) <= 1:
        dest = os.path.join(os.path.dirname(qrc), leaf)
    else:
        dest = os.path.join(project_root, *parts[:-1], leaf)
    return qrc, dest


def _diagnostic(code: str, message: str) -> FormDiagnostic:
    info = CODES.get(code)
    severity = info.severity if info is not None else Severity.ERROR
    return FormDiagnostic(
        code=code,
        severity=severity,
        message=message,
        location=DiagnosticLocation(),
        source="project",
    )
