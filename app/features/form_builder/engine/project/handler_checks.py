"""Design-time checks on the window file (CONTRACTS section 16.5).

Pure. The Qt base class's attribute names arrive in ``inherited``, measured
once on the Qt side. This module does not import Qt or the user's code.
"""

from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.diagnostic_codes import fb2xx_code as _fb2xx_code
from app.features.form_builder.engine.diagnostics import (
    DiagnosticLocation,
    FormDiagnostic,
    QuickFix,
    Severity,
)
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.project.handler_names import (
    header_words,
    signature_arg_count,
    signal_name,
)
from app.features.form_builder.engine.project.window_facts import MethodFacts, WindowRead
from app.features.form_builder.engine.project.window_file import file_label
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import ActionNode, ConnectionNode
from app.features.form_builder.engine.ui4.schema import SlotsDecl
from app.features.form_builder.engine.ui4.values import StringValue

_FB2XX_DECLARED = _fb2xx_code.__name__

_KIND_WORDS = {
    "staticmethod": "staticmethod",
    "classmethod": "class method",
    "property": "property",
}
#: Names longer than this are never compared for spelling. A window file can
#: hold one-line identifiers of hundreds of kilobytes.
_FUZZY_CHARS = 128

_TYPE_ALIAS = {
    "str": "QString",
    "QString": "QString",
    "string": "QString",
    "float": "double",
    "qreal": "double",
    "bool": "bool",
    "int": "int",
}


def check_handlers(
    doc: UiDocument,
    read: WindowRead,
    *,
    classes: object,
    registry: Sequence[object] = (),
    inherited: Iterable[str] = (),
    connect_by_name: bool = True,
) -> Tuple[FormDiagnostic, ...]:
    """One row per UX-CODE-011 rule. FB209 or FB210 alone when the file can't be checked."""
    if not _FB2XX_DECLARED:
        raise RuntimeError("FB201–FB213 were not registered")
    label = file_label(read.relative)
    if read.status != "ok":
        return (_with_code(_file_problem(read, label), read.relative),)
    facts = read.facts
    if not facts.class_name:
        return (
            _with_code(
                _diag(
                    "FB210",
                    Severity.WARNING,
                    "%s has no class that calls self.ui.setupUi(self), so methods can't be added or checked."
                    % label,
                    line=0,
                    fixes=(_go("", 1),),
                ),
                read.relative,
            ),
        )
    methods = _method_index(read)
    stock = frozenset(inherited)
    qt_base = _qt_base(facts.bases, classes)
    objects = _objects(doc)
    calls = _calls(doc, objects, classes, registry)
    called = {call.method for call in calls}
    rows: List[FormDiagnostic] = []
    shadowed = set()
    for method in methods.values():
        # Only methods the form calls: overriding closeEvent or keyPressEvent
        # in the window class is ordinary Qt code, not a naming mistake.
        if method.name not in called:
            continue
        if method.name in stock and method.name not in shadowed:
            shadowed.add(method.name)
            rows.append(_shadow(method.name, qt_base, None, method.line))
    for call in calls:
        rows.extend(
            _call_rows(
                call,
                methods,
                stock,
                facts.class_name,
                label,
                facts.unread_bases,
                called,
            )
        )
    rows.extend(_declared_shadows(doc, stock, qt_base, shadowed))
    rows.extend(
        _by_name_rows(
            methods, objects, classes, registry, doc, connect_by_name, called,
        )
    )
    return tuple(_with_code(item, read.relative) for item in rows)


class _Call:
    def __init__(
        self,
        method: str,
        sender: str,
        sender_class: str,
        signal: str,
        sends: int,
        node_id: Optional[NodeId],
    ) -> None:
        self.method = method
        self.sender = sender
        self.sender_class = sender_class
        self.signal = signal
        self.sends = sends
        self.node_id = node_id


def _file_problem(read: WindowRead, label: str) -> FormDiagnostic:
    if read.status == "syntax_error":
        line = read.line or 1
        message = (
            "%s has an error on line %s, so the code this form calls isn't checked."
            % (label, line)
        )
        return _diag("FB209", Severity.INFO, message, line=line, fixes=(_go("", line),))
    reason = read.reason or "it can't be read"
    message = (
        "%s can't be read, so the code this form calls isn't checked: %s."
        % (label, reason)
    )
    return _diag("FB209", Severity.INFO, message, line=read.line, fixes=(_go("", read.line or 1),))


