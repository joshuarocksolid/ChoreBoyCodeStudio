"""The read-only ``.qrc`` picture index: prefixes, aliases, missing files."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.features.form_builder.engine.project.pictures import (
    clear_picture_cache,
    file_name_of,
    index_for_document,
    is_missing,
    load_pictures,
    lookup_stored,
    resource_path,
)

pytestmark = pytest.mark.unit

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x00\x03\x00\x01\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_prefix_alias_nested_path_and_a_header_without_an_extension(tmp_path: Path) -> None:
    icons = tmp_path / "icons"
    nested = icons / "actions"
    nested.mkdir(parents=True)
    (nested / "save.png").write_bytes(_PNG)
    (icons / "dot.png").write_bytes(_PNG)
    bare = icons / "bare"
    bare.write_bytes(_PNG)
    qrc = tmp_path / "app.qrc"
    qrc.write_text(
        """<!DOCTYPE RCC><RCC version="1.0">
<qresource prefix="/icons">
 <file>icons/dot.png</file>
 <file alias="save.png">icons/actions/save.png</file>
 <file>icons/bare</file>
</qresource>
</RCC>
""",
        encoding="utf-8",
    )
    index = load_pictures((str(qrc),), str(tmp_path))
    assert index.issues == ()
    by_name = {item.file_name: item for item in index.pictures}
    assert set(by_name) == {"dot.png", "save.png", "bare"}
    assert by_name["dot.png"].resource_path == ":/icons/icons/dot.png"
    assert by_name["save.png"].resource_path == ":/icons/save.png"
    assert by_name["save.png"].disk_path == str(nested / "save.png")
    assert by_name["bare"].resource_path == ":/icons/icons/bare"
    assert is_missing(by_name["save.png"]) is False
    assert resource_path("icons", "save.png", "icons/actions/save.png") == ":/icons/save.png"


def test_a_missing_image_stays_in_the_index(tmp_path: Path) -> None:
    qrc = tmp_path / "app.qrc"
    qrc.write_text(
        """<RCC version="1.0"><qresource prefix="icons">
 <file>gone.png</file>
</qresource></RCC>
""",
        encoding="utf-8",
    )
    index = load_pictures(("app.qrc",), str(tmp_path))
    assert len(index.pictures) == 1
    picture = index.pictures[0]
    assert picture.resource_path == ":/icons/gone.png"
    assert is_missing(picture) is True
    disk, missing = lookup_stored(":/icons/gone.png", str(tmp_path), index)
    assert disk == "" and missing is True


def test_a_malformed_qrc_is_a_sentence(tmp_path: Path) -> None:
    qrc = tmp_path / "bad.qrc"
    qrc.write_text("<RCC><qresource>", encoding="utf-8")
    index = load_pictures((str(qrc),), str(tmp_path))
    assert index.pictures == ()
    assert len(index.issues) == 1
    assert index.issues[0].sentence == "bad.qrc is not a valid resource file."


def test_two_qrc_files_keep_their_own_prefixes(tmp_path: Path) -> None:
    (tmp_path / "a.png").write_bytes(_PNG)
    (tmp_path / "b.png").write_bytes(_PNG)
    first = tmp_path / "one.qrc"
    second = tmp_path / "two.qrc"
    first.write_text(
        '<RCC><qresource prefix="one"><file>a.png</file></qresource></RCC>',
        encoding="utf-8",
    )
    second.write_text(
        '<RCC><qresource prefix="two"><file alias="alias.png">b.png</file></qresource></RCC>',
        encoding="utf-8",
    )
    index = load_pictures(("one.qrc", "two.qrc"), str(tmp_path))
    found = {item.resource_path: item.qrc_name for item in index.pictures}
    assert found == {":/one/a.png": "one.qrc", ":/two/alias.png": "two.qrc"}


def test_cache_follows_mtime_and_a_missing_qrc_is_not_cached_as_valid(tmp_path: Path) -> None:
    clear_picture_cache()
    qrc = tmp_path / "app.qrc"
    qrc.write_text(
        '<RCC><qresource prefix="icons"><file>a.png</file></qresource></RCC>',
        encoding="utf-8",
    )
    (tmp_path / "a.png").write_bytes(_PNG)
    first = load_pictures((str(qrc),), str(tmp_path))
    assert first.pictures[0].file_name == "a.png"
    qrc.write_text(
        '<RCC><qresource prefix="icons"><file alias="renamed.png">a.png</file></qresource></RCC>',
        encoding="utf-8",
    )
    stamped = qrc.stat().st_mtime_ns + 1000
    os.utime(qrc, ns=(stamped, stamped))
    second = load_pictures((str(qrc),), str(tmp_path))
    assert second.pictures[0].file_name == "renamed.png"
    absent = load_pictures(("nope.qrc",), str(tmp_path))
    assert absent.issues[0].sentence == "Code Studio can't find nope.qrc."
    assert file_name_of(":/icons/renamed.png") == "renamed.png"


def test_form_includes_are_read_from_the_document(tmp_path: Path) -> None:
    from app.features.form_builder.engine.ui4.reader import read_ui
    from app.features.form_builder.engine.ids import IdAllocator

    (tmp_path / "dot.png").write_bytes(_PNG)
    (tmp_path / "app.qrc").write_text(
        '<RCC><qresource><file>dot.png</file></qresource></RCC>',
        encoding="utf-8",
    )
    text = """<?xml version="1.0"?>
<ui version="4.0"><class>Form</class>
 <widget class="QWidget" name="Form"/>
 <resources><include location="app.qrc"/></resources>
 <connections/>
</ui>
"""
    document = read_ui(text, allocator=IdAllocator()).document
    index = index_for_document(document, str(tmp_path))
    assert [item.resource_path for item in index.pictures] == [":/dot.png"]
    disk, missing = lookup_stored("dot.png", str(tmp_path), index)
    assert missing is False and disk.endswith("dot.png")
