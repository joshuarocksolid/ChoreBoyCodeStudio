"""Cached Jedi project instances keyed by project root and source layout."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def get_project(
    project_cache: dict[tuple[str, tuple[str, ...]], Any],
    project_root: str,
) -> Any:
    """Return a cached Jedi project for the given root, creating one if needed."""
    from app.bootstrap.paths import project_manifest_path
    from app.project.import_layout import resolve_project_import_layout
    from app.project.project_manifest import load_project_manifest

    normalized_root = str(Path(project_root).expanduser().resolve())
    root = Path(normalized_root)
    metadata = None
    manifest_path = project_manifest_path(root)
    if manifest_path.is_file():
        try:
            metadata = load_project_manifest(manifest_path)
        except Exception:
            metadata = None
    layout = resolve_project_import_layout(root, metadata)
    cache_key = (normalized_root, tuple(str(path) for path in layout.source_roots))
    cached = project_cache.get(cache_key)
    if cached is not None:
        return cached

    import jedi

    project = jedi.Project(
        normalized_root,
        added_sys_path=layout.jedi_added_sys_path,
        load_unsafe_extensions=False,
        smart_sys_path=True,
    )
    project_cache[cache_key] = project
    return project


def invalidate_project_cache(
    project_cache: dict[tuple[str, tuple[str, ...]], Any],
    project_root: str | None = None,
) -> None:
    """Clear cached Jedi project(s) so the next query rebuilds paths."""
    if project_root is not None:
        normalized = str(Path(project_root).expanduser().resolve())
        keys_to_remove = [key for key in project_cache if key[0] == normalized]
        for key in keys_to_remove:
            project_cache.pop(key, None)
    else:
        project_cache.clear()
