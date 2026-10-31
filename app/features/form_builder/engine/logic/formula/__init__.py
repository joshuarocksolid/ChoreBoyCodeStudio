"""Formula front end and back end.

UI and codegen call ``analyze``, ``normalize``, ``apply_fix``, ``compile_formula``,
and ``evaluate``.
"""

from __future__ import annotations

from app.features.form_builder.engine.logic.formula.check import analyze
from app.features.form_builder.engine.logic.formula.compile import Emitted, compile_formula
from app.features.form_builder.engine.logic.formula.env import FormulaEnv, SlotKind, WidgetFacts
from app.features.form_builder.engine.logic.formula.evaluate import EvalBlank, evaluate
from app.features.form_builder.engine.logic.formula.nodes import (
    Analysis,
    Attr,
    Bin,
    Bool,
    Call,
    Compare,
    Fix,
    FormulaProblem,
    IfElse,
    ListLit,
    Lit,
    Ref,
    Span,
    Unary,
    WindowCall,
)
from app.features.form_builder.engine.logic.formula.normalize import normalize
from app.features.form_builder.engine.logic.formula.parse import apply_fix
from app.features.form_builder.engine.logic.formula.runtime import (
    HELPERS,
    helper_sources,
    helper_table,
    live_helpers,
)
from app.features.form_builder.engine.logic.formula.types import FType

__all__ = (
    "HELPERS",
    "Analysis",
    "Attr",
    "Bin",
    "Bool",
    "Call",
    "Compare",
    "EvalBlank",
    "Emitted",
    "FType",
    "Fix",
    "FormulaEnv",
    "FormulaProblem",
    "IfElse",
    "ListLit",
    "Lit",
    "Ref",
    "SlotKind",
    "Span",
    "Unary",
    "WidgetFacts",
    "WindowCall",
    "analyze",
    "apply_fix",
    "compile_formula",
    "evaluate",
    "helper_sources",
    "helper_table",
    "live_helpers",
    "normalize",
)
