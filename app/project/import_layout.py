"""Single source of truth for project import search paths (source roots)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TypeVar

from app.bootstrap.paths import PathInput, project_manifest_path
from app.bootstrap.toml_io import read_toml_mapping
from app.core import constants
from app.core.models import ProjectMetadata

_RESERVED_ROOT_NAMES = constants.RESERVED_PROJECT_TOP_LEVEL_NAMES

_T = TypeVar("_T")


def _ordered_unique(values: Sequence[_T], *, key: Callable[[_T], str]) -> tuple[_T, ...]:
    """Preserve order while deduplicating by a resolved string key."""
    seen: set[str] = set()
    ordered: list[_T] = []
    for value in values:
        normalized = key(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(value)
    return tuple(ordered)


@dataclass(frozen=True)
class ProjectImportLayout:
    """Resolved import search layout for one project."""

    project_root: Path
    source_roots: tuple[Path, ...]
    vendor_root: Path

    @property
    def import_search_bases(self) -> tuple[Path, ...]:
        """Ordered bases for module resolution: source roots, project root, vendor."""
        bases: list[Path] = list(self.source_roots)
        if self.project_root not in bases:
            bases.append(self.project_root)
        if self.vendor_root not in bases:
            bases.append(self.vendor_root)
        return tuple(bases)

    @property
    def runtime_sys_path_entries(self) -> tuple[str, ...]:
        """Paths to prepend for runner/Jedi (project root + source roots, no vendor duplicate)."""
        unique_paths = _ordered_unique(
            (self.project_root, *self.source_roots),
            key=lambda path: str(path.resolve()),
        )
        return tuple(str(path) for path in unique_paths)

    @property
    def jedi_added_sys_path(self) -> tuple[str, ...]:
        """Extra sys.path entries for Jedi (source roots + vendor)."""
        unique_paths = _ordered_unique(
            (*self.source_roots, self.vendor_root),
            key=lambda path: str(path.resolve()),
        )
        return tuple(str(path) for path in unique_paths)


def resolve_configured_src_paths(
    project_root: Path,
    raw_value: Any,
    *,
    auto_detect_src: bool = True,
) -> tuple[Path, ...]:
    """Resolve explicit src path entries from pyproject or manifest lists."""
    resolved: list[Path] = []
    values = raw_value if isinstance(raw_value, list) else []
    for entry in values:
        if not isinstance(entry, str):
            continue
        stripped = entry.strip()
        if not stripped:
            continue
        candidate = (project_root / stripped).resolve()
        if _is_valid_source_root_candidate(project_root, candidate):
            resolved.append(candidate)
    if resolved:
        return tuple(resolved)
    if not auto_detect_src:
        return tuple()
    return _auto_detect_src_root(project_root)


def _auto_detect_src_root(project_root: Path) -> tuple[Path, ...]:
    """Pylance-aligned: auto-add ``src/`` when it is a directory without ``__init__.py``."""
    default_src = project_root / "src"
    if not default_src.is_dir():
        return tuple()
    if (default_src / "__init__.py").is_file():
        return tuple()
    return (default_src.resolve(),)


def _is_valid_source_root_candidate(project_root: Path, candidate: Path) -> bool:
    if not candidate.is_dir():
        return False
    try:
        candidate.relative_to(project_root)
    except ValueError:
        return False
    if candidate == project_root:
        return False
    parts = candidate.relative_to(project_root).parts
    if not parts:
        return False
    if parts[0] in _RESERVED_ROOT_NAMES:
        return False
    return True


def normalize_source_root_entries(
    project_root: Path,
    entries: Sequence[str],
) -> tuple[str, ...]:
    """Normalize manifest ``source_roots`` to relative POSIX paths under project root."""
    normalized: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, str):
            continue
        stripped = entry.strip().replace("\\", "/").strip("/")
        if not stripped or stripped in seen:
            continue
        candidate = (project_root / stripped).resolve()
        if not _is_valid_source_root_candidate(project_root, candidate):
            continue
        relative = candidate.relative_to(project_root).as_posix()
        seen.add(relative)
        normalized.append(relative)
    return tuple(normalized)


def load_project_import_layout(project_root: PathInput) -> ProjectImportLayout:
    """Load manifest (when present) and resolve the canonical import layout."""
    from app.project.project_manifest import load_project_manifest

    root = Path(project_root).expanduser().resolve()
    metadata: ProjectMetadata | None = None
    manifest = project_manifest_path(root)
    if manifest.is_file():
        try:
            metadata = load_project_manifest(manifest)
        except Exception:
            metadata = None
    return resolve_project_import_layout(root, metadata)


def resolve_project_import_layout(
    project_root: PathInput,
    metadata: ProjectMetadata | None = None,
) -> ProjectImportLayout:
    """Build import layout using manifest, pyproject, then auto-detect precedence."""
    root = Path(project_root).expanduser().resolve()
    vendor_root = root / "vendor"

    if metadata is not None:
        configured = resolve_configured_src_paths(
            root,
            list(metadata.source_roots),
            auto_detect_src=False,
        )
        return ProjectImportLayout(project_root=root, source_roots=configured, vendor_root=vendor_root)

    pyproject_paths = _read_pyproject_src_paths(root)
    if pyproject_paths:
        return ProjectImportLayout(project_root=root, source_roots=pyproject_paths, vendor_root=vendor_root)

    auto_paths = _auto_detect_src_root(root)
    return ProjectImportLayout(project_root=root, source_roots=auto_paths, vendor_root=vendor_root)


def _read_pyproject_src_paths(project_root: Path) -> tuple[Path, ...]:
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.is_file():
        return tuple()
    try:
        payload = read_toml_mapping(pyproject_path)
    except Exception:
        return tuple()
    tool_section = payload.get("tool", {})
    if not isinstance(tool_section, dict):
        return tuple()
    isort_section = tool_section.get("isort", {})
    if not isinstance(isort_section, dict):
        return tuple()
    return resolve_configured_src_paths(
        project_root,
        isort_section.get("src_paths"),
        auto_detect_src=False,
    )


def module_name_for_file(layout: ProjectImportLayout, file_path: Path) -> str | None:
    """Return canonical import module name for a project ``.py`` file."""
    resolved_file = file_path.expanduser().resolve()
    try:
        relative = resolved_file.relative_to(layout.project_root).as_posix()
    except ValueError:
        return None
    return module_name_from_relative_path(layout, relative)


def module_name_from_relative_path(layout: ProjectImportLayout, relative_path: str) -> str | None:
    if not relative_path.endswith(".py"):
        return None
    module_path = relative_path[:-3]
    if module_path.endswith("/__init__"):
        module_path = module_path[: -len("/__init__")]
    module_path = module_path.strip("/")
    if not module_path:
        return None
    dotted = module_path.replace("/", ".")
    return _strip_source_root_prefix(layout, dotted)


def _strip_source_root_prefix(layout: ProjectImportLayout, dotted_module: str) -> str:
    for source_root in layout.source_roots:
        try:
            prefix = source_root.relative_to(layout.project_root).as_posix()
        except ValueError:
            continue
        if not prefix:
            continue
        prefix_dotted = prefix.replace("/", ".")
        if dotted_module == prefix_dotted:
            return ""
        if dotted_module.startswith(f"{prefix_dotted}."):
            stripped = dotted_module[len(prefix_dotted) + 1 :]
            return stripped if stripped else dotted_module
    return dotted_module


def discover_canonical_project_modules(
    layout: ProjectImportLayout,
    *,
    iter_python_files: Callable[[Path], Any] | None = None,
) -> set[str]:
    """Collect importable module names using canonical naming."""
    from app.project.file_inventory import iter_python_files as default_iter_python_files

    iterator = iter_python_files or default_iter_python_files
    discovered: set[str] = set()
    for file_path in iterator(layout.project_root):
        module_name = module_name_for_file(layout, Path(file_path))
        if module_name:
            discovered.add(module_name)
    return discovered


def module_path_prefix_exists(layout: ProjectImportLayout, module_name: str) -> bool:
    """Return True when any import search base has a prefix path for ``module_name``."""
    for base in layout.import_search_bases:
        if _module_path_prefix_exists_at_base(base, module_name):
            return True
    return False


def module_path_prefix_exists_at_base(base: Path, module_name: str) -> bool:
    if not base.exists():
        return False
    probe_base = base
    for part in [segment for segment in module_name.split(".") if segment.strip()]:
        if (probe_base / f"{part}.py").exists() or (probe_base / part).exists():
            return True
        probe_base = probe_base / part
    return False


def _module_path_prefix_exists_at_base(base: Path, module_name: str) -> bool:
    return module_path_prefix_exists_at_base(base, module_name)


def package_name_for_file(file_path: Path, *, layout: ProjectImportLayout) -> str | None:
    module_name = module_name_for_file(layout, file_path)
    if module_name is None:
        return None
    if file_path.name == "__init__.py":
        return module_name
    if "." not in module_name:
        return None
    return module_name.rsplit(".", 1)[0]


def resolve_import_from_module(
    file_path: Path,
    module: str | None,
    level: int,
    *,
    layout: ProjectImportLayout,
) -> str | None:
    if level <= 0:
        return module
    package_name = package_name_for_file(file_path, layout=layout)
    if package_name is None:
        return None
    try:
        from importlib.util import resolve_name

        relative_spec = module if module is not None else ""
        return resolve_name(relative_spec, package_name, level)
    except (ImportError, ValueError):
        return None


def resolve_import_at_base(base: Path, module_name: str) -> str | None:
    """Resolve module file or package init under one search base."""
    module_path = Path(*module_name.split("."))
    module_file = (base / module_path).with_suffix(".py")
    package_init = base / module_path / "__init__.py"
    if module_file.is_file():
        return str(module_file.resolve())
    if package_init.is_file():
        return str(package_init.resolve())
    package_dir = base / module_path
    if package_dir.is_dir() and not package_init.is_file():
        if any(package_dir.glob("*.py")):
            return str(package_dir.resolve())
    return None


def detect_suggested_source_root(project_root: PathInput) -> str | None:
    """Return a relative source-root path worth offering during project import."""
    layout = resolve_project_import_layout(project_root, metadata=None)
    if layout.source_roots:
        return layout.source_roots[0].relative_to(layout.project_root).as_posix()
    return None


def suggest_missing_source_root(layout: ProjectImportLayout, module_name: str) -> str | None:
    """If the module exists under a non-root child dir (e.g. ``src/``), return that dir as a source root."""
    configured = {path.resolve() for path in layout.source_roots}
    for child in sorted(layout.project_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name in _RESERVED_ROOT_NAMES:
            continue
        if child.resolve() in configured:
            continue
        if _module_path_prefix_exists_at_base(child, module_name):
            return child.relative_to(layout.project_root).as_posix()
    return None
