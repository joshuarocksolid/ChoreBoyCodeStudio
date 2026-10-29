"""Item contents (tooltips and one other property each) match ``uic -g python``.

The tree is nested and has several columns, so a later item must not land on
an earlier item's variable. The oracle compares every item's role data.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.oracle

_spec = importlib.util.spec_from_file_location(
    "cbcs_uic_compare_items", Path(__file__).resolve().parent / "uic_compare.py"
)
assert _spec is not None and _spec.loader is not None
_uic = importlib.util.module_from_spec(_spec)
sys.modules["cbcs_uic_compare_items"] = _uic
_spec.loader.exec_module(_uic)

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QTreeWidget" name="tree">
   <column><property name="text"><string>A</string></property><property name="toolTip"><string>head tip</string></property></column>
   <column><property name="text"><string>B</string></property></column>
   <item>
    <property name="text"><string>Fruit</string></property>
    <property name="checkState"><enum>Qt::Checked</enum></property>
    <property name="text"><string>Red</string></property>
    <property name="toolTip"><string>red tip</string></property>
    <property name="textAlignment"><set>Qt::AlignRight|Qt::AlignVCenter</set></property>
    <item>
     <property name="text"><string>Apple</string></property>
     <property name="toolTip"><string>apple tip</string></property>
     <item>
      <property name="text"><string>Deep</string></property>
      <property name="toolTip"><string>deep tip</string></property>
     </item>
    </item>
    <item>
     <property name="text"><string>Pear</string></property>
     <property name="toolTip"><string>pear tip</string></property>
     <property name="text"><string>Green</string></property>
     <property name="statusTip"><string>green status</string></property>
    </item>
   </item>
   <item>
    <property name="text"><string>Veg</string></property>
    <property name="toolTip"><string>veg tip</string></property>
   </item>
  </widget>
  <widget class="QListWidget" name="lst">
   <item>
    <property name="text"><string>one</string></property>
    <property name="toolTip"><string>one tip</string></property>
    <property name="checkState"><enum>Qt::Checked</enum></property>
   </item>
   <item>
    <property name="text"><string>two</string></property>
    <property name="toolTip"><string>two tip</string></property>
    <property name="statusTip"><string>two status</string></property>
   </item>
  </widget>
  <widget class="QComboBox" name="combo">
   <item>
    <property name="text"><string>first</string></property>
    <property name="toolTip"><string>first tip</string></property>
   </item>
   <item>
    <property name="text"><string notr="true">second</string></property>
   </item>
  </widget>
  <widget class="QTableWidget" name="grid">
   <row><property name="text"><string>r0</string></property><property name="toolTip"><string>row tip</string></property></row>
   <column><property name="text"><string>c0</string></property></column>
   <column><property name="text"><string>c1</string></property></column>
   <item row="0" column="0">
    <property name="text"><string>a</string></property>
    <property name="toolTip"><string>a tip</string></property>
    <property name="textAlignment"><set>Qt::AlignRight</set></property>
   </item>
   <item row="0" column="1">
    <property name="text"><string>b</string></property>
    <property name="whatsThis"><string>b help</string></property>
   </item>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _path(tmp_path: Path) -> Path:
    uic = os.environ.get("CBCS_FB_UIC", "") or "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"
    if not Path(uic).is_file():
        pytest.skip("CBCS_FB_UIC is not set")
    os.environ["CBCS_FB_UIC"] = uic
    path = tmp_path / "items.ui"
    path.write_text(_FORM, encoding="utf-8")
    return path


def test_nested_tree_list_combo_and_table_items_match_uic(qapp, tmp_path: Path) -> None:
    del qapp
    outcome = _uic.compare(_path(tmp_path))
    assert outcome[0] == "ok", outcome


def test_oracle_notices_a_dropped_item_tooltip(qapp, tmp_path: Path) -> None:
    del qapp
    path = _path(tmp_path)

    def drop(source: str) -> str:
        return "\n".join(line for line in source.splitlines() if ".setToolTip(" not in line)

    outcome = _uic.compare(path, rewrite=drop)
    assert outcome[0] == "diff", outcome
