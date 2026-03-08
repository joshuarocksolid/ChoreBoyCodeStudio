"""Project packaging: create distributable folder with .desktop launcher."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

_EXCLUDED_DIR_NAMES = {"__pycache__", "cbcs/runs", "cbcs/logs", "cbcs/cache"}

_EXCLUDED_SUFFIXES = {".pyc"}

_APPRUN_PATH = "/opt/freecad/AppRun"


@dataclass(frozen=True)
class PackageResult:
    """Outcome of a project packaging operation."""

    output_path: str
    desktop_name: str
    project_folder_name: str
    success: bool
    error: str | None = None


def sanitize_project_name(name: str) -> str:
    """Convert a human project name to a filesystem-safe identifier.

    Rules: lowercase, strip whitespace, replace non-alphanumeric (except
    hyphens/underscores) with underscores, collapse runs of underscores,
    fall back to ``"project"`` if nothing remains.
    """
    cleaned = name.strip().lower()
    cleaned = re.sub(r"[^a-z0-9_\-]", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned or "project"


def build_desktop_entry(
    project_name: str,
    entry_file: str,
    install_dir: str,
) -> str:
    """Generate a ``.desktop`` file string for a ChoreBoy FreeCAD-launched app.

    *project_name* is the human-readable name shown in the launcher.
    *entry_file* is the Python entry point relative to *install_dir*.
    *install_dir* is the packaged project subdirectory containing source files
    (typically ``app_files``).
    """
    install_dir_normalized = install_dir.strip().strip("/")
    entry_path = f"{install_dir_normalized}/{entry_file}".strip("/")
    exec_line = (
        "/bin/sh -c "
        f"'desktop=\"%k\";"
        "root=\"$(cd \"$(dirname \"$desktop\")\" && pwd)\";"
        "export CBCS_PROJECT_ROOT=\"$root\";"
        f"{_APPRUN_PATH} -c "
        "\"import os,runpy,sys;"
        "root=os.environ.get('CBCS_PROJECT_ROOT', os.getcwd());"
        "sys.path.insert(0,root) if root not in sys.path else None;"
        "os.chdir(root);"
        f"runpy.run_path(os.path.join(root, {entry_path!r}), run_name='__main__')\"'"
    )
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name={project_name}\n"
        f"Comment=Launch {project_name} (Qt via FreeCAD AppRun)\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        "\n"
        f"Exec={exec_line}\n"
    )


def _paths_overlap(a: Path, b: Path) -> bool:
    """Return True if resolved *a* and *b* are the same path or nested."""
    ra = a.resolve()
    rb = b.resolve()
    if ra == rb:
        return True
    try:
        ra.relative_to(rb)
        return True
    except ValueError:
        pass
    try:
        rb.relative_to(ra)
        return True
    except ValueError:
        pass
    return False


def _should_exclude(rel_path: Path) -> bool:
    """Return True if *rel_path* should be excluded from the package."""
    parts_str = rel_path.as_posix()
    for excluded in _EXCLUDED_DIR_NAMES:
        if parts_str == excluded or parts_str.startswith(excluded + "/"):
            return True
    if rel_path.suffix in _EXCLUDED_SUFFIXES:
        return True
    return False


def package_project(
    *,
    project_root: str,
    project_name: str,
    entry_file: str,
    output_dir: str,
) -> PackageResult:
    """Create a distributable folder for the project.

    The folder ``<output_dir>/<sanitized>/`` contains:
    - ``<sanitized>.desktop`` launcher file
    - ``app_files/`` subfolder with all project source files

    Returns a :class:`PackageResult` with outcome details.
    """
    root = Path(project_root)
    if not root.is_dir():
        return PackageResult(
            output_path="",
            desktop_name="",
            project_folder_name="",
            success=False,
            error=f"Project root does not exist: {project_root}",
        )
    root = root.resolve()

    resolved_entry_path, entry_error = _resolve_entry_path(root=root, entry_file=entry_file)
    if entry_error is not None:
        return PackageResult(
            output_path="",
            desktop_name="",
            project_folder_name="",
            success=False,
            error=entry_error,
        )
    assert resolved_entry_path is not None
    entry_relative_path = resolved_entry_path.relative_to(root).as_posix()
    if _should_exclude(Path(entry_relative_path)):
        return PackageResult(
            output_path="",
            desktop_name="",
            project_folder_name="",
            success=False,
            error=(
                "Entry file resolves to an excluded path and would not be packaged: "
                f"{entry_file}"
            ),
        )

    sanitized = sanitize_project_name(project_name)
    project_files_folder = "app_files"
    desktop_name = f"{sanitized}.desktop"

    out = Path(output_dir)
    package_dir = out / sanitized
    project_dest = package_dir / project_files_folder
    install_dir = project_files_folder

    if _paths_overlap(package_dir, root):
        return PackageResult(
            output_path=str(package_dir),
            desktop_name=desktop_name,
            project_folder_name=project_files_folder,
            success=False,
            error=(
                f"Package output path '{package_dir.resolve()}' overlaps with "
                f"the project directory '{root.resolve()}'. "
                "Choose a different output location to avoid overwriting "
                "the project."
            ),
        )

    try:
        if package_dir.exists():
            shutil.rmtree(package_dir)
        package_dir.mkdir(parents=True, exist_ok=True)
        project_dest.mkdir(parents=True, exist_ok=True)

        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(root)
            if _should_exclude(rel):
                continue
            dest = project_dest / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest)

        desktop_content = build_desktop_entry(project_name, entry_relative_path, install_dir)
        (package_dir / desktop_name).write_text(desktop_content, encoding="utf-8")
    except Exception as exc:
        return PackageResult(
            output_path=str(package_dir),
            desktop_name=desktop_name,
            project_folder_name=project_files_folder,
            success=False,
            error=str(exc),
        )

    return PackageResult(
        output_path=str(package_dir),
        desktop_name=desktop_name,
        project_folder_name=project_files_folder,
        success=True,
    )


def _resolve_entry_path(*, root: Path, entry_file: str) -> tuple[Path | None, str | None]:
    if not entry_file.strip():
        return None, "Entry file must be a non-empty path."
    candidate = Path(entry_file).expanduser()
    resolved_entry = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved_entry.relative_to(root)
    except ValueError:
        return None, f"Entry file must be inside project root: {entry_file}"
    if not resolved_entry.exists() or not resolved_entry.is_file():
        return None, f"Entry file not found in project: {entry_file}"
    return resolved_entry, None
