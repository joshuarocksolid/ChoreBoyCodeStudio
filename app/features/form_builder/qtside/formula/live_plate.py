"""The Qt values the canvas shows while a State formula editor is open.

Design values stay in the document. ``pushed`` empty means the canvas is on
those design values. An error keeps the editor armed and puts the canvas back
on design values, so the next keystroke can try again.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Tuple

from app.features.form_builder.engine.commands.live import LiveProp
from app.features.form_builder.engine.logic.events_catalog import class_chain
from app.features.form_builder.engine.logic.formula import analyze, compile_formula, evaluate
from app.features.form_builder.engine.logic.formula.env import SlotKind
from app.features.form_builder.engine.logic.formula.evaluate import EvalBlank
from app.features.form_builder.engine.logic.formula.runtime import live_helpers
from app.features.form_builder.engine.logic.formula.types import TEXT, lookup_spec, written_type
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.values import (
    BoolValue,
    DoubleValue,
    FloatValue,
    NumberValue,
    StringValue,
    Value,
)

_CONDITION = {
    "cbcsEnabledWhen": "enabled",
    "cbcsReadOnlyWhen": "readOnly",
    "cbcsVisibleWhen": "visible",
}
_WRITE_PROP = {
    "setText(formatted)": "text",
    "setPlainText": "plainText",
    "setValue": "value",
    "setValue(float(x))": "value",
    "setChecked": "checked",
}


class LivePlate:
    def __init__(self, realizer: object) -> None:
        self._realizer = realizer
        self._pushed: Tuple[LiveProp, ...] = ()
        self._armed = False
        self._node: object = None
        self._key = ""
        self._env: object = None

    @property
    def pushed(self) -> Tuple[LiveProp, ...]:
        return self._pushed

    def arm(self, node: object, key: str, text: str, env: object, reader: object) -> None:
        self._node = node
        self._key = key
        self._env = env
        self._armed = True
        self._publish(text, reader)

    def revise(self, text: str, reader: object) -> None:
        if not self._armed:
            return
        self._publish(text, reader)

    def clear(self) -> None:
        if not self._armed and not self._pushed:
            return
        keys = tuple(prop.key for prop in self._pushed)
        self._pushed = ()
        self._armed = False
        self._node = None
        self._key = ""
        self._env = None
        if keys:
            reapply = getattr(self._realizer, "reapply", None)
            if callable(reapply):
                reapply(keys)

    def _publish(self, text: str, reader: object) -> None:
        prop = self._prop(text, reader)
        previous = self._pushed
        if prop is None:
            if previous:
                reapply = getattr(self._realizer, "reapply", None)
                if callable(reapply):
                    reapply(tuple(item.key for item in previous))
            self._pushed = ()
            return
        restore = tuple(item.key for item in previous if item.key != prop.key)
        if restore:
            reapply = getattr(self._realizer, "reapply", None)
            if callable(reapply):
                reapply(restore)
        apply_live = getattr(self._realizer, "apply_live", None)
        if callable(apply_live):
            apply_live((prop,))
        self._pushed = (prop,)

    def _prop(self, text: str, reader: object) -> Optional[LiveProp]:
        node = self._node
        env = self._env
        key = self._key
        if node is None or env is None or not key:
            return None
        owner = getattr(node, "id", None)
        if owner is None:
            return None
        result = self._result(text, reader, node, env, key)
        if result is None:
            return None
        if key in _CONDITION:
            if type(result) is not bool:
                return None
            return LiveProp(owner, _CONDITION[key], BoolValue(result))
        if key not in ("cbcsValue", "cbcsDefault"):
            return None
        return _value_prop(node, owner, result)

    def _result(self, text: str, reader: object, node: object, env: object, key: str) -> object:
        try:
            found = analyze(text, env, _slot(node, env, key))
            emitted = compile_formula(found, env)
            value = evaluate(emitted, reader, None)
        except Exception:
            return None
        if isinstance(value, EvalBlank):
            return None
        return value


def plate_for(realizer: object) -> LivePlate:
    plate = getattr(realizer, "_cbcs_live_plate", None)
    if isinstance(plate, LivePlate):
        return plate
    plate = LivePlate(realizer)
    setattr(realizer, "_cbcs_live_plate", plate)
    return plate


def _slot(node: object, env: object, key: str) -> SlotKind:
    if key in _CONDITION:
        return SlotKind.condition()
    name = getattr(node, "object_name", "") or ""
    facts = env.widgets.get(name)  # type: ignore[attr-defined]
    target = TEXT
    if facts is not None:
        chain = env.class_chain(facts.class_name)  # type: ignore[attr-defined]
        matched, spec = lookup_spec(facts.class_name, chain)
        if spec is not None and matched is not None:
            target = written_type(
                spec,
                matched,
                kind=facts.kind,
                prefix=facts.prefix,
                decimals=facts.decimals,
                has_items_data=facts.has_items_data,
                fmt=_format(node),
            )
    if key == "cbcsDefault":
        return SlotKind.default(target)
    return SlotKind.value(target)


def _value_prop(node: object, owner: object, result: object) -> Optional[LiveProp]:
    class_name = (getattr(node, "class_name", "") or "").rsplit(".", 1)[-1]
    chain = class_chain(QtClassTable.shared(), class_name) or (class_name,)
    _matched, spec = lookup_spec(class_name, chain)
    write = spec.write if spec is not None else ""
    prop_name = _WRITE_PROP.get(write, "")
    if not prop_name:
        return None
    try:
        value = _written(node, class_name, write, prop_name, result)
    except Exception:
        return None
    if value is None:
        return None
    return LiveProp(owner, prop_name, value)


def _written(node: object, class_name: str, write: str, prop_name: str, result: object) -> Optional[Value]:
    if write == "setChecked":
        if type(result) is not bool:
            return None
        return BoolValue(result)
    if write in ("setValue", "setValue(float(x))"):
        if result is None:
            return None
        kind = "double" if write == "setValue(float(x))" else _prop_kind(class_name, prop_name)
        return _number(result, kind)
    if write == "setText(formatted)":
        return StringValue(_formatted(node, result))
    if write == "setPlainText":
        return StringValue("" if result is None else str(result))
    return None


def _format(node: object) -> str:
    raw = node.value("cbcsFormat") if hasattr(node, "value") else None
    text = getattr(raw, "text", None)
    return text if isinstance(text, str) else ""


def _formatted(node: object, result: object) -> str:
    fmt = _format(node)
    helpers = live_helpers()
    if fmt == "money":
        shown = helpers["_cbcs_money"](result)
    elif fmt:
        shown = helpers["_cbcs_text"](result, fmt)
        if shown is None:
            shown = ""
    else:
        shown = "" if result is None else str(result)
    return shown if isinstance(shown, str) else str(shown)


def _prop_kind(class_name: str, prop_name: str) -> str:
    info = QtClassTable.shared().property_info(class_name, prop_name)
    if info is None or not info.kind:
        return "number"
    return info.kind


def _number(result: object, kind: str) -> Optional[Value]:
    if type(result) is bool or isinstance(result, str):
        return None
    if isinstance(result, bool):
        return None
    if not isinstance(result, (int, float, Decimal)):
        return None
    if kind in ("double", "float"):
        try:
            value = float(result)
        except (TypeError, ValueError, ArithmeticError):
            return None
        if kind == "float":
            return FloatValue(value)
        return DoubleValue(value)
    try:
        value = int(result)
    except (TypeError, ValueError, ArithmeticError):
        return None
    return NumberValue(value)
