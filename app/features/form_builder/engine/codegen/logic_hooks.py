"""Logic expansion hooks (CONTRACTS.md section 9.4).

The core generator owns everything ``uic`` emits. Expanders, discovered from
``engine/codegen/expanders/`` and ordered by ``order``, add behaviour sections.
No built-in expander ships in M1.3. Discovery returns an empty tuple when the
package is absent.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import List, Protocol, Tuple

from app.features.form_builder.engine.diagnostics import FormDiagnostic
from app.features.form_builder.engine.ui4.document import UiDocument

#: Helper id -> source, emitted once, in this order, when an expander asks.
HELPER_TABLE: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CodegenContext:
    """Read-only facts the core computed: the Ui class name, the ``setupUi``
    parameter name (the form object, e.g. ``Invoice``), widget attribute names,
    the widget kinds table (LOGIC_DESIGN 4.3), and the options."""

    ui_class_name: str
    form_param: str
    attribute_names: Tuple[str, ...]


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


class LogicExpander(Protocol):
    """``level``: 1-4 (documentation). ``order``: sort key; ties broken by
    ``expander_id``. Built-ins: 100 step lists (L1/L3 events), 200 state rules
    and values (L3), 300 checks (L3), 400 data (L4)."""

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
        module = importlib.import_module(package + "." + info.name)
        expander = getattr(module, "EXPANDER", None)
        if expander is None or not hasattr(expander, "contribute"):
            continue
        found.append(expander)
    found.sort(key=lambda item: (item.order, item.expander_id))
    return tuple(found)
