"""Fixes on the FB2xx rows: Create method, Go to code, Use method, Connect methods by name."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.commands.catalog_ext.form_fields import SetFormField
from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.logic.compat import is_name, is_signature
from app.features.form_builder.engine.logic.events import read_event, read_events
from app.features.form_builder.engine.logic.events_catalog import event_words
from app.features.form_builder.integration.handlers import service
from app.features.form_builder.integration.problem_fixes import FixContext, ProblemFix

_GO = (
    "FB202", "FB203", "FB204", "FB205", "FB206", "FB208", "FB209", "FB210", "FB213",
)


def _offered(fix_id: str):
    def offered(diagnostic: FormDiagnostic) -> bool:
        return any(item.fix_id == fix_id for item in diagnostic.fixes)

    return offered


def _arg(diagnostic: FormDiagnostic, key: str) -> str:
    for fix in diagnostic.fixes:
        for name, value in fix.args:
            if name == key:
                return value
    return ""


def go_to_code(context: FixContext) -> None:
    surface = context.surface
    if surface is None:
        return
    method = _arg(context.diagnostic, "method")
    if not method:
        _open_line(surface, _arg(context.diagnostic, "line"))
        return
    if not service().go_to(surface, method):
        _narrate(surface, "%s() isn't in %s yet. Press Ctrl+. to create it." % (method, _file(surface)))


def create_method(context: FixContext) -> None:
    surface = context.surface
    if surface is None:
        return
    method = _arg(context.diagnostic, "method")
    if not method:
        return
    call = _one_call(context.session.document, method)
    if call is None:
        service().go_to(surface, method)
        return
    sender, signal = call
    state = read_event(context.session.document, sender, signal)
    if not is_name(method) or state.has_unreadable_list or _unusable(state):
        return
    from app.features.form_builder.engine.commands.catalog_ext.methods import PairStub
    from app.features.form_builder.integration.handlers import MethodRequest

    header = event_words(signal).header
    service().make_method(
        surface,
        MethodRequest("Create method", (PairStub(method),), method, "", sender, header),
    )


def use_method(context: FixContext) -> None:
    surface = context.surface
    if surface is None:
        return
    suggestion = ""
    missing = ""
    for fix in context.diagnostic.fixes:
        if fix.fix_id == "use-method":
            suggestion = _arg_of(fix, "method")
        elif fix.fix_id == "create-method":
            missing = _arg_of(fix, "method")
    if not suggestion or not missing:
        return
    doc = context.session.document
    for state in read_events(doc):
        for index, step in enumerate(state.steps):
            if step.verb == "call" and step.method == missing:
                from app.features.form_builder.engine.logic.events_codec import EventStep
                from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps

                steps = list(state.steps)
                steps[index] = EventStep("call", method=suggestion, args=step.args)
                context.session.log.execute(
                    SetEventSteps(state.sender, state.signal_name, tuple(steps), caption="Use %s" % suggestion)
                )
                return


def connect_by_name(context: FixContext) -> None:
    context.session.log.execute(
        SetFormField(
            "connectslotsbyname",
            None,
            "Change form setting: connect methods by name",
        )
    )


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    add(ProblemFix("FB201", "create-method", "Create method", create_method, _offered("create-method")))
    add(ProblemFix("FB201", "use-method", _use_title, use_method, _offered("use-method")))
    for code in _GO:
        add(ProblemFix(code, "go-to-code", "Go to code", go_to_code, _offered("go-to-code")))
    add(ProblemFix("FB211", "connect-by-name", "Turn on Connect methods by name", connect_by_name, _offered("connect-by-name")))


def _use_title(diagnostic: FormDiagnostic) -> str:
    name = _arg(diagnostic, "method")
    for fix in diagnostic.fixes:
        if fix.fix_id == "use-method":
            return fix.title
    return "Use %s" % name if name else "Use method"


def _arg_of(fix: object, key: str) -> str:
    for name, value in getattr(fix, "args", ()):
        if name == key:
            return value
    return ""


def _unusable(state: object) -> bool:
    """A typed step whose name cannot be saved. Same rule the event list uses."""
    for step in getattr(state, "steps", ()):
        if getattr(step, "raw", None) is not None:
            continue
        if step.verb == "slot" and (not is_name(step.target) or not is_signature(step.slot)):
            return True
        if step.verb == "call" and not is_name(step.method):
            return True
    return False


def _one_call(doc: object, method: str) -> Optional[tuple]:
    for state in read_events(doc):  # type: ignore[arg-type]
        for step in state.steps:
            if step.verb == "call" and step.method == method:
                return state.sender, state.signal_name
    return None


def _open_line(surface: object, line: str) -> None:
    scope = getattr(getattr(surface, "session", None), "scope", None)
    path = str(getattr(scope, "window_path", "") or "")
    bridge = getattr(surface, "code_bridge", None)
    opener = getattr(bridge, "open_at", None)
    if path and callable(opener):
        opener(path, int(line or "1") or 1)


def _file(surface: object) -> str:
    scope = getattr(getattr(surface, "session", None), "scope", None)
    path = str(getattr(scope, "window_path", "") or "")
    return path.rsplit("/", 1)[-1] if path else "the window file"


def _narrate(surface: object, sentence: str) -> None:
    narrate = getattr(surface, "narrate", None)
    if callable(narrate):
        narrate(sentence)

