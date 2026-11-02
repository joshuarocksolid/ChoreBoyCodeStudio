# pyright: reportAttributeAccessIssue=false
"""M8.0s seams: data codecs, checks, verbs, formula names, codegen hooks, the shop fixture."""

from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.change_signals import CHANGE_SIGNALS, change_signal
from app.features.form_builder.engine.codegen.expanders import form_events
from app.features.form_builder.engine.codegen.logic_hooks import Contribution, load_expanders
from app.features.form_builder.engine.data.check import load_checks, run_checks
from app.features.form_builder.engine.data.schema import Column, Schema, Table, is_stale, read_schema, set_schema_reader, write_schema
from app.features.form_builder.engine.data.source import (
    Bind,
    BindMode,
    DataColumn,
    Lookup,
    RecordSource,
    Rows,
    read_bind,
    read_bind_mode,
    read_data,
    read_lookup,
    read_rows,
    write_bind,
    write_bind_mode,
    write_data,
    write_lookup,
    write_rows,
)
from app.features.form_builder.engine.data.types import describe, formula_kind, from_sql, to_sql
from app.features.form_builder.engine.diagnostics import CODES
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic import verbs
from app.features.form_builder.engine.logic.codec import TYPED_VERBS
from app.features.form_builder.engine.logic.formula.check import analyze
from app.features.form_builder.engine.logic.formula.compile import compile_formula
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.engine.logic.formula.support import SLOTS
from tests.form_builder.engine.test_m6_1a_events import form
from tests.form_builder.fixtures.m8.make_shop import build, dump
from tests.form_builder.m5_0s_support import forget_package, make_package

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _ROOT / "tests" / "form_builder" / "fixtures"

# sha256 of the generated module, captured before the M8.0s codegen edits.
_GOLDEN = {
    "m6/designer_made": "81a37a20a99e859d04763ccd10a95de78392101ff9d069ddd924e35ad3a06baf",
    "m6/sale": "263e46e14e5241943e133aa73c19fd8d6fa76cedbf70fc7e1a1732d5b7c765c3",
    "m7/designer_made": "81a37a20a99e859d04763ccd10a95de78392101ff9d069ddd924e35ad3a06baf",
    "m7/sale": "263e46e14e5241943e133aa73c19fd8d6fa76cedbf70fc7e1a1732d5b7c765c3",
    "m7/invoice": "bf28dcec77d987bcda5d205bf21e2d8693ac3db0d9359edf2500407a5b1f3352",
}


def _generate(text: str, name: str, tmp_path: Path) -> str:
    path = tmp_path / ("%s.ui" % name)
    path.write_text(text, encoding="utf-8")
    read = read_ui(text, allocator=IdAllocator())
    scope = FormScope(
        kind="project",
        ui_path=str(path),
        project_root=str(tmp_path),
        generated_path=str(tmp_path / ("ui_%s.py" % name)),
        window_path=str(tmp_path / ("%s_window.py" % name)),
        module_name="ui_%s" % name,
    )
    result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"))
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    return result.text


def test_codecs_round_trip_the_section_6_shapes_and_keep_unknown_keys() -> None:
    record = RecordSource("shop", "invoices", "id", record_word="bill", search=("invoice_no",))
    assert read_data(write_data(record)).value == record
    listed = read_data('{"mode":"list","connection":"shop","query":"select 1","columns":["id"]}')
    assert listed.value is not None and listed.value.sql == "select 1"
    assert "query" not in write_data(listed.value)
    lookup = Lookup("customers", "id", "name", also=("city",))
    assert read_lookup(write_lookup(lookup))[0] == lookup
    rows = Rows("invoice_lines", "invoice_id", "id", (DataColumn("qty", header="Qty"),))
    assert read_rows(write_rows(rows))[0] == rows
    assert read_bind(write_bind(Bind("customer_id"))).column == "customer_id"
    assert read_bind_mode(write_bind_mode(BindMode(True))).read_only is True
    kept = read_data('{"connection":"shop","table":"invoices","key":"id","lane":"later"}')
    assert kept.value is not None
    written = write_data(kept.value)
    assert written.index('"key"') < written.index('"lane"')
    assert read_data(written).value == kept.value


