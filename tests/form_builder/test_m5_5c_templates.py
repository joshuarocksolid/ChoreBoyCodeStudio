# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Saved templates: save, copy into a project, rename, delete (UX-TMPL-001 ... 004). O-logic gate rows."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict

import pytest

from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project import user_templates as ut
from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.engine.project.pictures import picture_uses
from app.features.form_builder.engine.project.qrc_write import parse_qrc
from app.features.form_builder.engine.project.template_use import create_from_template
from app.features.form_builder.engine.ui4.reader import read_ui
from tests.form_builder.inspector.test_m43c_pictures import _png_bytes

pytestmark = pytest.mark.unit

_SHOP = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>ShopWindow</class>
 <widget class="QDialog" name="ShopWindow">
  <property name="windowTitle">
   <string>ShopWindow</string>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="logo">
     <property name="pixmap">
      <pixmap resource="resources.qrc">:/pictures/logo.png</pixmap>
     </property>
    </widget>
   </item>
   <item>
    <widget class="QDialogButtonBox" name="buttonBox">
     <property name="standardButtons">
      <set>QDialogButtonBox::StandardButton::Cancel|QDialogButtonBox::StandardButton::Ok</set>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources>
  <include location="resources.qrc"/>
 </resources>
 <connections>
  <connection>
   <sender>buttonBox</sender>
   <signal>accepted()</signal>
   <receiver>ShopWindow</receiver>
   <slot>accept()</slot>
  </connection>
 </connections>
</ui>
"""

_QRC = """<!DOCTYPE RCC>
<RCC version="1.0">
  <qresource prefix="/">
    <file>pictures/logo.png</file>
  </qresource>
