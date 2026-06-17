"""Path/layout helpers shared across packaging workflows."""

from __future__ import annotations

import re
from pathlib import Path

from app.packaging.payload_policy import DEFAULT_PACKAGING_PAYLOAD_POLICY

_UNSAFE_ENTRY_CHARS = {'"', "'", "\n", "\r", "\t", "\x00"}


def sanitize_project_name(name: str) -> str:
    """Convert a human name into a filesystem-safe slug."""
    cleaned = name.strip().lower()
    cleaned = re.sub(r"[^a-z0-9_\-]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("_")
    return cleaned or "project"


def build_launcher_filename(display_name: str) -> str:
    """Return the stable launcher filename for one package."""
    return f"{sanitize_project_name(display_name)}.desktop"


def build_default_install_dirname(display_name: str, version: str) -> str:
    """Return the versioned default install directory name."""
    safe_name = sanitize_project_name(display_name)
    safe_version = version.strip() or "dev"
    return f"{safe_name}_v{safe_version}"


def build_artifact_root_name(display_name: str, version: str, profile: str) -> str:
    """Return the export folder name for one profile."""
    safe_name = sanitize_project_name(display_name)
    safe_version = version.strip() or "dev"
    return f"{safe_name}_installer_v{safe_version}"


def build_installer_launcher_filename(display_name: str) -> str:
    """Return the launcher used to start the installer package itself."""
    return f"install_{sanitize_project_name(display_name)}.desktop"


def rewrite_installer_desktop_path(launcher_path: Path, package_root: str | Path) -> None:
    """Rewrite the Path= key in an installer launcher to match *package_root*."""
    resolved_package_root = str(Path(package_root).expanduser().resolve())
    lines = launcher_path.read_text(encoding="utf-8").splitlines()
    rewritten: list[str] = []
    path_written = False
    for line in lines:
        if line.startswith("Path="):
            rewritten.append(f"Path={resolved_package_root}")
            path_written = True
            continue
        rewritten.append(line)
    if not path_written:
        rewritten.append(f"Path={resolved_package_root}")
    launcher_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def paths_overlap(a: Path, b: Path) -> bool:
    """Return True if resolved *a* and *b* are identical or nested."""
    resolved_a = a.resolve()
    resolved_b = b.resolve()
    if resolved_a == resolved_b:
        return True
    try:
        resolved_a.relative_to(resolved_b)
        return True
    except ValueError:
        pass
    try:
        resolved_b.relative_to(resolved_a)
        return True
    except ValueError:
        pass
    return False


def resolve_entry_path(*, root: Path, entry_file: str) -> tuple[Path | None, str | None]:
    """Resolve an entry file path relative to *root* with clear validation errors."""
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


def validate_packaged_entry_relative_path(entry_relative_path: str) -> str:
    """Return a normalized package entry path or raise for unsafe values."""
    normalized = entry_relative_path.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("entry_relative_path must be a non-empty relative path.")
    if any(char in normalized for char in _UNSAFE_ENTRY_CHARS):
        raise ValueError("entry_relative_path contains unsafe shell or control characters.")
    path = Path(normalized)
    if path.is_absolute():
        raise ValueError("entry_relative_path must be relative.")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("entry_relative_path must not contain empty, current, or parent segments.")
    return path.as_posix()


def is_packaging_excluded_path(rel_path: Path) -> bool:
    """Return True if *rel_path* should be excluded from a package export.

    Delegates to :data:`DEFAULT_PACKAGING_PAYLOAD_POLICY`. See
    :class:`app.packaging.payload_policy.PackagingPayloadPolicy` for the
    canonical copy/audit rules.

    Distinct from :func:`app.project.file_excludes.should_exclude_relative_path`,
    which is the user-pattern based exclusion used by editor search and project
    enumeration.
    """
    return DEFAULT_PACKAGING_PAYLOAD_POLICY.is_payload_excluded(rel_path)
