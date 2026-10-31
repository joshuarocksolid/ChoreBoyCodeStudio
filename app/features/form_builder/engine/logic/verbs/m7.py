"""M7 step verbs (CONTRACTS section 18.4, LOGIC_DESIGN section 4.12).

One ``VerbSpec`` per verb. ``register`` is discovered beside ``m6.py``. Formula
text goes through ``analyze`` and ``compile_formula``. FB117 and FB120 are
declared by M7.1a; this module only produces them.
"""

from __future__ import annotations

import os
from contextvars import ContextVar, Token
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.verbs import FieldSpec, VerbSpec, require_text

_FORM_LOOKUP: ContextVar[Optional[str]] = ContextVar("cbcs_m7_forms_dir", default=None)

_LEVELS = {"info": "information", "warning": "warning", "critical": "critical"}
_CLOSE = {"accept": "accept", "reject": "reject", "close": "close"}
_CLOSE_WORDS = {"accept": "Accept (OK)", "reject": "Cancel", "close": "Close this form"}
_TEXT_WRITE = {
    "QLineEdit": "setText",
    "QLabel": "setText",
    "QPlainTextEdit": "setPlainText",
    "QTextEdit": "setPlainText",
    "QComboBox": "setCurrentText",
}
_VALUE_WRITE = {
    "QSpinBox": "setValue",
    "QSlider": "setValue",
    "QDial": "setValue",
    "QProgressBar": "setValue",
    "QDoubleSpinBox": "setValue",
}
_CHECK_WRITE = {"QCheckBox": "setChecked", "QRadioButton": "setChecked"}
_DATE_WRITE = {"QDateEdit": "setDate", "QTimeEdit": "setTime", "QDateTimeEdit": "setDateTime"}
_CLEAR = {
    "QLineEdit": 'setText(u"")',
    "QLabel": 'setText(u"")',
    "QPlainTextEdit": 'setPlainText(u"")',
    "QTextEdit": 'setPlainText(u"")',
    "QComboBox": "setCurrentIndex(-1)",
    "QCheckBox": "setChecked(False)",
    "QRadioButton": "setChecked(False)",
    "QSpinBox": "setValue({owner}.minimum())",
    "QDoubleSpinBox": "setValue({owner}.minimum())",
    "QSlider": "setValue({owner}.minimum())",
    "QDial": "setValue({owner}.minimum())",
}


def bind_form_lookup(scope: Any) -> Token:
    """Remember the forms folder for this generate, so ``openForm`` can raise FB120."""
    path = getattr(scope, "ui_path", "") or ""
    folder = os.path.dirname(os.path.abspath(path)) if path else ""
    return _FORM_LOOKUP.set(folder or None)


def reset_form_lookup(token: Token) -> None:
    _FORM_LOOKUP.reset(token)


def _refused(message: str) -> None:
    from app.features.form_builder.engine.logic.codec import _Refused

    raise _Refused(1, message)


def _text(step: Any, name: str, default: str = "") -> str:
    raw = getattr(step, "raw", None)
    if raw is None:
        value = getattr(step, name, default)
        return value if isinstance(value, str) else default
    value = raw.field(name, default)
    return value if isinstance(value, str) else default


def _seq(step: Any, name: str) -> Tuple[str, ...]:
    raw = getattr(step, "raw", None)
    value = raw.field(name) if raw is not None else None
    if not isinstance(value, tuple):
        return ()
    found = []
    for item in value:
        if isinstance(item, str):
            found.append(item)
    return tuple(found)


def _names_ok(names: Sequence[str]) -> bool:
    return all(compat.is_name(name) for name in names)


def _bag(ctx: Any) -> Dict[str, List[Any]]:
    bag = getattr(ctx, "bag", None)
    if isinstance(bag, dict):
        return bag
    return {"helpers": [], "imports": [], "diagnostics": []}


