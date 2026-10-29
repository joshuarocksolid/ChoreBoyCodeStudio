# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""Picture problems and the add-picture plan: FB031, FB032, packaging errors, one undo step."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.diagnostics import CODES
from app.features.form_builder.engine.project.forms import classify_form
from app.features.form_builder.engine.project.packaging import inspect_forms
from app.features.form_builder.engine.project.picture_adopt import adopt_raw_picture, plan_add
from app.features.form_builder.engine.project.picture_checks import picture_diagnostics
from app.features.form_builder.engine.project.pictures import (
    clear_picture_cache,
    project_pictures,
    raw_pictures,
)
from app.features.form_builder.engine.project.qrc_write import add_pictures
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import ResourcePixmap

pytestmark = [pytest.mark.unit]

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Till</class>
 <widget class="QWidget" name="Till">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="logo">
     <property name="pixmap">
      <pixmap>art/logo.png</pixmap>
     </property>
    </widget>
   </item>
   <item>
    <widget class="QPushButton" name="payButton">
     <property name="icon">
      <iconset>
       <normaloff>art/pay.png</normaloff>
       <normalon>:/pictures/ok.png</normalon>
      </iconset>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _project(tmp_path: Path):
    root = tmp_path / "shop"
    (root / "forms" / "art").mkdir(parents=True)
    (root / "forms" / "art" / "logo.png").write_bytes(PNG)
    (root / "forms" / "art" / "pay.png").write_bytes(PNG + b"1")
    ui = root / "forms" / "till.ui"
    ui.write_text(_FORM, encoding="utf-8")
    return root, ui


def _open(root: Path, ui: Path) -> FormSession:
    scope = classify_form(str(ui), project_root=str(root))
    return FormSession.open(ui.read_text(encoding="utf-8"), path=str(ui), scope=scope)


def test_file_paths_in_pixmaps_and_icon_states_are_found_and_resource_paths_are_not(tmp_path: Path) -> None:
    root, ui = _project(tmp_path)
    found = raw_pictures(_open(root, ui).document)
    assert [(r.object_name, r.property_name, r.state, r.path) for r in found] == [
        ("logo", "pixmap", "", "art/logo.png"),
        ("payButton", "icon", "normaloff", "art/pay.png"),
    ]


def test_fb031_and_fb032_use_the_spec_sentences(tmp_path: Path) -> None:
    root, ui = _project(tmp_path)
    clear_picture_cache()
    session = _open(root, ui)
    plan = plan_add(session.document, str(ui), str(root), [str(root / "forms" / "art" / "logo.png")])
    (root / "forms" / "art" / "logo.png").unlink()
    with session.log.transaction(plan.label) as txn:
        for command in plan.commands:
            txn.execute(command)
    clear_picture_cache()
    found = picture_diagnostics(session.document, str(ui), str(root))
    codes = [d.code for d in found]
    assert codes.count("FB031") == 2 and codes.count("FB032") == 1
    messages = {d.code: d.message for d in found if d.code == "FB032"}
    assert messages["FB032"] == "forms/resources.qrc lists art/logo.png, but the file is missing."
    assert found[0].message == "logo uses a picture from a file path (art/logo.png). A packaged app may not find it."
    assert all(CODES[d.code].severity == d.severity for d in found)


def test_picker_sections_put_this_forms_pictures_first_and_skip_tool_folders(tmp_path: Path) -> None:
    root, ui = _project(tmp_path)
    add_pictures(str(root), str(root / "forms" / "resources.qrc"), [str(root / "forms" / "art" / "logo.png")])
    add_pictures(str(root), str(root / "assets" / "more.qrc"), [str(root / "forms" / "art" / "pay.png")])
    add_pictures(str(root), str(root / "build" / "gen.qrc"), [str(root / "forms" / "art" / "pay.png")])
    (root / "cbcs").mkdir()
    add_pictures(str(root), str(root / "cbcs" / "tool.qrc"), [str(root / "forms" / "art" / "pay.png")])
    shown = project_pictures(("resources.qrc",), str(root / "forms"), str(root))
    assert [p.resource_path for p in shown.mine.pictures] == [":/art/logo.png"]
    assert [p.qrc_name for p in shown.others.pictures] == ["more.qrc"]
    assert shown.qrc_files == ("assets/more.qrc", "forms/resources.qrc")
    assert shown.find(":/pictures/pay.png") is not None
    # A hand-written entry that leaves the project is never listed (or read for a thumbnail).
    (tmp_path / "secret.png").write_bytes(PNG)
    (root / "assets" / "more.qrc").write_text(
        '<RCC><qresource prefix="/"><file>../../secret.png</file></qresource></RCC>', encoding="utf-8"
    )
    clear_picture_cache()
    shown = project_pictures(("resources.qrc",), str(root / "forms"), str(root))
    assert shown.others.pictures == ()


def test_adding_a_raw_path_is_one_undo_step_and_undo_keeps_the_files(tmp_path: Path) -> None:
    root, ui = _project(tmp_path)
    session = _open(root, ui)
    raw = raw_pictures(session.document)[0]
    plan = adopt_raw_picture(session.document, str(ui), str(root), raw)
    assert plan.label == "Add picture logo.png"
    assert plan.notice == "Made forms/resources.qrc for this project's pictures and added logo.png."
    with session.log.transaction(plan.label) as txn:
        for command in plan.commands:
            txn.execute(command)
    logo = session.document.by_name("logo")[0]
    assert session.document.node(logo).value("pixmap") == ResourcePixmap(":/art/logo.png")
    assert [n.field("location") for n in session.document.ui.children("resources")] == ["resources.qrc"]
    assert [d.code for d in picture_diagnostics(session.document, str(ui), str(root))] == ["FB031"]
    assert session.log.undo_label() == "Add picture logo.png"
    assert session.log.undo()
    assert session.document.node(logo).value("pixmap") == ResourcePixmap("art/logo.png")
    assert not session.document.ui.children("resources")
    assert (root / "forms" / "resources.qrc").is_file()


def test_the_icon_fix_changes_only_that_state(tmp_path: Path) -> None:
    root, ui = _project(tmp_path)
    session = _open(root, ui)
    raw = raw_pictures(session.document)[1]
    plan = adopt_raw_picture(session.document, str(ui), str(root), raw)
    with session.log.transaction(plan.label) as txn:
        for command in plan.commands:
            txn.execute(command)
    icon = session.document.node(session.document.by_name("payButton")[0]).value("icon")
    assert icon.normaloff.path == ":/art/pay.png" and icon.normalon.path == ":/pictures/ok.png"


def test_packaging_lists_each_raw_path_as_an_error_row(tmp_path: Path) -> None:
    root, _ui = _project(tmp_path)
    rows = [r for r in inspect_forms(str(root)).files if r.role == "picture"]
    assert [(r.state, r.relative_path, r.source_relative) for r in rows] == [
        ("raw_path", "art/logo.png", "forms/till.ui"),
        ("raw_path", "art/pay.png", "forms/till.ui"),
    ]
    assert rows[0].message == "logo uses a picture from a file path (art/logo.png). A packaged app may not find it."
