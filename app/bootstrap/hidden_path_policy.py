"""Per-parent hidden-path support probe. Evidence and policy: docs/DISCOVERY.md section 4A."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Union

PathInput = Union[str, Path]

_CANARY_BYTES = b"cbcs probe\n"


@dataclass(frozen=True)
class HiddenPathProbeResult:
    parent: Path
    hidden_file_ok: bool
    hidden_dir_ok: bool
    visible_dir_ok: bool
    errors: tuple[str, ...]


_PROBE_CACHE: dict[Path, HiddenPathProbeResult] = {}


def normalize_state_root_identity(path: PathInput) -> Path:
    """Return an absolute path without following the final symlink hop."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValueError("state_root must be an absolute path")
    return Path(os.path.abspath(str(candidate)))


def probe_hidden_path_support(parent: PathInput) -> HiddenPathProbeResult:
    """Return the per-parent probe result, running the canaries once per process."""
    identity = normalize_state_root_identity(parent)
    cached = _PROBE_CACHE.get(identity)
    if cached is None:
        cached = _probe(identity)
        _PROBE_CACHE[identity] = cached
    return cached


def clear_hidden_path_probe_cache() -> None:
    _PROBE_CACHE.clear()


def _probe(parent: Path) -> HiddenPathProbeResult:
    if not _is_directory(parent):
        return HiddenPathProbeResult(
            parent=parent,
            hidden_file_ok=False,
            hidden_dir_ok=False,
            visible_dir_ok=False,
            errors=(f"parent is not a directory: {parent}",),
        )
    pid = os.getpid()
    errors: list[str] = []
    return HiddenPathProbeResult(
        parent=parent,
        hidden_file_ok=_probe_file(parent / f".cbcs_probe_file.{pid}", errors),
        hidden_dir_ok=_probe_dir(parent / f".cbcs_probe_dir.{pid}", errors),
        visible_dir_ok=_probe_dir(parent / f"cbcs_probe_visible_dir.{pid}", errors),
        errors=tuple(errors),
    )


def _probe_file(canary: Path, errors: list[str]) -> bool:
    try:
        canary.write_bytes(_CANARY_BYTES)
        readback = canary.read_bytes()
        canary.unlink()
    except OSError as exc:
        errors.append(_describe(canary, exc))
        return False
    finally:
        _remove_quietly(canary)
    if readback != _CANARY_BYTES:
        errors.append(f"{canary.name}: read back mismatch")
        return False
    return True


def _probe_dir(canary: Path, errors: list[str]) -> bool:
    inner = canary / "probe"
    try:
        canary.mkdir(exist_ok=True)
        inner.write_bytes(_CANARY_BYTES)
        inner.unlink()
        canary.rmdir()
    except OSError as exc:
        errors.append(_describe(canary, exc))
        return False
    finally:
        _remove_quietly(inner)
        _remove_quietly(canary)
    return True


def _describe(canary: Path, exc: OSError) -> str:
    return f"{canary.name}: {exc.__class__.__name__}: {exc}"


def _is_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _remove_quietly(path: Path) -> None:
    try:
        if path.is_dir():
            path.rmdir()
        else:
            path.unlink()
    except OSError:
        pass
