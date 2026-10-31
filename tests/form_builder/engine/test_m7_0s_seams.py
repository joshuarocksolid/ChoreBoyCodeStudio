# pyright: reportAttributeAccessIssue=false
"""M7.0s seams: verb registry, golden codegen, trace, helpers, change connects."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict

import pytest

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.codegen.change_signals import change_signal
from app.features.form_builder.engine.codegen import emit as emit_module
from app.features.form_builder.engine.codegen.expanders import steps as steps_expander
from app.features.form_builder.engine.codegen.logic_hooks import (
    Contribution,
    helper_table,
    one_line,
    set_helper_provider,
)
from app.features.form_builder.engine.commands.catalog import SetProperty
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.logic import verbs
from app.features.form_builder.engine.logic.codec import parse_steps
from app.features.form_builder.engine.logic.events_codec import EventStep
from app.features.form_builder.engine.logic.storage import signal_property
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.reader import read_ui
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.qtside.inspector.behavior_ext._rows import _readonly_step
from tests.form_builder.engine.codegen import test_m6_1a_steps_codegen as cg
from tests.form_builder.engine.commands._support import open_log, saved
from tests.form_builder.engine.test_m6_1a_events import ROOT, connection, form
from tests.form_builder.m5_0s_support import forget_package, make_package

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _ROOT / "tests" / "form_builder" / "fixtures"
_M7 = _FIXTURES / "m7"

# sha256 of the full module, captured before the M7.0s edits. Basenames match that capture.
_GOLDEN = {
    "designer_made": "81a37a20a99e859d04763ccd10a95de78392101ff9d069ddd924e35ad3a06baf",
    "sale": "263e46e14e5241943e133aa73c19fd8d6fa76cedbf70fc7e1a1732d5b7c765c3",
    "inline_list": "b0b9f86b1206be97df3ed2a0efe6e9e901b2d7aaa77484f885fb4e298e4eba59",
    "inline_native_only": "920c3d568b8b5628a7e22e0433d5efeb9842249119a2dd3e816361eb5ff323f6",
    "inline_order": "980ac5dab6fba9adf019f921af3e75453457ecc7767b5bfe130bd5e8727e2318",
    "inline_false_stop": "a43f83a4701e8faa16b7adf72024362b987cc84488a801a10aaddef30faf1fc9",
    "inline_engine": "da505eb4512ed883fff8b9750af7d7ab0f8322d8211303c676ff2de0a01b0d3a",
    "inline_missing": "f6ff84d4678bad74f9ce001663a1bc3be474cb48cd5c714529c058224ced254a",
}

_PROBE_VERB = {
    "probe": """
        from app.features.form_builder.engine.logic.verbs import FieldSpec, VerbSpec, require_text

        def validate(taken):
            require_text("probe", ("method",), taken)

        def emit(step, ctx):
            return ("self._form.probe_ran()",)

        def blocks(step):
            return False

        def words(step, w, is_form=False, target_chain=()):
            return "Probe step"

        def register(registry):
            registry.add(VerbSpec(
                "probe",
                (FieldSpec("method", "method", required=True),),
                True,
                validate,
                emit,
                blocks,
                "everything",
                words,
            ))
    """,
}


def _generate(text: str, name: str, tmp_path: Path, trace: bool = False) -> str:
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
    result = generate_form_module(read.document, scope=scope, source_bytes=text.encode("utf-8"), trace=trace)
    assert result.text is not None, [(item.code, item.message) for item in result.diagnostics]
    return result.text


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _inline_sources() -> Dict[str, str]:
    off = cg.slot_step("phoneEdit", "setFocus()", enabled=False)
    missing = cg.with_list(cg.CLEAR, cg.slot_step("phoneEdit", "setFocus()", enabled=False), cg.call_step("m_none", 0))
    missing = missing.replace("&quot;target&quot;: &quot;nameEdit&quot;", "&quot;target&quot;: &quot;gone&quot;")
    return {
        "inline_list": cg.with_list(cg.CLEAR, cg.call_step("m_one", 1), off, cg.call_step("m_none", 0)),
        "inline_native_only": form(connection("cancelButton", "clicked()", ROOT, "close()")),
        "inline_order": cg.with_list(
            cg.call_step("m_none", 0),
            cg.CLEAR,
            off,
            cg.call_step("m_one", 1),
            cg.slot_step("giftCheck", "toggle()"),
        ),
        "inline_false_stop": cg.with_list(
            cg.call_step("m_check", 0), cg.CLEAR, cg.slot_step("giftCheck", "toggle()", enabled=False)
        ),
        "inline_engine": cg._engine_made_form(),
        "inline_missing": missing,
    }


def _use_verbs(monkeypatch: pytest.MonkeyPatch, registry: Any) -> None:
    monkeypatch.setattr(verbs, "default_registry", lambda: registry)
    monkeypatch.setattr(steps_expander, "default_registry", lambda: registry)


def test_generated_modules_match_the_pre_change_hashes(tmp_path: Path) -> None:
    sources = {
        "designer_made": (_FIXTURES / "m6" / "forms" / "designer_made.ui").read_text(encoding="utf-8"),
        "sale": (_FIXTURES / "m6" / "forms" / "sale.ui").read_text(encoding="utf-8"),
    }
    sources.update(_inline_sources())
    assert set(sources) == set(_GOLDEN)
    for name, text in sources.items():
        generated = _generate(text, name, tmp_path)
        assert _sha(generated) == _GOLDEN[name], name


def test_trace_is_absent_by_default_and_present_when_asked(tmp_path: Path) -> None:
    text = _inline_sources()["inline_list"]
    plain = _generate(text, "inline_list", tmp_path, trace=False)
    assert "_cbcs_trace" not in plain
    traced = _generate(text, "inline_list", tmp_path, trace=True)
    assert 'self._cbcs_trace("step", ' in traced
    assert "def _cbcs_trace(self, kind, ref, value):" in traced
    assert traced.index("def _cbcs_clearButton_clicked") < traced.index("def _cbcs_trace")
    assert traced.index("def _cbcs_trace") < traced.index("def _cbcs_setup")
    assert "Move focus to phoneEdit" in traced


def test_one_line_replaces_line_breaks() -> None:
    assert one_line("a\nb\u2028c\u2029d") == "a b c d"


def test_helper_table_uses_a_provider_or_the_formula_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.features.form_builder.engine.logic.formula.runtime import helper_table as formula_table

    assert helper_table() == formula_table()
    source = "def demo():\n    return 1\n"
    set_helper_provider(lambda: (("demo", source),))
    try:
        assert helper_table() == (("demo", source),)

        class _Probe:
            expander_id = "probe-helper"
            level = 1
            order = 1

            def contribute(self, doc: object, ctx: object) -> Contribution:
                del doc, ctx
                return Contribution(helpers=("demo",))

        monkeypatch.setattr(emit_module, "load_expanders", lambda: (_Probe(),))
        generated = _generate(form(), "plain", tmp_path)
        assert source in generated
    finally:
        set_helper_provider(None)
    assert helper_table() == formula_table()


def test_a_change_connect_uses_the_widget_class_and_skips_an_unknown_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert change_signal("QLineEdit", ()) == "textChanged"
    assert change_signal("MyEdit", ("QLineEdit", "QWidget")) == "textChanged"
    assert change_signal("QCheckBox", ("QAbstractButton", "QWidget")) == "toggled"
    assert change_signal("QDialog", ("QWidget",)) is None

    class _Probe:
        expander_id = "probe-connect"
        level = 1
        order = 1

        def contribute(self, doc: object, ctx: object) -> Contribution:
            del doc, ctx
            return Contribution(connects=(("nameEdit", "on_name"), ("buttonBox", "on_box")))

    monkeypatch.setattr(emit_module, "load_expanders", lambda: (_Probe(),))
    sale = (_FIXTURES / "m6" / "forms" / "sale.ui").read_text(encoding="utf-8")
    generated = _generate(sale, "sale", tmp_path)
    assert "self.nameEdit.textChanged.connect(self.on_name)" in generated
    assert "buttonBox" not in generated.split("def _cbcs_setup", 1)[-1].split("def ", 1)[0]


def test_invoice_widget_facts_keep_class_and_decimals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: Dict[str, Any] = {}

    class _Probe:
        expander_id = "probe-facts"
        level = 1
        order = 1

        def contribute(self, doc: object, ctx: object) -> Contribution:
            del doc
            seen.update(getattr(ctx, "widgets"))
            return Contribution()

    monkeypatch.setattr(emit_module, "load_expanders", lambda: (_Probe(),))
    text = (_M7 / "forms" / "invoice.ui").read_text(encoding="utf-8")
    generated = _generate(text, "invoice", tmp_path)
    assert "_cbcs" not in generated
    assert seen["priceSpin"].class_name == "QDoubleSpinBox"
    assert seen["priceSpin"].decimals == 2
    assert seen["qtySpin"].class_name == "QSpinBox"
    assert seen["discountCheck"].class_name == "QCheckBox"
    assert seen["discountCheck"].tristate is False
    assert seen["emailEdit"].class_name == "QLineEdit"
    assert seen["emailEdit"].prefix == ""
    assert seen["emailEdit"].has_items_data is False
    window = (_M7 / "forms" / "invoice_window.py").read_bytes()
    assert b"def save_invoice(self):" in window
    assert b"Runs when saveButton is clicked." in window


def test_a_dummy_verb_from_a_new_file_parses_and_emits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = make_package(tmp_path, monkeypatch, "m70s_verb_probe", _PROBE_VERB)
    try:
        registry = verbs.load_verbs(verbs, package)
        _use_verbs(monkeypatch, registry)
        read = parse_steps('[{"do": "probe", "method": "save_invoice"}]')
        assert read.error is None
        assert read.steps[0].is_typed
        assert read.steps[0].field("method") == "save_invoice"
        unknown = parse_steps('[{"do": "nope"}]')
        assert unknown.error is None and not unknown.steps[0].is_typed

        log = open_log(form())
        owner = log.document.by_name("clearButton")[0]
        log.execute(SetProperty(owner, signal_property("clicked"), StringValue('[{"do": "probe", "method": "save_invoice"}]')))
        generated = _generate(saved(log.document), "probe_form", tmp_path)
        assert "self._form.probe_ran()" in generated
        assert "Probe step" in generated

        blocked = open_log(form())
        blocked.execute(
            SetProperty(
                blocked.document.by_name("clearButton")[0],
                signal_property("clicked"),
                StringValue('[{"do": "slot", "target": "nameEdit", "slot": "clear()"}, {"do": "nope"}]'),
            )
        )
        silent = _generate(saved(blocked.document), "blocked_form", tmp_path)
        assert "_cbcs" not in silent
    finally:
        forget_package("m70s_verb_probe")


def test_slot_and_call_stay_editable_and_an_unknown_verb_does_not() -> None:
    assert _readonly_step(EventStep("slot", target="nameEdit", slot="clear()")) is False
    assert _readonly_step(EventStep("call", method="show_total")) is False
    assert _readonly_step(EventStep("slot", raw=object())) is True
    assert _readonly_step(EventStep("nope")) is True