def test_type_words_and_conversion_follow_the_column() -> None:
    money = describe("numeric(10, 2)", engine="postgres")
    assert money.words == "money" and money.widget == "QDoubleSpinBox"
    assert formula_kind(money) == "money"
    whole = describe("numeric(8, 0)")
    assert whole.words == "whole number" and whole.widget == "QSpinBox"
    text = describe("varchar(40)")
    assert text.words == "text up to 40"
    pointed = describe("INTEGER", column_name="customer_id", references_table="customers")
    assert pointed.widget == "QComboBox" and pointed.words == "points to customers"
    flag = describe("INTEGER", column_name="is_open")
    assert flag.words == "yes/no" and flag.widget == "QCheckBox"
    assert describe("timestamp", engine="postgres").widget == "QDateTimeEdit"
    assert describe("date").words == "date"
    assert to_sql(money, "1.50", "sqlite") == "1.50"
    assert to_sql(money, "1.50", "postgres") == from_sql(money, "1.50", "postgres")
    blank = describe("text", nullable=True)
    assert to_sql(blank, "", "sqlite") is None


def test_schema_cache_round_trips_and_stales_after_seven_days() -> None:
    import datetime

    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (Table("invoices", (Column("id", "INTEGER", False),), key="id"),),
    )
    again, error = read_schema(write_schema(schema))
    assert error is None and again == schema
    fresh = datetime.datetime(2026, 1, 8, 0, 0, 0)
    later = datetime.datetime(2026, 1, 8, 0, 0, 1)
    assert is_stale(schema, fresh) is False
    assert is_stale(schema, later) is True


def test_a_lane_check_is_loaded_and_the_builtin_checks_fire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = make_package(
        tmp_path,
        monkeypatch,
        "m80s_checks",
        {
            "probe": """
                def register(registry):
                    from app.features.form_builder.engine.data.check import DataCheck
                    registry.add(DataCheck("probe", lambda doc, connections, schema: ()))
            """
        },
    )
    try:
        registry = load_checks(package)
        assert [item.check_id for item in registry.checks() if item.check_id == "probe"] == ["probe"]
    finally:
        forget_package("m80s_checks")
    bare = read_ui(
        form(
            extra_root=(
                '<property name="cbcsOnClicked" stdset="0"><string notr="true">'
                '[{"do": "save"}]</string></property>'
            )
        ),
        allocator=IdAllocator(),
    ).document
    found = run_checks(bare)
    assert any(item.code == "FB318" and item.message == CODES["FB318"].title for item in found)
    grid = (
        '<property name="cbcsRows" stdset="0"><string notr="true">'
        '{"table":"invoice_lines","link":"invoice_id","key":"id","columns":[]}'
        "</string></property>"
    )
    two = read_ui(
        form().replace('name="nameEdit"/>', 'name="nameEdit">' + grid + "</widget>", 1).replace(
            'name="phoneEdit"/>', 'name="phoneEdit">' + grid + "</widget>", 1
        ),
        allocator=IdAllocator(),
    ).document
    assert any(item.code == "FB320" for item in run_checks(two))


def test_record_verbs_stay_untyped_and_a_lane_verb_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec = verbs.default_registry().get("save")
    assert spec is not None and spec.editable is False and spec.group_id == "records"
    assert spec.blocks_list(None) is True
    assert "save" not in TYPED_VERBS
    assert spec.words(None, None) == "Save record"
    package = make_package(
        tmp_path,
        monkeypatch,
        "m80s_verbs",
        {
            "probe": """
                from app.features.form_builder.engine.logic.verbs import VerbSpec

                def register(registry):
                    registry.add(VerbSpec(
                        "probeLane", (), False, lambda taken: None, lambda step, ctx: (),
                        lambda step: True, "records", lambda step, w, is_form=False, target_chain=(): "Probe",
                        False,
                    ))
            """
        },
    )
    try:
        loaded = verbs.load_verbs(package)
        probe = loaded.get("probeLane")
        assert probe is not None and probe.words(None, None) == "Probe"
    finally:
        forget_package("m80s_verbs")


