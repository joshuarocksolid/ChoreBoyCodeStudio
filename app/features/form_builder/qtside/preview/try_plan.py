"""What Preview sends when Run behavior is on.

The window file is read as text. Nothing here imports it. ``FormulaEnv.returns``
stays empty in the checker so an annotation does not change FB110. The strip
reads the same annotation text beside that map.
"""

from __future__ import annotations

import ast
import os
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ipc.protocol import Appearance, TryDataPlan, TryStart
from app.features.form_builder.engine.logic.checks import FormulaCheck, read_checks
from app.features.form_builder.engine.logic.events import read_events
from app.features.form_builder.engine.logic.formula import analyze
from app.features.form_builder.engine.logic.formula.env import SlotKind
from app.features.form_builder.engine.logic.formula_env import env_for
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS, is_signal_property
from app.features.form_builder.engine.project.window_file import read_window
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue


def form_has_logic(document: object) -> bool:
    """True when the form has a rule, a check, or a step list."""
    nodes = _nodes(document)
    for node in nodes:
        for key in FORMULA_KEYS:
            if _stored(node, key):
                return True
        if _stored(node, "cbcsValidate"):
            return True
        try:
            props = node.properties()
        except Exception:
            props = ()
        for entry in props:
            name = getattr(entry, "name", "")
            if is_signal_property(name) and _stored(node, name):
                return True
    try:
        return any(state.steps for state in read_events(document))  # type: ignore[arg-type]
    except Exception:
        return False


def window_method_specs(document: object, scope: object) -> Tuple[Tuple[str, str], ...]:
    """``(method, annotation)`` for each ``window.m()`` a formula calls. Annotation ``""`` is ANY."""
    text, facts = _window(scope)
    env = env_for(document, facts, QtClassTable.shared())  # type: ignore[arg-type]
    names: List[str] = []

    def take(formula: str) -> None:
        if not formula:
            return
        found = analyze(formula, env, SlotKind.when())
        for name in found.window_calls:
            if name not in names:
                names.append(name)

    for node in _nodes(document):
        for key in FORMULA_KEYS:
            take(_stored(node, key) or "")
        raw = _stored(node, "cbcsValidate")
        if raw:
            read = read_checks(raw)
            for item in read.checks:
                if isinstance(item, FormulaCheck):
                    take(item.formula)
    try:
        states = read_events(document)  # type: ignore[arg-type]
    except Exception:
        states = ()
    for state in states:
        for step in state.steps:
            when = getattr(step, "when", None)
            if isinstance(when, str):
                take(when)
    noted = _annotations(text)
    specs = []
    for name in names:
        annotation = (env.returns.get(name) or noted.get(name) or "").strip()
        specs.append((name, annotation))
    return tuple(specs)


def wire_to_value(text: str, annotation: str) -> object:
    """A Window values box as the value the formula should see. ``None`` means unset."""
    if text == "":
        return None
    kind = (annotation or "").strip()
    if kind == "bool":
        if text == "true":
            return True
        if text == "false":
            return False
        return None
    if kind == "int":
        try:
            return int(text)
        except ValueError:
            return text
    if kind == "float":
        try:
            return float(text)
        except ValueError:
            return text
    if kind == "Decimal":
        try:
            return Decimal(text)
        except Exception:
            return text
    return text


def value_to_wire(value: object, annotation: str) -> str:
    """The text the parent stores so the next reload can build the same value."""
    if value is None:
        return ""
    kind = (annotation or "").strip()
    if kind == "bool":
        if value is True:
            return "true"
        if value is False:
            return "false"
        return ""
    return str(value)


