"""Form diagnostics (CONTRACTS.md section 7).

Codes are ``FB`` + three digits. Ranges:

=========  ====================================================  ==========
Range      Area                                                   Owner WP
=========  ====================================================  ==========
FB001-099  File, reader, model structure, names, layout sanity   M1.1, M1.2
FB101-199  Formulas / expressions (LOGIC_DESIGN 2.9)             M7.1
FB201-299  Your code: handlers, signatures, auto-connect          M6.1, M6.2
FB301-399  Data and schema                                        M8.x
FB401-499  Logic storage and versioning                           M6.0b
FB501-599  Codegen, project, generated files, resources           M1.3, M1.4
FB601-699  Preview and Try mode                                   M2.5, M7.6
FB901-999  Internal (never shown in Problems unless debug)        any
=========  ====================================================  ==========

Every code is declared once in ``CODES`` (a registry module per range adds its
codes; ``engine/diagnostic_codes/<range>.py``). A test fails on duplicates and
on any diagnostic emitted with an undeclared code.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Tuple, Union

from app.features.form_builder.engine.ids import NodeId

_CODE_RE = re.compile(r"^FB[0-9]{3}$")
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


class Severity(str, Enum):
    """Values match ``app.intelligence.diagnostics_models.DiagnosticSeverity``."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class CodeInfo:
    code: str
    severity: Severity
    title: str
    #: True when the code can block opening the visual editor (FB001/FB002/FB004/FB008).
    #: No code may block saving (LOGIC_DESIGN 2.9; checked by test).
    blocks_visual_open: bool = False


RulePathPart = Union[str, int]


@dataclass(frozen=True)
class DiagnosticLocation:
    """Where a problem is.

    ``node_id``: the node, or None for form-level problems. Session-local.
    ``object_name``: the node's name when the diagnostic was made (display, and
    the stable key across sessions and the Problems panel).
    ``property``: property or attribute name, e.g. ``buddy``, ``cbcsValidate``.
    ``rule_path``: path inside a logic JSON value, e.g. ``("cbcsValidate", 1, "pattern")``,
    or a connection index ``("connections", 3)``.
    ``span``: (start, end) character offsets inside a formula string.
    ``line``: 1-based XML line from the reader or the last serialization; 0 = unknown.
    """

    node_id: Optional[NodeId] = None
    object_name: Optional[str] = None
    property: Optional[str] = None
    rule_path: Tuple[RulePathPart, ...] = ()
    span: Optional[Tuple[int, int]] = None
    line: int = 0


