"""A form save stops when a generated file was edited by hand."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.header import is_hand_edited, render_header
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.integration.generated_hold import (
    first_hand_edited_output,
    watched_generated_paths,
)

pytestmark = pytest.mark.unit

_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QWidget" name="Invoice"/>
 <resources>
  <include location="icons.qrc"/>
 </resources>
 <connections/>
</ui>
"""


def _clean_module() -> str:
    body = "pass\n"
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    header = render_header(
        ui_file_name="invoice.ui",
        window_file_name="invoice_window.py",
        has_logic=False,
        source_sha256="a" * 64,
        body_sha256=digest,
    )
    return header + body


def test_watched_paths_include_the_ui_module_and_resource_module(tmp_path: Path) -> None:
    ui = tmp_path / "invoice.ui"
    ui.write_text(_UI, encoding="utf-8")
    document = read_ui(_UI, allocator=IdAllocator()).document
    scope = FormScope(
        kind="project",
        ui_path=str(ui),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / "ui_invoice.py"),
    )
    paths = watched_generated_paths(scope, document)
    assert str(tmp_path / "ui_invoice.py") in paths
    assert any(path.endswith("icons_rc.py") for path in paths)


def test_a_dirty_or_hand_edited_output_holds_the_save(tmp_path: Path) -> None:
    generated = tmp_path / "ui_invoice.py"
    clean = _clean_module()
    assert not is_hand_edited(clean)
    hand = clean + "\n# mine\n"

    held = first_hand_edited_output(
        (str(generated),),
        open_buffer=lambda _path: (clean, True),
        read_disk=lambda _path: clean,
    )
    assert held == str(generated)

    held = first_hand_edited_output(
        (str(generated),),
        open_buffer=lambda _path: (hand, False),
        read_disk=lambda _path: clean,
    )
    assert held == str(generated)

    held = first_hand_edited_output(
        (str(generated),),
        open_buffer=lambda _path: None,
        read_disk=lambda _path: hand,
    )
    assert held == str(generated)

    assert (
        first_hand_edited_output(
            (str(generated),),
            open_buffer=lambda _path: (clean, False),
            read_disk=lambda _path: hand,
        )
        is None
    )
    assert (
        first_hand_edited_output(
            (str(generated),),
            open_buffer=lambda _path: None,
            read_disk=lambda _path: clean,
        )
        is None
    )