def _add(ctx: Any, key: str, item: Any) -> None:
    bag = _bag(ctx)
    if item not in bag[key]:
        bag[key].append(item)


def _class_of(ctx: Any, name: str) -> str:
    doc = getattr(ctx, "doc", None)
    classes = getattr(ctx, "classes", None)
    if doc is None or classes is None or not name:
        return ""
    found = doc.by_name(name)
    if not found:
        return ""
    node = doc.node(found[0])
    if node is None:
        return ""
    return compat.node_class(doc, classes, node)[0]


def _node(ctx: Any, name: str) -> Any:
    doc = getattr(ctx, "doc", None)
    if doc is None or not name:
        return None
    found = doc.by_name(name)
    if not found:
        return None
    return doc.node(found[0])


def _prop_text(ctx: Any, name: str, key: str) -> str:
    node = _node(ctx, name)
    if node is None:
        return ""
    entry = node.prop(key)
    if entry is None:
        return ""
    text = getattr(entry.value, "text", "")
    return text if isinstance(text, str) else ""


def _env(ctx: Any) -> Any:
    cached = getattr(ctx, "formula_env", None)
    if cached is not None:
        return cached
    from app.features.form_builder.engine.logic.formula.env import FormulaEnv, WidgetFacts

    doc = getattr(ctx, "doc", None)
    classes = getattr(ctx, "classes", None)
    widgets: Dict[str, Any] = {}
    if doc is not None and classes is not None:
        for node in doc.iter_preorder():
            name = getattr(node, "object_name", None) or getattr(node, "name", None)
            if not isinstance(name, str) or not name:
                continue
            class_name = compat.node_class(doc, classes, node)[0]
            widgets[name] = WidgetFacts(class_name or "QWidget", display=name)
    env = FormulaEnv.for_test(widgets)
    if ctx is not None:
        try:
            ctx.formula_env = env
        except Exception:
            pass
    return env


def compile_text(text: str, slot: Any, ctx: Any) -> Tuple[Optional[str], Optional[str]]:
    """Compiled source, or ``(None, FBcode)`` when the formula has an Error."""
    from app.features.form_builder.engine.diagnostics import CODES, Severity
    from app.features.form_builder.engine.logic.formula import analyze, compile_formula

    import app.features.form_builder.engine.diagnostic_codes.fb1xx_formula  # noqa: F401

    analysis = analyze(text, _env(ctx), slot)
    try:
        emitted = compile_formula(analysis, _env(ctx))
    except ValueError:
        code = "FB108"
        for problem in analysis.problems:
            info = CODES.get(problem.code)
            if info is None or info.severity == Severity.ERROR:
                code = problem.code or code
                break
        _diagnose(ctx, code, _problem_message(analysis, code), _text(getattr(ctx, "step", None), "field"))
        return None, code
    for helper in emitted.helpers:
        _add(ctx, "helpers", helper)
    for pair in emitted.imports:
        _add(ctx, "imports", pair)
    source = emitted.source.replace("\n", " ").strip()
    return source, None


def _problem_message(analysis: Any, code: str) -> str:
    for problem in analysis.problems:
        if problem.code == code and problem.message:
            return str(problem.message)
    from app.features.form_builder.engine.diagnostics import CODES

    info = CODES.get(code)
    return info.title if info is not None else code


def _diagnose(ctx: Any, code: str, message: str, object_name: str, fix: str = "") -> None:
    from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic, QuickFix, Severity

    import app.features.form_builder.engine.diagnostic_codes.fb1xx_formula  # noqa: F401

    info = CODES.get(code)
    severity = info.severity if info is not None else Severity.ERROR
    fixes = ()
    if fix:
        fixes = (QuickFix("show-rule", fix, action="show-rule", args=(("widget", object_name),)),)
    _add(
        ctx,
        "diagnostics",
        FormDiagnostic(
            code,
            severity,
            message,
            DiagnosticLocation(object_name=object_name or None, property="cbcsOn"),
            "logic.steps",
            fixes,
        ),
    )


