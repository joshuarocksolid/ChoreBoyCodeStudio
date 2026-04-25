"""Project-local configuration resolution for Python tooling."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.bootstrap.toml_io import read_toml_mapping
from app.bootstrap.vendor_paths import ensure_vendor_path_on_sys_path
from app.python_tools.models import (
    PYTHON_TOOLING_CONFIG_SOURCE_DEFAULTS,
    PYTHON_TOOLING_CONFIG_SOURCE_PROJECT_PYPROJECT,
    PythonToolingSettings,
)

DEFAULT_PYTHON_TARGET_MINOR = 39
DEFAULT_BLACK_LINE_LENGTH = 88
SUPPORTED_PYTHON_TARGET_MINORS: tuple[int, ...] = (39, 310, 311, 312, 313, 314)


def resolve_python_tooling_settings(*, project_root: str, file_path: str) -> PythonToolingSettings:
    """Resolve project-local Python formatting/import settings."""
    ensure_vendor_path_on_sys_path()
    project_root_path = Path(project_root).expanduser().resolve()
    file_path_path = Path(file_path).expanduser().resolve()
    pyproject_path = project_root_path / "pyproject.toml"

    config_source = PYTHON_TOOLING_CONFIG_SOURCE_DEFAULTS
    config_error: str | None = None
    pyproject_payload: dict[str, Any] = {}

    if pyproject_path.exists() and pyproject_path.is_file():
        config_source = PYTHON_TOOLING_CONFIG_SOURCE_PROJECT_PYPROJECT
        try:
            pyproject_payload = _load_toml_payload(pyproject_path)
        except Exception as exc:  # pragma: no cover - defensive guard
            config_error = str(exc)

    tool_section = pyproject_payload.get("tool", {}) if isinstance(pyproject_payload.get("tool", {}), dict) else {}
    black_section = tool_section.get("black", {}) if isinstance(tool_section.get("black", {}), dict) else {}
    isort_section = tool_section.get("isort", {}) if isinstance(tool_section.get("isort", {}), dict) else {}

    black_target_versions = _resolve_black_target_versions(pyproject_payload=pyproject_payload, black_section=black_section)
    python_target_minor = _resolve_python_target_minor(black_target_versions)
    black_line_length = _coerce_int(
        black_section.get("line-length"),
        default=DEFAULT_BLACK_LINE_LENGTH,
        minimum=1,
    )
    isort_line_length = _coerce_int(
        isort_section.get("line_length"),
        default=black_line_length,
        minimum=1,
    )

    return PythonToolingSettings(
        project_root=project_root_path,
        file_path=file_path_path,
        pyproject_path=pyproject_path if pyproject_path.is_file() else None,
        config_source=config_source,
        config_error=config_error,
        python_target_minor=python_target_minor,
        black_line_length=black_line_length,
        black_target_versions=black_target_versions,
        black_string_normalization=not _coerce_bool(black_section.get("skip-string-normalization"), default=False),
        black_magic_trailing_comma=not _coerce_bool(black_section.get("skip-magic-trailing-comma"), default=False),
        black_preview=_coerce_bool(black_section.get("preview"), default=False),
        isort_profile=_coerce_str(isort_section.get("profile"), default="black"),
        isort_line_length=isort_line_length,
        isort_src_paths=_resolve_src_paths(project_root_path, isort_section.get("src_paths")),
        isort_known_first_party=_coerce_str_tuple(isort_section.get("known_first_party")),
    )


def _load_toml_payload(path: Path) -> dict[str, Any]:
    return read_toml_mapping(path)


def _resolve_black_target_versions(*, pyproject_payload: dict[str, Any], black_section: dict[str, Any]) -> tuple[str, ...]:
    explicit = _normalize_target_versions(black_section.get("target-version"))
    if explicit:
        return explicit

    project_section = pyproject_payload.get("project", {})
    requires_python = project_section.get("requires-python") if isinstance(project_section, dict) else None
    if isinstance(requires_python, str) and requires_python.strip():
        inferred = _infer_target_versions_from_requires_python(requires_python.strip())
        if inferred:
            return inferred
    return ("py39",)


def _infer_target_versions_from_requires_python(requires_python: str) -> tuple[str, ...]:
    try:
        from packaging.specifiers import InvalidSpecifier, SpecifierSet
        from packaging.version import Version
    except Exception:  # pragma: no cover - vendored dependency missing
        return ("py39",)

    try:
        specifier = SpecifierSet(requires_python)
    except InvalidSpecifier:
        return ("py39",)

    supported: list[str] = []
    for minor in SUPPORTED_PYTHON_TARGET_MINORS:
        version_text = _minor_to_version_text(minor)
        if Version(version_text) in specifier:
            supported.append(f"py{minor}")
    return tuple(supported) or ("py39",)


def _resolve_python_target_minor(target_versions: tuple[str, ...]) -> int:
    if not target_versions:
        return DEFAULT_PYTHON_TARGET_MINOR
    parsed: list[int] = []
    for target_version in target_versions:
        if not target_version.startswith("py"):
            continue
        suffix = target_version[2:]
        if suffix.isdigit():
            parsed.append(int(suffix))
    return min(parsed) if parsed else DEFAULT_PYTHON_TARGET_MINOR


def _resolve_src_paths(project_root: Path, raw_value: Any) -> tuple[Path, ...]:
    resolved: list[Path] = []
    values = raw_value if isinstance(raw_value, list) else []
    for entry in values:
        if not isinstance(entry, str):
            continue
        stripped = entry.strip()
        if not stripped:
            continue
        resolved.append((project_root / stripped).resolve())
    if resolved:
        return tuple(resolved)
    default_src = project_root / "src"
    if default_src.is_dir():
        return (default_src.resolve(),)
    return tuple()


def _normalize_target_versions(raw_value: Any) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        return tuple()
    normalized: list[str] = []
    for value in raw_value:
        if not isinstance(value, str):
            continue
        stripped = value.strip().lower()
        if stripped.startswith("py") and stripped[2:].isdigit():
            normalized.append(stripped)
    return tuple(normalized)


def _coerce_int(value: Any, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _coerce_str(value: Any, *, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return tuple()
    normalized: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        stripped = entry.strip()
        if stripped:
            normalized.append(stripped)
    return tuple(normalized)


def _minor_to_version_text(minor: int) -> str:
    if minor >= 100:
        return f"3.{minor - 300 if minor >= 300 else minor - 30}"
    return f"3.{minor - 30}"
