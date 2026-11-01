"""Format on leave (order 350). US helpers stay as they are. Other settings swap afterwards."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.codegen.logic_hooks import CodegenContext, Contribution, FormatSettings, Method
from app.features.form_builder.engine.logic.checks import close_helpers, helper_imports, helpers_in, source_imports
from app.features.form_builder.engine.logic.compat import is_name
from app.features.form_builder.engine.project.formats import format_expr
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.engine.ui4.values import NumberValue, StringValue

_SPINS = frozenset({"QSpinBox", "QDoubleSpinBox"})
_DATE_FORMAT = {
    ("MM/DD/YYYY", "date:short"): "MM/dd/yyyy",
    ("MM/DD/YYYY", "date:long"): "MMMM d, yyyy",
    ("MM/DD/YYYY", "date:iso"): "yyyy-MM-dd",
    ("DD/MM/YYYY", "date:short"): "dd/MM/yyyy",
    ("DD/MM/YYYY", "date:long"): "MMMM d, yyyy",
    ("DD/MM/YYYY", "date:iso"): "yyyy-MM-dd",
    ("YYYY-MM-DD", "date:short"): "yyyy-MM-dd",
    ("YYYY-MM-DD", "date:long"): "MMMM d, yyyy",
    ("YYYY-MM-DD", "date:iso"): "yyyy-MM-dd",
}


class FormatsExpander:
    expander_id = "formats"
    level = 3
    order = 350

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        methods: List[Method] = []
        setup: List[str] = ["self._cbcs_quiet = False"]
        helper_ids: List[str] = []
        bodies: List[str] = []
        for node in doc.iter_widgets():
            name = node.object_name
            code = _format_code(node)
            if not name or not code or not is_name(name) or name not in ctx.attribute_names:
                continue
            class_name = node.class_name or ""
            if class_name in _SPINS:
                continue
            if class_name == "QDateEdit":
                display = _DATE_FORMAT.get((ctx.formats.date, code))
                if display is None:
                    continue
                setup.append("self.%s.setDisplayFormat(%r)" % (name, display))
                continue
            if class_name != "QLineEdit":
                continue
            built = _line_edit(name, code, ctx.formats, _decimals(node))
            if built is None:
                continue
            leave, write, ids = built
            source_ref = "%s:cbcsFormat" % name
            methods.append(Method("_cbcs_format_%s" % name, leave, source_ref))
            methods.append(Method("_cbcs_write_%s" % name, write, source_ref, params="value"))
            setup.append("self.%s.editingFinished.connect(self._cbcs_format_%s)" % (name, name))
            helper_ids.extend(ids)
            bodies.append(leave)
            bodies.append(write)
        if len(setup) == 1 and not methods:
            return Contribution()
        text = "\n".join(bodies)
        closed = close_helpers(helper_ids + list(helpers_in(text)))
        imports = set(helper_imports(closed))
        imports.update(source_imports(text))
        return Contribution(
            imports=tuple(sorted(imports)),
            setup_lines=tuple(setup),
            methods=tuple(methods),
            helpers=closed,
        )


EXPANDER = FormatsExpander()


def _line_edit(
    name: str, code: str, settings: FormatSettings, decimals: int
) -> Optional[Tuple[str, str, Tuple[str, ...]]]:
    target = "self.%s" % name
    resolved = _resolve(code, decimals)
    if resolved is None:
        return None
    expr = format_expr(resolved, "value", settings)
    if expr is None:
        return None
    helpers = list(expr.helpers)
    if resolved == "money":
        read = ["value = _cbcs_read_money(%s)" % target, "if value is None:", "    return"]
        helpers.append("_cbcs_read_money")
    elif resolved.startswith("percent:"):
        # A bare number is the ratio (0.125 shows as 12.5%). Text with % is percent points.
        read = [
            "raw = %s.text().strip()" % target,
            'if raw == "":',
            "    return",
            'if "%" in raw:',
            "    value = _cbcs_read_percent(%s)" % target,
            "else:",
            "    value = _cbcs_number(raw)",
            "if value is None:",
            "    return",
        ]
        helpers.extend(("_cbcs_read_percent", "_cbcs_number"))
    elif resolved.startswith("number:"):
        places = int(resolved.split(":", 1)[1])
        read = [
            "value = _cbcs_read_number(%s, %d)" % (target, places),
            "if value is None:",
            "    return",
        ]
        helpers.append("_cbcs_read_number")
    elif resolved.startswith("date:"):
        order, sentence = _date_order(code, settings)
        read = [
            "raw = %s.text().strip()" % target,
            'if raw == "":',
            "    return",
            "value = _cbcs_read_short_date(raw, %r)" % order,
            "if value is None:",
            "    %s.setToolTip(%r)" % (target, sentence),
            "    return",
            "%s.setToolTip('')" % target,
        ]
        helpers.append("_cbcs_read_short_date")
    else:
        read = ["value = _cbcs_read_line(%s)" % target, "if value is None:", "    return"]
        helpers.append("_cbcs_read_line")
    shown = _shown(expr.source, settings, resolved)
    leave = read + shown + ["if shown is None:", "    return"] + _quiet(target)
    write = _shown(expr.source, settings, resolved) + ["if shown is None:", '    shown = ""'] + _quiet(target)
    return "\n".join(leave), "\n".join(write), tuple(helpers)


def _date_order(code: str, settings: FormatSettings) -> Tuple[str, str]:
    """Project order for a short date. Anything else stays month, day, year.

    A string that is not a date in that order is left in the field and the
    tooltip says how to type it. The reader does not swap the day and the month.
    """
    if code == "date:short" and settings.date == "DD/MM/YYYY":
        return "DMY", "Enter a date as DD/MM/YYYY."
    if code == "date:short" and settings.date == "YYYY-MM-DD":
        return "YMD", "Enter a date as YYYY-MM-DD."
    if code == "date:iso":
        return "YMD", "Enter a date as YYYY-MM-DD."
    return "MDY", "Enter a date as MM/DD/YYYY."


def _resolve(code: str, decimals: int) -> Optional[str]:
    if code == "money":
        return "money"
    if code == "number":
        return "number:%d" % decimals
    if code.startswith("number:") and code.split(":", 1)[1].isdigit():
        return code
    if code == "percent":
        return "percent:0"
    if code.startswith("percent:") and code.split(":", 1)[1].isdigit():
        return code
    if code in ("date:short", "date:long", "date:iso", "text:upper", "text:proper"):
        return code
    return None


def _shown(expr: str, settings: FormatSettings, code: str) -> List[str]:
    lines = ["shown = %s" % expr]
    if code == "money" and (settings.currency != "$" or settings.grouping != "1,234.50"):
        lines.extend(_grouping(settings.grouping))
        if settings.currency != "$":
            lines.append('shown = shown.replace("$", %r)' % settings.currency)
    elif code.startswith("number:") or code.startswith("percent:"):
        if settings.grouping != "1,234.50":
            lines.extend(_grouping(settings.grouping))
    elif code == "date:short" and settings.date == "DD/MM/YYYY":
        lines.extend(
            (
                "if shown:",
                '    bits = shown.split("/")',
                "    if len(bits) == 3:",
                '        shown = bits[1] + "/" + bits[0] + "/" + bits[2]',
            )
        )
    elif code == "date:short" and settings.date == "YYYY-MM-DD":
        lines.extend(
            (
                "if shown:",
                '    bits = shown.split("/")',
                "    if len(bits) == 3:",
                '        shown = bits[2] + "-" + bits[0] + "-" + bits[1]',
            )
        )
    return lines


def _grouping(grouping: str) -> Sequence[str]:
    if grouping == "1.234,50":
        return ('shown = shown.replace(",", "\\x00").replace(".", ",").replace("\\x00", ".")',)
    if grouping == "1 234.50":
        return ('shown = shown.replace(",", " ")',)
    if grouping == "1234.50":
        return ('shown = shown.replace(",", "")',)
    return ()


def _quiet(target: str) -> List[str]:
    return [
        "self._cbcs_quiet = True",
        "try:",
        "    %s.setText(shown)" % target,
        "finally:",
        "    self._cbcs_quiet = False",
    ]


def _format_code(node: WidgetNode) -> str:
    value = node.value("cbcsFormat")
    if isinstance(value, StringValue):
        return value.text.strip()
    return ""


def _decimals(node: WidgetNode) -> int:
    value = node.value("decimals")
    if isinstance(value, NumberValue):
        return value.value
    return 2
