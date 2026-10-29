"""Picture files dropped on a label, a button or the form (UX-RES-003)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine.project.forms import classify_form
from app.features.form_builder.engine.project.fs import ProjectOpError
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.values import IconSetValue, ResourcePixmap
from app.features.form_builder.qtside.resources.drops import plan_file_drop
from tests.form_builder.inspector.test_m43c_pictures import _png_bytes

pytestmark = [pytest.mark.unit]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0"><class>Till</class>
 <widget class="QWidget" name="Till">
  <widget class="QLabel" name="logo"/>
  <widget class="QPushButton" name="payButton"/>
  <widget class="QLineEdit" name="note"/>
 </widget><resources/><connections/></ui>
"""


def _open(tmp_path: Path):  # type: ignore[no-untyped-def]
    root = tmp_path / "shop"
    (root / "forms").mkdir(parents=True)
    ui = root / "forms" / "till.ui"
    ui.write_text(_FORM, encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(_png_bytes())
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    session = FormSession.open(_FORM, path=str(ui), scope=classify_form(str(ui), project_root=str(root)))
    return root, ui, session


@pytest.mark.parametrize(
    "target,property_name,kind",
    [("logo", "pixmap", ResourcePixmap), ("payButton", "icon", IconSetValue), ("Till", "windowIcon", IconSetValue)],
)
def test_a_dropped_picture_sets_the_targets_picture_in_one_step(tmp_path: Path, target: str, property_name: str, kind: type) -> None:
    root, ui, session = _open(tmp_path)
    drop = plan_file_drop(session.document, str(ui), str(root), session.document.by_name(target)[0], [str(tmp_path / "logo.png")])
    with session.log.transaction(drop.label) as txn:
        for command in drop.commands:
            txn.execute(command)
    value = session.document.node(session.document.by_name(target)[0]).value(property_name)
    assert isinstance(value, kind)
    assert (root / "forms" / "pictures" / "logo.png").is_file()
    assert session.log.undo_label() == "Add picture logo.png" and len(session.log.entries()) == 1


def test_a_file_that_is_not_a_picture_is_refused_with_the_spec_sentence(tmp_path: Path) -> None:
    root, ui, session = _open(tmp_path)
    with pytest.raises(ProjectOpError) as error:
        plan_file_drop(session.document, str(ui), str(root), session.document.by_name("logo")[0], [str(tmp_path / "notes.txt")])
    assert str(error.value) == "Only pictures can go here."
    assert not (root / "forms" / "resources.qrc").exists()


def test_a_widget_that_shows_no_picture_takes_none(tmp_path: Path) -> None:
    root, ui, session = _open(tmp_path)
    with pytest.raises(ProjectOpError):
        plan_file_drop(session.document, str(ui), str(root), session.document.by_name("note")[0], [str(tmp_path / "logo.png")])


@pytest.mark.xfail(
    strict=True,
    reason="M5.1 owns qtside/canvas/**: the canvas exposes no file-drop hook yet. Expected contract: "
    "qtside/canvas/file_drops.py register_file_drop(handler) with handler(target_id, paths) -> Optional[str]",
)
def test_the_canvas_hands_file_drops_to_a_registered_handler() -> None:
    from app.features.form_builder.qtside.canvas import file_drops

    assert callable(file_drops.register_file_drop)
