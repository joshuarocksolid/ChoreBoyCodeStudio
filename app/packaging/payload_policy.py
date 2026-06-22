"""Packaging payload copy vs audit policy (Project SSOT Wave 4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Union

from app.packaging.prune_rules import DEFAULT_PACKAGING_PRUNE_RULES
from app.project.file_inventory import iter_python_files, walk_project

PathInput = Union[str, Path]


@dataclass(frozen=True)
class PackagingPayloadPolicy:
    """Explicit rules for packaging copy vs static Python dependency audit.

    Product policy:

    - ``vendor/`` ships in the payload but top-level vendor Python is not
      statically audited (vendored code is assumed managed separately).
    - ``cbcs/`` metadata (``package.json``, ``project.json``, etc.) ships;
      ``cbcs/runs``, ``cbcs/logs``, and ``cbcs/cache`` are pruned from copy.
    - Hidden dot-paths, ``__pycache__``, and ``*.pyc`` / ``*.pyo`` never ship.
    """

    include_vendor: bool = True
    audit_vendor_python: bool = False
    include_cbcs_metadata: bool = True
    prune_cbcs_subtrees: tuple[str, ...] = ("runs", "logs", "cache")

    def is_payload_excluded(self, rel_path: Path) -> bool:
        """Return True when *rel_path* must not appear in the exported payload."""
        parts = rel_path.parts
        if any(DEFAULT_PACKAGING_PRUNE_RULES.is_path_part_excluded(part) for part in parts):
            return True
        posix_path = rel_path.as_posix()
        for subtree in self.prune_cbcs_subtrees:
            excluded_prefix = f"cbcs/{subtree}"
            if posix_path == excluded_prefix or posix_path.startswith(excluded_prefix + "/"):
                return True
        if DEFAULT_PACKAGING_PRUNE_RULES.should_prune_file_name(rel_path.name):
            return True
        return False

    def iter_payload_entries(self, project_root: PathInput) -> Iterator[Path]:
        """Yield absolute paths included in the packaging payload, sorted."""
        yield from iter_packaging_payload_entries(project_root, policy=self)

    def iter_audit_python_files(self, project_root: PathInput) -> Iterator[Path]:
        """Yield absolute ``.py`` files included in the static dependency audit."""
        root = Path(project_root).expanduser().resolve()
        extra_skips = () if self.audit_vendor_python else ("vendor",)
        for file_path in iter_python_files(root, extra_top_level_skips=extra_skips):
            rel_path = file_path.relative_to(root)
            if self.is_payload_excluded(rel_path):
                continue
            yield file_path


DEFAULT_PACKAGING_PAYLOAD_POLICY = PackagingPayloadPolicy()


def iter_packaging_payload_entries(
    project_root: PathInput,
    *,
    policy: PackagingPayloadPolicy | None = None,
) -> Iterator[Path]:
    """Yield absolute paths under *project_root* for packaging copy, sorted."""
    effective_policy = policy or DEFAULT_PACKAGING_PAYLOAD_POLICY
    root = Path(project_root).expanduser().resolve()
    collected: list[Path] = []

    for current_path, relative_dir, dir_names, file_names in walk_project(
        root,
        include_meta_dir=effective_policy.include_cbcs_metadata,
    ):
        retained_dirs: list[str] = []
        for name in dir_names:
            rel_path = Path(name) if not relative_dir else Path(relative_dir) / name
            if effective_policy.is_payload_excluded(rel_path):
                continue
            retained_dirs.append(name)
            collected.append(current_path / name)
        dir_names[:] = retained_dirs

        for name in file_names:
            rel_path = Path(name) if not relative_dir else Path(relative_dir) / name
            if effective_policy.is_payload_excluded(rel_path):
                continue
            collected.append(current_path / name)

    for path in sorted(collected, key=lambda item: item.relative_to(root).as_posix()):
        yield path
