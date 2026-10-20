from __future__ import annotations

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
    source: str = ""
    version: str = ""


_RUNTIME_INITIALIZED = False
_RUNTIME_STATUS = TreeSitterRuntimeStatus(False, "not_initialized")
_RUNTIME_TRACEBACK: str | None = None
_TREE_SITTER_MODULE: ModuleType | None = None
_LANGUAGE_MODULES: dict[str, ModuleType] = {}
_OPEN_FDS: list[int] = []
_SOURCE_ENV = "CBCS_TREE_SITTER_SOURCE"
_MIN_RUNTIME_VERSION = (0, 22)


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
        vendor_roots = _vendor_roots(vendor_root)
        source_kind = _requested_source_kind()
        if source_kind != "vendored" and _candidate_runtime_origins(vendor_roots):
            try:
                _initialize_from_runtime(vendor_roots)
            except Exception:
                if source_kind == "runtime":
                    raise
                _initialize_from_vendor(vendor_root)
        else:
            if source_kind == "runtime":
                raise RuntimeError(
                    f"{_SOURCE_ENV}=runtime but no tree-sitter >= 0.22 is importable "
                    "outside the CBCS vendor directory"
                )
            _initialize_from_vendor(vendor_root)
        _RUNTIME_TRACEBACK = None
    except Exception as exc:
        _TREE_SITTER_MODULE = None
        _LANGUAGE_MODULES = {}
        _RUNTIME_STATUS = TreeSitterRuntimeStatus(False, f"{exc.__class__.__name__}: {exc}")
        _RUNTIME_TRACEBACK = traceback.format_exc()
    _RUNTIME_INITIALIZED = True
    return _RUNTIME_STATUS


def _requested_source_kind() -> str:
    raw = os.environ.get(_SOURCE_ENV, "").strip().lower()
    if raw in ("", "auto"):
        return "auto"
    if raw in ("runtime", "vendored"):
        return raw
    raise RuntimeError(f"{_SOURCE_ENV} must be runtime or vendored, got {raw!r}")


def _vendor_roots(vendor_root: Path) -> tuple[Path, ...]:
    roots = [vendor_root]
    from app.bootstrap.vendor_paths import resolve_vendor_root

    repo_vendor = resolve_vendor_root()
    if repo_vendor not in roots:
        roots.append(repo_vendor)
    return tuple(roots)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _is_treesitter_module_name(name: str) -> bool:
    return name == "tree_sitter" or name.startswith("tree_sitter.") or name.startswith("tree_sitter_")


def _candidate_runtime_origins(vendor_roots: tuple[Path, ...]) -> list[Path]:
    origins: list[Path] = []
    seen: set[str] = set()
    for entry in sys.path:
        if not entry:
            continue
        entry_path = Path(entry)
        if any(_is_under(entry_path, root) for root in vendor_roots):
            continue
        init_path = entry_path / "tree_sitter" / "__init__.py"
        if not init_path.is_file():
            continue
        key = str(init_path.resolve())
        if key in seen:
            continue
        seen.add(key)
        origins.append(entry_path)
    return origins


