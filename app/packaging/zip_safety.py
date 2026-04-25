"""Safe zip extraction helpers for untrusted package inputs."""

from __future__ import annotations

from pathlib import Path
import zipfile


class UnsafeArchiveError(ValueError):
    """Raised when an archive member would escape the extraction root."""


def safe_extract_zip(archive: zipfile.ZipFile, destination_root: str | Path) -> None:
    """Extract *archive* under *destination_root* after validating member paths."""
    root = Path(destination_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for member in archive.infolist():
        _validate_member_path(root, member.filename)
    archive.extractall(root)


def _validate_member_path(root: Path, member_name: str) -> None:
    if not member_name or "\x00" in member_name:
        raise UnsafeArchiveError("Unsafe archive member path.")
    candidate = (root / member_name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafeArchiveError(f"Unsafe archive member path: {member_name}") from exc
