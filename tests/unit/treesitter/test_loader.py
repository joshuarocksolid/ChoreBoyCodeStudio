"""Unit tests for curated tree-sitter runtime loading."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import app.treesitter.loader as loader

pytestmark = pytest.mark.unit


def _reset_loader_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "_RUNTIME_INITIALIZED", False)
    monkeypatch.setattr(loader, "_RUNTIME_STATUS", loader.TreeSitterRuntimeStatus(False, "not_initialized"))
    monkeypatch.setattr(loader, "_RUNTIME_TRACEBACK", None)
    monkeypatch.setattr(loader, "_TREE_SITTER_MODULE", None)
    monkeypatch.setattr(loader, "_LANGUAGE_MODULES", {})


def _force_choreboy_soabi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "_current_soabi", lambda: "cpython-39-x86_64-linux-gnu")


def test_initialize_runtime_tracks_bundled_and_optional_languages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _reset_loader_state(monkeypatch)
    _force_choreboy_soabi(monkeypatch)
    monkeypatch.setenv("CBCS_TREE_SITTER_SOURCE", "vendored")
    tree_sitter_dir = tmp_path / "vendor" / "tree_sitter"
    tree_sitter_dir.mkdir(parents=True)
    (tree_sitter_dir / "_binding.cpython-39-x86_64-linux-gnu.so").write_bytes(b"core")

    fake_optional_spec = loader.TreeSitterLanguageSpec(
        key="fake_optional",
        display_name="Fake Optional",
        extensions=(".fake",),
        highlights_query_file="fake.scm",
        language_name="fake_optional",
        package_name="tree_sitter_fake_optional",
        included_by_default=False,
    )
    patched_specs = loader.LANGUAGE_SPECS + (fake_optional_spec,)
    monkeypatch.setattr(loader, "LANGUAGE_SPECS", patched_specs)

    def fake_load_extension_module(module_name: str, shared_object_path: Path, label: str) -> ModuleType:
        return ModuleType(module_name)

    def fake_import_module(module_name: str) -> ModuleType:
        if module_name == "tree_sitter":
            module = ModuleType("tree_sitter")
            # The fake language handle is the grammar's language ABI version.
            module.Language = lambda handle, name: SimpleNamespace(version=handle)  # type: ignore[attr-defined]
            module.LANGUAGE_VERSION = 14  # type: ignore[attr-defined]
            module.MIN_COMPATIBLE_LANGUAGE_VERSION = 13  # type: ignore[attr-defined]
            return module
        raise AssertionError(f"unexpected import {module_name}")

    def fake_load_language_module(spec, vendor_root: Path) -> ModuleType | None:
        if spec.key in {"python", "json", "sql"}:
            module = ModuleType(spec.package_name)
            # sql mimics tree-sitter-sql 0.3.9: ABI 15 against a 0.23 core (max 14).
            abi = 15 if spec.key == "sql" else 14
            module.language = lambda: abi  # type: ignore[attr-defined]
            return module
        if spec.key == "fake_optional":
            raise RuntimeError("broken optional package")
        return None

    monkeypatch.setattr(loader, "_load_extension_module", fake_load_extension_module)
    monkeypatch.setattr(loader.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(loader, "_load_language_module", fake_load_language_module)

    status = loader.initialize_tree_sitter_runtime(app_root=tmp_path)

    assert status.is_available is True
    assert status.available_language_keys == ("json", "python")
    assert status.missing_default_language_keys == tuple(
        sorted(set(loader.DEFAULT_LANGUAGE_KEYS) - {"json", "python", "sql"})
    )
    assert set(status.skipped_optional_language_keys) == {"fake_optional", "sql"}
    assert status.source == "vendored"
    assert f"2/{len(loader.DEFAULT_LANGUAGE_KEYS)} bundled grammars loaded" in status.message
    assert "optional skipped: " in status.message and "sql" in status.message


def test_load_language_module_requires_language_callable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _force_choreboy_soabi(monkeypatch)
    vendor_root = tmp_path / "vendor"
    package_dir = vendor_root / "tree_sitter_python"
    package_dir.mkdir(parents=True)
    (package_dir / "_binding.abi3.so").write_bytes(b"grammar")

    spec = next(spec for spec in loader.LANGUAGE_SPECS if spec.key == "python")

    monkeypatch.setattr(loader, "_load_extension_module", lambda *args, **kwargs: ModuleType("binding"))
    monkeypatch.setattr(loader.importlib, "import_module", lambda name: ModuleType(name))

    with pytest.raises(AttributeError, match="callable language"):
        loader._load_language_module(spec, vendor_root)


def test_runtime_message_reports_optional_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "OPTIONAL_LANGUAGE_KEYS", loader.OPTIONAL_LANGUAGE_KEYS + ("scheme",))
    message = loader._build_runtime_message(
        binding_name="_binding.cpython-39-x86_64-linux-gnu.so",
        available_language_keys=("bash", "python", "scheme", "toml"),
        missing_default_language_keys=("css",),
        skipped_optional_language_keys=(),
    )

    assert f"3/{len(loader.DEFAULT_LANGUAGE_KEYS)} bundled grammars loaded" in message
    assert "missing bundled: css" in message
    assert "optional installed: scheme" in message


def test_resolve_extension_path_rejects_wrong_soabi_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _force_choreboy_soabi(monkeypatch)
    package_dir = tmp_path / "tree_sitter"
    package_dir.mkdir(parents=True)
    (package_dir / "_binding.cpython-311-x86_64-linux-gnu.so").write_bytes(b"wrong")

    with pytest.raises(RuntimeError, match="expected binding artifact _binding.cpython-39-x86_64-linux-gnu.so"):
        loader._resolve_extension_path(package_dir, preferred_stem="_binding")


def test_resolve_extension_path_rejects_mixed_binding_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _force_choreboy_soabi(monkeypatch)
    package_dir = tmp_path / "tree_sitter"
    package_dir.mkdir(parents=True)
    (package_dir / "_binding.cpython-39-x86_64-linux-gnu.so").write_bytes(b"right")
    (package_dir / "_binding.cpython-311-x86_64-linux-gnu.so").write_bytes(b"wrong")

    with pytest.raises(RuntimeError, match="expected one exact binding artifact"):
        loader._resolve_extension_path(package_dir, preferred_stem="_binding")


def _write_runtime_site(site: Path, *, version: str) -> None:
    core = site / "tree_sitter"
    core.mkdir(parents=True)
    (core / "__init__.py").write_text(
        f"__version__ = {version!r}\n"
        "class Language:\n"
        "    def __init__(self, handle, name=None):\n"
        "        self.handle = handle\n",
        encoding="utf-8",
    )
    grammar = site / "tree_sitter_python"
    grammar.mkdir()
    (grammar / "__init__.py").write_text("def language():\n    return 1\n", encoding="utf-8")


def _restore_treesitter_modules(saved: dict[str, ModuleType]) -> None:
    for name in list(sys.modules):
        if loader._is_treesitter_module_name(name):
            sys.modules.pop(name, None)
    sys.modules.update(saved)
    loader._RUNTIME_INITIALIZED = False
    loader._RUNTIME_STATUS = loader.TreeSitterRuntimeStatus(False, "not_initialized")
    loader._TREE_SITTER_MODULE = None
    loader._LANGUAGE_MODULES = {}


def test_runtime_source_uses_external_package_and_skips_memfd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if loader._is_treesitter_module_name(name)
    }
    saved_path = sys.path[:]
    _reset_loader_state(monkeypatch)
    monkeypatch.delenv("CBCS_TREE_SITTER_SOURCE", raising=False)
    site = tmp_path / "site"
    _write_runtime_site(site, version="0.26.0")
    monkeypatch.syspath_prepend(str(site))
    def refuse_memfd(*_args: object, **_kwargs: object) -> ModuleType:
        raise AssertionError("memfd loader ran")

    monkeypatch.setattr(loader, "_load_extension_module", refuse_memfd)
    app_root = tmp_path / "app"
    (app_root / "vendor").mkdir(parents=True)
    try:
        status = loader.initialize_tree_sitter_runtime(app_root)
    finally:
        sys.path[:] = saved_path
        _restore_treesitter_modules(saved_modules)

    assert status.is_available is True
    assert status.source == "runtime"
    assert status.version == "0.26.0"
    assert "python" in status.available_language_keys


def test_vendored_override_ignores_runtime_site(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _reset_loader_state(monkeypatch)
    monkeypatch.setenv("CBCS_TREE_SITTER_SOURCE", "vendored")
    site = tmp_path / "site"
    _write_runtime_site(site, version="0.26.0")
    monkeypatch.syspath_prepend(str(site))
    app_root = tmp_path / "app"
    (app_root / "vendor").mkdir(parents=True)

    status = loader.initialize_tree_sitter_runtime(app_root)

    assert status.is_available is False
    assert status.source == ""
    assert "missing tree-sitter binding" in status.message


def test_runtime_override_without_external_package_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _reset_loader_state(monkeypatch)
    monkeypatch.setenv("CBCS_TREE_SITTER_SOURCE", "runtime")
    from app.bootstrap.vendor_paths import resolve_vendor_root

    repo_vendor = resolve_vendor_root()
    filtered: list[str] = []
    for entry in sys.path:
        if not entry:
            filtered.append(entry)
            continue
        entry_path = Path(entry)
        if (entry_path / "tree_sitter" / "__init__.py").is_file() and not loader._is_under(entry_path, repo_vendor):
            continue
        filtered.append(entry)
    monkeypatch.setattr(sys, "path", filtered)
    app_root = tmp_path / "app"
    (app_root / "vendor").mkdir(parents=True)

    status = loader.initialize_tree_sitter_runtime(app_root)

    assert status.is_available is False
    assert "CBCS_TREE_SITTER_SOURCE=runtime" in status.message
