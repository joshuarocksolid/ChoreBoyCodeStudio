"""Formula front end. Text in, a typed tree and problems out.

UI and codegen call ``analyze``, ``normalize``, and ``apply_fix``. Evaluation
lives in M7.1b and is not imported here.
"""

from __future__ import annotations

from app.features.form_builder.engine.logic.formula.check import analyze
from app.features.form_builder.engine.logic.formula.env import FormulaEnv, SlotKind, WidgetFacts
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
from app.features.form_builder.engine.logic.formula.types import FType

__all__ = (
    "Analysis",
    "Attr",
    "Bin",
    "Bool",
    "Call",
    "Compare",
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
    "normalize",
)