def _call_rows(
    call: _Call,
    methods: Dict[str, MethodFacts],
    stock: frozenset,
    class_name: str,
    label: str,
    unread: Tuple[str, ...],
    called: set,
) -> List[FormDiagnostic]:
    method = methods.get(call.method)
    if method is None:
        if call.method in stock:
            return []
        if unread:
            return [
                _diag(
                    "FB212",
                    Severity.INFO,
                    "%s comes from %s, which Code Studio can't read, so it isn't checked."
                    % (call.method, unread[0]),
                    call,
                )
            ]
        return [_missing(call, methods, class_name, label, called)]
    rows: List[FormDiagnostic] = []
    if method.kind in _KIND_WORDS:
        rows.append(
            _diag(
                "FB213",
                Severity.ERROR,
                "%s is a %s, so Qt can't call it for an event."
                % (method.name, _KIND_WORDS[method.kind]),
                call,
                method.line,
                (_go(method.name, method.line),),
            )
        )
        return rows
    if not method.has_varargs and method.required > call.sends:
        params = ", ".join(method.params[: method.required])
        head = "%s(self, %s)" % (method.name, params) if params else "%s(self)" % method.name
        rows.append(
            _diag(
                "FB202",
                Severity.ERROR,
                "%s needs %s values, but %s sends %s. It would fail every time."
                % (head, method.required, header_words(call.signal, call.sender_class), call.sends),
                call,
                method.line,
                (_go(method.name, method.line),),
            )
        )
    if method.body_is_empty:
        rows.append(
            _diag(
                "FB203",
                Severity.INFO,
                "%s is still empty (pass)." % method.name,
                call,
                method.line,
                (_go(method.name, method.line),),
            )
        )
    return rows


def _missing(
    call: _Call,
    methods: Dict[str, MethodFacts],
    class_name: str,
    label: str,
    called: set,
) -> FormDiagnostic:
    options = [name for name in methods if name not in called]
    suggestion = _closest(call.method, options, 2)
    fixes = [_create(call.method)]
    if suggestion:
        fixes.append(
            QuickFix(
                "use-method",
                "Use %s" % suggestion,
                action="use-method",
                args=(("method", suggestion),),
            )
        )
    return _diag(
        "FB201",
        Severity.ERROR,
        "%s is not defined in %s (%s)." % (call.method, class_name, label),
        call,
        fixes=tuple(fixes),
    )


def _declared_shadows(
    doc: UiDocument,
    stock: frozenset,
    qt_base: str,
    called: set,
) -> List[FormDiagnostic]:
    rows = []
    declared = doc.ui.field("form_slots")
    if not isinstance(declared, SlotsDecl):
        return rows
    for signature in declared.slots:
        name = signal_name(signature)
        if name in stock and name not in called:
            rows.append(_shadow(name, qt_base, None, 0))
    return rows


