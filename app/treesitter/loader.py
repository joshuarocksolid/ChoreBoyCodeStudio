from __future__ import annotations

import ctypes
import importlib
import importlib.machinery
import importlib.util
import os
import sys
import sysconfig
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from app.bootstrap.paths import resolve_app_root


@dataclass(frozen=True)
class TreeSitterRuntimeStatus:
    is_available: bool
    message: str


_RUNTIME_INITIALIZED = False
_RUNTIME_STATUS = TreeSitterRuntimeStatus(False, "not_initialized")
_RUNTIME_TRACEBACK: str | None = None
_TREE_SITTER_MODULE: ModuleType | None = None
_LANGUAGES_LIBRARY: ctypes.CDLL | None = None
_OPEN_FDS: list[int] = []


def runtime_status() -> TreeSitterRuntimeStatus:
    return _RUNTIME_STATUS


def runtime_traceback() -> str | None:
    return _RUNTIME_TRACEBACK


def tree_sitter_module() -> ModuleType | None:
    return _TREE_SITTER_MODULE


def languages_library() -> ctypes.CDLL | None:
    return _LANGUAGES_LIBRARY


def initialize_tree_sitter_runtime(app_root: Path | None = None) -> TreeSitterRuntimeStatus:
    global _RUNTIME_INITIALIZED, _RUNTIME_STATUS, _RUNTIME_TRACEBACK, _TREE_SITTER_MODULE, _LANGUAGES_LIBRARY
    if _RUNTIME_INITIALIZED:
        return _RUNTIME_STATUS
    try:
        root = app_root if app_root is not None else resolve_app_root()
        vendor_root = root / "vendor"
        tree_sitter_dir = vendor_root / "tree_sitter"
        languages_dir = vendor_root / "tree_sitter_languages"
        binding_path = _resolve_binding_path(tree_sitter_dir)
        languages_path = languages_dir / "languages.so"

        if not binding_path.exists():
            raise FileNotFoundError(f"missing tree-sitter binding shared object at {binding_path}")
        if not languages_path.exists():
            raise FileNotFoundError(f"missing tree-sitter languages shared object at {languages_path}")

        vendor_root_str = str(vendor_root)
        if vendor_root_str not in sys.path:
            sys.path.insert(0, vendor_root_str)

        _load_extension_module("tree_sitter._binding", binding_path, "tree_sitter_binding")
        _TREE_SITTER_MODULE = importlib.import_module("tree_sitter")
        _LANGUAGES_LIBRARY = _load_shared_library(languages_path, "tree_sitter_languages")
        _RUNTIME_STATUS = TreeSitterRuntimeStatus(
            True,
            f"ready ({binding_path.name}, {languages_path.name})",
        )
        _RUNTIME_TRACEBACK = None
    except Exception as exc:
        _TREE_SITTER_MODULE = None
        _LANGUAGES_LIBRARY = None
        _RUNTIME_STATUS = TreeSitterRuntimeStatus(False, f"{exc.__class__.__name__}: {exc}")
        _RUNTIME_TRACEBACK = traceback.format_exc()
    _RUNTIME_INITIALIZED = True
    return _RUNTIME_STATUS


def _resolve_binding_path(tree_sitter_dir: Path) -> Path:
    candidates = sorted(tree_sitter_dir.glob("_binding*.so"))
    soabi = sysconfig.get_config_var("SOABI")
    if soabi:
        preferred_name = f"_binding.{soabi}.so"
        preferred_path = tree_sitter_dir / preferred_name
        if preferred_path.exists():
            return preferred_path
    for candidate in candidates:
        if "cpython-39" in candidate.name:
            return candidate
    if candidates:
        return candidates[0]
    return tree_sitter_dir / "_binding.cpython-39-x86_64-linux-gnu.so"


def _load_extension_module(module_name: str, shared_object_path: Path, label: str) -> ModuleType:
    memfd_path = _write_memfd(shared_object_path, label)
    loader = importlib.machinery.ExtensionFileLoader(module_name, memfd_path)
    spec = importlib.util.spec_from_loader(module_name, loader, origin=memfd_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to build extension spec for {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_shared_library(shared_object_path: Path, label: str) -> ctypes.CDLL:
    memfd_path = _write_memfd(shared_object_path, label)
    return ctypes.CDLL(memfd_path)


def _write_memfd(shared_object_path: Path, label: str) -> str:
    data = shared_object_path.read_bytes()
    fd = _memfd_create(label, 0)
    os.write(fd, data)
    os.lseek(fd, 0, os.SEEK_SET)
    _OPEN_FDS.append(fd)
    return f"/proc/self/fd/{fd}"


def _memfd_create(name: str, flags: int) -> int:
    """Call memfd_create, falling back to libc ctypes when os.memfd_create is missing."""
    if hasattr(os, "memfd_create"):
        return os.memfd_create(name, flags)
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.memfd_create.argtypes = [ctypes.c_char_p, ctypes.c_uint]
    libc.memfd_create.restype = ctypes.c_int
    fd = libc.memfd_create(name.encode("utf-8"), flags)
    if fd < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno), name)
    return fd
