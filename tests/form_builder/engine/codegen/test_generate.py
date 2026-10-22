"""Codegen contracts that a widget-tree oracle does not exercise."""
from __future__ import annotations

import ast
import unicodedata
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.api import (
    generate_form_module,
    is_hand_edited,
    is_stale,
)
from app.features.form_builder.engine.codegen.api_types import CodegenOptions
from app.features.form_builder.engine.codegen.literals import py_bytes, py_float, py_string
from app.features.form_builder.engine.codegen.names import header_module
from app.features.form_builder.engine.codegen.window_template import plan_stub, render_window_class
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope, classify_form
from app.features.form_builder.engine.ui4.reader import read_ui

_UI = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>%(class_name)s</class>
 <widget class="%(root_class)s" name="%(root_name)s">
  <property name="windowTitle"><string%(string_attrs)s>%(title)s</string></property>
  %(body)s
 </widget>
 %(tail)s
</ui>
"""


def _form(tmp_path: Path, stem: str = "invoice", **kwargs: str) -> tuple:
    fields = {
        "class_name": "Invoice",
        "root_class": "QWidget",
        "root_name": "Invoice",
        "string_attrs": "",
        "title": "Hello",
        "body": "",
        "tail": "",
    }
    fields.update(kwargs)
    forms = tmp_path / "forms"
    forms.mkdir(parents=True, exist_ok=True)
    path = forms / ("%s.ui" % stem)
    path.write_text(_UI % fields, encoding="utf-8")
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(forms / ("ui_%s.py" % stem)),
        window_path=str(forms / ("%s_window.py" % stem)),
        module_name="forms.ui_%s" % stem,
    )
    document = read_ui(path.read_text(encoding="utf-8"), allocator=IdAllocator()).document
    return path, scope, document


def _generate(tmp_path: Path, **kwargs: str):
    path, scope, document = _form(tmp_path, **kwargs)
    return generate_form_module(document, scope=scope, source_bytes=path.read_bytes())


def test_refuses_a_name_that_cannot_be_a_python_identifier(tmp_path: Path) -> None:
    result = _generate(tmp_path, root_name="setupUi")
    assert result.text is None
    assert result.diagnostics
    assert {item.code for item in result.diagnostics} == {"FB502"}


def test_compatibility_character_does_not_alias_another_attribute(tmp_path: Path) -> None:
    body = '<widget class="QLabel" name="fix"/><widget class="QLabel" name="ﬁx"/>'
    result = _generate(tmp_path, body=body)
    assert result.text is not None
    assert "ﬁ" not in result.text
    folded = {unicodedata.normalize("NFKC", name) for name in result.attribute_names}
    assert len(result.attribute_names) == len(folded) == 2


@pytest.mark.parametrize(
    "root_name",
    (
        "icon",
        "icon1",
        "sizePolicy",
        "font",
        "palette",
        "brush",
        "brush2",
        "gradient",
        "__sortingEnabled",
        "___qtreewidgetitem",
        "QSizePolicy",
        "Qt",
        "QCoreApplication",
    ),
)
def test_form_parameter_cannot_shadow_setupui(tmp_path: Path, root_name: str) -> None:
    result = _generate(tmp_path, root_name=root_name)
    assert result.text is None
    assert {item.code for item in result.diagnostics} == {"FB502"}


def test_external_form_is_not_written(tmp_path: Path) -> None:
    path, scope, document = _form(tmp_path)
    external = FormScope(kind="external", ui_path=scope.ui_path)
    result = generate_form_module(document, scope=external, source_bytes=path.read_bytes())
    assert result.text is None
    assert result.diagnostics[0].code == "FB506"


def test_stem_that_is_a_keyword_is_not_a_module(tmp_path: Path) -> None:
    path, scope, document = _form(tmp_path, stem="class")
    result = generate_form_module(document, scope=scope, source_bytes=path.read_bytes())
    assert result.text is None
    assert result.diagnostics[0].code == "FB507"


def test_hand_edited_and_stale_truth_table(tmp_path: Path) -> None:
    path, scope, document = _form(tmp_path)
    source = path.read_bytes()
    result = generate_form_module(document, scope=scope, source_bytes=source)
    assert result.text is not None
    text = result.text
    rows = (
        ("pristine", text, False, False),
        ("body edit", text.replace("def setupUi", "def setupUi ", 1), True, False),
        (
            "header edit",
            text.replace("# -*- coding: utf-8 -*-", "# -*- coding: utf-8 -*-\nimport os", 1),
            True,
            False,
        ),
        ("crlf", text.replace("\n", "\r\n"), True, True),
        (
            "missing source line",
            "".join(line + "\n" for line in text.splitlines() if "cbcs-source-sha256" not in line),
            False,
            True,
        ),
    )
    for label, sample, hand_edited, stale in rows:
        assert is_hand_edited(sample) is hand_edited, label
        assert is_stale(sample, source) is stale, label


def test_generated_module_parses_as_python_39_and_tracks_edits(tmp_path: Path) -> None:
    path, scope, document = _form(tmp_path, title='Say "hi"\n')
    source = path.read_bytes()
    result = generate_form_module(document, scope=scope, source_bytes=source)
    assert result.text is not None
    ast.parse(result.text, feature_version=(3, 9))
    assert result.header is not None
    assert result.header.source_sha256 is not None
    assert is_hand_edited(result.text) is False
    assert is_stale(result.text, source) is False
    edited = result.text.replace("def setupUi", "def setupUi ", 1)
    assert is_hand_edited(edited) is True
    preview = generate_form_module(document, scope=scope, source_bytes=None)
    assert preview.text is not None
    assert "cbcs-source-sha256" not in preview.text.split("class ", 1)[0]
    assert is_stale(preview.text, source) is True


@pytest.mark.parity("R3-323")
def test_no_autoconnection_omits_connect_slots_by_name(tmp_path: Path) -> None:
    path, scope, document = _form(tmp_path)
    result = generate_form_module(
        document,
        scope=scope,
        source_bytes=path.read_bytes(),
        options=CodegenOptions(connect_slots_by_name=False),
    )
    assert result.text is not None
    assert "connectSlotsByName" not in result.text
    default = generate_form_module(document, scope=scope, source_bytes=path.read_bytes())
    assert default.text is not None
    assert "QMetaObject.connectSlotsByName(Invoice)" in default.text


@pytest.mark.parity("R3-324")
def test_translate_function_replaces_the_i18n_call(tmp_path: Path) -> None:
    path, scope, document = _form(tmp_path, title="Hello")
    result = generate_form_module(
        document,
        scope=scope,
        source_bytes=path.read_bytes(),
        options=CodegenOptions(translate_function="cbcs_tr"),
    )
    assert result.text is not None
    assert 'cbcs_tr(u"Invoice", u"Hello", None)' in result.text
    assert "QCoreApplication.translate" not in result.text


@pytest.mark.parity("R3-325")
def test_id_based_translation_uses_the_string_id(tmp_path: Path) -> None:
    path, scope, document = _form(tmp_path, string_attrs=' id="TITLE"', title="Hello")
    result = generate_form_module(
        document,
        scope=scope,
        source_bytes=path.read_bytes(),
        options=CodegenOptions(id_based=True),
    )
    assert result.text is not None
    assert 'u"TITLE"' in result.text
    assert 'u"Hello"' not in result.text


@pytest.mark.parity("R3-326")
def test_connection_is_a_python_connect_call(tmp_path: Path) -> None:
    tail = """<connections>
 <connection>
  <sender>Invoice</sender>
  <signal>customContextMenuRequested(QPoint)</signal>
  <receiver>Invoice</receiver>
  <slot>close()</slot>
 </connection>
