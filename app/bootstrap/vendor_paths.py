"""Helpers for vendored dependency import paths."""
from __future__ import annotations

from pathlib import Path
import sys

from app.bootstrap.paths import ensure_directory, resolve_app_root


def resolve_vendor_root(app_root: Path | None = None) -> Path:
    """Return the repository vendor directory."""
    root = app_root if app_root is not None else resolve_app_root()
    return root / "vendor"


def ensure_vendor_path_on_sys_path(app_root: Path | None = None) -> Path:
    """Insert the vendor directory on ``sys.path`` if missing."""
    vendor_root = resolve_vendor_root(app_root)
    vendor_root_text = str(vendor_root)
    if vendor_root_text not in sys.path:
        sys.path.insert(0, vendor_root_text)
    return vendor_root


def ensure_vendor_subdir(name: str, app_root: Path | None = None) -> Path:
    """Return and create a named directory under ``vendor/``."""
    return ensure_directory(resolve_vendor_root(app_root) / name)
