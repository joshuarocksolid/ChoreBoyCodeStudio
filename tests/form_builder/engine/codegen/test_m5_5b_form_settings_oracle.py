# pyright: reportAttributeAccessIssue=false
"""The form settings the generator must honour, against ``uic -g python`` (UX-FSET-005, R3-186, R3-187, R3-188, R3-191).

``layoutdefault`` matches the Designer tool for layouts that sit on a widget. Four things
do not match yet, and ``engine/codegen/emit.py`` is M5.4's file in the M5 lanes table, so each
is a strict xfail here: a nested layout takes the default margin (uic leaves it alone),
``layoutfunction`` and ``pixmapfunction`` are ignored, and ``idbasedtr`` writes
``translate(context, id)`` where uic 6.8 writes ``qtTrId(id)``.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import List

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui

pytestmark = pytest.mark.unit

_HERE = Path(__file__).resolve().parent
_UIC = os.environ.get("CBCS_FB_UIC", "") or "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"


def _load_helper(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"%s>
 <class>Till</class>
 <widget class="QWidget" name="Till">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <layout class="QHBoxLayout" name="row">
     <item><widget class="QPushButton" name="payButton"><property name="text"><string>Pay</string></property></widget></item>
    </layout>
   </item>
   <item>
    <widget class="QGroupBox" name="receipt">
     <layout class="QGridLayout" name="grid">
      <property name="spacing"><number>3</number></property>
      <item row="0" column="0"><widget class="QLabel" name="total"><property name="text"><string>Total</string></property></widget></item>
     </layout>
    </widget>
   </item>
  </layout>
 </widget>
%s <resources/>
 <connections/>
</ui>
"""


_NO_NESTED = _FORM.replace(
    """   <item>
    <layout class="QHBoxLayout" name="row">
     <item><widget class="QPushButton" name="payButton"><property name="text"><string>Pay</string></property></widget></item>
    </layout>
   </item>
""",
    """   <item><widget class="QPushButton" name="payButton"><property name="text"><string>Pay</string></property></widget></item>
""",
)


def _need_uic() -> None:
    if not Path(_UIC).is_file():
        pytest.skip("CBCS_FB_UIC is not set")


def _save(tmp_path: Path, attrs: str, extra: str, text: str = _FORM) -> Path:
    path = tmp_path / "till.ui"
    path.write_text(text % (attrs, extra), encoding="utf-8")
    return path


def _ours(path: Path) -> List[str]:
    data = path.read_bytes()
    document = read_ui(data.decode("utf-8"), allocator=IdAllocator()).document
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(path.parent),
        generated_path=str(path.with_name("ui_till.py")),
        window_path=str(path.with_name("till_window.py")),
        module_name="ui_till",
    )
    generated = generate_form_module(document, scope=scope, source_bytes=data)
    assert generated.text is not None
    return [line.strip() for line in generated.text.splitlines()]


def _uic(path: Path) -> List[str]:
    done = subprocess.run([_UIC, "-g", "python", str(path)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return [line.strip() for line in done.stdout.splitlines()]


def _spacing_lines(lines: List[str]) -> List[str]:
    """The gap and margin calls. Their order inside one layout does not change the form."""
    return sorted(line for line in lines if "etSpacing" in line or "etMargin" in line or "etContentsMargins" in line)


@pytest.mark.oracle
@pytest.mark.parity("R3-186")
@pytest.mark.parametrize("default", ['<layoutdefault spacing="6" margin="11"/>', '<layoutdefault spacing="4"/>', '<layoutdefault margin="2"/>'])
def test_layoutdefault_sets_the_same_gaps_as_uic(tmp_path: Path, default: str) -> None:
    _need_uic()
    path = _save(tmp_path, "", " %s\n" % default, _NO_NESTED)
    assert _spacing_lines(_ours(path)) == _spacing_lines(_uic(path))
    assert _spacing_lines(_ours(path)), "the default reaches the generated code"


@pytest.mark.oracle
def test_layoutdefault_margin_skips_nested_layouts_like_uic(tmp_path: Path) -> None:
    _need_uic()
    path = _save(tmp_path, "", ' <layoutdefault margin="2"/>\n')
    assert _spacing_lines(_ours(path)) == _spacing_lines(_uic(path))


@pytest.mark.oracle
def test_idbasedtr_writes_qttrid_like_uic(tmp_path: Path) -> None:
    _need_uic()
    path = _save(tmp_path, ' idbasedtr="true"', "", _FORM.replace("<string>Pay</string>", '<string id="pay_id">Pay</string>'))
    ours = [line for line in _ours(path) if "payButton.setText" in line]
    theirs = [line for line in _uic(path) if "payButton.setText" in line]
    assert theirs == ['self.payButton.setText(qtTrId(u"pay_id"))']
    assert ours == theirs


@pytest.mark.oracle
def test_layoutfunction_calls_the_named_functions_like_uic(tmp_path: Path) -> None:
    _need_uic()
    path = _save(tmp_path, "", ' <layoutfunction spacing="spacing_for" margin="margin_for"/>\n')
    theirs = _spacing_lines(_uic(path))
    assert any("spacing_for()" in line for line in theirs)
    assert _spacing_lines(_ours(path)) == theirs


@pytest.mark.oracle
def test_pixmapfunction_wraps_picture_paths_like_uic(tmp_path: Path) -> None:
    _need_uic()
    extra = ' <pixmapfunction>load_picture</pixmapfunction>\n'
    path = tmp_path / "till.ui"
    path.write_text(
        _FORM.replace('<property name="text"><string>Total</string></property>', '<property name="pixmap"><pixmap>:/a.png</pixmap></property>') % ("", extra),
        encoding="utf-8",
    )
    theirs = [line for line in _uic(path) if "load_picture" in line]
    assert theirs
    assert [line for line in _ours(path) if "load_picture" in line] == theirs