</connections>"""
    path, scope, document = _form(tmp_path, tail=tail)
    result = generate_form_module(document, scope=scope, source_bytes=path.read_bytes())
    assert result.text is not None
    assert "Invoice.customContextMenuRequested.connect(Invoice.close)" in result.text


@pytest.mark.parity("R3-327")
def test_resource_import_styles(tmp_path: Path) -> None:
    path, scope, document = _form(tmp_path, tail='<resources><include location="icons.qrc"/></resources>')
    source = path.read_bytes()

    def rendered(options: CodegenOptions) -> str:
        result = generate_form_module(document, scope=scope, source_bytes=source, options=options)
        assert result.text is not None
        return result.text

    assert "import icons_rc" in rendered(CodegenOptions())
    assert "from . import icons_rc" in rendered(CodegenOptions(import_style="from"))
    assert "from icons_rc import *" in rendered(CodegenOptions(import_style="star"))
    assert "from forms import icons_rc" in rendered(CodegenOptions(import_style="absolute"))
    nested = _form(tmp_path, stem="themed", tail='<resources><include location="theme/icons.qrc"/></resources>')
    prefixed = generate_form_module(
        nested[2],
        scope=nested[1],
        source_bytes=nested[0].read_bytes(),
        options=CodegenOptions(rc_prefix=True),
    )
    assert prefixed.text is not None
    assert "import theme.icons_rc" in prefixed.text
    pathed = generate_form_module(
        nested[2],
        scope=nested[1],
        source_bytes=nested[0].read_bytes(),
        options=CodegenOptions(python_paths=(str(nested[0].parent),)),
    )
    assert pathed.text is not None
    assert "import theme.icons_rc" in pathed.text


@pytest.mark.parity("R3-330")
def test_postfix_is_appended_to_the_ui_class(tmp_path: Path) -> None:
    path, scope, document = _form(tmp_path)
    result = generate_form_module(
        document,
        scope=scope,
        source_bytes=path.read_bytes(),
        options=CodegenOptions(postfix="_Gen"),
    )
    assert result.text is not None
    assert "class Ui_Invoice_Gen(object):" in result.text


def test_promoted_header_and_freecad_gui_fallback(tmp_path: Path) -> None:
    tail = """<customwidgets>
 <customwidget>
  <class>InvoiceHeader</class>
  <extends>QWidget</extends>
  <header>shop/widgets/invoice_header.h</header>
 </customwidget>
