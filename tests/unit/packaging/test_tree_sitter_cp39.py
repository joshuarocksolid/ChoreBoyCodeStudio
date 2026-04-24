"""Unit tests for cp39 tree-sitter core binding staging."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.packaging import tree_sitter_cp39
from app.packaging.tree_sitter_cp39 import (
    CP39_TREE_SITTER_BINDING_NAME,
    CP39_TREE_SITTER_VERSION,
    download_cp39_tree_sitter_wheel,
    stage_cp39_tree_sitter_core_binding,
)

pytestmark = pytest.mark.unit


def _build_fake_wheel(path: Path, *, binding_payload: bytes = b"cp39-binding") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr(
            f"tree_sitter/{CP39_TREE_SITTER_BINDING_NAME}", binding_payload
        )
        wheel.writestr("tree_sitter/__init__.py", "")
    return path


def _wheel_filename() -> str:
    return (
        f"tree_sitter-{CP39_TREE_SITTER_VERSION}-cp39-cp39-"
        "manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
    )


def test_stage_cp39_replaces_cp311_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = tmp_path / "payload" / "vendor" / "tree_sitter"
    staged.mkdir(parents=True)
    cp311 = staged / "_binding.cpython-311-x86_64-linux-gnu.so"
    cp311.write_bytes(b"cp311-binding")
    (staged / "__init__.py").write_text("# pkg\n", encoding="utf-8")

    cache_dir = tmp_path / "cache"
    wheel_path = _build_fake_wheel(cache_dir / _wheel_filename())

    monkeypatch.setattr(
        tree_sitter_cp39,
        "download_cp39_tree_sitter_wheel",
        lambda cache: wheel_path,
    )

    staged_binding = stage_cp39_tree_sitter_core_binding(staged, cache_dir)

    assert staged_binding == staged / CP39_TREE_SITTER_BINDING_NAME
    assert staged_binding.exists()
    assert staged_binding.read_bytes() == b"cp39-binding"
    assert not cp311.exists()
    assert (staged / "__init__.py").exists()


def test_stage_cp39_succeeds_when_no_existing_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = tmp_path / "payload" / "vendor" / "tree_sitter"
    staged.mkdir(parents=True)
    cache_dir = tmp_path / "cache"
    wheel_path = _build_fake_wheel(cache_dir / _wheel_filename())

    monkeypatch.setattr(
        tree_sitter_cp39,
        "download_cp39_tree_sitter_wheel",
        lambda cache: wheel_path,
    )

    staged_binding = stage_cp39_tree_sitter_core_binding(staged, cache_dir)

    assert staged_binding.exists()
    assert staged_binding.read_bytes() == b"cp39-binding"
    bindings = sorted(p.name for p in staged.glob("_binding*.so"))
    assert bindings == [CP39_TREE_SITTER_BINDING_NAME]


def test_stage_cp39_raises_when_staged_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "payload" / "vendor" / "tree_sitter"
    cache_dir = tmp_path / "cache"

    with pytest.raises(RuntimeError, match="staged tree_sitter directory"):
        stage_cp39_tree_sitter_core_binding(missing, cache_dir)


def test_download_uses_cache_when_wheel_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "cache"
    wheel_path = _build_fake_wheel(cache_dir / _wheel_filename())

    def _fail(*args, **kwargs):
        raise AssertionError("subprocess.run should not be invoked when cache hits")

    monkeypatch.setattr(tree_sitter_cp39.subprocess, "run", _fail)

    result = download_cp39_tree_sitter_wheel(cache_dir)
    assert result == wheel_path


def test_download_invokes_pip_with_expected_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "cache"
    captured: dict[str, list[str]] = {}

    class _FakeCompleted:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, capture_output=False, text=False):
        captured["cmd"] = list(cmd)
        _build_fake_wheel(cache_dir / _wheel_filename())
        return _FakeCompleted()

    monkeypatch.setattr(tree_sitter_cp39.subprocess, "run", _fake_run)

    result = download_cp39_tree_sitter_wheel(cache_dir)

    assert result.exists()
    cmd = captured["cmd"]
    assert "pip" in cmd
    assert "download" in cmd
    assert f"tree-sitter=={CP39_TREE_SITTER_VERSION}" in cmd
    assert "--no-deps" in cmd
    assert "--only-binary=:all:" in cmd
    assert "--python-version=3.9" in cmd
    assert "--platform=manylinux_2_17_x86_64" in cmd
    assert "--abi=cp39" in cmd
    assert "--dest" in cmd


def test_download_raises_runtime_error_on_pip_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "cache"

    class _FakeCompleted:
        returncode = 1
        stdout = "no internet"
        stderr = "Could not find a version"

    monkeypatch.setattr(
        tree_sitter_cp39.subprocess,
        "run",
        lambda *args, **kwargs: _FakeCompleted(),
    )

    with pytest.raises(RuntimeError, match="pip download failed"):
        download_cp39_tree_sitter_wheel(cache_dir)


def test_download_raises_runtime_error_when_pip_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "cache"

    def _missing(*args, **kwargs):
        raise FileNotFoundError("pip")

    monkeypatch.setattr(tree_sitter_cp39.subprocess, "run", _missing)

    with pytest.raises(RuntimeError, match="pip is not available"):
        download_cp39_tree_sitter_wheel(cache_dir)


def test_extract_raises_when_wheel_missing_binding(tmp_path: Path) -> None:
    staged = tmp_path / "payload" / "vendor" / "tree_sitter"
    staged.mkdir(parents=True)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    bad_wheel = cache_dir / _wheel_filename()
    with zipfile.ZipFile(bad_wheel, "w") as wheel:
        wheel.writestr("tree_sitter/__init__.py", "")

    with pytest.raises(RuntimeError, match="missing"):
        stage_cp39_tree_sitter_core_binding(staged, cache_dir)
