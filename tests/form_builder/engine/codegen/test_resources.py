"""``.qrc`` parsing and the resource binary the runtime loader reads."""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.resources import (
    compile_resource_tree,
    qt_hash,
    read_qrc,
    render_rc_module,
)

_QRC = """<!DOCTYPE RCC><RCC version="1.0">
<qresource prefix="/cbcs">
 <file>dot.bin</file>
 <file alias="icons/dot.bin">nested.bin</file>
</qresource>
</RCC>
"""


def test_plain_doctype_parses_and_entities_do_not() -> None:
    document = read_qrc(_QRC)
    assert [item.path for item in document.files] == ["dot.bin", "nested.bin"]
    assert document.files[1].alias == "icons/dot.bin"
    with pytest.raises(ValueError):
        read_qrc('<!DOCTYPE RCC [<!ENTITY x "y">]><RCC></RCC>')


def test_missing_file_is_fb503_and_the_module_still_parses(tmp_path: Path) -> None:
    present = tmp_path / "dot.bin"
    present.write_bytes(b"HELLO")
    document = read_qrc(_QRC)

    def read_file(rel: str) -> bytes:
        return (tmp_path / rel).read_bytes()

    tree, diagnostics = compile_resource_tree(document, read_file=read_file)
    assert [item.code for item in diagnostics] == ["FB503"]
    text = render_rc_module(tree, qrc_file_name="demo.qrc")
    ast.parse(text, feature_version=(3, 9))
    assert "qRegisterResourceData" in text
    assert b"HELLO" in tree.data


def test_resource_bytes_do_not_depend_on_mtime(tmp_path: Path) -> None:
    blob = tmp_path / "dot.bin"
    blob.write_bytes(b"HELLO")
    other = tmp_path / "nested.bin"
    other.write_bytes(b"WORLD")
    document = read_qrc(_QRC)

    def read_file(rel: str) -> bytes:
        return (tmp_path / rel).read_bytes()

    first, first_diag = compile_resource_tree(document, read_file=read_file)
    os.utime(blob, (1_000, 1_000))
    os.utime(other, (2_000, 2_000))
    second, second_diag = compile_resource_tree(document, read_file=read_file)
    assert first_diag == second_diag
    assert first == second


def test_qt_hash_matches_the_rcc_value_for_cbcs() -> None:
    # rcc 6.8.3 orders ":/cbcs/..." with this hash. A drift makes QFile miss.
    assert qt_hash("cbcs") == 0x698A3
