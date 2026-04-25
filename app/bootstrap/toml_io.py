"""Single TOML reader used by project and Python tooling config."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

try:  # Python 3.11+
    import tomllib as _toml_module
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.9 runtimes
    try:
        import tomli as _toml_module  # type: ignore[import-not-found]
    except ModuleNotFoundError:  # pragma: no cover - no TOML parser available
        _toml_module = None


class TomlReadError(ValueError):
    """Raised when TOML exists but cannot be parsed into an object mapping."""


class TomlParserUnavailableError(TomlReadError):
    """Raised when neither tomllib nor tomli is available."""


def read_toml_mapping(path: str | Path) -> dict[str, Any]:
    """Read TOML from *path* and return a mutable object mapping."""
    parser = _toml_module
    if parser is None:
        raise TomlParserUnavailableError("No TOML parser is available.")
    target = Path(path).expanduser().resolve()
    toml_decode_error = getattr(parser, "TOMLDecodeError", ValueError)
    try:
        payload = parser.loads(target.read_text(encoding="utf-8"))
    except (OSError, toml_decode_error) as exc:
        raise TomlReadError(str(exc)) from exc
    if not isinstance(payload, Mapping):
        raise TomlReadError("TOML document root must be a table.")
    return dict(payload)