def _owner(ctx: Any, name: str) -> str:
    root = getattr(ctx, "root", "")
    if name and name == root:
        return "self._form"
    return "self.%s" % name


def _present(ctx: Any, name: str) -> bool:
    if not compat.is_name(name):
        return False
    names = getattr(ctx, "attribute_names", ()) or ()
    root = getattr(ctx, "root", "")
    return name == root or name in names


def _quote(text: str) -> str:
    from app.features.form_builder.engine.codegen.literals import py_string

    return py_string(text)


def _need_box(ctx: Any) -> None:
    _add(ctx, "imports", ("PySide6.QtWidgets", "QMessageBox"))


def _message_call(level: str, expr: str) -> str:
    method = _LEVELS.get(level, "information")
    return "QMessageBox.%s(self._form, u\"\", %s)" % (method, expr)


def _one_off(step: Any, ctx: Any, name: str, prop: str) -> None:
    if not _prop_text(ctx, name, prop).strip():
        return
    _diagnose(
        ctx,
        "FB117",
        "A one-off step changes a property a rule controls",
        name,
        "Show the rule",
    )


def _block_names(step: Any, names: Sequence[str]) -> bool:
    del step
    return not _names_ok(names)


def _validate_names(verb: str, taken: Any, names: Tuple[str, ...], lists: Tuple[str, ...] = ()) -> None:
    require_text(verb, names, taken)
    for name in names:
        if not compat.is_name(str(taken.get(name, ""))):
            _refused('a "%s" step needs "%s" as a name' % (verb, name))
    for name in lists:
        value = taken.get(name)
        if value is None:
            continue
        if isinstance(value, str) or not isinstance(value, tuple) or not value:
            _refused('a "%s" step needs "%s" as a list of names' % (verb, name))
        if not all(isinstance(item, str) and compat.is_name(item) for item in value):
            _refused('a "%s" step needs "%s" as a list of names' % (verb, name))


def _validate_validate(taken: Any) -> None:
    _validate_names("validate", taken, (), ("fields",))


def _skip(ctx: Any, code: str) -> Tuple[str, ...]:
    number = getattr(ctx, "step_number", 0) or 0
    if number:
        return ("# step %d skipped (%s: see Problems)" % (number, code),)
    return ("# step skipped (%s: see Problems)" % code,)


def _validate_set(taken: Any) -> None:
    require_text("set", ("field", "formula"), taken)
    if not compat.is_name(str(taken.get("field", ""))):
        _refused('a "set" step needs "field" as a name')


def _validate_clear(taken: Any) -> None:
    value = taken.get("fields")
    if value is None:
        _refused('a "clear" step needs "fields" as a list of names')
    _validate_names("clear", taken, (), ("fields",))


def _validate_field(verb: str) -> Any:
    def check(taken: Any) -> None:
        _validate_names(verb, taken, ("field",))

    return check


def _validate_message(taken: Any) -> None:
    level = taken.get("level", "info")
    if level is not None and level not in _LEVELS:
        _refused('a "message" step needs "level" to be info, warning or critical')
    text = taken.get("text")
    formula = taken.get("formula")
    if not (isinstance(text, str) and text) and not (isinstance(formula, str) and formula):
        _refused('a "message" step needs "text" or "formula"')


def _validate_ask(taken: Any) -> None:
    require_text("ask", ("text",), taken)


def _validate_stop(taken: Any) -> None:
    message = taken.get("message")
    if message is not None and not isinstance(message, str):
        _refused('a "stop" step needs "message" as text')


def _validate_page(taken: Any) -> None:
    _validate_names("page", taken, ("field", "page"))