</customwidgets>"""
    body = '<widget class="InvoiceHeader" name="header"/>'
    path, scope, document = _form(tmp_path, body=body, tail=tail)
    result = generate_form_module(document, scope=scope, source_bytes=path.read_bytes())
    assert result.text is not None
    assert "from shop.widgets.invoice_header import InvoiceHeader" in result.text
    assert [item.code for item in result.diagnostics] == []

    gui_path, gui_scope, gui_doc = _form(
        tmp_path,
        stem="qty",
        body='<widget class="Gui::QuantitySpinBox" name="qty"/>',
    )
    gui = generate_form_module(gui_doc, scope=gui_scope, source_bytes=gui_path.read_bytes())
    assert gui.text is not None
    assert gui.uses_freecadgui is True
    assert "import FreeCADGui as _cbcs_FreeCADGui" in gui.text
    assert "_cbcs_widget(" in gui.text
    assert "QWidget" in gui.text


def test_dotted_promoted_header_is_a_module() -> None:
    assert header_module("shop.widgets.invoice_header") == "shop.widgets.invoice_header"
    assert header_module("mypackage/widget.h") == "mypackage.widget"
    assert header_module("not a module") is None


def test_string_literal_rule_round_trips_without_repr() -> None:
    raw = 'say "hi"\n\t\x01é'
    literal = py_string(raw)
    assert literal.startswith('u"')
    assert "\\n" in literal
    assert ast.literal_eval(literal) == raw
    assert py_bytes(b'a\x00"\\') == 'b"a\\x00\\"\\\\"'
    assert ast.literal_eval(py_bytes(b"\x00\xff")) == b"\x00\xff"
    assert float(py_float(0.1)) == 0.1


def test_scoped_cpp_names_follow_uic(tmp_path: Path) -> None:
    path, scope, document = _form(
        tmp_path,
        stem="remote",
        class_name="Gui::Dialog::RemoteDebugger",
        root_name="Gui::Dialog::RemoteDebugger",
        body='<widget class="QLabel" name="label"><property name="text"><string>Hi</string></property></widget>',
    )
    result = generate_form_module(document, scope=scope, source_bytes=path.read_bytes())
    assert result.text is not None
    assert "class Ui_Gui_Dialog_RemoteDebugger(object):" in result.text
    assert "def setupUi(self, Gui__Dialog__RemoteDebugger):" in result.text
    assert 'setObjectName(u"Gui__Dialog__RemoteDebugger")' in result.text
    ast.parse(result.text, feature_version=(3, 9))


def test_missing_size_field_is_zero(tmp_path: Path) -> None:
    body = (
        '<widget class="QLineEdit" name="edit">'
        '<property name="minimumSize"><size><width>100</width></size></property>'
        "</widget>"
    )
    path, scope, document = _form(tmp_path, body=body)
    result = generate_form_module(document, scope=scope, source_bytes=path.read_bytes())
    assert result.text is not None
    assert "setMinimumSize(QSize(100, 0))" in result.text


def test_table_header_attributes_go_through_the_header(tmp_path: Path) -> None:
    body = (
        '<widget class="QTableWidget" name="table">'
        '<attribute name="horizontalHeaderVisible"><bool>true</bool></attribute>'
        '<attribute name="horizontalHeaderStretchLastSection"><bool>true</bool></attribute>'
        '<attribute name="verticalHeaderVisible"><bool>false</bool></attribute>'
        '<attribute name="horizontalHeaderShowSortIndicator"><bool>true</bool></attribute>'
        '<column><property name="text"><string>License</string></property></column>'
        "</widget>"
    )
    path, scope, document = _form(tmp_path, body=body)
    result = generate_form_module(document, scope=scope, source_bytes=path.read_bytes())
    assert result.text is not None
    assert "self.table.horizontalHeader().setVisible(True)" in result.text
    assert "self.table.horizontalHeader().setStretchLastSection(True)" in result.text
    assert "self.table.verticalHeader().setVisible(False)" in result.text
    assert 'self.table.horizontalHeader().setProperty(u"showSortIndicator", True)' in result.text
    assert "self.table.horizontalHeaderItem(0).setText(" in result.text


def test_spacer_without_a_size_hint_is_zero(tmp_path: Path) -> None:
    body = (
        '<layout class="QVBoxLayout" name="verticalLayout">'
        "<item><spacer name=\"gap\">"
        '<property name="orientation"><enum>Qt::Vertical</enum></property>'
        '<property name="sizeType"><enum>QSizePolicy::Expanding</enum></property>'
        "</spacer></item></layout>"
    )
    path, scope, document = _form(tmp_path, body=body)
    result = generate_form_module(document, scope=scope, source_bytes=path.read_bytes())
    assert result.text is not None
    assert "QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)" in result.text


def test_splitter_sizes_are_a_setsizes_call() -> None:
    path = Path(__file__).resolve().parents[2] / "corpus" / "synthetic" / "cbcs" / "splitter_sizes.ui"
    document = read_ui(path.read_text(encoding="utf-8"), allocator=IdAllocator()).document
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(path.parent),
        generated_path=str(path.with_name("ui_splitter_sizes.py")),
        window_path=str(path.with_name("splitter_sizes_window.py")),
        module_name="ui_splitter_sizes",
    )
    result = generate_form_module(document, scope=scope, source_bytes=path.read_bytes())
    assert result.text is not None
    assert ".setSizes([200, 400])" in result.text
    ast.parse(result.text, feature_version=(3, 9))


def test_window_stub_is_inserted_once() -> None:
    document = read_ui(
        _UI
        % {
            "class_name": "Invoice",
            "root_class": "QDialog",
            "root_name": "Invoice",
            "string_attrs": "",
            "title": "Hi",
            "body": "",
            "tail": "",
        },
        allocator=IdAllocator(),
    ).document
    scope = FormScope(
        kind="project",
        ui_path="/proj/forms/invoice.ui",
        project_root="/proj",
        module_name="forms.ui_invoice",
    )
    source = render_window_class(document, scope=scope)
    ast.parse(source, feature_version=(3, 9))
    assert "class InvoiceWindow(QDialog):" in source
    assert "from forms.ui_invoice import Ui_Invoice" in source
    plan = plan_stub(source, class_name="InvoiceWindow", method_name="on_save", params=("checked",), decorator=None)
    updated = source[: plan.edit.start] + plan.edit.text + source[plan.edit.end :]
    ast.parse(updated)
    assert "def on_save(self, checked):" in updated
    with pytest.raises(ValueError):
        plan_stub(updated, class_name="InvoiceWindow", method_name="on_save", params=(), decorator=None)


def test_classify_form_matches_forms_dir_and_adopted(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    ui = project / "forms" / "invoice.ui"
    ui.parent.mkdir(parents=True)
    ui.write_text("x", encoding="utf-8")
    adopted_path = project / "shared" / "other.ui"
    adopted_path.parent.mkdir()
    adopted_path.write_text("x", encoding="utf-8")
    project_scope = classify_form(str(ui), project_root=str(project))
    assert project_scope.kind == "project"
    assert project_scope.generates is True
    assert project_scope.module_name == "forms.ui_invoice"
    adopted = classify_form(str(adopted_path), project_root=str(project), adopted=("shared/other.ui",))
    assert adopted.kind == "adopted"
    outside = classify_form(str(adopted_path), project_root=str(project))
    assert outside.kind == "external"
    assert outside.generates is False