</RCC>
"""


def _digest(folder: Path) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            found[str(path.relative_to(folder))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def _shop(tmp_path: Path, *, name: str = "shop") -> Path:
    root = tmp_path / name
    (root / "forms" / "pictures").mkdir(parents=True)
    (root / "forms" / "pictures" / "logo.png").write_bytes(_png_bytes())
    (root / "forms" / "resources.qrc").write_text(_QRC, encoding="utf-8")
    (root / "forms" / "shop_window.ui").write_text(_SHOP, encoding="utf-8")
    return root


def _save(tmp_path: Path, root: Path, *, name: str = "Shop window", scope: str = ut.SCOPE_USER, **extra) -> ut.TemplateInfo:
    return ut.save_template(
        scope=scope,
        state_root=str(tmp_path / "state"),
        project_root=str(root),
        name=name,
        description="Till and receipts",
        ui_text=(root / "forms" / "shop_window.ui").read_text(encoding="utf-8"),
        ui_path=str(root / "forms" / "shop_window.ui"),
        thumbnail=b"\x89PNG-thumbnail",
        **extra,
    )


def test_save_keeps_the_form_its_pictures_and_a_description(tmp_path: Path) -> None:
    root = _shop(tmp_path)
    info = _save(tmp_path, root)
    folder = Path(info.folder)
    assert folder.parent == tmp_path / "state" / "form_templates"
    assert sorted(path.name for path in folder.iterdir()) == [
        "form.ui",
        "pictures",
        "resources.qrc",
        "template.json",
        "thumbnail.png",
    ]
    assert (folder / "pictures" / "logo.png").read_bytes() == _png_bytes()
    meta = json.loads((folder / "template.json").read_text(encoding="utf-8"))
    assert (meta["name"], meta["description"], meta["root_class"]) == ("Shop window", "Till and receipts", "QDialog")
    layout = parse_qrc((folder / "resources.qrc").read_text(encoding="utf-8"))
    assert [entry.path for group in layout.groups for entry in group.entries] == ["pictures/logo.png"]
    assert info.title == "Shop window" and not info.error


def test_a_name_in_use_asks_and_replace_swaps_the_folder_whole(tmp_path: Path) -> None:
    root = _shop(tmp_path)
    first = _save(tmp_path, root)
    with pytest.raises(ut.TemplateExists) as raised:
        _save(tmp_path, root, name="shop WINDOW")
    assert raised.value.existing.folder == first.folder
    again = _save(tmp_path, root, name="shop WINDOW", replace=True)
    assert again.folder == first.folder and again.name == "shop WINDOW"
    assert [p.name for p in Path(first.folder).parent.iterdir()] == [Path(first.folder).name]


@pytest.mark.parity("R3-184")
def test_a_project_template_is_kept_in_the_project(tmp_path: Path) -> None:
    root = _shop(tmp_path)
    info = _save(tmp_path, root, scope=ut.SCOPE_PROJECT)
    assert Path(info.folder).parent == root / "cbcs" / "form_builder" / "templates"
    listed = ut.list_templates(str(tmp_path / "state"), str(root))
    assert [(item.name, item.scope) for item in listed] == [("Shop window", "project")]
    assert ut.list_templates(str(tmp_path / "state"), str(tmp_path / "elsewhere")) == ()


def test_using_a_template_renames_the_root_and_merges_pictures(tmp_path: Path) -> None:
    source = _shop(tmp_path, name="shop")
    info = _save(tmp_path, source)
    target = tmp_path / "office"
    (target / "forms").mkdir(parents=True)
    before = _digest(Path(info.folder))
    made = create_from_template(str(target), info, "back_office", OsFileSystem())
    assert made.result.refused is None
    ui = (target / "forms" / "back_office.ui").read_text(encoding="utf-8")
    document = read_ui(ui, allocator=IdAllocator()).document
    assert document.root.object_name == "BackOffice" and document.form_class_name() == "BackOffice"
    assert [use.path for use in picture_uses(document)] == [":/pictures/logo.png"]
    assert "<receiver>BackOffice</receiver>" in ui and "<string>BackOffice</string>" in ui
    assert (target / "forms" / "pictures" / "logo.png").read_bytes() == _png_bytes()
    assert '<include location="resources.qrc"/>' in ui
    assert (target / "forms" / "ui_back_office.py").is_file() and (target / "forms" / "back_office_window.py").is_file()
    assert _digest(Path(info.folder)) == before, "the template is read, never written"


def test_a_picture_name_that_is_taken_gets_a_number_and_nothing_is_overwritten(tmp_path: Path) -> None:
    info = _save(tmp_path, _shop(tmp_path, name="shop"))
    target = tmp_path / "office"
    pictures = target / "forms" / "pictures"
    pictures.mkdir(parents=True)
    other = b"not the shop logo"
    (pictures / "logo.png").write_bytes(other)
    (target / "forms" / "resources.qrc").write_text(_QRC, encoding="utf-8")
    kept_qrc = (target / "forms" / "resources.qrc").read_text(encoding="utf-8")
    made = create_from_template(str(target), info, "back_office", OsFileSystem())
    assert made.result.refused is None
    assert (pictures / "logo.png").read_bytes() == other
    assert (pictures / "logo_2.png").read_bytes() == _png_bytes()
    document = read_ui((target / "forms" / "back_office.ui").read_text(encoding="utf-8"), allocator=IdAllocator()).document
    assert [use.path for use in picture_uses(document)] == [":/pictures/logo_2.png"]
    now = (target / "forms" / "resources.qrc").read_text(encoding="utf-8")
    assert "pictures/logo.png" in now and "pictures/logo_2.png" in now and kept_qrc.count("logo.png") == 1


def test_the_same_picture_already_in_the_project_is_reused(tmp_path: Path) -> None:
    info = _save(tmp_path, _shop(tmp_path, name="shop"))
    target = _shop(tmp_path, name="office")
    (target / "forms" / "shop_window.ui").unlink()
    made = create_from_template(str(target), info, "back_office", OsFileSystem())
    assert made.result.refused is None
    assert sorted(p.name for p in (target / "forms" / "pictures").iterdir()) == ["logo.png"]


def test_a_case_only_clash_never_reuses_or_writes_the_other_file(tmp_path: Path) -> None:
    info = _save(tmp_path, _shop(tmp_path, name="shop"))
    target = tmp_path / "office"
    (target / "forms" / "pictures").mkdir(parents=True)
    (target / "forms" / "pictures" / "Logo.png").write_bytes(b"capital")
    made = create_from_template(str(target), info, "back_office", OsFileSystem())
    assert made.result.refused is None
    assert (target / "forms" / "pictures" / "Logo.png").read_bytes() == b"capital"
    assert (target / "forms" / "pictures" / "logo_2.png").read_bytes() == _png_bytes()


def test_a_refused_name_copies_no_picture(tmp_path: Path) -> None:
    info = _save(tmp_path, _shop(tmp_path, name="shop"))
    target = tmp_path / "office"
    (target / "forms").mkdir(parents=True)
    made = create_from_template(str(target), info, "not a name", OsFileSystem())
    assert made.result.refused
    assert sorted(p.name for p in (target / "forms").iterdir()) == []


def test_a_failed_create_puts_the_pictures_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.form_builder.engine.project import template_use

    info = _save(tmp_path, _shop(tmp_path, name="shop"))
    target = tmp_path / "office"
    (target / "forms").mkdir(parents=True)
    kept = "<!DOCTYPE RCC>\n<RCC version=\"1.0\">\n  <qresource prefix=\"/\"/>\n</RCC>\n"
    (target / "forms" / "resources.qrc").write_text(kept, encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(template_use, "create_form", lambda *a, **k: template_use.CreateResult((), (), None, "no"))
    made = create_from_template(str(target), info, "back_office", OsFileSystem())
    assert made.result.refused == "no"
    assert not (target / "forms" / "pictures" / "logo.png").exists()
    assert (target / "forms" / "resources.qrc").read_text(encoding="utf-8") == kept


def test_rename_and_description_touch_template_json_only(tmp_path: Path) -> None:
    info = _save(tmp_path, _shop(tmp_path))
    state = str(tmp_path / "state")
    before = _digest(Path(info.folder))
    renamed = ut.rename_template(info, "Till window", state_root=state, project_root=None)
    described = ut.change_description(renamed, "Tills")
    assert (described.name, described.description, described.folder) == ("Till window", "Tills", info.folder)
    after = _digest(Path(info.folder))
    assert {k for k in after if after[k] != before[k]} == {"template.json"}


def test_delete_removes_that_folder_only(tmp_path: Path) -> None:
    root = _shop(tmp_path)
    one = _save(tmp_path, root, name="One")
    two = _save(tmp_path, root, name="Two")
    state = str(tmp_path / "state")
    form = root / "forms" / "shop_window.ui"
    kept = form.read_bytes()
    ut.delete_template(one, state_root=state, project_root=str(root))
    assert not Path(one.folder).exists() and Path(two.folder).is_dir()
    assert form.read_bytes() == kept and (root / "forms" / "pictures" / "logo.png").is_file()
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "keep.txt").write_text("x")
    forged = ut.TemplateInfo(ut.SCOPE_USER, str(outside), "x")
    with pytest.raises(ProjectOpError):
        ut.delete_template(forged, state_root=state, project_root=str(root))
    assert (outside / "keep.txt").is_file()


def test_delete_of_a_symlinked_template_unlinks_the_link_not_the_target(tmp_path: Path) -> None:
    state = tmp_path / "state"
    templates = state / "form_templates"
    templates.mkdir(parents=True)
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("x")
    link = templates / "linked"
    os.symlink(target, link)
    info = ut.TemplateInfo(ut.SCOPE_USER, str(link), "linked")
    ut.delete_template(info, state_root=str(state), project_root=None)
    assert not link.exists() and (target / "keep.txt").is_file()


def test_a_template_that_cannot_be_read_is_listed_with_its_reason(tmp_path: Path) -> None:
    state = tmp_path / "state"
    broken = state / "form_templates" / "oops"
    broken.mkdir(parents=True)
    (broken / "template.json").write_text("{not json", encoding="utf-8")
    (listed,) = ut.list_templates(str(state), None)
    assert listed.title == "Can't open oops" and "template.json" in listed.error
    with pytest.raises(ProjectOpError):
        ut.rename_template(listed, "x", state_root=str(state), project_root=None)
    made = create_from_template(str(tmp_path), listed, "new_form", OsFileSystem())
    assert made.result.refused and "can't be opened" in made.result.refused


def test_a_template_never_copies_files_from_outside_its_pictures_folder(tmp_path: Path) -> None:
    """A dropped-in template whose form names ``../`` pictures, or whose picture is a symlink out, copies nothing."""
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"not for the project")
    templates = tmp_path / "state" / "form_templates"
    for key, form_path in (("climb", ":/pictures/../../../../secret.png"), ("linked", ":/pictures/logo.png")):
        folder = templates / key
        (folder / "pictures").mkdir(parents=True)
        (folder / "template.json").write_text(json.dumps({"name": key}), encoding="utf-8")
        (folder / "form.ui").write_text(_SHOP.replace(":/pictures/logo.png", form_path), encoding="utf-8")
    os.symlink(secret, templates / "linked" / "pictures" / "logo.png")
    for key in ("climb", "linked"):
        target = tmp_path / ("project_" + key)
        (target / "forms").mkdir(parents=True)
        made = create_from_template(str(target), ut.read_template(str(templates / key), ut.SCOPE_USER), "shop", OsFileSystem())
        assert made.result.refused is None
        copied = [path.read_bytes() for path in target.rglob("*.png")]
        assert copied == [], key


def test_a_huge_template_json_name_is_cut_to_the_name_limit(tmp_path: Path) -> None:
    folder = tmp_path / "state" / "form_templates" / "huge"
    folder.mkdir(parents=True)
    (folder / "template.json").write_text(json.dumps({"name": "N" * 50000, "description": "d" * 5000}), encoding="utf-8")
    (folder / "form.ui").write_text(_SHOP, encoding="utf-8")
    info = ut.read_template(str(folder), ut.SCOPE_USER)
    assert (len(info.name), len(info.description), info.error) == (ut.NAME_LIMIT, ut.DESCRIPTION_LIMIT, "")