def _validate_open(taken: Any) -> None:
    require_text("openForm", ("form",), taken)
    if not compat.is_name(str(taken.get("form", ""))):
        _refused('an "openForm" step needs "form" as a name')
    mode = taken.get("mode", "dialog")
    if mode is not None and mode not in ("dialog", "window"):
        _refused('an "openForm" step needs "mode" to be dialog or window')
    for name in ("key", "then"):
        value = taken.get(name)
        if value is not None and (not isinstance(value, str) or (value and not compat.is_name(value))):
            _refused('an "openForm" step needs "%s" as a name' % name)


def _validate_close(taken: Any) -> None:
    result = taken.get("result")
    if result not in _CLOSE:
        _refused('a "close" step needs "result" to be accept, reject or close')


def _words_validate(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    names = _seq(step, "fields")
    if names:
        return "Check %s (stops here if a field fails)" % ", ".join(names)
    return "Check all fields (stops here if a field fails)"


def _words_set(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Set %s to %s" % (_text(step, "field"), _text(step, "formula"))


def _words_clear(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Clear %s" % ", ".join(_seq(step, "fields"))


def _words_focus(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Move focus to %s" % _text(step, "field")


def _words_enable(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Enable %s" % _text(step, "field")


def _words_disable(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Disable %s" % _text(step, "field")


def _words_show(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Show %s" % _text(step, "field")


def _words_hide(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Hide %s" % _text(step, "field")


def _words_message(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    formula = _text(step, "formula")
    if formula:
        return "Show a message %s" % formula
    return "Show a message %s" % _quote(_text(step, "text"))


def _words_ask(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Ask %s (stops here on No)" % _quote(_text(step, "text"))


def _words_stop(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Stop here if %s" % (step.when or "")


def _words_page(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Switch %s to %s" % (_text(step, "field"), _text(step, "page"))


def _words_open(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Open %s" % _text(step, "form")


def _words_close(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return _CLOSE_WORDS.get(_text(step, "result"), "Close this form")


def _emit_validate(step: Any, ctx: Any) -> Tuple[str, ...]:
    del step
    return ("if not self.cbcs_validate():", "    return")


def _set_type(class_name: str) -> Any:
    from app.features.form_builder.engine.logic.formula.types import DATE, NUMBER, TEXT, WHOLE, YESNO

    if class_name in _VALUE_WRITE:
        return NUMBER if class_name == "QDoubleSpinBox" else WHOLE
    if class_name in _CHECK_WRITE:
        return YESNO
    if class_name in _DATE_WRITE:
        return DATE
    return TEXT


def _emit_set(step: Any, ctx: Any) -> Tuple[str, ...]:
    from app.features.form_builder.engine.logic.formula.env import SlotKind

    name = _text(step, "field")
    if not _present(ctx, name):
        return ("# (missing %s)" % name,)
    ctx.step = step
    source, code = compile_text(_text(step, "formula"), SlotKind.set(_set_type(_class_of(ctx, name))), ctx)
    if code or not source:
        return _skip(ctx, code or "FB108")
    owner = _owner(ctx, name)
    class_name = _class_of(ctx, name)
    if class_name in _TEXT_WRITE:
        return ("%s.%s(str(%s))" % (owner, _TEXT_WRITE[class_name], source),)
    if class_name in _VALUE_WRITE:
        return ("%s.%s(%s)" % (owner, _VALUE_WRITE[class_name], source),)
    if class_name in _CHECK_WRITE:
        return ("%s.setChecked(bool(%s))" % (owner, source),)
    if class_name in _DATE_WRITE:
        return ("%s.%s(%s)" % (owner, _DATE_WRITE[class_name], source),)
    return ("%s.setText(str(%s))" % (owner, source),)


def _emit_clear(step: Any, ctx: Any) -> Tuple[str, ...]:
    lines = []
    for name in _seq(step, "fields"):
        if not _present(ctx, name):
            lines.append("# (missing %s)" % name)
            continue
        owner = _owner(ctx, name)
        pattern = _CLEAR.get(_class_of(ctx, name), 'setText(u"")')
        lines.append("%s.%s" % (owner, pattern.format(owner=owner)))
    return tuple(lines)


def _emit_focus(step: Any, ctx: Any) -> Tuple[str, ...]:
    name = _text(step, "field")
    if not _present(ctx, name):
        return ("# (missing %s)" % name,)
    return ("%s.setFocus()" % _owner(ctx, name),)


def _emit_flag(step: Any, ctx: Any, call: str, prop: str) -> Tuple[str, ...]:
    name = _text(step, "field")
    if not _present(ctx, name):
        return ("# (missing %s)" % name,)
    ctx.step = step
    _one_off(step, ctx, name, prop)
    return ("%s.%s" % (_owner(ctx, name), call),)


def _emit_enable(step: Any, ctx: Any) -> Tuple[str, ...]:
    return _emit_flag(step, ctx, "setEnabled(True)", "cbcsEnabledWhen")


def _emit_disable(step: Any, ctx: Any) -> Tuple[str, ...]:
    return _emit_flag(step, ctx, "setEnabled(False)", "cbcsEnabledWhen")


def _emit_show(step: Any, ctx: Any) -> Tuple[str, ...]:
    return _emit_flag(step, ctx, "show()", "cbcsVisibleWhen")


def _emit_hide(step: Any, ctx: Any) -> Tuple[str, ...]:
    return _emit_flag(step, ctx, "hide()", "cbcsVisibleWhen")


def _emit_message(step: Any, ctx: Any) -> Tuple[str, ...]:
    from app.features.form_builder.engine.logic.formula.env import SlotKind

    _need_box(ctx)
    formula = _text(step, "formula")
    level = _text(step, "level", "info") or "info"
    ctx.step = step
    if formula:
        source, code = compile_text(formula, SlotKind.message(), ctx)
        if code or not source:
            return _skip(ctx, code or "FB108")
        expr = "str(%s)" % source
    else:
        expr = _quote(_text(step, "text"))
    return (_message_call(level, expr),)


def _emit_ask(step: Any, ctx: Any) -> Tuple[str, ...]:
    _need_box(ctx)
    text = _quote(_text(step, "text"))
    return (
        "if QMessageBox.question(self._form, u\"\", %s, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:"
        % text,
        "    return",
    )


def _emit_stop(step: Any, ctx: Any) -> Tuple[str, ...]:
    message = _text(step, "message")
    if not message:
        return ("return",)
    _need_box(ctx)
    return (_message_call("info", _quote(message)), "return")


def _emit_page(step: Any, ctx: Any) -> Tuple[str, ...]:
    field = _text(step, "field")
    page = _text(step, "page")
    if not _present(ctx, field) or not _present(ctx, page):
        missing = field if not _present(ctx, field) else page
        return ("# (missing %s)" % missing,)
    return ("%s.setCurrentWidget(%s)" % (_owner(ctx, field), _owner(ctx, page)),)


def _window_class(stem: str) -> str:
    parts = [part for part in stem.split("_") if part]
    return "".join(part[:1].upper() + part[1:] for part in parts) + "Window"


def form_is_generated(stem: str) -> bool:
    """False when this generate can see the forms folder and the form is not in it."""
    if not compat.is_name(stem):
        return False
    folder = _FORM_LOOKUP.get()
    if not folder or not os.path.isdir(folder):
        return True
    return os.path.isfile(os.path.join(folder, "%s.ui" % stem))


def _emit_open(step: Any, ctx: Any) -> Tuple[str, ...]:
    stem = _text(step, "form")
    if not form_is_generated(stem):
        ctx.step = step
        _diagnose(ctx, "FB120", "That form isn't in this project's forms folder", stem)
        return _skip(ctx, "FB120")
    class_name = _window_class(stem)
    local = "_cbcs_%s" % stem
    lines = ["from forms.%s_window import %s" % (stem, class_name), "%s = %s(self._form)" % (local, class_name)]
    key = _text(step, "key")
    if key and _present(ctx, key):
        lines.append("%s.cbcs_open(%s.currentData())" % (local, _owner(ctx, key)))
    mode = _text(step, "mode", "dialog") or "dialog"
    lines.append("%s.exec()" % local if mode == "dialog" else "%s.show()" % local)
    then = _text(step, "then")
    if then:
        lines.append("# then %s" % then)
    return tuple(lines)


def _emit_close(step: Any, ctx: Any) -> Tuple[str, ...]:
    result = _CLOSE.get(_text(step, "result"), "close")
    return ("self._form.%s()" % result,)


def _block_field(step: Any) -> bool:
    return _block_names(step, (_text(step, "field"),))


def _block_clear(step: Any) -> bool:
    return _block_names(step, _seq(step, "fields"))


def _block_validate(step: Any) -> bool:
    return _block_names(step, _seq(step, "fields"))


def _block_open(step: Any) -> bool:
    names = [_text(step, "form")]
    for key in ("key",):
        value = _text(step, key)
        if value:
            names.append(value)
    return _block_names(step, names)


def _block_page(step: Any) -> bool:
    return _block_names(step, (_text(step, "field"), _text(step, "page")))


def _block_close(step: Any) -> bool:
    return _text(step, "result") not in _CLOSE


def _never(step: Any) -> bool:
    del step
    return False


def _spec(
    name: str,
    fields: Tuple[FieldSpec, ...],
    validate: Any,
    emit: Any,
    blocks: Any,
    group_id: str,
    words: Any,
) -> VerbSpec:
    return VerbSpec(name, fields, False, validate, emit, blocks, group_id, words, True)


def register(registry: Any) -> None:
    add = registry.add
    field = FieldSpec
    add(_spec("validate", (field("fields", "object_name"),), _validate_validate, _emit_validate, _block_validate, "fields", _words_validate))
    add(_spec("set", (field("field", "object_name", True), field("formula", "formula", True)), _validate_set, _emit_set, _block_field, "fields", _words_set))
    add(_spec("clear", (field("fields", "object_name", True),), _validate_clear, _emit_clear, _block_clear, "fields", _words_clear))
    add(_spec("focus", (field("field", "object_name", True),), _validate_field("focus"), _emit_focus, _block_field, "fields", _words_focus))
    add(_spec("enable", (field("field", "object_name", True),), _validate_field("enable"), _emit_enable, _block_field, "show", _words_enable))
    add(_spec("disable", (field("field", "object_name", True),), _validate_field("disable"), _emit_disable, _block_field, "show", _words_disable))
    add(_spec("show", (field("field", "object_name", True),), _validate_field("show"), _emit_show, _block_field, "show", _words_show))
    add(_spec("hide", (field("field", "object_name", True),), _validate_field("hide"), _emit_hide, _block_field, "show", _words_hide))
    add(
        _spec(
            "message",
            (field("level", "enum"), field("text", "text"), field("formula", "formula")),
            _validate_message,
            _emit_message,
            _never,
            "show",
            _words_message,
        )
    )
    add(_spec("ask", (field("text", "text", True),), _validate_ask, _emit_ask, _never, "show", _words_ask))
    add(_spec("stop", (field("message", "text"),), _validate_stop, _emit_stop, _never, "flow", _words_stop))
    add(_spec("page", (field("field", "object_name", True), field("page", "object_name", True)), _validate_page, _emit_page, _block_page, "show", _words_page))
    add(
        _spec(
            "openForm",
            (field("form", "text", True), field("mode", "enum"), field("key", "object_name"), field("then", "text")),
            _validate_open,
            _emit_open,
            _block_open,
            "windows",
            _words_open,
        )
    )
    add(_spec("close", (field("result", "enum", True),), _validate_close, _emit_close, _block_close, "windows", _words_close))