def _by_name_rows(
    methods: Dict[str, MethodFacts],
    objects: Dict[str, Tuple[str, Optional[NodeId]]],
    classes: object,
    registry: Sequence[object],
    doc: UiDocument,
    connect_by_name: bool,
    called: set,
) -> List[FormDiagnostic]:
    rows: List[FormDiagnostic] = []
    names = tuple(objects)
    near = _NearNames(names)
    for method in methods.values():
        parsed = _parse_on(method.name, names, near)
        if parsed is None:
            continue
        obj, signal, fuzzy = parsed
        if fuzzy:
            rows.append(
                _diag(
                    "FB208",
                    Severity.WARNING,
                    "%s looks like a method Qt runs by its name, but there is no widget %s. Did you mean %s?"
                    % (method.name, obj, fuzzy),
                    line=method.line,
                    prop=method.name,
                    fixes=(_go(method.name, method.line),),
                )
            )
            continue
        info = objects.get(obj)
        if info is None:
            continue
        class_name, node_id = info
        signatures = _signatures(doc, classes, registry, class_name)
        events = {signal_name(item) for item in signatures}
        if signal not in events:
            suggestion = _closest(signal, list(events), 8) or signal
            rows.append(
                _diag(
                    "FB208",
                    Severity.WARNING,
                    "%s looks like a method Qt runs by its name, but %s has no event %s. Did you mean %s?"
                    % (method.name, obj, signal, suggestion),
                    line=method.line,
                    prop=method.name,
                    node_id=node_id,
                    object_name=obj,
                    fixes=(_go(method.name, method.line),),
                )
            )
            continue
        matched = _slot_matches(method, signatures, signal)
        if connect_by_name and method.name in called and matched:
            rows.append(
                _diag(
                    "FB205",
                    Severity.WARNING,
                    "%s also runs by its name, so it would run twice." % method.name,
                    line=method.line,
                    prop=method.name,
                    node_id=node_id,
                    object_name=obj,
                    fixes=(_go(method.name, method.line),),
                )
            )
        if not connect_by_name:
            if method.name not in called:
                rows.append(
                    _diag(
                        "FB211",
                        Severity.INFO,
                        "Connect methods by name is off, so %s won't run by itself." % method.name,
                        line=method.line,
                        prop=method.name,
                        node_id=node_id,
                        object_name=obj,
                        fixes=(
                            QuickFix(
                                "connect-by-name",
                                "Turn on Connect methods by name",
                                action="connect-by-name",
                            ),
                        ),
                    )
                )
            continue
        if not matched:
            if method.slot_types is None:
                message = "%s has no @Slot(), so Qt won't run it by its name." % method.name
            else:
                shown = ", ".join(method.slot_types)
                message = (
                    "%s's @Slot(%s) doesn't match %s's %s, so Qt won't run it by its name."
                    % (method.name, shown, obj, signal)
                )
            rows.append(
                _diag(
                    "FB206",
                    Severity.WARNING,
                    message,
                    line=method.line,
                    prop=method.name,
                    node_id=node_id,
                    object_name=obj,
                    fixes=(_go(method.name, method.line),),
                )
            )
    return rows


def _calls(
    doc: UiDocument,
    objects: Dict[str, Tuple[str, Optional[NodeId]]],
    classes: object,
    registry: Sequence[object],
) -> List[_Call]:
    found: List[_Call] = []
    root_name = doc.root.object_name or ""
    form_name = doc.form_class_name()
    for node in doc.connections():
        if not isinstance(node, ConnectionNode):
            continue
        if node.receiver not in (root_name, form_name):
            continue
        sender = objects.get(node.sender)
        sender_class = sender[0] if sender else doc.root.class_name
        node_id = sender[1] if sender else doc.root.node_id
        found.append(
            _Call(
                signal_name(node.slot),
                node.sender,
                sender_class,
                node.signal,
                signature_arg_count(node.signal),
                node_id,
            )
        )
    for owner_name, (class_name, node_id) in objects.items():
        node = _node_for(doc, owner_name)
        if node is None:
            continue
        for prop in node.properties():
            if not prop.name.startswith("cbcsOn") or len(prop.name) <= len("cbcsOn"):
                continue
            if not isinstance(prop.value, StringValue):
                continue
            signal = prop.name[len("cbcsOn") :]
            signal = signal[:1].lower() + signal[1:]
            for method, _args in _call_steps(prop.value.text):
                signatures = _signatures(doc, classes, registry, class_name)
                sends = _sends(signatures, signal)
                found.append(_Call(method, owner_name, class_name, signal, sends, node_id))
    return found


