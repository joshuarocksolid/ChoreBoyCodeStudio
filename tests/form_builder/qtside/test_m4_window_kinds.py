# pyright: reportAttributeAccessIssue=false
"""UX-CAT-015 and R3-111/112/121-shape: window kinds build round-trip forms that match uic.

The New form cards for Main window, Dialog and Wizard are checked the way the file
is written: create_form writes the card's text, the form reads back, the uic oracle
builds the same tree, and a second save is byte-identical.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.features.form_builder.engine.project.create import create_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.names import class_name_for_stem
from app.features.form_builder.engine.project.templates import build_template_ui
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.qtside.start.wizard import WIZARD_KEY, wizard_document
from tests.form_builder.qtside.support import open_session

_UIC = Path("/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic")


def _oracle() -> None:
    override = os.environ.get("CBCS_FB_UIC")
    if override and Path(override).is_file():
        return
    if _UIC.is_file():
        os.environ.setdefault("CBCS_FB_UIC", str(_UIC))
        return
    pytest.skip("uic is not available; set CBCS_FB_UIC")


def _check_round_trip(path: Path, text: str) -> None:
    from tests.form_builder.engine.codegen.uic_compare import compare  # pyright: ignore[reportMissingImports]

    path.write_text(text, encoding="utf-8")
    outcome = compare(path)
    assert outcome[0] == "ok", outcome
    again = open_session(text, str(path))
    try:
        assert again.text() == text
    finally:
        again.dispose()


def _create(tmp_path: Path, stem: str, template: str, text: str | None = None) -> str:
    root = tmp_path / "shop"
    (root / "cbcs").mkdir(parents=True)
    (root / "cbcs" / "project.json").write_text("{}", encoding="utf-8")
    result = create_form(str(root), stem, OsFileSystem(), template=template, directory=str(root / "forms"), ui_text=text)
    assert not result.refused, result.refused
    assert result.scope is not None
    return Path(result.scope.ui_path).read_text(encoding="utf-8")


@pytest.mark.parity("R3-111")
def test_a_main_window_form_round_trips_and_matches_uic(tmp_path: Path) -> None:
    _oracle()
    text = _create(tmp_path, "shop_main", "main_window")
    assert 'class="QMainWindow"' in text
    _check_round_trip(tmp_path / "shop_main.ui", text)


@pytest.mark.parity("R3-112")
def test_a_dialog_form_round_trips_and_matches_uic(tmp_path: Path) -> None:
    _oracle()
    text = _create(tmp_path, "shop_dialog", "dialog")
    assert 'class="QDialog"' in text
    _check_round_trip(tmp_path / "shop_dialog.ui", text)


def test_the_wizard_card_creates_a_qwizard_with_two_pages(tmp_path: Path) -> None:
    _oracle()
    stem = "shop_wizard"
    text = _create(tmp_path, stem, "widget", wizard_document(class_name_for_stem(stem)))
    session = open_session(text, str(tmp_path / "shop_wizard.ui"))
    try:
        root = session.document.root
        assert root.class_name == "QWizard"
        pages = [child for child in session.document.iter_preorder() if isinstance(child, WidgetNode) and child.class_name == "QWizardPage"]
        assert [page.object_name for page in pages] == ["wizardPage", "wizardPage_2"]
        titles = [str(entry.value.text) for page in pages for entry in page.properties() if entry.name == "title"]
        assert titles == ["Step 1", "Step 2"]
    finally:
        session.dispose()
    _check_round_trip(tmp_path / "shop_wizard.ui", text)


def test_the_wizard_card_key_is_not_an_engine_template() -> None:
    """The Wizard card is finished .ui text from qtside/start (the engine table is M4.2's to change)."""
    assert WIZARD_KEY == "wizard"
    assert build_template_ui("widget", "Shop").count("QWidget") >= 1
    with pytest.raises(KeyError):
        build_template_ui("wizard", "Shop")
