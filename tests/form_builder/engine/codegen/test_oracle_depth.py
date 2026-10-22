"""The uic oracle must notice the five generator mutants the shallow snapshot missed."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from tests.form_builder.engine.codegen.uic_compare import compare

_CORPUS = Path(__file__).resolve().parents[2] / "corpus"
_ICONS = _CORPUS / "synthetic" / "qt"


def _drop_lines(token: str):
    def rewrite(text: str) -> str:
        return "\n".join(line for line in text.splitlines() if token not in line) + "\n"

    return rewrite


def _stretch_zero(text: str) -> str:
    return re.sub(r"setHorizontalStretch\(\d+\)", "setHorizontalStretch(0)", text)


def _modes_normal(text: str) -> str:
    return (
        text.replace("QIcon.Mode.Disabled", "QIcon.Mode.Normal")
        .replace("QIcon.Mode.Active", "QIcon.Mode.Normal")
        .replace("QIcon.Mode.Selected", "QIcon.Mode.Normal")
    )


def _require_uic() -> None:
    uic = os.environ.get("CBCS_FB_UIC", "")
    if not uic or not Path(uic).is_file():
        message = "CBCS_FB_UIC is not set"
        if os.environ.get("CBCS_FB_REQUIRE_ORACLE") == "1":
            pytest.fail(message)
        pytest.skip(message)


def _expect_diff(path: Path, rewrite) -> None:
    base = compare(path)
    assert base[0] == "ok", base
    mutated = compare(path, rewrite=rewrite)
    assert mutated[0] == "diff", mutated


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("label", "relative", "rewrite"),
    (
        ("buddies", "synthetic/forms/address_form.ui", _drop_lines(".setBuddy(")),
        (
            "tab-order",
            "qt_examples/pyside6/examples/serialbus/modbus/modbusclient/mainwindow.ui",
            _drop_lines(".setTabOrder("),
        ),
        (
            "horizontal-stretch",
            "qt_examples/pyside6/examples/serialbus/can/sendframebox.ui",
            _stretch_zero,
        ),
        ("disabled-palette", "synthetic/properties/palette.ui", _drop_lines("ColorGroup.Disabled")),
    ),
)
def test_mutant_fails_oracle(qapp, label: str, relative: str, rewrite) -> None:
    del qapp, label
    _require_uic()
    _expect_diff(_CORPUS / relative, rewrite)


@pytest.mark.oracle
def test_icon_mode_mutant_fails_oracle(qapp, tmp_path: Path) -> None:
    del qapp
    _require_uic()
    normal = (_ICONS / "normaloff.png").resolve()
    selected = (_ICONS / "normalon.png").resolve()
    path = tmp_path / "icons.ui"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>IconForm</class>
 <widget class="QWidget" name="IconForm">
  <property name="windowTitle"><string>Icons</string></property>
  <property name="windowIcon">
   <iconset>
    <normaloff>%s</normaloff>
    <selectedoff>%s</selectedoff>%s
   </iconset>
  </property>
 </widget>
</ui>
"""
        % (normal, selected, normal),
        encoding="utf-8",
    )
    _expect_diff(path, _modes_normal)


_CONNECT_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Dialog</class>
 <widget class="QDialog" name="Dialog">
  <layout class="QVBoxLayout">
   <item>
    <widget class="QLabel" name="label">
     <property name="text"><string>Hello</string></property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="go">
     <property name="text"><string>Go</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <connections>
  <connection>
   <sender>go</sender>
   <signal>clicked()</signal>
   <receiver>label</receiver>
   <slot>clear()</slot>
  </connection>
 </connections>
</ui>
"""


@pytest.mark.oracle
def test_uic_nameerror_is_compared_to_quiloader(qapp) -> None:
    del qapp
    _require_uic()
    result = compare(_CORPUS / "synthetic/properties/char.ui")
    assert result[0] == "ok", result


@pytest.mark.oracle
def test_different_import_failures_are_not_env(qapp) -> None:
    del qapp
    _require_uic()
    result = compare(_CORPUS / "synthetic/schema/kitchen_sink.ui")
    assert result[0] != "env", result


@pytest.mark.oracle
def test_freecad_quantity_spinbox_matches_uic(qapp) -> None:
    del qapp
    _require_uic()
    path = Path("/opt/freecad-1.1/usr/Mod/Fem/Resources/ui/BodyHeatSource.ui")
    if not path.is_file():
        message = "FreeCAD forms are not installed"
        if os.environ.get("CBCS_FB_REQUIRE_ORACLE") == "1":
            pytest.fail(message)
        pytest.skip(message)
    result = compare(path)
    assert result[0] == "ok", result


@pytest.mark.oracle
def test_dropped_connection_fails_oracle(qapp, tmp_path: Path) -> None:
    del qapp
    _require_uic()
    path = tmp_path / "connected.ui"
    path.write_text(_CONNECT_UI, encoding="utf-8")
    _expect_diff(path, _drop_lines(".connect("))


_KITCHEN_SINK = _CORPUS / "synthetic" / "schema" / "kitchen_sink.ui"


@pytest.mark.oracle
def test_kitchen_sink_matches_through_the_quiloader_fallback(qapp) -> None:
    """uic's module for this form cannot run, so QUiLoader stands in.

    Only the cited QUiLoader differences are ignored. Dropping the window
    title (an id-based string) is still a diff.
    """
    del qapp
    _require_uic()
    _expect_diff(_KITCHEN_SINK, _drop_lines(".setWindowTitle("))

