"""Filesystem-backed project tree operations."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.project.file_operation_models import FileOperationResult


def create_file(target_path: str, *, content: str = "") -> FileOperationResult:
    destination = Path(target_path).expanduser().resolve()
    if destination.exists():
        return FileOperationResult(success=False, message=f"Path already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return FileOperationResult(success=True, message="File created.", destination_path=str(destination))


def create_directory(target_path: str) -> FileOperationResult:
    destination = Path(target_path).expanduser().resolve()
    if destination.exists():
        return FileOperationResult(success=False, message=f"Path already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    return FileOperationResult(success=True, message="Directory created.", destination_path=str(destination))


def rename_path(source_path: str, destination_path: str) -> FileOperationResult:
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    if not source.exists():
        return FileOperationResult(success=False, message=f"Source does not exist: {source}")
    if destination.exists():
        return FileOperationResult(success=False, message=f"Destination already exists: {destination}")
    source.rename(destination)
    return FileOperationResult(
        success=True,
        message="Path renamed.",
        source_path=str(source),
        destination_path=str(destination),
    )


def move_path(source_path: str, destination_path: str) -> FileOperationResult:
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    if not source.exists():
        return FileOperationResult(success=False, message=f"Source does not exist: {source}")
    if destination.exists():
        return FileOperationResult(success=False, message=f"Destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return FileOperationResult(
        success=True,
        message="Path moved.",
        source_path=str(source),
        destination_path=str(destination),
    )


def copy_path(source_path: str, destination_path: str) -> FileOperationResult:
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    if not source.exists():
        return FileOperationResult(success=False, message=f"Source does not exist: {source}")
    if destination.exists():
        return FileOperationResult(success=False, message=f"Destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return FileOperationResult(
        success=True,
        message="Path copied.",
        source_path=str(source),
        destination_path=str(destination),
    )


def delete_path(target_path: str) -> FileOperationResult:
    target = Path(target_path).expanduser().resolve()
    if not target.exists():
        return FileOperationResult(success=False, message=f"Path does not exist: {target}")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return FileOperationResult(success=True, message="Path deleted.", source_path=str(target))


def duplicate_path(source_path: str) -> FileOperationResult:
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        return FileOperationResult(success=False, message=f"Source does not exist: {source}")
    destination = _next_duplicate_path(source)
    return copy_path(str(source), str(destination))


def _next_duplicate_path(source: Path) -> Path:
    base_name = source.name
    for suffix in range(1, 1000):
        candidate_name = f"{base_name}.copy{suffix}" if suffix > 1 else f"{base_name}.copy"
        candidate = source.parent / candidate_name
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to allocate duplicate name for {source}")