def _call_steps(text: str) -> List[Tuple[str, int]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = data.get("steps")
    if not isinstance(data, list):
        return []
    found = []
    for item in data:
        if not isinstance(item, dict) or item.get("do") != "call":
            continue
        if item.get("enabled", True) is False:
            continue
        name = item.get("method")
        if not isinstance(name, str) or not name:
            continue
        args = item.get("args", 0)
        found.append((name, args if isinstance(args, int) else 0))
    return found


def _sends(signatures: Sequence[str], signal: str) -> int:
    counts = [signature_arg_count(item) for item in signatures if signal_name(item) == signal]
    if not counts:
        return 0
    return max(counts)


def _objects(doc: UiDocument) -> Dict[str, Tuple[str, Optional[NodeId]]]:
    found: Dict[str, Tuple[str, Optional[NodeId]]] = {}
    for widget in doc.iter_widgets():
        if widget.object_name:
            found[widget.object_name] = (widget.class_name, widget.node_id)
    for node in doc.iter_preorder():
        if isinstance(node, ActionNode) and node.name:
            found[node.name] = ("QAction", node.node_id)
    return found


def _node_for(doc: UiDocument, name: str) -> object:
    for widget in doc.iter_widgets():
        if widget.object_name == name:
            return widget
    for node in doc.iter_preorder():
        if isinstance(node, ActionNode) and node.name == name:
            return node
    return None


def _signatures(
    doc: UiDocument,
    classes: object,
    registry: Sequence[object],
    class_name: str,
) -> Tuple[str, ...]:
    found: List[str] = []
    signals = getattr(classes, "signals", None)
    effective = class_name
    if classes is not None and hasattr(classes, "effective_class"):
        effective = classes.effective_class(class_name)
    if callable(signals):
        found.extend(signals(effective))
    for entry in registry:
        if getattr(entry, "class_name", "") != class_name:
            continue
        found.extend(getattr(entry, "signals", ()) or ())
        extends = getattr(entry, "extends", "") or ""
        if extends and callable(signals):
            found.extend(signals(extends))
    custom = doc.custom_widget(class_name)
    if custom is not None:
        declared = custom.field("slots")
        if isinstance(declared, SlotsDecl):
            found.extend(declared.signals)
    ordered: List[str] = []
    for item in found:
        if item not in ordered:
            ordered.append(item)
    return tuple(ordered)


def _method_index(read: WindowRead) -> Dict[str, MethodFacts]:
    found: Dict[str, MethodFacts] = {}
    facts = read.facts
    if not facts.class_name:
        return found
    for method in facts.methods:
        found[method.name] = method
    for method in facts.base_methods:
        found.setdefault(method.name, method)
    return found


def _qt_base(bases: Tuple[str, ...], classes: object) -> str:
    info = getattr(classes, "class_info", None)
    if callable(info):
        for name in bases:
            if info(name) is not None:
                return name
    if bases:
        return bases[0]
    return "QWidget"


def _slot_matches(method: MethodFacts, signatures: Sequence[str], signal: str) -> bool:
    if method.slot_types is None:
        return False
    overloads = [item for item in signatures if signal_name(item) == signal]
    return _types_match(method.slot_types, overloads)


def _types_match(types: Tuple[str, ...], overloads: Sequence[str]) -> bool:
    if not types:
        return any(signature_arg_count(item) == 0 for item in overloads)
    for item in overloads:
        parts = _signature_types(item)
        if len(parts) == len(types) and all(_same_type(a, b) for a, b in zip(types, parts)):
            return True
    return False


def _signature_types(signature: str) -> Tuple[str, ...]:
    start = signature.find("(")
    end = signature.rfind(")")
    if start < 0 or end <= start:
        return ()
    inner = signature[start + 1 : end].strip()
    if not inner or inner == "void":
        return ()
    return tuple(part.strip() for part in inner.split(",") if part.strip())


def _same_type(left: str, right: str) -> bool:
    return _TYPE_ALIAS.get(left, left) == _TYPE_ALIAS.get(right, right)


class _NearNames:
    """Widget names within two letters of a word, found without comparing all.

    Each name is filed under every string left after deleting up to two of
    its letters; two words within two edits share one of those strings. The
    exact distance is then checked on the few names found.
    """

    def __init__(self, names: Sequence[str]) -> None:
        self.names = tuple(names)
        self.longest_first = tuple(sorted(self.names, key=len, reverse=True))
        self._index: Dict[str, List[int]] = {}
        for number, name in enumerate(self.names):
            if len(name) > _FUZZY_CHARS:
                continue
            for key in _deletions(name):
                self._index.setdefault(key, []).append(number)

    def closest(self, word: str) -> Optional[str]:
        """The first name (in form order) at the smallest distance, at most 2."""
        if len(word) > _FUZZY_CHARS:
            return None
        found = set()
        for key in _deletions(word):
            found.update(self._index.get(key, ()))
        best: Optional[Tuple[int, int]] = None
        for number in sorted(found):
            name = self.names[number]
            if name == word:
                continue
            distance = _edits(word, name, 2)
            if distance <= 2 and (best is None or distance < best[0]):
                best = (distance, number)
        return None if best is None else self.names[best[1]]


def _deletions(word: str) -> set:
    found = {word}
    for _round in range(2):
        found |= {item[:index] + item[index + 1 :] for item in found for index in range(len(item))}
    return found


def _parse_on(
    method: str,
    names: Sequence[str],
    near: Optional[_NearNames] = None,
) -> Optional[Tuple[str, str, Optional[str]]]:
    """``(object, signal, fuzzy object)``. Fuzzy is set when the object is a near miss."""
    if not method.startswith("on_"):
        return None
    if near is None:
        near = _NearNames(names)
    rest = method[3:]
    for name in near.longest_first:
        prefix = name + "_"
        if rest.startswith(prefix) and rest[len(prefix) :]:
            return name, rest[len(prefix) :], None
    best: Optional[Tuple[str, str, str, int]] = None
    if len(rest) > _FUZZY_CHARS:
        return None
    parts = rest.split("_")
    for cut in range(1, len(parts)):
        obj = "_".join(parts[:cut])
        signal = "_".join(parts[cut:])
        if not obj or not signal:
            continue
        close = near.closest(obj)
        if close is None:
            continue
        distance = _edits(obj, close, 2)
        if best is None or distance < best[3]:
            best = (obj, signal, close, distance)
    if best is None:
        return None
    return best[0], best[1], best[2]


def _shadow(
    name: str,
    qt_base: str,
    call: Optional[_Call],
    line: int,
) -> FormDiagnostic:
    return _diag(
        "FB204",
        Severity.ERROR,
        "The method name %s would replace %s's own %s." % (name, qt_base, name),
        call,
        line,
        (_go(name, line or 1),),
    )


def _create(method: str) -> QuickFix:
    return QuickFix(
        "create-method",
        "Create method",
        action="create-method",
        args=(("method", method),),
    )


def _go(method: str, line: int) -> QuickFix:
    return QuickFix(
        "go-to-code",
        "Go to code",
        action="go-to-code",
        args=(("method", method), ("line", str(line or 1))),
    )


def _diag(
    code: str,
    severity: Severity,
    message: str,
    call: Optional[_Call] = None,
    line: int = 0,
    fixes: Tuple[QuickFix, ...] = (),
    prop: Optional[str] = None,
    node_id: Optional[NodeId] = None,
    object_name: Optional[str] = None,
) -> FormDiagnostic:
    if call is not None:
        node_id = call.node_id if node_id is None else node_id
        object_name = call.sender if object_name is None else object_name
        prop = call.method if prop is None else prop
        if not line:
            line = 0
    return FormDiagnostic(
        code=code,
        severity=severity,
        message=message,
        location=DiagnosticLocation(
            node_id=node_id,
            object_name=object_name,
            property=prop,
            line=line,
        ),
        source="handlers",
        fixes=fixes,
    )


def _with_code(item: FormDiagnostic, path: str) -> FormDiagnostic:
    """Copy the row and name the window file M6.0s's Problems bridge opens."""
    loc = item.location
    return FormDiagnostic(
        code=item.code,
        severity=item.severity,
        message=item.message,
        location=DiagnosticLocation(
            node_id=loc.node_id,
            object_name=loc.object_name,
            property=loc.property,
            rule_path=loc.rule_path,
            span=loc.span,
            line=loc.line,
            code_path=path,
            code_line=loc.line,
        ),
        source=item.source,
        fixes=item.fixes,
    )


def _closest(name: str, options: Sequence[str], limit: int) -> Optional[str]:
    best = None
    best_distance = limit + 1
    if len(name) > _FUZZY_CHARS:
        return None
    for option in options:
        if option == name or abs(len(option) - len(name)) > limit:
            continue
        if len(option) > _FUZZY_CHARS:
            continue
        distance = _edits(name, option, limit)
        if distance < best_distance:
            best = option
            best_distance = distance
    if best is None or best_distance > limit:
        return None
    return best


def _edits(left: str, right: str, limit: int = 8) -> int:
    """Edit distance, or ``limit + 1`` once it is known to be larger.

    Only the diagonal band of width ``limit`` is filled and a row whose best
    cell is past ``limit`` stops early, so a check over hundreds of widgets
    and methods stays well under a second on ChoreBoy.
    """
    if left == right:
        return 0
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    big = limit + 1
    previous = [j if j <= limit else big for j in range(len(right) + 1)]
    for i, ch in enumerate(left, 1):
        low = max(1, i - limit)
        high = min(len(right), i + limit)
        current = [big] * (len(right) + 1)
        current[0] = i if i <= limit else big
        best = current[0]
        for j in range(low, high + 1):
            cost = previous[j - 1] + (ch != right[j - 1])
            if current[j - 1] + 1 < cost:
                cost = current[j - 1] + 1
            if previous[j] + 1 < cost:
                cost = previous[j] + 1
            current[j] = cost if cost <= limit else big
            if current[j] < best:
                best = current[j]
        if best > limit:
            return big
        previous = current
    return previous[-1] if previous[-1] <= limit else big
