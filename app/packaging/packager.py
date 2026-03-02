"""Project packaging: create distributable .zip with .desktop launcher."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

_EXCLUDED_DIR_NAMES = {"__pycache__", ".cbcs/runs", ".cbcs/logs", ".cbcs/cache"}

_EXCLUDED_SUFFIXES = {".pyc"}

_APPRUN_PATH = "/opt/freecad/AppRun"


@dataclass(frozen=True)
class PackageResult:
    """Outcome of a project packaging operation."""

    zip_path: str
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
    *install_dir* is the absolute path where the hidden project folder will live
    (e.g. ``/home/default/.myapp``).
    """
    entry_path = f"{install_dir}/{entry_file}"
    exec_line = (
        f"{_APPRUN_PATH} -c "
        f"\"p='{entry_path}';"
        f"exec(compile(open(p,'r',encoding='utf-8').read(),p,'exec'),"
        f"{{'__name__':'__main__','__file__':p}})\""
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


def _should_exclude(rel_path: Path) -> bool:
    """Return True if *rel_path* should be excluded from the package zip."""
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
    """Create a distributable .zip for the project.

    The zip contains:
    - ``<sanitized>.desktop`` at the root
    - ``.<sanitized>/`` folder with all project source files

    Returns a :class:`PackageResult` with outcome details.
    """
    root = Path(project_root)
    if not root.is_dir():
        return PackageResult(
            zip_path="",
            desktop_name="",
            project_folder_name="",
            success=False,
            error=f"Project root does not exist: {project_root}",
        )

    sanitized = sanitize_project_name(project_name)
    hidden_folder = f".{sanitized}"
    desktop_name = f"{sanitized}.desktop"
    install_dir = f"/home/default/{hidden_folder}"

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    zip_path = out / f"{sanitized}.zip"

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            desktop_content = build_desktop_entry(project_name, entry_file, install_dir)
            zf.writestr(desktop_name, desktop_content)

            for file_path in sorted(root.rglob("*")):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(root)
                if _should_exclude(rel):
                    continue
                arcname = f"{hidden_folder}/{rel.as_posix()}"
                zf.write(file_path, arcname)
    except Exception as exc:
        return PackageResult(
            zip_path=str(zip_path),
            desktop_name=desktop_name,
            project_folder_name=hidden_folder,
            success=False,
            error=str(exc),
        )

    return PackageResult(
        zip_path=str(zip_path),
        desktop_name=desktop_name,
        project_folder_name=hidden_folder,
        success=True,
    )
