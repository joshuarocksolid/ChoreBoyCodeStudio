# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""The form inspector's pictures-files group (UX-RES-006)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.project.qrc_write import add_pictures
from app.features.form_builder.engine.query.selection import SelectionSource
from app.qt.QtWidgets import QLabel, QPushButton, QToolButton, QWidget
from tests.form_builder.inspector.test_m43c_pictures import _close, _png_bytes
from tests.form_builder.inspector.test_m5_2_add_picture import _open

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


def _group(pane, session):  # type: ignore[no-untyped-def]
    session.selection.clear(source=SelectionSource.PROGRAM)
    pane.flush()
    body = pane.findChild(QWidget, "formBuilder.picturesFiles")
    assert body is not None
    return body


@pytest.fixture()
def shop(tmp_path: Path) -> Path:
    root = tmp_path / "shop"
    root.mkdir()
    (tmp_path / "logo.png").write_bytes(_png_bytes())
    (tmp_path / "mark.png").write_bytes(_png_bytes() + b"")
    add_pictures(str(root), str(root / "assets" / "more.qrc"), [str(tmp_path / "mark.png")])
    return root


def test_the_group_lists_included_files_with_counts_and_offers_the_others(qapp, shop: Path) -> None:  # type: ignore[no-untyped-def]
    add_pictures(str(shop), str(shop / "forms" / "resources.qrc"), [str(shop.parent / "logo.png")])
    window, pane, session, realizer, _toasts = _open(qapp, shop)
    try:
        from app.features.form_builder.engine.project.picture_adopt import include_commands

        with session.log.transaction("x") as txn:
            for command in include_commands(session.document, session.path, str(shop / "forms" / "resources.qrc")):
                txn.execute(command)
        body = _group(pane, session)
        text = body.findChild(QLabel, "formBuilder.picturesFileText")
        assert text.text() == "Pictures from forms/resources.qrc · 1 picture"
        use = body.findChild(QPushButton, "formBuilder.picturesFilesUse")
        assert [a.text() for a in use.menu().actions()] == ["assets/more.qrc"]
        steps = len(session.log.entries())
        use.menu().actions()[0].trigger()
        assert len(session.log.entries()) == steps + 1
        assert session.log.undo_label() == "Use pictures file assets/more.qrc"
        assert 'location="../assets/more.qrc"' in session.text()
    finally:
        _close(window, pane, realizer, session, qapp)


def test_stop_using_asks_when_properties_use_its_pictures_and_is_one_step(qapp, shop: Path) -> None:  # type: ignore[no-untyped-def]
    window, pane, session, realizer, _toasts = _open(qapp, shop)
    try:
        from app.features.form_builder.engine.commands.catalog import SetProperty, SetResourceIncludes
        from app.features.form_builder.engine.ui4.values import ResourcePixmap

        with session.log.transaction("setup") as txn:
            txn.execute(SetResourceIncludes(("../assets/more.qrc",)))
            txn.execute(SetProperty(session.document.by_name("logo")[0], "pixmap", ResourcePixmap(":/pictures/mark.png")))
        body = _group(pane, session)
        from app.features.form_builder.qtside.inspector.editors import form_files

        asked = []
        steps = len(session.log.entries())
        group = pane.findChild(QWidget, "formBuilder.formGroup.pictures")
        assert group is not None
        # The prompt sentence is the spec's; Cancel leaves the form alone.
        assert form_files.stop_prompt(2) == "2 properties use pictures from this file. They will show as missing."
        assert form_files.stop_prompt(1) == "1 property uses pictures from this file. They will show as missing."
        files_body = [c for c in (getattr(group, "_custom", None),) if c][0]
        files_body.stop("../assets/more.qrc", "assets/more.qrc", (":/pictures/mark.png",), ask=lambda n: asked.append(n) or False)
        assert asked == [1] and len(session.log.entries()) == steps
        files_body.stop("../assets/more.qrc", "assets/more.qrc", (":/pictures/mark.png",), ask=lambda n: True)
        assert len(session.log.entries()) == steps + 1
        assert session.log.undo_label() == "Stop using pictures file assets/more.qrc"
        assert "more.qrc" not in session.text()
    finally:
        _close(window, pane, realizer, session, qapp)
