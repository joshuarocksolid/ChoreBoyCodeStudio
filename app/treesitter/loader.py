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
from app.treesitter.language_specs import DEFAULT_LANGUAGE_KEYS, LANGUAGE_SPECS, OPTIONAL_LANGUAGE_KEYS, TreeSitterLanguageSpec


@dataclass(frozen=True)
class TreeSitterRuntimeStatus:
    is_available: bool
    message: str
    available_language_keys: tuple[str, ...] = ()
    missing_default_language_keys: tuple[str, ...] = ()
    skipped_optional_language_keys: tuple[str, ...] = ()


_RUNTIME_INITIALIZED = False
_RUNTIME_STATUS = TreeSitterRuntimeStatus(False, "not_initialized")
_RUNTIME_TRACEBACK: str | None = None
_TREE_SITTER_MODULE: ModuleType | None = None
_LANGUAGE_MODULES: dict[str, ModuleType] = {}
_OPEN_FDS: list[int] = []


def runtime_status() -> TreeSitterRuntimeStatus:
    return _RUNTIME_STATUS


def runtime_traceback() -> str | None:
    return _RUNTIME_TRACEBACK


def tree_sitter_module() -> ModuleType | None:
    return _TREE_SITTER_MODULE


def language_module(language_key: str) -> ModuleType | None:
    return _LANGUAGE_MODULES.get(language_key)


def available_language_keys() -> tuple[str, ...]:
    return tuple(sorted(_LANGUAGE_MODULES))


def initialize_tree_sitter_runtime(app_root: Path | None = None) -> TreeSitterRuntimeStatus:
    global _RUNTIME_INITIALIZED, _RUNTIME_STATUS, _RUNTIME_TRACEBACK, _TREE_SITTER_MODULE, _LANGUAGE_MODULES
    if _RUNTIME_INITIALIZED:
        return _RUNTIME_STATUS
    try:
        root = app_root if app_root is not None else resolve_app_root()
        vendor_root = root / "vendor"
        tree_sitter_dir = vendor_root / "tree_sitter"
        binding_path = _resolve_binding_path(tree_sitter_dir)

        if not binding_path.exists():
            raise FileNotFoundError(f"missing tree-sitter binding shared object at {binding_path}")

        vendor_root_str = str(vendor_root)
        if vendor_root_str not in sys.path:
            sys.path.insert(0, vendor_root_str)

        _load_extension_module("tree_sitter._binding", binding_path, "tree_sitter_binding")
        _TREE_SITTER_MODULE = importlib.import_module("tree_sitter")
        loaded_language_modules: dict[str, ModuleType] = {}
        missing_default_languages: list[str] = []
        skipped_optional_languages: list[str] = []
        for spec in LANGUAGE_SPECS:
            try:
                module = _load_language_module(spec, vendor_root)
            except Exception as exc:
                if spec.included_by_default:
                    raise RuntimeError(
                        f"failed to load bundled tree-sitter grammar '{spec.key}' from {spec.package_name}: {exc}"
                    ) from exc
                skipped_optional_languages.append(spec.key)
                continue
            if module is None:
                if spec.included_by_default:
                    missing_default_languages.append(spec.key)
                continue
            loaded_language_modules[spec.key] = module
        if not loaded_language_modules:
            raise FileNotFoundError(
                f"no curated tree-sitter language packages found under {vendor_root}"
            )
        _LANGUAGE_MODULES = loaded_language_modules
        available_keys = tuple(sorted(loaded_language_modules))
        missing_default_keys = tuple(sorted(missing_default_languages))
        skipped_optional_keys = tuple(sorted(skipped_optional_languages))
        _RUNTIME_STATUS = TreeSitterRuntimeStatus(
            True,
            _build_runtime_message(
                binding_name=binding_path.name,
                available_language_keys=available_keys,
                missing_default_language_keys=missing_default_keys,
                skipped_optional_language_keys=skipped_optional_keys,
            ),
            available_language_keys=available_keys,
            missing_default_language_keys=missing_default_keys,
            skipped_optional_language_keys=skipped_optional_keys,
        )
        _RUNTIME_TRACEBACK = None
    except Exception as exc:
        _TREE_SITTER_MODULE = None
        _LANGUAGE_MODULES = {}
        _RUNTIME_STATUS = TreeSitterRuntimeStatus(False, f"{exc.__class__.__name__}: {exc}")
        _RUNTIME_TRACEBACK = traceback.format_exc()
    _RUNTIME_INITIALIZED = True
    return _RUNTIME_STATUS


def _resolve_binding_path(tree_sitter_dir: Path) -> Path:
    return _resolve_extension_path(tree_sitter_dir, preferred_stem="_binding")


def _resolve_extension_path(package_dir: Path, *, preferred_stem: str) -> Path:
    candidates = sorted(package_dir.glob(f"{preferred_stem}*.so"))
    if not candidates:
        candidates = sorted(package_dir.glob("*.so"))
    soabi = sysconfig.get_config_var("SOABI")
    if soabi:
        preferred_name = f"{preferred_stem}.{soabi}.so"
        preferred_path = package_dir / preferred_name
        if preferred_path.exists():
            return preferred_path
    for candidate in candidates:
        if "cpython-39" in candidate.name:
            return candidate
    if candidates:
        return candidates[0]
    return package_dir / f"{preferred_stem}.cpython-39-x86_64-linux-gnu.so"


def _load_language_module(spec: TreeSitterLanguageSpec, vendor_root: Path) -> ModuleType | None:
    package_dir = vendor_root / spec.package_name
    if not package_dir.is_dir():
        return None
    binding_path = _resolve_extension_path(package_dir, preferred_stem="_binding")
    if not binding_path.exists():
        raise FileNotFoundError(f"missing grammar binding shared object at {binding_path}")
    _load_extension_module(
        f"{spec.package_name}._binding",
        binding_path,
        f"{spec.package_name}_binding",
    )
    module = importlib.import_module(spec.package_name)
    if not callable(getattr(module, spec.language_callable_name, None)):
        raise AttributeError(
            f"{spec.package_name} does not export a callable {spec.language_callable_name}()"
        )
    return module


def _build_runtime_message(
    *,
    binding_name: str,
    available_language_keys: tuple[str, ...],
    missing_default_language_keys: tuple[str, ...],
    skipped_optional_language_keys: tuple[str, ...],
) -> str:
    default_loaded = [key for key in available_language_keys if key in DEFAULT_LANGUAGE_KEYS]
    optional_loaded = [key for key in available_language_keys if key in OPTIONAL_LANGUAGE_KEYS]
    parts = [
        (
            f"ready ({binding_name}; "
            f"{len(default_loaded)}/{len(DEFAULT_LANGUAGE_KEYS)} bundled grammars loaded)"
        )
    ]
    if missing_default_language_keys:
        parts.append(f"missing bundled: {', '.join(missing_default_language_keys)}")
    if optional_loaded:
        parts.append(f"optional installed: {', '.join(optional_loaded)}")
    if skipped_optional_language_keys:
        parts.append(f"optional skipped: {', '.join(skipped_optional_language_keys)}")
    return "; ".join(parts)


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
