"""What a form save would overwrite that someone edited by hand."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.save import find_hand_edits, write_generated
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.reader import read_ui

pytestmark = pytest.mark.unit

_QRC = '<!DOCTYPE RCC><RCC version="1.0"><qresource prefix="/cbcs"><file>dot.bin</file></qresource></RCC>\n'

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

_SHOP_NOTE = "\n# shop note\n"


def _generated_project(tmp_path: Path) -> Tuple[FormScope, UiDocument, Path]:
    root = tmp_path / "proj"
    forms = root / "forms"
    forms.mkdir(parents=True)
    (forms / "dot.bin").write_bytes(b"one")
    (forms / "icons.qrc").write_text(_QRC, encoding="utf-8")
    ui_path = forms / "invoice.ui"
    ui_path.write_text(_UI, encoding="utf-8")
    fs = OsFileSystem()
    scope = scope_for(str(ui_path), str(root), fs)
    document = read_ui(_UI, allocator=IdAllocator()).document
    write_generated(scope, document, ui_path.read_bytes(), fs)
    return scope, document, forms


@pytest.mark.parametrize(
    ("edited_on_disk", "edited_in_buffer", "held"),
    [
        pytest.param((), (), (), id="nothing-edited"),
        pytest.param(("ui_invoice.py",), (), ("ui_invoice.py",), id="module-on-disk"),
        pytest.param((), ("ui_invoice.py",), ("ui_invoice.py",), id="module-in-unsaved-buffer"),
        pytest.param(("icons_rc.py",), (), ("icons_rc.py",), id="resource-on-disk"),
        pytest.param((), ("icons_rc.py",), (), id="resource-buffer-the-save-leaves-alone"),
    ],
)
def test_the_hold_names_hand_edits_the_save_would_overwrite(
    tmp_path: Path,
    edited_on_disk: Tuple[str, ...],
    edited_in_buffer: Tuple[str, ...],
    held: Tuple[str, ...],
) -> None:
    scope, document, forms = _generated_project(tmp_path)
    for name in edited_on_disk:
        path = forms / name
        path.write_text(path.read_text(encoding="utf-8") + _SHOP_NOTE, encoding="utf-8")
    buffers = {
        str(forms / name): (forms / name).read_text(encoding="utf-8") + _SHOP_NOTE for name in edited_in_buffer
    }

    edits = find_hand_edits(scope, document, OsFileSystem(), buffers.get)

    assert tuple(Path(edit.path).name for edit in edits) == held


def test_the_held_digest_names_the_copy_the_save_keeps(tmp_path: Path) -> None:
    scope, document, forms = _generated_project(tmp_path)
    module = forms / "ui_invoice.py"
    module.write_text(module.read_text(encoding="utf-8") + _SHOP_NOTE, encoding="utf-8")
    (edit,) = find_hand_edits(scope, document, OsFileSystem(), lambda _path: None)

    result = write_generated(scope, document, (forms / "invoice.ui").read_bytes(), OsFileSystem())

    copies = [Path(path).name for path in result.files if "hand_edits" in Path(path).parts]
    assert copies == ["ui_invoice.%s.py.txt" % edit.body8]