def test_unbound_forms_generate_the_pre_change_bytes(tmp_path: Path) -> None:
    for key, digest in _GOLDEN.items():
        lane, name = key.split("/")
        text = (_FIXTURES / lane / "forms" / ("%s.ui" % name)).read_text(encoding="utf-8")
        generated = _generate(text, name, tmp_path)
        assert hashlib.sha256(generated.encode("utf-8")).hexdigest() == digest, key


def test_ordered_setup_and_close_guard_are_absent_until_a_lane_adds_them(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = form(extra_root='<property name="cbcsOnOpened" stdset="0"><string notr="true">[{"do": "stop"}]</string></property>')
    before = _generate(text, "plain", tmp_path)
    assert "_cbcs_open_at_start" not in before

    class _Late:
        expander_id = "probe"
        level = 1
        order = 400

        def contribute(self, doc, ctx):
            del doc, ctx
            return Contribution(ordered_setup=((890, "self._cbcs_open_at_start()"),), needs_form=True)

    current = load_expanders()
    monkeypatch.setattr(
        "app.features.form_builder.engine.codegen.emit.load_expanders",
        lambda: current + (_Late(),),
    )
    placed = _generate(text, "placed", tmp_path)
    assert placed.index("self._cbcs_open_at_start()") < placed.index("self._cbcs_Sale_opened()")

    closing = form(
        extra_root='<property name="cbcsOnClosing" stdset="0"><string notr="true">[{"do": "stop"}]</string></property>'
    )
    form_events.register_close_guard(10, "probe", lambda doc, ctx: ("self._cbcs_ask_save()",))
    try:
        guarded = _generate(closing, "guarded", tmp_path)
        assert guarded.index("_cbcs_ask_save") < guarded.index("event.type()")
    finally:
        form_events.clear_close_guards()
    assert "_cbcs_ask_save" not in _generate(closing, "clear", tmp_path)


def test_model_change_signals_do_not_become_a_widget_connect() -> None:
    assert CHANGE_SIGNALS["QStandardItemModel"] == ("dataChanged", "rowsInserted", "rowsRemoved")
    assert change_signal("QStandardItemModel", ()) is None
    assert change_signal("QLineEdit", ()) == "textChanged"


def test_env_for_types_a_bound_form_and_keeps_fb115_on_an_unbound_one() -> None:
    data = write_data(RecordSource("shop", "invoices", "id"))
    lookup = write_lookup(Lookup("customers", "id", "name", also=("city",)))
    rows = write_rows(Rows("invoice_lines", "invoice_id", "id", (DataColumn("qty"),)))
    text = _bound_form(data, lookup, rows)
    document = read_ui(text, allocator=IdAllocator()).document
    schema = Schema(
        "shop",
        "sqlite",
        "",
        "2026-01-01T00:00:00",
        "sqlite3",
        (
            Table(
                "invoices",
                (Column("invoice_no", "TEXT", True), Column("total", "NUMERIC", False)),
                key="id",
            ),
        ),
    )
    set_schema_reader(lambda _doc, name: schema if name == "shop" else None)
    try:
        env = env_for(document, None, QtClassTable.shared())
        assert env.data is not None
        assert env.data.record["invoice_no"].kind.value == "text"
        assert env.data.record["total"].kind.value == "money"
        assert env.widgets["customerCombo"].also == ("city",)
        assert env.data.grids["linesView"] == ("qty",)
        shown = analyze("form.isNew", env, SLOTS["cond"])
        assert shown.problems == ()
        loaded = analyze("record.invoice_no", env, SLOTS["text"])
        assert loaded.problems == ()
        assert compile_formula(shown, env).source == "self._cbcs_form_is_new()"
        assert compile_formula(loaded, env).source == 'self._cbcs_record.get("invoice_no")'
    finally:
        set_schema_reader(None)
    unbound = read_ui(form(), allocator=IdAllocator()).document
    plain = env_for(unbound, None, QtClassTable.shared())
    got = analyze("form.isNew", plain, SLOTS["cond"])
    assert got.problems[0].code == "FB115"
    assert got.problems[0].message == "Connect this form to a table first."
    same = analyze("form.isNew", env_for(unbound, None, QtClassTable.shared()), SLOTS["cond"])
    assert same.problems[0].message == got.problems[0].message


def test_designer_resave_keeps_the_five_data_properties() -> None:
    data = write_data(RecordSource("shop", "invoices", "id", record_word="invoice"))
    bind = write_bind(Bind("invoice_no"))
    mode = write_bind_mode(BindMode(True))
    lookup = write_lookup(Lookup("customers", "id", "name", also=("city",)))
    rows = write_rows(Rows("invoice_lines", "invoice_id", "id", (DataColumn("qty", header="Qty"),)))
    document = read_ui(_bound_form(data, lookup, rows, bind, mode), allocator=IdAllocator()).document
    first = write_ui(document).text
    second = write_ui(read_ui(first, allocator=IdAllocator()).document).text
    assert second == first
    saved = read_ui(second, allocator=IdAllocator()).document
    data_prop = saved.root.prop("cbcsData")
    combo = next(node for node in saved.iter_widgets() if node.object_name == "customerCombo")
    grid = next(node for node in saved.iter_widgets() if node.object_name == "linesView")
    field = next(node for node in saved.iter_widgets() if node.object_name == "invoiceNoEdit")
    lookup_prop = combo.prop("cbcsLookup")
    rows_prop = grid.prop("cbcsRows")
    bind_prop = field.prop("cbcsBind")
    mode_prop = field.prop("cbcsBindMode")
    assert data_prop is not None and data_prop.value is not None and data_prop.value.text == data
    assert lookup_prop is not None and lookup_prop.value is not None and lookup_prop.value.text == lookup
    assert rows_prop is not None and rows_prop.value is not None and rows_prop.value.text == rows
    assert bind_prop is not None and bind_prop.value is not None and bind_prop.value.text == bind
    assert mode_prop is not None and mode_prop.value is not None and mode_prop.value.text == mode


def test_shop_fixture_dump_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "a.db"
    second = tmp_path / "b.db"
    build(str(first))
    build(str(second))
    assert dump(str(first)) == dump(str(second))
    text = (_FIXTURES / "m8" / "project" / "forms" / "invoice.ui").read_text(encoding="utf-8")
    assert "cbcsData" not in text
    assert "linesView" in text
    connections = (_FIXTURES / "m8" / "project" / "connections.json").read_text(encoding="utf-8")
    assert '"name": "shop"' in connections


def _bound_form(data: str, lookup: str, rows: str, bind: str = "invoice_no", mode: str = "readOnly") -> str:
    def prop(name: str, value: str) -> str:
        return '<property name="%s" stdset="0"><string notr="true">%s</string></property>' % (name, escape(value))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0">\n <class>Invoice</class>\n'
        ' <widget class="QDialog" name="Invoice">\n'
        + prop("cbcsData", data)
        + '  <layout class="QVBoxLayout" name="verticalLayout">\n'
        '   <item><widget class="QLineEdit" name="invoiceNoEdit">'
        + prop("cbcsBind", bind)
        + prop("cbcsBindMode", mode)
        + "</widget></item>\n"
        '   <item><widget class="QComboBox" name="customerCombo">' + prop("cbcsLookup", lookup) + "</widget></item>\n"
        '   <item><widget class="QTableView" name="linesView">' + prop("cbcsRows", rows) + "</widget></item>\n"
        "  </layout>\n </widget>\n <resources/>\n <connections/>\n</ui>\n"
    )
