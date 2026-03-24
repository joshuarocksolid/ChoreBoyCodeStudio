"""Unit tests for curated tree-sitter runtime loading."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

import app.treesitter.loader as loader

pytestmark = pytest.mark.unit


def _reset_loader_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "_RUNTIME_INITIALIZED", False)
    monkeypatch.setattr(loader, "_RUNTIME_STATUS", loader.TreeSitterRuntimeStatus(False, "not_initialized"))
    monkeypatch.setattr(loader, "_RUNTIME_TRACEBACK", None)
    monkeypatch.setattr(loader, "_TREE_SITTER_MODULE", None)
    monkeypatch.setattr(loader, "_LANGUAGE_MODULES", {})


def test_initialize_runtime_tracks_bundled_and_optional_languages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _reset_loader_state(monkeypatch)
    tree_sitter_dir = tmp_path / "vendor" / "tree_sitter"
    tree_sitter_dir.mkdir(parents=True)
    (tree_sitter_dir / "_binding.cpython-39-x86_64-linux-gnu.so").write_bytes(b"core")

    def fake_load_extension_module(module_name: str, shared_object_path: Path, label: str) -> ModuleType:
        return ModuleType(module_name)

    def fake_import_module(module_name: str) -> ModuleType:
        if module_name == "tree_sitter":
            module = ModuleType("tree_sitter")
            module.Language = lambda handle, name: (handle, name)  # type: ignore[attr-defined]
            return module
        raise AssertionError(f"unexpected import {module_name}")

    def fake_load_language_module(spec, vendor_root: Path) -> ModuleType | None:
        if spec.key in {"python", "json"}:
            module = ModuleType(spec.package_name)
            module.language = lambda: 11  # type: ignore[attr-defined]
            return module
        if spec.key == "sql":
            raise RuntimeError("broken optional package")
        return None

    monkeypatch.setattr(loader, "_load_extension_module", fake_load_extension_module)
    monkeypatch.setattr(loader.importlib, "import_module", fake_import_module)
    monkeypatch.setattr(loader, "_load_language_module", fake_load_language_module)

    status = loader.initialize_tree_sitter_runtime(app_root=tmp_path)

    assert status.is_available is True
    assert status.available_language_keys == ("json", "python")
    assert status.missing_default_language_keys == tuple(
        sorted(set(loader.DEFAULT_LANGUAGE_KEYS) - {"json", "python"})
    )
    assert status.skipped_optional_language_keys == ("sql",)
    assert f"2/{len(loader.DEFAULT_LANGUAGE_KEYS)} bundled grammars loaded" in status.message
    assert "optional skipped: sql" in status.message


def test_load_language_module_requires_language_callable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vendor_root = tmp_path / "vendor"
    package_dir = vendor_root / "tree_sitter_python"
    package_dir.mkdir(parents=True)
    (package_dir / "_binding.cpython-39-x86_64-linux-gnu.so").write_bytes(b"grammar")

    spec = next(spec for spec in loader.LANGUAGE_SPECS if spec.key == "python")

    monkeypatch.setattr(loader, "_load_extension_module", lambda *args, **kwargs: ModuleType("binding"))
    monkeypatch.setattr(loader.importlib, "import_module", lambda name: ModuleType(name))

    with pytest.raises(AttributeError, match="callable language"):
        loader._load_language_module(spec, vendor_root)


def test_runtime_message_reports_optional_languages() -> None:
    message = loader._build_runtime_message(
        binding_name="_binding.cpython-39-x86_64-linux-gnu.so",
        available_language_keys=("bash", "python", "sql", "toml"),
        missing_default_language_keys=("css",),
        skipped_optional_language_keys=(),
    )

    assert f"3/{len(loader.DEFAULT_LANGUAGE_KEYS)} bundled grammars loaded" in message
    assert "missing bundled: css" in message
    assert "optional installed: sql" in message
