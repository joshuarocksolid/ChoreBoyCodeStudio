"""Logic expansion hooks (CONTRACTS.md section 9.4).

The core generator owns everything ``uic`` emits. Expanders, discovered from
``engine/codegen/expanders/`` and ordered by ``order``, add behaviour sections.
No built-in expander ships in M1.3. Discovery returns an empty tuple when the
package is absent.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import re
from dataclasses import dataclass, field
from typing import Callable, List, Mapping, Optional, Protocol, Sequence, Tuple

from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.project.window_facts import WindowFacts
from app.features.form_builder.engine.ui4.document import UiDocument

logger = logging.getLogger(__name__)

#: Every character Python or ``str.splitlines`` treats as a line break, and other control characters.
_BREAKS = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")

_HELPER_PROVIDER: Optional[Callable[[], Sequence[Tuple[str, str]]]] = None


def one_line(text: str) -> str:
    """Text for a ``#`` comment: one line, whatever the file held."""
    return _BREAKS.sub(" ", text)


def set_helper_provider(fn: Optional[Callable[[], Sequence[Tuple[str, str]]]]) -> None:
    """Install the helper table a lane provides. ``None`` clears it."""
    global _HELPER_PROVIDER
    _HELPER_PROVIDER = fn


def helper_table() -> Tuple[Tuple[str, str], ...]:
    """Helper id -> source. A provider wins; otherwise the formula runtime, or nothing."""
    provider = _HELPER_PROVIDER
    if provider is not None:
        return tuple(provider())
    name = "app.features.form_builder.engine.logic.formula.runtime"
    try:
        loaded = importlib.import_module(name).helper_table
    except ModuleNotFoundError as exc:
        # Only "the runtime isn't there yet" means no helpers; a broken runtime must fail loudly.
        if exc.name not in (name, name.rpartition(".")[0]):
            raise
        return ()
    return tuple(loaded())


@dataclass(frozen=True)
class FormatSettings:
    """US English formats. Not read from ``project.json``."""

    currency: str = "$"
    grouping: str = "1,234.50"
    date: str = "MM/DD/YYYY"


@dataclass(frozen=True)
class WidgetFacts:
    """Codegen's record of one widget. ``kind`` and ``allow_blank`` stay default until a later lane."""

    class_name: str
    kind: str = ""
    decimals: int = 0
    prefix: str = ""
    tristate: bool = False
    allow_blank: bool = False
    has_items_data: bool = False
    pages: Tuple[str, ...] = ()
    also: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CodegenContext:
    """Read-only facts the core computed: the Ui class name, the ``setupUi``
    parameter name (the form object, e.g. ``Invoice``), widget attribute names,
    the window reading, formats, widget facts and whether Preview asked for trace."""

    ui_class_name: str
    form_param: str
    attribute_names: Tuple[str, ...]
    window: Optional[WindowFacts] = None
    formats: FormatSettings = FormatSettings()
    widgets: Mapping[str, WidgetFacts] = field(default_factory=dict)
    trace: bool = False


@dataclass(frozen=True)
class Method:
    """One generated method on the Ui class. ``name`` starts with ``cbcs_`` or
    ``_cbcs_`` (LOGIC_DESIGN 7.9). ``source_ref`` names the rule it came from
    (``"lineTotalLabel:cbcsValue"``) and is written as the block's first comment
    so tracebacks map back ("Open rule" links). ``params`` is what follows
    ``self`` in the ``def`` line (``"*args"`` for a step list, CONTRACTS 15.6);
    empty by default."""

    name: str
    body: str
    source_ref: str
    params: str = ""


@dataclass(frozen=True)
class Contribution:
    """``imports``: ``(module, name)`` pairs; the core dedups and sorts them.
    ``setup_lines``: appended to ``_cbcs_setup``; when any expander contributes
    setup lines, ``setupUi`` ends with ``self._cbcs_setup(<form_param>)`` after
    ``connectSlotsByName``.
    ``helpers``: helper ids from the fixed helper table (emitted once, in table
    order, at module bottom).
    A rule with an error contributes nothing and reports a diagnostic; it never
    raises and never stops other rules or the core (LOGIC_DESIGN 2.9)."""

    imports: Tuple[Tuple[str, str], ...] = ()
    setup_lines: Tuple[str, ...] = ()
    methods: Tuple[Method, ...] = ()
    helpers: Tuple[str, ...] = ()
    diagnostics: Tuple[FormDiagnostic, ...] = ()
    needs_form: bool = False
    connects: Tuple[Tuple[str, str], ...] = ()  # (widget, handler)


class LogicExpander(Protocol):
    """``level``: 1-4 (documentation). ``order``: sort key; ties broken by
    ``expander_id``. Built-ins: 100 steps, 200 rules (with defaults), 300 checks,
    350 formats, 900+ "after everything" (form events)."""

    expander_id: str
    level: int
    order: int

    def contribute(self, doc: UiDocument, ctx: CodegenContext) -> Contribution:
        """Pure function of the document. Rules are emitted in dependency order with
        ties broken by widget document order (LOGIC_DESIGN 7.1 rule 3)."""


def load_expanders() -> Tuple[LogicExpander, ...]:
    """Import ``codegen/expanders`` modules and collect their ``EXPANDER`` object.

    The import is inside the function because the package is optional and is
    loaded only when a form is generated.
    """
    package = "app.features.form_builder.engine.codegen.expanders"
    try:
        imported = importlib.import_module(package)
    except ImportError:
        return ()
    found: List[LogicExpander] = []
    search = getattr(imported, "__path__", None)
    if not search:
        return ()
    for info in pkgutil.iter_modules(search):
        full = package + "." + info.name
        try:
            module = importlib.import_module(full)
        except Exception as exc:
            # A module that can't load adds nothing; the form still generates (CONTRACTS 9.4).
            from app.features.form_builder.engine.contributors import FAILURES

            FAILURES[full] = "expander: %s: %s" % (type(exc).__name__, exc)
            logger.exception("expander %s failed to load", full)
            continue
        expander = getattr(module, "EXPANDER", None)
        if expander is None or not hasattr(expander, "contribute"):
            continue
        found.append(expander)
    found.sort(key=lambda item: (item.order, item.expander_id))
    return tuple(found)
