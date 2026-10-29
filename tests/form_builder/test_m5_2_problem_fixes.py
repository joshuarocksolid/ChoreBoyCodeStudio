# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""FB031/FB032 in Problems with their fix buttons, packaging errors, and P-9 end to end."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import List

import pytest

from app.features.form_builder.engine.project.forms import classify_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.packaging import adopt_pictures_now, inspect_forms
from app.features.form_builder.engine.project.save import write_generated
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.integration.problem_fixes import FixContext, default_registry
from app.features.form_builder.integration.problems_bridge import code_diagnostics_for_form, fixes_for, run_fix
from app.features.form_builder.integration.qrc_provider import attach_picture_checks
from app.packaging.form_files import add_packaged_pictures, form_packaging_issues
from app.qt.QtUiTools import QUiLoader
from app.qt.QtWidgets import QPushButton, QWidget
from tests.form_builder.inspector.test_m43c_pictures import _png_bytes

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Till</class>
 <widget class="QWidget" name="Till">
  <widget class="QPushButton" name="payButton">
   <property name="icon">
    <iconset>
     <normaloff>art/pay.png</normaloff>
    </iconset>
   </property>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _shop(tmp_path: Path) -> Path:
    root = tmp_path / "shop"
    (root / "forms" / "art").mkdir(parents=True)
    (root / "forms" / "art" / "pay.png").write_bytes(_png_bytes())
    (root / "forms" / "till.ui").write_text(_FORM, encoding="utf-8")
    return root


class _Surface:
    def __init__(self) -> None:
        self.said: List[str] = []

    def show_plain(self, sentence: str) -> None:
        self.said.append(sentence)


def _session(root: Path) -> FormSession:
    ui = root / "forms" / "till.ui"
    return FormSession.open(ui.read_text(encoding="utf-8"), path=str(ui), scope=classify_form(str(ui), project_root=str(root)))


def test_fb031_shows_in_problems_with_its_fix_and_the_fix_clears_it(tmp_path: Path) -> None:
    root = _shop(tmp_path)
    session = _session(root)
    attach_picture_checks(session, str(root))
    (row,) = [d for d in session.diagnostics.all() if d.code == "FB031"]
    assert row.message == "payButton uses a picture from a file path (art/pay.png). A packaged app may not find it."
    assert fixes_for(row) == (("add-to-project-pictures", "Add to project pictures"),)
    rows = code_diagnostics_for_form(str(root / "forms" / "till.ui"), session.diagnostics.all())
    assert rows[0].severity.value == "warning"
    surface = _Surface()
    steps = len(session.log.entries())
    assert run_fix(row, "add-to-project-pictures", FixContext(row, session, str(root), surface))
    assert len(session.log.entries()) == steps + 1
    assert session.log.undo_label() == "Add picture pay.png"
    assert [d.code for d in session.diagnostics.all()] == []
    assert surface.said == ["Made forms/resources.qrc for this project's pictures and added pay.png."]
    assert session.log.undo()
    assert [d.code for d in session.diagnostics.all()] == ["FB031"]


def test_fb032_names_the_pictures_file_and_offers_to_open_it(tmp_path: Path) -> None:
    root = _shop(tmp_path)
    (root / "forms" / "resources.qrc").write_text(
        '<RCC><qresource prefix="/"><file>art/pay.png</file><file>art/gone.png</file></qresource></RCC>',
        encoding="utf-8",
    )
    ui = root / "forms" / "till.ui"
    ui.write_text(_FORM.replace("<resources/>", '<resources><include location="resources.qrc"/></resources>'), encoding="utf-8")
    session = _session(root)
    attach_picture_checks(session, str(root))
    (problem,) = [d for d in session.diagnostics.all() if d.code == "FB032"]
    assert problem.message == "forms/resources.qrc lists art/gone.png, but the file is missing."
    assert problem.severity.value == "warning"
    assert fixes_for(problem) == (("open-pictures-file", "Open forms/resources.qrc"),)
    opened: List[str] = []
    anchor = QWidget()
    anchor._request = type("R", (), {"open_linked_file": staticmethod(opened.append)})()
    assert run_fix(problem, "open-pictures-file", FixContext(problem, session, str(root), anchor))
    assert opened == [str(root / "forms" / "resources.qrc")]


def test_both_codes_are_registered_for_the_default_registry() -> None:
    assert {"FB031", "FB032"} <= set(default_registry().codes())


def test_packaging_blocks_a_file_path_picture_and_the_fix_clears_the_error(tmp_path: Path) -> None:
    root = _shop(tmp_path)
    issues = [i for i in form_packaging_issues(str(root)) if i.issue_id == "package.form.picture_path"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == "blocking" and issue.title == "A picture uses a file path"
    assert issue.summary == "payButton uses a picture from a file path (art/pay.png). A packaged app may not find it."
    assert issue.evidence["fix_action"] == "add_pictures"
    ui = str(root / "forms" / "till.ui")
    assert add_packaged_pictures(str(root), ui) == ""
    assert [r for r in inspect_forms(str(root)).files if r.role == "picture"] == []
    assert "<normaloff>:/art/pay.png</normaloff>" in (root / "forms" / "till.ui").read_text(encoding="utf-8")
    assert (root / "forms" / "resources.qrc").is_file() and (root / "forms" / "ui_till.py").is_file()
    assert [i for i in form_packaging_issues(str(root)) if i.issue_id == "package.form.picture_path"] == []


def test_a_missing_file_is_reported_and_nothing_changes(tmp_path: Path) -> None:
    root = _shop(tmp_path)
    (root / "forms" / "art" / "pay.png").unlink()
    ui = root / "forms" / "till.ui"
    assert adopt_pictures_now(str(root), str(ui)) == (0, "Code Studio can't find pay.png.")
    assert ui.read_text(encoding="utf-8") == _FORM


@pytest.mark.pain("P-9")
@pytest.mark.parity("R3-174", "R3-175")
def test_p9_save_is_never_blocked_packaging_is_and_the_icon_shows_once_it_is_in_the_qrc(
    qapp, tmp_path: Path  # type: ignore[no-untyped-def]
) -> None:
    del qapp
    root = _shop(tmp_path)
    ui = root / "forms" / "till.ui"
    session = _session(root)
    scope = session.scope
    # Save with a file-path icon: not blocked, and Problems warns.
    attach_picture_checks(session, str(root))
    saved = write_generated(scope, session.document, ui.read_bytes(), OsFileSystem())
    assert saved.text_written
    assert [d.severity.value for d in session.diagnostics.all()] == ["warning"]
    assert any(i.issue_id == "package.form.picture_path" for i in form_packaging_issues(str(root)))
    # The fix puts the icon in a pictures file; the saved Python registers it, and a loader shows it.
    assert add_packaged_pictures(str(root), str(ui)) == ""
    rc = root / "forms" / "resources_rc.py"
    assert rc.is_file()
    namespace = runpy.run_path(str(rc))
    try:
        loaded = QUiLoader().load(str(ui))
        button = loaded.findChild(QPushButton, "payButton")
        assert button is not None and not button.icon().isNull()
        loaded.deleteLater()
    finally:
        namespace["qCleanupResources"]()
