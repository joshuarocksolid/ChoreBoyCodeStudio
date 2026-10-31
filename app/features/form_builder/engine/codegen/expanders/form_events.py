"""Form events Opened and Closing (CONTRACTS section 18.2, order 900).

``cbcsOnOpened`` is called as the last ``_cbcs_setup`` line. ``cbcsOnClosing``
runs from ``_CbcsCloseGuard``. The guard is defined inside ``_cbcs_setup``
because a contribution cannot add a module-level class. A closing step that
returns leaves the form open.
"""

from __future__ import annotations

from typing import List, Tuple

from app.features.form_builder.engine.codegen.expanders.steps import _body, _generates
from app.features.form_builder.engine.codegen.logic_hooks import CodegenContext, Contribution, Method, one_line
from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.events_codec import read_list
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.values import StringValue

_FORM_SIGNALS = ("opened", "closing")


class FormEventsExpander:
    expander_id = "form_events"
    level = 1
    order = 900

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        root = doc.root.object_name
        if not isinstance(root, str) or not compat.is_name(root):
            return Contribution()
        classes = QtClassTable.shared()
        bag = {"helpers": [], "imports": [], "diagnostics": []}
        methods: List[Method] = []
        opened = ""
        closing = ""
        for signal_name in _FORM_SIGNALS:
            parsed = _read(doc, signal_name)
            if parsed is None or not _generates(parsed) or not compat.is_name(signal_name):
                continue
            handler = "_cbcs_%s_%s" % (root, signal_name)
            if not compat.is_name(handler):
                continue
            source_ref = one_line("%s: When %s" % (root, signal_name))
            body = _body(doc, classes, ctx, root, parsed.steps, source_ref, bag, root)
            if signal_name == "closing":
                body = body + "\nreturn True" if body else "return True"
                closing = handler
            else:
                opened = handler
            methods.append(Method(name=handler, body=body, source_ref=source_ref))
        if not methods:
            return Contribution()
        setup: List[str] = []
        imports: List[Tuple[str, str]] = list(bag["imports"])
        if closing:
            setup.extend(_guard_lines(ctx.ui_class_name, ctx.form_param, closing))
            for pair in (
                ("PySide6.QtCore", "QObject"),
                ("PySide6.QtCore", "QEvent"),
                ("PySide6.QtCore", "Qt"),
                ("PySide6.QtWidgets", "QDialog"),
            ):
                if pair not in imports:
                    imports.append(pair)
        if opened:
            setup.append("self.%s()" % opened)
        return Contribution(
            imports=tuple(imports),
            setup_lines=tuple(setup),
            methods=tuple(methods),
            helpers=tuple(bag["helpers"]),
            diagnostics=tuple(bag["diagnostics"]),
            needs_form=True,
        )


def _read(doc: UiDocument, signal_name: str):
    from app.features.form_builder.engine.logic.storage import signal_property

    entry = doc.root.prop(signal_property(signal_name))
    if entry is None or not isinstance(entry.value, StringValue):
        return None
    return read_list(entry.value.text)


def _guard_lines(ui_class: str, form_param: str, handler: str) -> Tuple[str, ...]:
    del ui_class
    call = "self.ui.%s() is not True" % handler
    return (
        "class _CbcsCloseGuard(QObject):",
        "    def __init__(self, ui, form):",
        "        super().__init__(form)",
        "        self.ui = ui",
        "        form.installEventFilter(self)",
        "    def eventFilter(self, obj, event):",
        "        if event.type() == QEvent.Type.Close and %s:" % call,
        "            event.ignore()",
        "            return True",
        "        if (event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape",
        "                and isinstance(obj, QDialog) and %s):" % call,
        "            return True",
        "        return False",
        "self._cbcs_close_guard = _CbcsCloseGuard(self, %s)" % form_param,
    )


EXPANDER = FormEventsExpander()
