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

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Mapping, Optional, Tuple, Union

from app.features.form_builder.engine.ids import NodeId


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
        ...


#: Code registry: code -> CodeInfo. Populated by ``engine/diagnostic_codes/*``.
CODES: Dict[str, CodeInfo] = {}


def declare(code: str, severity: Severity, title: str, *, blocks_visual_open: bool = False) -> None:
    """Register a code. ValueError on a duplicate or a malformed code."""
    ...


class DiagnosticsStore:
    """Per-session diagnostics, grouped by producer.

    ``publish(source, diagnostics)`` atomically replaces everything that producer
    published before, then notifies subscribers once with the full sorted list.
    Order of ``all()``: severity (error, warning, info), then line, then key.
    Producers run after the ChangeSet that made their input stale; cheap producers
    synchronously at listener priority ``PRIORITY_DIAGNOSTICS``, expensive ones
    (formula type-check, handler parse) coalesced to idle by the Qt side.
    """

    def publish(self, source: str, diagnostics: Tuple[FormDiagnostic, ...]) -> None:
        ...

    def clear(self, source: str) -> None:
        ...

    def all(self) -> Tuple[FormDiagnostic, ...]:
        ...

    def for_node(self, node_id: NodeId) -> Tuple[FormDiagnostic, ...]:
        """O(k) via an index by node id."""
        ...

    def subscribe(self, listener: Callable[[Tuple[FormDiagnostic, ...]], None]) -> Callable[[], None]:
        """Returns an unsubscribe function."""
        ...


def to_problem_detail(diagnostic: FormDiagnostic) -> Mapping[str, str]:
    """The ``CodeDiagnostic.detail`` mapping the Problems bridge sends to the shell:
    ``fb_key``, ``fb_object``, ``fb_property``, ``fb_rule_path`` (JSON), ``fb_source``.
    Never contains the session-local node id."""
    ...