def preview_request(
    session: object,
    path: str,
    view_id: str,
    *,
    run_behavior: bool = True,
    keep_values: bool = False,
    window_values: Sequence[Tuple[str, str]] = (),
    appearance: Optional[Appearance] = None,
) -> object:
    """``TryStart`` when behavior runs, otherwise today's ``LoadForm``."""
    from app.features.form_builder.integration.preview_notice import build_load_form

    document = session.document
    if run_behavior and form_has_logic(document):
        started = build_try_start(
            session,
            path,
            view_id,
            keep_values=keep_values,
            window_values=window_values,
            appearance=appearance,
        )
        if started is not None:
            return started
    message = build_load_form(session, path, view_id, appearance=appearance)
    if keep_values and not message.keep_values:
        from dataclasses import replace

        return replace(message, keep_values=True)
    return message


def build_try_start(
    session: object,
    path: str,
    view_id: str,
    *,
    keep_values: bool = False,
    window_values: Sequence[Tuple[str, str]] = (),
    appearance: Optional[Appearance] = None,
    request_id: str = "",
) -> Optional[TryStart]:
    """The traced module and the window-value strip. ``None`` when there is no module yet."""
    from app.features.form_builder.engine.codegen.api import generate_form_module
    from app.features.form_builder.integration.preview_control import methods_for
    from app.features.form_builder.integration.preview_notice import project_root_of, promoted_for

    document = session.document
    scope = session.scope
    root = project_root_of(session)
    if not root or not getattr(scope, "generates", False):
        return None
    made = generate_form_module(document, scope=scope, source_bytes=None, trace=True)
    if not made.text:
        return None
    specs = window_method_specs(document, scope)
    annotations = {name: annotation for name, annotation in specs}
    values: List[Tuple[str, object]] = []
    for name, text in window_values:
        value = wire_to_value(text, annotations.get(name, ""))
        if value is not None:
            values.append((name, value))
    methods = dict(methods_for(document))
    for name, _annotation in specs:
        methods.setdefault(name, 0)
    import uuid

    class_name, _facts = _class_name(scope)
    root_widget = getattr(document, "root", None)
    base = str(getattr(root_widget, "class_name", "") or "QWidget")
    return TryStart(
        request_id=request_id or uuid.uuid4().hex,
        view_id=view_id,
        module_name=getattr(scope, "module_name", None) or "ui_preview",
        module_source=made.text,
        window_class_name=class_name or "Window",
        base_class=base,
        window_values=tuple(values),
        data=TryDataPlan(),
        show_form=True,
        run_behavior=True,
        form_path=path,
        project_root=root,
        sys_path=(root,) if root else (),
        appearance=appearance if appearance is not None else Appearance(),
        keep_values=keep_values,
        revision=int(getattr(document, "revision", 0) or 0),
        promoted=promoted_for(document, root),
        form_methods=tuple(sorted(methods.items())),
        window_methods=specs,
    )


def _nodes(document: object) -> List[object]:
    found: List[object] = []
    try:
        found.extend(document.iter_widgets())  # type: ignore[attr-defined]
    except Exception:
        pass
    root = getattr(document, "root", None)
    if root is not None and root not in found:
        found.append(root)
    return found


def _stored(node: object, key: str) -> Optional[str]:
    try:
        value = node.value(key)  # type: ignore[attr-defined]
    except Exception:
        return None
    if isinstance(value, (StringValue, CStringValue)):
        return value.text
    return None


def _window(scope: object) -> Tuple[str, object]:
    path = str(getattr(scope, "window_path", "") or "")
    root = str(getattr(scope, "project_root", "") or "")
    if not path or not os.path.isfile(path):
        return "", None
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return "", None
    facts = None
    if root:
        relative = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            facts = read_window(root, relative, text).facts
        except Exception:
            facts = None
    return text, facts


def _class_name(scope: object) -> Tuple[str, object]:
    _text, facts = _window(scope)
    name = str(getattr(facts, "class_name", "") or "")
    return name, facts


def _annotations(text: str) -> Dict[str, str]:
    if not text:
        return {}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    found: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            try:
                found[node.name] = ast.unparse(node.returns)
            except Exception:
                continue
    return found
