"""Add picture: the copy rules, stable ``.qrc`` bytes and the ``*_rc.py`` that follows (UX-RES-002, 004)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.features.form_builder.engine.project.fs import OsFileSystem, ProjectOpError
from app.features.form_builder.engine.project.qrc_write import (
    NOT_A_PICTURE,
    QrcEntry,
    add_entries,
    add_pictures,
    add_prefix,
    new_layout,
    parse_qrc,
    remove_entries,
    render_qrc,
    set_alias,
)
from app.features.form_builder.engine.project.save import rewrite_resource_modules

pytestmark = [pytest.mark.unit]

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True)
    return root


def _source(tmp_path: Path, name: str = "logo.png", data: bytes = PNG) -> str:
    folder = tmp_path / "desktop"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(data)
    return str(path)


def test_first_picture_makes_resources_qrc_copies_the_file_and_lists_it(tmp_path: Path) -> None:
    root = _project(tmp_path)
    source = _source(tmp_path)
    qrc = root / "forms" / "resources.qrc"
    outcome = add_pictures(str(root), str(qrc), [source])
    assert outcome.qrc_created and outcome.qrc_relative == "forms/resources.qrc"
    assert outcome.resource_paths == (":/pictures/logo.png",)
    assert (root / "forms" / "pictures" / "logo.png").read_bytes() == PNG
    assert qrc.read_text(encoding="utf-8") == (
        "<!DOCTYPE RCC>\n"
        '<RCC version="1.0">\n'
        '  <qresource prefix="/">\n'
        "    <file>pictures/logo.png</file>\n"
        "  </qresource>\n"
        "</RCC>\n"
    )
    assert outcome.written == ("forms/resources.qrc", "forms/pictures/logo.png")


def test_a_picture_already_inside_the_qrc_folder_is_listed_where_it_is(tmp_path: Path) -> None:
    root = _project(tmp_path)
    inside = root / "forms" / "art" / "mark.png"
    inside.parent.mkdir()
    inside.write_bytes(PNG)
    outcome = add_pictures(str(root), str(root / "forms" / "resources.qrc"), [str(inside)])
    assert outcome.copied == ()
    assert outcome.resource_paths == (":/art/mark.png",)
    assert not (root / "forms" / "pictures").exists()


def test_same_name_different_bytes_gets_a_number_and_same_bytes_is_reused(tmp_path: Path) -> None:
    root = _project(tmp_path)
    qrc = str(root / "forms" / "resources.qrc")
    first = add_pictures(str(root), qrc, [_source(tmp_path)])
    other = _source(tmp_path / "elsewhere", data=PNG + b"different")
    second = add_pictures(str(root), qrc, [other])
    assert second.resource_paths == (":/pictures/logo_2.png",)
    again = add_pictures(str(root), qrc, [_source(tmp_path)])
    assert again.resource_paths == first.resource_paths
    assert again.copied == () and not again.qrc_created
    text = Path(qrc).read_text(encoding="utf-8")
    assert text.count("<file>pictures/logo.png</file>") == 1
    assert text.count("<file>pictures/logo_2.png</file>") == 1


def test_a_picture_listed_twice_in_one_call_is_listed_once(tmp_path: Path) -> None:
    root = _project(tmp_path)
    source = _source(tmp_path)
    outcome = add_pictures(str(root), str(root / "forms" / "resources.qrc"), [source, source])
    assert outcome.resource_paths == (":/pictures/logo.png", ":/pictures/logo.png")
    assert Path(root / "forms" / "resources.qrc").read_text(encoding="utf-8").count("<file>") == 1


def test_a_file_that_is_not_a_picture_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    root = _project(tmp_path)
    good = _source(tmp_path)
    bad = _source(tmp_path, "notes.txt", b"hello")
    with pytest.raises(ProjectOpError) as error:
        add_pictures(str(root), str(root / "forms" / "resources.qrc"), [good, bad])
    assert str(error.value) == NOT_A_PICTURE
    assert not (root / "forms" / "resources.qrc").exists()
    assert not (root / "forms" / "pictures").exists()


def test_nothing_is_written_outside_the_project(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with pytest.raises(ProjectOpError):
        add_pictures(str(root), str(tmp_path / "other" / "resources.qrc"), [_source(tmp_path)])
    with pytest.raises(ProjectOpError):
        add_pictures(str(root), str(root / "forms" / ".." / ".." / "x.qrc"), [_source(tmp_path)])
    assert not (tmp_path / "other").exists() and not (tmp_path / "x.qrc").exists()


def test_a_failed_qrc_write_puts_back_every_earlier_file(tmp_path: Path) -> None:
    root = _project(tmp_path)

    class Failing(OsFileSystem):
        def write_bytes(self, path: str, data: bytes) -> None:
            if path.endswith(".qrc"):
                raise OSError("disk full")
            super().write_bytes(path, data)

    with pytest.raises(ProjectOpError):
        add_pictures(str(root), str(root / "forms" / "resources.qrc"), [_source(tmp_path)], Failing())
    assert not (root / "forms" / "pictures" / "logo.png").exists()


def test_an_existing_qrc_keeps_its_other_groups_and_only_gains_the_entry(tmp_path: Path) -> None:
    root = _project(tmp_path)
    qrc = root / "forms" / "resources.qrc"
    qrc.write_text(
        '<RCC><qresource prefix="/icons"><file alias="save.png">art/s.png</file></qresource></RCC>',
        encoding="utf-8",
    )
    add_pictures(str(root), str(qrc), [_source(tmp_path)])
    layout = parse_qrc(qrc.read_text(encoding="utf-8"))
    assert [g.prefix for g in layout.groups] == ["/icons", "/"]
    assert layout.groups[0].entries == (QrcEntry("art/s.png", "save.png"),)
    assert layout.groups[1].entries == (QrcEntry("pictures/logo.png"),)


def test_render_is_stable_and_round_trips_empty_groups_and_aliases() -> None:
    layout = add_prefix(new_layout(), "/extra/")
    layout = add_entries(layout, 0, ["pictures/a&b.png"])
    layout = set_alias(layout, 0, 0, "shop_logo.png")
    text = render_qrc(layout)
    assert '<file alias="shop_logo.png">pictures/a&amp;b.png</file>' in text
    assert '<qresource prefix="/extra"/>' in text
    assert parse_qrc(text) == layout
    assert render_qrc(parse_qrc(text)) == text
    assert remove_entries(layout, 0, [0]).groups[0].entries == ()


def test_a_doctype_with_an_entity_is_refused() -> None:
    with pytest.raises(ValueError):
        parse_qrc('<!DOCTYPE RCC [<!ENTITY x "y">]><RCC></RCC>')


def test_rewrite_resource_modules_updates_every_form_that_includes_the_qrc(tmp_path: Path) -> None:
    root = _project(tmp_path)
    qrc = root / "forms" / "resources.qrc"
    add_pictures(str(root), str(qrc), [_source(tmp_path)])
    form = (
        '<ui version="4.0"><class>Till</class><widget class="QWidget" name="Till"/>'
        '<resources><include location="resources.qrc"/></resources></ui>'
    )
    (root / "forms" / "till.ui").write_text(form, encoding="utf-8")
    (root / "forms" / "plain.ui").write_text(
        '<ui version="4.0"><class>Plain</class><widget class="QWidget" name="Plain"/></ui>', encoding="utf-8"
    )
    result = rewrite_resource_modules(str(root), str(qrc))
    rc = root / "forms" / "resources_rc.py"
    assert result.text_written and result.files == (str(rc),)
    first = rc.read_bytes()
    add_pictures(str(root), str(qrc), [_source(tmp_path, "mark.png", PNG + b"2")])
    rewrite_resource_modules(str(root), str(qrc))
    assert rc.read_bytes() != first and b"mark.png" not in first
    assert not (root / "forms" / "ui_till.py").exists()
    assert os.path.getsize(rc) > 0


def test_a_name_that_differs_only_in_case_is_a_clash_on_every_file_system(tmp_path: Path) -> None:
    # ChoreBoy is case-sensitive and macOS is not; the copy must give one answer on both.
    root = _project(tmp_path)
    qrc = str(root / "forms" / "resources.qrc")
    add_pictures(str(root), qrc, [_source(tmp_path, "Logo.png")])
    same_bytes = _source(tmp_path / "other", "logo.png")
    outcome = add_pictures(str(root), qrc, [same_bytes])
    assert outcome.resource_paths == (":/pictures/logo_2.png",)
    assert sorted(os.listdir(root / "forms" / "pictures")) == ["Logo.png", "logo_2.png"]


def test_renaming_a_picture_and_saving_updates_the_forms_that_use_it_and_undo_maps_back(tmp_path: Path) -> None:
    from app.features.form_builder.engine.project.qrc_edit import QrcEditSource

    root = _project(tmp_path)
    qrc = root / "forms" / "resources.qrc"
    add_pictures(str(root), str(qrc), [_source(tmp_path)])
    form = (
        '<ui version="4.0"><class>Till</class><widget class="QWidget" name="Till">'
        '<widget class="QLabel" name="logo"><property name="pixmap">'
        '<pixmap resource="resources.qrc">:/pictures/logo.png</pixmap></property></widget>'
        '<widget class="QPushButton" name="pay"><property name="icon"><iconset resource="resources.qrc">'
        "<normaloff>:/pictures/logo.png</normaloff></iconset></property></widget></widget>"
        '<resources><include location="resources.qrc"/></resources></ui>'
    )
    till = root / "forms" / "till.ui"
    till.write_text(form, encoding="utf-8")
    source = QrcEditSource(qrc.read_text(encoding="utf-8"), str(qrc), str(root))

    def save() -> None:
        text = source.current_text()
        qrc.write_text(text, encoding="utf-8")
        source.mark_saved(text)
        source.after_save()

    source.apply("Rename logo.png", set_alias(source.layout, 0, 0, "brand.png"))
    assert ":/pictures/logo.png" in till.read_text(encoding="utf-8")  # nothing on disk before Save
    save()
    ui = till.read_text(encoding="utf-8")
    assert ":/pictures/logo.png" not in ui and ui.count(":/brand.png") == 2
    assert 'resource="resources.qrc"' in ui
    assert ":/brand.png" in (root / "forms" / "ui_till.py").read_text(encoding="utf-8")
    assert source.info == "Updated 1 form to the new picture name."
    source.undo()
    save()
    assert till.read_text(encoding="utf-8").count(":/pictures/logo.png") == 2