@dataclass(frozen=True)
class QuickFix:
    """A fix offered with a diagnostic.

    Exactly one of ``command`` (an engine command, executed through the session's
    command log; if planning rejects it the fix is shown disabled) or ``action``
    (an id the Qt side handles, e.g. ``"open-raw"``, ``"go-to-code"``,
    ``"refresh-schema"``) is set. ``args`` are plain strings for actions.
    """

    fix_id: str
    title: str
    command: object = None
    action: Optional[str] = None
    args: Tuple[Tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        has_command = self.command is not None
        has_action = self.action is not None
        if has_command == has_action:
            raise ValueError("QuickFix needs exactly one of command or action")


@dataclass(frozen=True)
class FormDiagnostic:
    """One problem. Plain-word ``message`` in the LOGIC_DESIGN 2.9 voice.

    ``source``: the producer (``"reader"``, ``"names"``, ``"layout"``,
    ``"logic.formula"``, ``"handlers"``, ``"codegen"``, ``"preview"``...).
    ``key``: stable identity for de-duplication and for keeping a row selected
    across refreshes: ``code|object_name|property|rule_path``.
    """

    code: str
    severity: Severity
    message: str
    location: DiagnosticLocation
    source: str
    fixes: Tuple[QuickFix, ...] = ()

    @property
    def key(self) -> str:
        location = self.location
        rule_path = json.dumps(
            list(location.rule_path),
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return "|".join(
            (
                self.code,
                location.object_name or "",
                location.property or "",
                rule_path,
            )
        )


#: Code registry: code -> CodeInfo. Populated by ``engine/diagnostic_codes/*``.
CODES: Dict[str, CodeInfo] = {}


def declare(code: str, severity: Severity, title: str, *, blocks_visual_open: bool = False) -> None:
    """Register a code. ValueError on a duplicate or a malformed code."""
    if _CODE_RE.match(code) is None:
        raise ValueError("malformed diagnostic code %r" % (code,))
    if code in CODES:
        raise ValueError("diagnostic code %s is already declared" % (code,))
    if blocks_visual_open and severity is not Severity.ERROR:
        raise ValueError("only errors can block opening the visual editor")
    CODES[code] = CodeInfo(
        code=code,
        severity=severity,
        title=title,
        blocks_visual_open=blocks_visual_open,
    )


class DiagnosticsStore:
    """Per-session diagnostics, grouped by producer.

    ``publish(source, diagnostics)`` atomically replaces everything that producer
    published before, then notifies subscribers once with the full sorted list.
    Order of ``all()``: severity (error, warning, info), then line, then key.
    Producers run after the ChangeSet that made their input stale; cheap producers
    synchronously at listener priority ``PRIORITY_DIAGNOSTICS``, expensive ones
    (formula type-check, handler parse) coalesced to idle by the Qt side.
    """

    def __init__(self) -> None:
        self._by_source: Dict[str, Tuple[FormDiagnostic, ...]] = {}
        self._by_node: Dict[NodeId, Tuple[FormDiagnostic, ...]] = {}
        self._sorted: Tuple[FormDiagnostic, ...] = ()
        self._listeners: List[Callable[[Tuple[FormDiagnostic, ...]], None]] = []

    def publish(self, source: str, diagnostics: Tuple[FormDiagnostic, ...]) -> None:
        self._by_source[source] = tuple(diagnostics)
        self._rebuild()
        self._notify()

    def clear(self, source: str) -> None:
        if source not in self._by_source:
            return
        del self._by_source[source]
        self._rebuild()
        self._notify()

    def all(self) -> Tuple[FormDiagnostic, ...]:
        return self._sorted

    def for_node(self, node_id: NodeId) -> Tuple[FormDiagnostic, ...]:
        """O(k) via an index by node id."""
        return self._by_node.get(node_id, ())

    def subscribe(self, listener: Callable[[Tuple[FormDiagnostic, ...]], None]) -> Callable[[], None]:
        """Returns an unsubscribe function."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                return

        return unsubscribe

    def _rebuild(self) -> None:
        combined: List[FormDiagnostic] = []
        for source in sorted(self._by_source):
            combined.extend(self._by_source[source])
        combined.sort(key=lambda item: (_SEVERITY_ORDER.get(item.severity.value, 9), item.location.line, item.key))
        self._sorted = tuple(combined)
        grouped: Dict[NodeId, List[FormDiagnostic]] = {}
        for item in self._sorted:
            node_id = item.location.node_id
            if node_id is None:
                continue
            grouped.setdefault(node_id, []).append(item)
        self._by_node = {node_id: tuple(items) for node_id, items in grouped.items()}

    def _notify(self) -> None:
        snapshot = self._sorted
        for listener in tuple(self._listeners):
            listener(snapshot)


def to_problem_detail(diagnostic: FormDiagnostic) -> Mapping[str, str]:
    """The ``CodeDiagnostic.detail`` mapping the Problems bridge sends to the shell:
    ``fb_key``, ``fb_object``, ``fb_property``, ``fb_rule_path`` (JSON), ``fb_source``.
    Never contains the session-local node id."""
    location = diagnostic.location
    return {
        "fb_key": diagnostic.key,
        "fb_object": location.object_name or "",
        "fb_property": location.property or "",
        "fb_rule_path": json.dumps(list(location.rule_path), separators=(",", ":"), ensure_ascii=True),
        "fb_source": diagnostic.source,
    }
