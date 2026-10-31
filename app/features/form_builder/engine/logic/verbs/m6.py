"""M6 verbs: ``slot`` and ``call`` (CONTRACTS 15.3). Qt-free.

Registered in this order so plain-verb lists and schema field order stay
slot then call. Codec imports stay inside functions: this module is loaded
while the codec asks the registry.
"""

from __future__ import annotations

from typing import Any, Tuple

from app.features.form_builder.engine.logic import compat
from app.features.form_builder.engine.logic.verbs import FieldSpec, VerbSpec, require_text

_FORM_WORDS = {"close": "Close this form", "accept": "Accept (OK)", "reject": "Cancel"}

_PLAIN_SLOT_WORDS = {
    "clear": "Clear {w}",
    "setFocus": "Move focus to {w}",
    "setChecked": "Check or uncheck {w} the same way",
    "toggle": "Toggle {w}",
    "click": "Click {w}",
    "setValue": "Set {w} to the same value",
    "setEnabled": "Enable {w} to match",
    "setDisabled": "Disable {w} to match",
    "setVisible": "Show {w} to match",
    "show": "Show {w}",
    "hide": "Hide {w}",
    "setText": "Copy the text into {w}",
    "selectAll": "Select all in {w}",
    "undo": "Undo in {w}",
    "redo": "Redo in {w}",
    "copy": "Copy in {w}",
    "paste": "Paste in {w}",
    "cut": "Cut in {w}",
    "update": "Redraw {w}",
    "repaint": "Redraw {w}",
    "raise": "Bring {w} to the front",
    "lower": "Send {w} to the back",
}


def _blocked(step: Any) -> bool:
    return step.when is not None or step.raw is not None


def _slot_blocks(step: Any) -> bool:
    if _blocked(step):
        return True
    return not (compat.is_name(step.target) and compat.is_signature(step.slot))


def _call_blocks(step: Any) -> bool:
    if _blocked(step):
        return True
    return not (compat.is_name(step.method) and 0 <= step.args <= 99)


def _slot_words(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    name = compat.split_signature(step.slot)[0]
    if is_form and name in _FORM_WORDS:
        return _FORM_WORDS[name]
    if name == "setCurrentIndex":
        if "QComboBox" in target_chain:
            return "Choose the matching item of %s" % w
        return "Show the matching page of %s" % w
    template = _PLAIN_SLOT_WORDS.get(name)
    if template is not None:
        return template.replace("{w}", w)
    return "%s · %s" % (w, name)


def _call_words(step: Any, w: str, *, is_form: bool = False, target_chain: Any = ()) -> str:
    del w, is_form, target_chain
    return "Call %s()" % step.method


def _args(count: int) -> str:
    return "*args[:%d]" % count if count else ""


def _emit_slot(step: Any, ctx: Any) -> Tuple[str, ...]:
    name, params = compat.split_signature(step.slot)
    owner = "self._form" if step.target == ctx.root else "self.%s" % step.target
    return ("%s.%s(%s)" % (owner, name, _args(len(params))),)


def _emit_call(step: Any, ctx: Any) -> Tuple[str, ...]:
    call = "self._form.%s(%s)" % (step.method, _args(step.args))
    if ctx.later_on:
        return ("if %s is False:" % call, "    return")
    return (call,)


def _validate_slot(taken: Any) -> None:
    require_text("slot", ("target", "slot"), taken)


def _validate_call(taken: Any) -> None:
    require_text("call", ("method",), taken)
    if "args" not in taken:
        return
    from app.features.form_builder.engine.logic.codec import _Refused

    count = taken.get("args")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise _Refused(1, '"args" must be a whole number')


def register(registry: Any) -> None:
    registry.add(
        VerbSpec(
            "slot",
            (
                FieldSpec("target", "object_name", required=True),
                FieldSpec("slot", "signature", required=True),
                FieldSpec("hints", "hints"),
            ),
            True,
            _validate_slot,
            _emit_slot,
            _slot_blocks,
            "everything",
            _slot_words,
        )
    )
    registry.add(
        VerbSpec(
            "call",
            (
                FieldSpec("method", "method", required=True),
                FieldSpec("args", "int"),
            ),
            True,
            _validate_call,
            _emit_call,
            _call_blocks,
            "your-code",
            _call_words,
        )
    )
