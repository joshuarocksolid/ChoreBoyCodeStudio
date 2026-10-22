"""Unit tests for cp39 tree-sitter core binding staging."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest

from app.packaging import product_builder
from app.packaging import tree_sitter_cp39
from app.packaging.tree_sitter_cp39 import (
    CORE_LANGUAGE_ABI_MAX,
    CP39_TREE_SITTER_BINDING_NAME,
    CP39_TREE_SITTER_VERSION,
    TreeSitterWheelPin,
    download_cp39_tree_sitter_wheel,
    download_tree_sitter_wheel,
    enforce_grammar_language_abi,
    grammar_wheel_pins,
    read_grammar_language_abi,
    stage_cp39_tree_sitter_core_binding,
    stage_linux_grammar_bindings,
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


_DARWIN_BINDING = b"\xcf\xfa\xed\xfe" + b"darwin-grammar-binding"


def _grammar_elf(language_abi: int, marker: bytes = b"") -> bytes:
    """ELF64 x86-64 object whose ``language.0`` symbol starts with *language_abi*."""
    language = struct.pack("<I", language_abi) + marker
    if len(language) < 32:
        language += b"\x00" * (32 - len(language))
    strtab = b"\x00language.0\x00"
    shstrtab = b"\x00.rodata\x00.strtab\x00.symtab\x00.shstrtab\x00"
    language_off = 120
    strtab_off = language_off + len(language)
    symtab_off = strtab_off + len(strtab)
    symtab = struct.pack("<IBBHQQ", 0, 0, 0, 0, 0, 0) + struct.pack(
        "<IBBHQQ", 1, 1, 0, 1, language_off, len(language)
    )
    shstr_off = symtab_off + len(symtab)
    shoff = shstr_off + len(shstrtab)
    file_size = shoff + (5 * 64)

    def _section(
        name: int,
        section_type: int,
        offset: int,
        size: int,
        link: int = 0,
        entsize: int = 0,
    ) -> bytes:
        return struct.pack(
            "<IIQQQQIIQQ",
            name,
            section_type,
            0,
            0,
            offset,
            size,
            link,
            0,
            1,
            entsize,
        )

    sections = b"".join(
        (
            _section(0, 0, 0, 0),
            _section(1, 1, language_off, len(language)),
            _section(9, 3, strtab_off, len(strtab)),
            _section(17, 2, symtab_off, len(symtab), link=2, entsize=24),
            _section(25, 3, shstr_off, len(shstrtab)),
        )
    )
    header = struct.pack(
        "<16sHHIQQQIHHHHHH",
        b"\x7fELF" + bytes([2, 1, 1, 0]) + bytes(8),
        3,
        62,
        1,
        0,
        64,
        shoff,
        0,
        64,
        56,
        1,
        64,
        5,
        4,
    )
    program = struct.pack("<IIQQQQQQ", 1, 5, 0, 0, 0, file_size, file_size, 8)
    blob = bytearray(file_size)
    blob[0:64] = header
    blob[64:120] = program
    blob[language_off : language_off + len(language)] = language
    blob[strtab_off : strtab_off + len(strtab)] = strtab
    blob[symtab_off : symtab_off + len(symtab)] = symtab
    blob[shstr_off : shstr_off + len(shstrtab)] = shstrtab
    blob[shoff : shoff + len(sections)] = sections
    return bytes(blob)


def _pin_wheel_name(pin: TreeSitterWheelPin) -> str:
    abi = pin.pip_abi or "abi3"
    return (
        f"{pin.package_name}-{pin.version}-cp39-{abi}-"
        "manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
    )


def _write_grammar_wheel(path: Path, pin: TreeSitterWheelPin, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr(pin.wheel_member, payload)


def _vendor_with_bindings(root: Path, payloads: dict[str, bytes]) -> Path:
    vendor = root / "vendor"
    for pin in grammar_wheel_pins():
        package_dir = vendor / pin.package_name
        package_dir.mkdir(parents=True)
        (package_dir / pin.binding_filename).write_bytes(payloads[pin.package_name])
    return vendor


def _fake_pip(monkeypatch: pytest.MonkeyPatch, cache_dir: Path, payloads: dict[str, bytes]) -> list[list[str]]:
    calls: list[list[str]] = []

    class _Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def _run(cmd, capture_output=False, text=False):
        calls.append(list(cmd))
        requirement = next(part for part in cmd if "==" in str(part))
        pin = next(item for item in grammar_wheel_pins() if item.requirement == requirement)
        _write_grammar_wheel(cache_dir / _pin_wheel_name(pin), pin, payloads[pin.package_name])
        return _Completed()

    monkeypatch.setattr(tree_sitter_cp39.subprocess, "run", _run)
    return calls


def _supported_payloads() -> dict[str, bytes]:
    return {
        pin.package_name: _grammar_elf(CORE_LANGUAGE_ABI_MAX, pin.package_name.encode())
        for pin in grammar_wheel_pins()
    }


@pytest.mark.parametrize("language_abi", (CORE_LANGUAGE_ABI_MAX, CORE_LANGUAGE_ABI_MAX + 1))
def test_read_grammar_language_abi_from_language_symbol(tmp_path: Path, language_abi: int) -> None:
    binding = tmp_path / "_binding.abi3.so"
    binding.write_bytes(_grammar_elf(language_abi))

    assert read_grammar_language_abi(binding) == language_abi


def test_every_shipped_grammar_is_downloaded_and_overlaid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = _supported_payloads()
    vendor = _vendor_with_bindings(
        tmp_path,
        {package_name: _DARWIN_BINDING for package_name in payloads},
    )
    calls = _fake_pip(monkeypatch, tmp_path / "cache", payloads)

    result = stage_linux_grammar_bindings(vendor, tmp_path / "cache")

    downloaded = {part for cmd in calls for part in cmd if "==" in part}
    assert downloaded == {pin.requirement for pin in grammar_wheel_pins()}
    assert len(calls) == len(grammar_wheel_pins())
    command = calls[0]
    assert "--no-deps" in command
    assert "--only-binary=:all:" in command
    assert "--python-version=3.9" in command
    assert "--platform=manylinux_2_17_x86_64" in command
    assert "--implementation=cp" in command
    assert "--abi=cp39" not in command
    assert result.exclusions == ()
    for pin in grammar_wheel_pins():
        staged = vendor / pin.package_name / pin.binding_filename
        assert staged.read_bytes() == payloads[pin.package_name]


def test_cached_grammar_wheel_is_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pin = next(item for item in grammar_wheel_pins() if item.package_name == "tree_sitter_python")
    cache_dir = tmp_path / "cache"
    wheel_path = cache_dir / _pin_wheel_name(pin)
    _write_grammar_wheel(wheel_path, pin, _grammar_elf(CORE_LANGUAGE_ABI_MAX))

    def _fail(*args, **kwargs):
        raise AssertionError("subprocess.run should not be invoked when cache hits")

    monkeypatch.setattr(tree_sitter_cp39.subprocess, "run", _fail)

    assert download_tree_sitter_wheel(pin, cache_dir) == wheel_path


def test_darwin_grammar_binding_is_replaced_before_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = _supported_payloads()
    vendor = _vendor_with_bindings(
        tmp_path,
        {package_name: _DARWIN_BINDING for package_name in payloads},
    )
    _fake_pip(monkeypatch, tmp_path / "cache", payloads)
    core_dir = vendor / "tree_sitter"
    core_dir.mkdir()
    (core_dir / CP39_TREE_SITTER_BINDING_NAME).write_bytes(
        b"\x7fELF" + b"\x02\x01\x01\x00" + bytes(8) + b"\x00\x00" + b"\x3e\x00"
    )

    stage_linux_grammar_bindings(vendor, tmp_path / "cache")

    python_binding = vendor / "tree_sitter_python" / "_binding.abi3.so"
    assert python_binding.read_bytes() == payloads["tree_sitter_python"]
    assert python_binding.read_bytes().startswith(b"\x7fELF")
    bundle = product_builder.validate_choreboy_tree_sitter_bundle(vendor)
    validated = {item["package"] for item in bundle["validated_bindings"]}
    assert "tree_sitter_python" in validated


def test_unsupported_sql_grammar_is_excluded(tmp_path: Path) -> None:
    payloads = _supported_payloads()
    payloads["tree_sitter_sql"] = _grammar_elf(CORE_LANGUAGE_ABI_MAX + 1, b"sql")
    vendor = _vendor_with_bindings(tmp_path, payloads)
    sql_pin = next(pin for pin in grammar_wheel_pins() if pin.package_name == "tree_sitter_sql")
    (vendor / f"{sql_pin.package_name}-{sql_pin.version}.dist-info").mkdir()

    exclusions = enforce_grammar_language_abi(vendor)

    assert [item.package_name for item in exclusions] == ["tree_sitter_sql"]
    assert str(CORE_LANGUAGE_ABI_MAX + 1) in exclusions[0].reason
    assert "plain text" in exclusions[0].reason
    assert not (vendor / "tree_sitter_sql").exists()
    assert not (vendor / f"{sql_pin.package_name}-{sql_pin.version}.dist-info").exists()
    assert (vendor / "tree_sitter_python" / "_binding.abi3.so").is_file()


def test_unsupported_grammar_without_exclusion_fails_the_build(tmp_path: Path) -> None:
    payloads = _supported_payloads()
    payloads["tree_sitter_python"] = _grammar_elf(CORE_LANGUAGE_ABI_MAX + 1, b"python")
    vendor = _vendor_with_bindings(tmp_path, payloads)

    with pytest.raises(RuntimeError, match="tree_sitter_python language ABI"):
        enforce_grammar_language_abi(vendor)
