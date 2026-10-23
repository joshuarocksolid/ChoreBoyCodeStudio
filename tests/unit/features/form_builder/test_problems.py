"""Form problems reach the shell Problems panel, and a row finds its widget."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.editors.editor_manager import EditorManager  # noqa: E402
from app.features.form_builder.engine.codegen.api import generate_form_module  # noqa: E402
from app.features.form_builder.engine.diagnostics import (  # noqa: E402
    DiagnosticLocation,
    DiagnosticsStore,
    FormDiagnostic,
    Severity,
)
from app.features.form_builder.engine.ids import IdAllocator, NodeId  # noqa: E402
from app.features.form_builder.engine.project.forms import classify_form  # noqa: E402
from app.features.form_builder.engine.ui4.reader import read_ui  # noqa: E402
from app.features.form_builder.engine.ui4.writer import write_ui  # noqa: E402
from app.features.form_builder.integration.chrome_text import (  # noqa: E402
    problem_property_sentence,
    problem_summary,
)
from app.features.form_builder.integration.content_source import open_document_log  # noqa: E402
from app.features.form_builder.integration.problems_bridge import (  # noqa: E402
    ProblemsBridge,
    to_code_diagnostics,
)
from app.features.form_builder.integration.provider import FormTabProvider  # noqa: E402
from app.features.form_builder.integration.surface import FormSurface  # noqa: E402
from app.intelligence.diagnostics_models import CodeDiagnostic, DiagnosticSeverity  # noqa: E402
from app.qt.QtGui import QTextCursor  # noqa: E402
from app.qt.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QWidget,
)
from app.shell.tab_content_providers import TabSurfaceRequest  # noqa: E402
from app.shell.theme_tokens import tokens_from_palette  # noqa: E402

pytestmark = pytest.mark.unit

_PATH = "/project/invoice.ui"

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QPushButton" name="okButton">
     <property name="text">
      <string>OK</string>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""

_TEXT_TWICE = _FORM.replace(
    "     <property name=\"text\">\n      <string>OK</string>\n     </property>\n",
    "     <property name=\"text\">\n      <string>Old</string>\n     </property>\n"
    "     <property name=\"text\">\n      <string>OK</string>\n     </property>\n",
)

_SAME_NAME = _FORM.replace(
    "   <item>\n    <widget class=\"QPushButton\"",
    "   <item>\n    <widget class=\"QLabel\" name=\"dup\"/>\n   </item>\n"
    "   <item>\n    <widget class=\"QPushButton\"",
).replace('name="okButton"', 'name="dup"')

_WIDGET_PROBLEM = FormDiagnostic(
    code="FB007",
    severity=Severity.WARNING,
    message='Property "text" is set more than once. The last value is the one that is used.',
    location=DiagnosticLocation(node_id=NodeId(7), object_name="okButton", property="text", line=12),
    source="reader",
)

_FORM_PROBLEM = FormDiagnostic(
    code="FB505",
    severity=Severity.WARNING,
    message="ui_invoice.py is out of date with this form. Save the form to bring it up to date.",
    location=DiagnosticLocation(),
    source="codegen",
)


class _Editor(QPlainTextEdit):
    def apply_theme(self, _tokens: object) -> None:
        return None

    def go_to_line(self, line_number: int) -> None:
        cursor = self.textCursor()
        move = getattr(QTextCursor, "MoveOperation", QTextCursor)
        mode = getattr(QTextCursor, "MoveMode", QTextCursor)
        cursor.movePosition(getattr(move, "Start"))
        cursor.movePosition(getattr(move, "Down"), getattr(mode, "MoveAnchor"), max(0, int(line_number) - 1))
        self.setTextCursor(cursor)


class _Shell:
    def __init__(self) -> None:
        self.pushes: List[Tuple[str, List[CodeDiagnostic]]] = []
        self.problems_shown = 0

    def publish(self, path: str, rows: List[CodeDiagnostic]) -> None:
        self.pushes.append((path, list(rows)))

    def show(self) -> None:
        self.problems_shown += 1

    def codes(self) -> List[Tuple[str, List[str]]]:
        return [(path, [row.code for row in rows]) for path, rows in self.pushes]


def _open(
    qapp: QApplication,
    text: str,
    *,
    path: str = _PATH,
    project_root: Optional[str] = None,
    parent: Optional[QWidget] = None,
) -> Tuple[FormSurface, _Shell]:
    host = parent if parent is not None else QWidget()
    shell = _Shell()

    def create_source_editor() -> _Editor:
        editor = _Editor(host)
        editor.setObjectName("shell.editorTabs.textEditor")
        return editor

    request = TabSurfaceRequest(
        file_path=path,
        initial_text=text,
        parent=host,
        theme=tokens_from_palette(qapp.palette(), force_mode="light"),
        create_source_editor=create_source_editor,  # type: ignore[arg-type]
        open_linked_file=lambda _linked: None,
        project_root=project_root,
        publish_problems=shell.publish,
        show_problems=shell.show,
    )
    surface = FormTabProvider().create_surface(request)
    qapp.processEvents()
    return surface, shell


def _selected(surface: FormSurface) -> str:
    tree = surface.findChild(QTreeWidget, "formBuilder.structure")
    assert tree is not None
    item = tree.currentItem()
    return "" if item is None else item.text(0)


def _xml_toggle(surface: FormSurface) -> QToolButton:
    toggle = surface.findChild(QToolButton, "formBuilder.viewXml")
    assert toggle is not None
    return toggle


def _editor_line(surface: FormSurface) -> int:
    editor = surface.source_editor()
    assert isinstance(editor, QPlainTextEdit)
    return editor.textCursor().blockNumber() + 1


def test_widget_problem_becomes_a_row_named_for_the_widget() -> None:
    rows = to_code_diagnostics(_PATH, (_WIDGET_PROBLEM,))

    assert rows == [
        CodeDiagnostic(
            code="FB007",
            severity=DiagnosticSeverity.WARNING,
            file_path=_PATH,
            line_number=12,
            message='Property "text" is set more than once. The last value is the one that is used.',
            detail={
                "fb_key": "FB007|okButton|text|[]",
                "fb_object": "okButton",
                "fb_property": "text",
                "fb_rule_path": "[]",
                "fb_source": "reader",
            },
            source="Form",
            location_label="okButton",
        )
    ]


def test_form_level_problem_points_at_line_one_with_no_widget() -> None:
    (row,) = to_code_diagnostics(_PATH, (_FORM_PROBLEM,))

    assert (row.line_number, row.location_label, row.message) == (
        1,
        "",
        "ui_invoice.py is out of date with this form. Save the form to bring it up to date.",
    )


@pytest.mark.parametrize(("debug", "codes"), [("", ["FB007"]), ("1", ["FB007", "FB901"])])
def test_internal_codes_are_listed_only_in_debug(
    monkeypatch: pytest.MonkeyPatch, debug: str, codes: List[str]
) -> None:
    monkeypatch.setenv("CBCS_FB_DEBUG", debug)
    internal = FormDiagnostic(
        code="FB901",
        severity=Severity.INFO,
        message="Internal check.",
        location=DiagnosticLocation(),
        source="debug",
    )

    rows = to_code_diagnostics(_PATH, (_WIDGET_PROBLEM, internal))

    assert [row.code for row in rows] == codes


def test_bridge_pushes_every_row_once_per_turn(qapp) -> None:  # type: ignore[no-untyped-def]
    store = DiagnosticsStore()
    shell = _Shell()
    bridge = ProblemsBridge(_PATH, store, shell.publish)

    store.publish("reader", (_WIDGET_PROBLEM,))
    store.publish("codegen", (_FORM_PROBLEM,))
    qapp.processEvents()

    assert shell.codes() == [(_PATH, ["FB505", "FB007"])]
    bridge.close()


def test_closed_bridge_clears_its_path_and_stops(qapp) -> None:  # type: ignore[no-untyped-def]
    store = DiagnosticsStore()
    store.publish("reader", (_WIDGET_PROBLEM,))
    shell = _Shell()
    bridge = ProblemsBridge(_PATH, store, shell.publish)
    qapp.processEvents()
    shell.pushes.clear()

    bridge.close()
    store.publish("codegen", (_FORM_PROBLEM,))
    qapp.processEvents()

    assert shell.codes() == [(_PATH, [])]


@pytest.mark.parametrize(
    ("severities", "summary"),
    [
        ((), ""),
        (("error",), "1 problem: 1 error"),
        (("warning", "error"), "2 problems: 1 error, 1 warning"),
        (("warning", "info", "warning"), "3 problems: 2 warnings, 1 info"),
    ],
)
def test_problem_summary_counts_each_severity(severities: Tuple[str, ...], summary: str) -> None:
    rows = [
        CodeDiagnostic(
            code="FB007",
            severity=DiagnosticSeverity(severity),
            file_path=_PATH,
            line_number=1,
            message="m",
        )
        for severity in severities
    ]

    assert problem_summary(rows) == summary


@pytest.mark.parametrize(
    ("name", "sentence"),
    [("buddy", "This problem is about Buddy."), ("toolTip", "This problem is about Tool tip.")],
)
def test_property_sentence_spells_out_the_property(name: str, sentence: str) -> None:
    assert problem_property_sentence(name) == sentence


def test_opening_a_form_lists_its_problems_once(qapp) -> None:  # type: ignore[no-untyped-def]
    surface, shell = _open(qapp, _TEXT_TWICE)

    assert [
        (path, [(row.code, row.source, row.location_label) for row in rows]) for path, rows in shell.pushes
    ] == [(_PATH, [("FB007", "Form", "okButton")])]
    surface.release()


@pytest.mark.parametrize(
    "detail",
    [
        {"fb_key": "FB007|okButton|text|[]", "fb_object": "okButton", "fb_property": "text"},
        {"fb_key": "FB007|okButton|text|[]", "fb_object": ""},
    ],
    ids=["object", "key"],
)
def test_reveal_selects_the_widget_a_row_names(qapp, detail: Dict[str, str]) -> None:  # type: ignore[no-untyped-def]
    surface, _shell = _open(qapp, _FORM)

    assert surface.reveal(8, detail) is True

    assert _selected(surface) == "QPushButton  okButton"
    assert _xml_toggle(surface).isChecked() is False
    surface.release()


def test_reveal_picks_the_first_of_two_widgets_with_one_name(qapp) -> None:  # type: ignore[no-untyped-def]
    surface, _shell = _open(qapp, _SAME_NAME)

    assert surface.reveal(1, {"fb_object": "dup"}) is True

    assert _selected(surface) == "QLabel  dup"
    surface.release()


def test_reveal_names_the_property_in_the_focused_inspector(qapp) -> None:  # type: ignore[no-untyped-def]
    host = QWidget()
    surface, shell = _open(qapp, _TEXT_TWICE, parent=host)
    host.show()
    surface.show()
    host.resize(1200, 800)
    surface.resize(1200, 800)
    qapp.processEvents()
    qapp.setActiveWindow(host)
    (row,) = shell.pushes[-1][1]

    assert surface.reveal(row.line_number, row.detail) is True
    qapp.processEvents()

    body = surface.findChild(QLabel, "formBuilder.inspectorBody")
    assert body is not None
    assert body.text() == "This problem is about Text."
    assert qapp.focusWidget() is body
    surface.release()
    host.close()


@pytest.mark.parametrize(
    "detail",
    [None, {"fb_key": "FB505|||[]", "fb_object": ""}, {"fb_object": "missingButton"}],
    ids=["no-detail", "form-level", "unknown-name"],
)
def test_reveal_without_a_widget_shows_the_line_in_xml(  # type: ignore[no-untyped-def]
    qapp, detail: Optional[Dict[str, str]]
) -> None:
    surface, _shell = _open(qapp, _FORM)

    assert surface.reveal(4, detail) is True

    assert _xml_toggle(surface).isChecked() is True
    assert _editor_line(surface) == 4
    surface.release()


def test_reveal_from_unedited_xml_returns_to_design(qapp) -> None:  # type: ignore[no-untyped-def]
    surface, _shell = _open(qapp, _FORM)
    _xml_toggle(surface).setChecked(True)

    assert surface.reveal(8, {"fb_object": "okButton"}) is True

    assert _xml_toggle(surface).isChecked() is False
    assert _selected(surface) == "QPushButton  okButton"
    surface.release()


def test_reveal_keeps_typed_xml_and_shows_the_line(qapp) -> None:  # type: ignore[no-untyped-def]
    surface, _shell = _open(qapp, _FORM)
    _xml_toggle(surface).setChecked(True)
    editor = surface.source_editor()
    assert isinstance(editor, QPlainTextEdit)
    editor.setPlainText(editor.toPlainText().replace(">OK<", ">Save<"))

    assert surface.reveal(4, {"fb_object": "okButton"}) is True

    assert _xml_toggle(surface).isChecked() is True
    assert ">Save<" in editor.toPlainText()
    assert _editor_line(surface) == 4
    surface.release()


def test_inspector_sums_up_problems_only_while_nothing_is_selected(qapp) -> None:  # type: ignore[no-untyped-def]
    surface, _shell = _open(qapp, _TEXT_TWICE)
    summary = surface.findChild(QLabel, "formBuilder.problemSummary")
    assert summary is not None
    assert summary.text() == "1 problem: 1 warning"
    assert summary.isVisibleTo(surface) is True

    surface.reveal(8, {"fb_object": "okButton"})

    assert summary.isVisibleTo(surface) is False
    surface.release()


def test_show_in_problems_asks_the_shell(qapp) -> None:  # type: ignore[no-untyped-def]
    surface, shell = _open(qapp, _TEXT_TWICE)
    button = surface.findChild(QPushButton, "formBuilder.showProblems")
    assert button is not None

    button.click()

    assert shell.problems_shown == 1
    surface.release()


def test_out_of_date_module_is_a_problem_until_save(qapp, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    forms = tmp_path / "forms"
    forms.mkdir()
    ui_path = forms / "invoice.ui"
    canonical = write_ui(open_document_log(_FORM).document).text
    ui_path.write_text(canonical, encoding="utf-8")
    scope = classify_form(str(ui_path), project_root=str(tmp_path))
    older = canonical.replace(">OK<", ">Old<")
    module = generate_form_module(
        read_ui(older, allocator=IdAllocator()).document,
        scope=scope,
        source_bytes=older.encode("utf-8"),
    ).text
    assert module is not None
    Path(scope.generated_path or "").write_text(module, encoding="utf-8")
    surface, shell = _open(qapp, canonical, path=str(ui_path), project_root=str(tmp_path))
    assert shell.codes() == [(str(ui_path), ["FB505"])]
    manager = EditorManager()
    opened = manager.open_file(str(ui_path))
    opened.tab.content_source = surface.content_source()

    manager.save_tab(str(ui_path))
    qapp.processEvents()

    assert shell.codes()[-1] == (str(ui_path), [])
    surface.release()