def _parse_version(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in text.split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _installed_version(module: ModuleType) -> str:
    explicit = getattr(module, "__version__", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str) or not origin:
        return ""
    search_root = Path(origin).resolve().parent.parent
    module_name = module.__name__.split(".")[0]
    best_key: tuple[int, ...] = ()
    best_text = ""
    for dist in search_root.glob(f"{module_name}-*.dist-info"):
        record_path = dist / "RECORD"
        if record_path.is_file():
            record = record_path.read_text(encoding="utf-8", errors="replace")
            if f"{module_name}/" not in record:
                continue
        metadata_path = dist / "METADATA"
        if not metadata_path.is_file():
            continue
        found = ""
        for line in metadata_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Version:"):
                found = line.split(":", 1)[1].strip()
                break
        parsed = _parse_version(found)
        if parsed >= best_key and found:
            best_key = parsed
            best_text = found
    return best_text


def _pop_treesitter_modules_under(vendor_roots: tuple[Path, ...]) -> dict[str, ModuleType]:
    displaced: dict[str, ModuleType] = {}
    for name, module in list(sys.modules.items()):
        if not _is_treesitter_module_name(name):
            continue
        origin = getattr(module, "__file__", None)
        if not isinstance(origin, str) or not origin:
            continue
        if any(_is_under(Path(origin), root) for root in vendor_roots):
            displaced[name] = sys.modules.pop(name)
    return displaced


def _drop_treesitter_modules() -> None:
    for name in list(sys.modules):
        if _is_treesitter_module_name(name):
            sys.modules.pop(name, None)


def _path_for_runtime(saved: list[str], vendor_roots: tuple[Path, ...], origin: Path) -> list[str]:
    rest: list[str] = []
    for entry in saved:
        if not entry:
            rest.append(entry)
            continue
        entry_path = Path(entry)
        if any(_is_under(entry_path, root) for root in vendor_roots):
            continue
        if entry_path.resolve() == origin.resolve():
            continue
        rest.append(entry)
    return [str(origin), *rest]


def _demote_vendor_paths(saved: list[str], vendor_roots: tuple[Path, ...], origin: Path) -> None:
    kept: list[str] = []
    vendors: list[str] = []
    origin_resolved = origin.resolve()
    origin_present = False
    for entry in saved:
        if not entry:
            kept.append(entry)
            continue
        entry_path = Path(entry)
        if any(_is_under(entry_path, root) for root in vendor_roots):
            vendors.append(entry)
            continue
        if entry_path.resolve() == origin_resolved:
            origin_present = True
        kept.append(entry)
    if not origin_present:
        kept.insert(0, str(origin))
    sys.path[:] = [*kept, *vendors]


def _require_compatible_language(core: ModuleType, spec: TreeSitterLanguageSpec, language_fn: object) -> None:
    language_class = getattr(core, "Language", None)
    if not callable(language_class):
        raise RuntimeError("runtime tree_sitter does not export Language")
    if not callable(language_fn):
        raise RuntimeError(f"grammar '{spec.key}' language callable is not callable")
    handle = language_fn()
    try:
        try:
            language = language_class(handle, spec.language_name)
        except TypeError:
            language = language_class(handle)
    except Exception as exc:
        raise RuntimeError(
            f"grammar '{spec.key}' is outside the runtime tree-sitter language ABI range"
        ) from exc
    minimum = getattr(core, "MIN_COMPATIBLE_LANGUAGE_VERSION", None)
    maximum = getattr(core, "LANGUAGE_VERSION", None)
    grammar_version = getattr(language, "version", None)
    if (
        isinstance(grammar_version, int)
        and isinstance(minimum, int)
        and isinstance(maximum, int)
        and not minimum <= grammar_version <= maximum
    ):
        raise RuntimeError(
            f"grammar '{spec.key}' language version {grammar_version} "
            f"is outside {minimum}..{maximum}"
        )


def _load_runtime_language_modules(
    core: ModuleType,
    vendor_roots: tuple[Path, ...],
) -> tuple[dict[str, ModuleType], list[str], list[str]]:
    loaded: dict[str, ModuleType] = {}
    missing_default: list[str] = []
    skipped_optional: list[str] = []
    for spec in LANGUAGE_SPECS:
        try:
            module = importlib.import_module(spec.package_name)
        except ImportError:
            if spec.included_by_default:
                missing_default.append(spec.key)
            continue
        origin = getattr(module, "__file__", "") or ""
        if origin and any(_is_under(Path(origin), root) for root in vendor_roots):
            raise RuntimeError(
                f"runtime tree-sitter refused vendored grammar '{spec.key}' from {origin}"
            )
        language_fn = getattr(module, spec.language_callable_name, None)
        if not callable(language_fn):
            if spec.included_by_default:
                raise RuntimeError(
                    f"{spec.package_name} does not export a callable {spec.language_callable_name}()"
                )
            skipped_optional.append(spec.key)
            continue
        try:
            _require_compatible_language(core, spec, language_fn)
        except Exception:
            if spec.included_by_default:
                raise
            skipped_optional.append(spec.key)
            continue
        loaded[spec.key] = module
    return loaded, missing_default, skipped_optional


def _initialize_from_runtime(vendor_roots: tuple[Path, ...]) -> None:
    global _TREE_SITTER_MODULE, _LANGUAGE_MODULES, _RUNTIME_STATUS
    origins = _candidate_runtime_origins(vendor_roots)
    rejections: list[str] = []
    for origin in origins:
        displaced = _pop_treesitter_modules_under(vendor_roots)
        saved_path = sys.path[:]
        try:
            sys.path[:] = _path_for_runtime(saved_path, vendor_roots, origin)
            module = importlib.import_module("tree_sitter")
            version = _installed_version(module)
            file_name = getattr(module, "__file__", "") or ""
            if not file_name or any(_is_under(Path(file_name), root) for root in vendor_roots):
                raise RuntimeError("tree_sitter import resolved inside the CBCS vendor directory")
            if _parse_version(version) < _MIN_RUNTIME_VERSION:
                raise RuntimeError(f"tree-sitter {version or 'unknown'} at {origin} is below 0.22")
            loaded, missing, skipped = _load_runtime_language_modules(module, vendor_roots)
            if not loaded:
                raise FileNotFoundError(
                    f"no runtime tree-sitter language packages found under {origin}"
                )
            _demote_vendor_paths(saved_path, vendor_roots, origin)
            _publish_status(
                source="runtime",
                version=version,
                binding_name=f"runtime {version}",
                loaded=loaded,
                missing=missing,
                skipped=skipped,
            )
            _TREE_SITTER_MODULE = module
            return
        except Exception as exc:
            rejections.append(f"{origin}: {exc}")
            _drop_treesitter_modules()
            sys.modules.update(displaced)
            sys.path[:] = saved_path
    detail = "; ".join(rejections) if rejections else "no runtime tree-sitter package was found"
    raise RuntimeError(detail)


def _initialize_from_vendor(vendor_root: Path) -> None:
    global _TREE_SITTER_MODULE, _LANGUAGE_MODULES
    tree_sitter_dir = vendor_root / "tree_sitter"
    binding_path = _resolve_binding_path(tree_sitter_dir)

    if not binding_path.exists():
        raise FileNotFoundError(f"missing tree-sitter binding shared object at {binding_path}")

    _move_vendor_to_front(vendor_root)
    _drop_treesitter_modules_outside(_vendor_roots(vendor_root))

    _load_extension_module("tree_sitter._binding", binding_path, "tree_sitter_binding")
    module = importlib.import_module("tree_sitter")
    loaded_language_modules: dict[str, ModuleType] = {}
    missing_default_languages: list[str] = []
    skipped_optional_languages: list[str] = []
    for spec in LANGUAGE_SPECS:
        try:
            language = _load_language_module(spec, vendor_root)
        except Exception as exc:
            if spec.included_by_default:
                raise RuntimeError(
                    f"failed to load bundled tree-sitter grammar '{spec.key}' from {spec.package_name}: {exc}"
                ) from exc
            skipped_optional_languages.append(spec.key)
            continue
        if language is None:
            if spec.included_by_default:
                missing_default_languages.append(spec.key)
            continue
        loaded_language_modules[spec.key] = language
    if not loaded_language_modules:
        raise FileNotFoundError(
            f"no curated tree-sitter language packages found under {vendor_root}"
        )
    _TREE_SITTER_MODULE = module
    _publish_status(
        source="vendored",
        version=_installed_version(module),
        binding_name=binding_path.name,
        loaded=loaded_language_modules,
        missing=missing_default_languages,
        skipped=skipped_optional_languages,
    )


def _move_vendor_to_front(vendor_root: Path) -> None:
    vendor_root_str = str(vendor_root)
    if vendor_root_str in sys.path:
        sys.path.remove(vendor_root_str)
    sys.path.insert(0, vendor_root_str)


def _drop_treesitter_modules_outside(vendor_roots: tuple[Path, ...]) -> None:
    for name, module in list(sys.modules.items()):
        if not _is_treesitter_module_name(name):
            continue
        origin = getattr(module, "__file__", None)
        if not isinstance(origin, str) or not origin:
            continue
        if not any(_is_under(Path(origin), root) for root in vendor_roots):
            sys.modules.pop(name, None)


def _publish_status(
    *,
    source: str,
    version: str,
    binding_name: str,
    loaded: dict[str, ModuleType],
    missing: list[str],
    skipped: list[str],
) -> None:
    global _LANGUAGE_MODULES, _RUNTIME_STATUS
    _LANGUAGE_MODULES = loaded
    available_keys = tuple(sorted(loaded))
    missing_keys = tuple(sorted(missing))
    skipped_keys = tuple(sorted(skipped))
    message = _build_runtime_message(
        binding_name=binding_name,
        available_language_keys=available_keys,
        missing_default_language_keys=missing_keys,
        skipped_optional_language_keys=skipped_keys,
    )
    _RUNTIME_STATUS = TreeSitterRuntimeStatus(
        True,
        f"{message}; source={source}; version={version}",
        available_language_keys=available_keys,
        missing_default_language_keys=missing_keys,
        skipped_optional_language_keys=skipped_keys,
        source=source,
        version=version,
    )


def _resolve_binding_path(tree_sitter_dir: Path) -> Path:
    return _resolve_extension_path(tree_sitter_dir, preferred_stem="_binding")


def _current_soabi() -> str:
    soabi = sysconfig.get_config_var("SOABI")
    if not isinstance(soabi, str) or not soabi.strip():
        raise RuntimeError("Python runtime did not report SOABI; cannot resolve tree-sitter extension exactly.")
    return soabi.strip()


def _expected_extension_names(package_dir: Path, *, preferred_stem: str) -> tuple[str, ...]:
    if package_dir.name == "tree_sitter":
        return (f"{preferred_stem}.{_current_soabi()}.so",)
    return (f"{preferred_stem}.abi3.so",)


def _resolve_extension_path(package_dir: Path, *, preferred_stem: str) -> Path:
    expected_names = _expected_extension_names(package_dir, preferred_stem=preferred_stem)
    expected_name = expected_names[0]
    expected_path = package_dir / expected_name
    candidates = sorted(package_dir.glob(f"{preferred_stem}*.so"))
    if not candidates:
        return expected_path
    candidate_names = tuple(candidate.name for candidate in candidates)
    if candidate_names == expected_names:
        return expected_path
    if any(name in candidate_names for name in expected_names):
        raise RuntimeError(
            f"expected one exact binding artifact {expected_name} in {package_dir}, "
            f"found multiple candidates: {', '.join(candidate_names)}"
        )
    raise RuntimeError(
        f"expected binding artifact {expected_name} in {package_dir}, "
        f"found incompatible candidates: {', '.join(candidate_names)}"
    )


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
    """Call memfd_create via the canonical bootstrap shim."""
    if not hasattr(os, "memfd_create"):
        from app.bootstrap import memfd_shim

        memfd_shim.install()
    return os.memfd_create(name, flags)
