"""Check timing (order 300). ``plan`` decides what fails. This module wires it."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.logic_hooks import (
    CodegenContext,
    Contribution,
    Method,
)
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic
from app.features.form_builder.engine.logic.checks import (
    FieldPlan,
    RuntimeCheck,
    Skipped,
    close_helpers,
    formula_env,
    helpers_in,
    kind_text,
    plan,
    read_checks,
    source_imports,
    validator_pattern,
)
from app.features.form_builder.engine.logic.compat import is_name
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue

_ON_LEAVE = """\
if self._cbcs_quiet or name not in self._cbcs_dirty:
    return
self._cbcs_dirty.discard(name)
self._cbcs_run(name)"""

_ON_EDIT = """\
if self._cbcs_quiet:
    return
if dirty:
    self._cbcs_dirty.add(name)
row = self._cbcs_row(name)
if row is None:
    return
widget = row[1]
if widget.property("cbcsInvalid"):
    self._cbcs_run(name)"""

_ROW = """\
for row in self._cbcs_fields:
    if row[0] == name:
        return row
return None"""

_RUN = """\
row = self._cbcs_row(name)
if row is None:
    return
message = row[3]()
self._cbcs_present(row[1], row[2], message)"""

_RUN_TRACE = """\
row = self._cbcs_row(name)
if row is None:
    return
message = row[3]()
if self._cbcs_trace_on:
    self._cbcs_trace("check", row[4], message)
self._cbcs_present(row[1], row[2], message)"""

_PRESENT = """\
if label is not None:
    label.setText(message)
    label.setVisible(bool(message))
widget.setToolTip(message)
showing = bool(message)
if widget.property("cbcsInvalid") != showing:
    widget.setProperty("cbcsInvalid", showing)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)"""

_VALIDATE = """\
\"\"\"Check every field. Shows messages, focuses the first bad field, returns True if all pass.\"\"\"
first_bad = None
for name, widget, label, check, _source_ref in self._cbcs_fields:
    self._cbcs_dirty.discard(name)
    message = check()
    self._cbcs_present(widget, label, message)
    if message and first_bad is None:
        first_bad = widget
if first_bad is not None:
    first_bad.setFocus()
    return False
return True"""

_FILTER = """\
class _CbcsLeaveFilter(QObject):
    def __init__(self, ui):
        QObject.__init__(self)
        self._ui = ui

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusOut:
            self._ui._cbcs_on_leave(watched.objectName())
        return False
