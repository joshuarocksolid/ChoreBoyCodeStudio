# pyright: reportAttributeAccessIssue=false
"""Tab stops and buddies the builder writes match ``uic -g python`` (UX-OVL-006, R3-10, R3-12, R3-8).

A form is edited with the M5.6 commands (a new tab order, an input inserted into
it, labels paired) and compared to the Designer tool. Needs ``CBCS_FB_UIC``;
skipped without it.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.features.form_builder.engine.commands.catalog import InsertFragment
from app.features.form_builder.engine.commands.catalog_ext.tab_order import ChangeTabOrder, PairLabels, SetLabelBuddy
from app.features.form_builder.engine.commands.placement import InFormRow
from app.features.form_builder.engine.query import tab_stops as q
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.engine.commands._support import button_spec, nid, open_log
from tests.form_builder.engine.test_m5_6_tab_order import ROWS

pytestmark = pytest.mark.unit

_HERE = Path(__file__).resolve().parent


def _load_helper(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_uic = _load_helper("cbcs_uic_compare_m56", _HERE / "uic_compare.py")


@pytest.fixture
def uic_env(monkeypatch):  # type: ignore[no-untyped-def]
    uic = os.environ.get("CBCS_FB_UIC", "") or "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic"
    if not Path(uic).is_file():
        pytest.skip("CBCS_FB_UIC is not set")
    monkeypatch.setenv("CBCS_FB_UIC", uic)


def _oracle(tmp_path: Path, text: str) -> None:
    path = tmp_path / "form.ui"
    path.write_text(text, encoding="utf-8")
    result = _uic.compare(path)
    assert result[0] == "ok", result


@pytest.mark.oracle
@pytest.mark.parity("R3-10", "R3-12")
def test_a_written_tab_order_and_a_spliced_input_match_uic(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(ROWS)
    doc = log.document
    log.execute(ChangeTabOrder(("phoneEdit", "nameEdit", "emailEdit")))
    layout = doc.by_name("formLayout")[0]
    log.execute(InsertFragment(InFormRow(layout, 1, "field", insert_row=True), Fragment(nodes=(button_spec("extraButton"),))))
    order = q.stops(doc)
    assert [stop.name for stop in order][:3] == ["phoneEdit", "nameEdit", "extraButton"]
    _oracle(tmp_path, write_ui(doc).text)


@pytest.mark.oracle
@pytest.mark.parity("R3-8", "R3-9")
def test_buddies_set_by_the_commands_match_uic(tmp_path: Path, qapp, uic_env) -> None:  # type: ignore[no-untyped-def]
    del qapp, uic_env
    log = open_log(ROWS)
    doc = log.document
    log.execute(PairLabels(q.form_row_pairs(doc)))
    log.execute(SetLabelBuddy(nid(doc, "note"), "nameEdit", "Note"))
    log.execute(SetLabelBuddy(nid(doc, "emailLabel"), None, "Email"))
    _oracle(tmp_path, write_ui(doc).text)