self._cbcs_leave_filter = _CbcsLeaveFilter(self)"""


class ChecksExpander:
    expander_id = "checks"
    level = 3
    order = 300

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        env = formula_env(doc)
        classes = QtClassTable.shared()
        methods: List[Method] = []
        setup: List[str] = []
        connects: List[Tuple[str, str]] = []
        diagnostics: List[FormDiagnostic] = []
        rows: List[str] = []
        labels: List[str] = []
        helper_ids: List[str] = []
        bodies: List[str] = []
        imports = []
        needs_form = False
        filtered = False
        for node in doc.iter_widgets():
            name = node.object_name
            if not name or not is_name(name) or name not in ctx.attribute_names:
                continue
            kind = kind_text(node)
            checks, failed = _stored(node)
            if failed:
                continue
            decimals = _decimals(node, kind)
            field = plan(
                node.class_name or "",
                checks,
                kind,
                label=_caption(doc, name),
                object_name=name,
                env=env,
                decimals=decimals,
            )
            if not _has_runtime(field):
                continue
            label_name = _error_label(node, ctx)
            if label_name is None:
                diagnostics.append(_missing_label(node))
            else:
                labels.append(label_name)
            read, read_helpers = _read_expr(node.class_name or "", name, decimals)
            body = _check_body(read, field)
            bodies.append(body)
            helper_ids.extend(read_helpers)
            for arm in field.runtime:
                if isinstance(arm, RuntimeCheck):
                    helper_ids.extend(arm.helpers)
                    helper_ids.extend(helpers_in(arm.predicate))
                    for other in arm.reads:
                        if other != name and other in ctx.attribute_names and is_name(other):
                            connects.append((other, "_cbcs_watch_%s" % name))
                    if "self._form" in arm.predicate:
                        needs_form = True
            if "self._form" in body:
                needs_form = True
            source_ref = "%s:cbcsValidate" % name
            methods.append(Method("_cbcs_check_%s" % name, body, source_ref))
            methods.append(Method("_cbcs_touch_%s" % name, 'self._cbcs_on_leave(%r)' % name, source_ref))
            methods.append(
                Method(
                    "_cbcs_recheck_%s" % name,
                    "self._cbcs_on_edit(%r, True)" % name,
                    source_ref,
                    params="*args",
                )
            )
            if any(isinstance(arm, RuntimeCheck) and arm.reads for arm in field.runtime):
                methods.append(
                    Method(
                        "_cbcs_watch_%s" % name,
                        "self._cbcs_on_edit(%r, False)" % name,
                        source_ref,
                        params="*args",
                    )
                )
            label_expr = "self.%s" % label_name if label_name else "None"
            rows.append(
                "(%r, self.%s, %s, self._cbcs_check_%s, %r)"
                % (name, name, label_expr, name, source_ref)
            )
            connects.append((name, "_cbcs_recheck_%s" % name))
            if _editing_finished(classes, node.class_name or ""):
                setup.append("self.%s.editingFinished.connect(self._cbcs_touch_%s)" % (name, name))
            else:
                filtered = True
                setup.append("self.%s.installEventFilter(self._cbcs_leave_filter)" % name)
            if field.validator:
                pattern = validator_pattern(kind, ctx.formats.currency)
                setup.append(
                    "self.%s.setValidator(QRegularExpressionValidator(QRegularExpression(%r), self.%s))"
                    % (name, pattern, name)
                )
                imports.append(("PySide6.QtCore", "QRegularExpression"))
                imports.append(("PySide6.QtGui", "QRegularExpressionValidator"))
        if not rows:
            return Contribution()
        if filtered:
            imports.append(("PySide6.QtCore", "QObject"))
            imports.append(("PySide6.QtCore", "QEvent"))
        header = ["self._cbcs_dirty = set()", "self._cbcs_quiet = False"]
        if ctx.trace:
            header.append("self._cbcs_trace_on = True")
        header.append("self._cbcs_fields = (%s,)" % ", ".join(rows))
        for label_name in labels:
            header.append("self.%s.setVisible(False)" % label_name)
        if filtered:
            header.extend(_FILTER.split("\n"))
        setup = header + setup
        source_ref = "cbcsValidate"
        methods.extend(
            (
                Method("_cbcs_on_leave", _ON_LEAVE, source_ref, params="name"),
                Method("_cbcs_on_edit", _ON_EDIT, source_ref, params="name, dirty"),
                Method("_cbcs_row", _ROW, source_ref, params="name"),
                Method("_cbcs_run", _RUN_TRACE if ctx.trace else _RUN, source_ref, params="name"),
                Method("_cbcs_present", _PRESENT, source_ref, params="widget, label, message"),
                Method("cbcs_validate", _VALIDATE, source_ref),
            )
        )
        closed = close_helpers(helper_ids + [item for body in bodies for item in helpers_in(body)])
        import_pairs = list(imports)
        import_pairs.extend(helper_imports_of(closed, "\n".join(bodies)))
        return Contribution(
            imports=tuple(sorted(set(import_pairs))),
            setup_lines=tuple(setup),
            methods=tuple(methods),
            helpers=closed,
            diagnostics=tuple(diagnostics),
            needs_form=needs_form,
            connects=tuple(_dedupe(connects)),
        )


EXPANDER = ChecksExpander()


def helper_imports_of(helper_ids: Sequence[str], body: str) -> Tuple[Tuple[str, str], ...]:
    from app.features.form_builder.engine.logic.checks import helper_imports

    found = set(helper_imports(helper_ids))
    found.update(source_imports(body))
    return tuple(sorted(found))


def _stored(node: WidgetNode) -> Tuple[Tuple[object, ...], bool]:
    value = node.value("cbcsValidate")
    if not isinstance(value, StringValue) or not value.text.strip():
        return (), False
    read = read_checks(value.text)
    if read.error is not None:
        return (), True
    return read.checks, False


def _has_runtime(field: FieldPlan) -> bool:
    return any(isinstance(arm, (RuntimeCheck, Skipped)) for arm in field.runtime)


def _check_body(read: str, field: FieldPlan) -> str:
    lines = ["value = %s" % read]
    for arm in field.runtime:
        if isinstance(arm, Skipped):
            lines.append(arm.comment)
            continue
        if arm.comment:
            lines.append("# %s" % arm.comment)
        lines.append("if %s:" % arm.predicate)
        lines.append("    return %s" % arm.message)
    lines.append('return ""')
    return "\n".join(lines)


def _read_expr(class_name: str, name: str, decimals: int) -> Tuple[str, Tuple[str, ...]]:
    target = "self.%s" % name
    if class_name == "QLineEdit":
        return "_cbcs_read_line(%s)" % target, ("_cbcs_read_line",)
    if class_name in ("QPlainTextEdit", "QTextEdit"):
        return "_cbcs_read_plain(%s)" % target, ("_cbcs_read_plain",)
    if class_name == "QSpinBox":
        return "_cbcs_read_spin(%s)" % target, ("_cbcs_read_spin",)
    if class_name == "QDoubleSpinBox":
        return "_cbcs_read_double(%s, %d)" % (target, decimals), ("_cbcs_read_double",)
    if class_name == "QDateEdit":
        return "_cbcs_read_dateedit(%s)" % target, ("_cbcs_read_dateedit",)
    if class_name == "QTimeEdit":
        return "_cbcs_read_timeedit(%s)" % target, ("_cbcs_read_timeedit",)
    if class_name == "QDateTimeEdit":
        return "_cbcs_read_datetime(%s)" % target, ("_cbcs_read_datetime",)
    return "_cbcs_read_shown(%s)" % target, ("_cbcs_read_shown",)


def _editing_finished(classes: QtClassTable, class_name: str) -> bool:
    if class_name == "QLineEdit":
        return True
    return any(info.name == "QAbstractSpinBox" for info in classes.chain(class_name))


def _error_label(node: WidgetNode, ctx: CodegenContext) -> Optional[str]:
    value = node.value("cbcsErrorLabel")
    if not isinstance(value, StringValue):
        return None
    name = value.text
    if name and is_name(name) and name in ctx.attribute_names:
        return name
    return None


def _missing_label(node: WidgetNode) -> FormDiagnostic:
    info = CODES.get("FB119")
    severity = info.severity if info is not None else CODES["FB119"].severity if "FB119" in CODES else None
    from app.features.form_builder.engine.diagnostics import Severity

    if severity is None:
        severity = Severity.INFO
    return FormDiagnostic(
        code="FB119",
        severity=severity,
        message="A check has no error label.",
        location=DiagnosticLocation(node_id=node.id, object_name=node.object_name, property="cbcsErrorLabel"),
        source="codegen",
    )


def _caption(doc: UiDocument, name: str) -> str:
    from app.features.form_builder.engine.query.tab_stops import display_name

    text = display_name(doc, name)
    if text.endswith(":"):
        return text[:-1]
    return text


def _decimals(node: WidgetNode, kind: str) -> int:
    if kind.startswith("number:") and kind.split(":", 1)[1].isdigit():
        return int(kind.split(":", 1)[1])
    value = node.value("decimals")
    if isinstance(value, NumberValue):
        return value.value
    return 2


def _dedupe(pairs: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for pair in pairs:
        if pair not in found:
            found.append(pair)
    return found
