"""Live "now:" text for a formula (UX-STATE-002)."""

from __future__ import annotations

import io
import re
import tokenize
from decimal import Decimal
from typing import Any

from app.features.form_builder.engine.diagnostic_codes import fb1xx_formula as _formula_codes
from app.features.form_builder.engine.diagnostics import CODES, Severity
from app.features.form_builder.engine.logic.formula import compile_formula, evaluate
from app.features.form_builder.engine.logic.formula.env import FormulaEnv
from app.features.form_builder.engine.logic.formula.evaluate import EvalBlank
from app.features.form_builder.engine.logic.formula.nodes import Analysis

_ = _formula_codes


def now_text(analysis: Analysis, env: FormulaEnv, reader: Any) -> str:
    """Compile and evaluate when nothing is an error. A missing widget is ``blank``."""
    if _has_error(analysis) or analysis.tree is None or reader is None:
        return "blank"
    for name in analysis.reads:
        if not hasattr(reader, name):
            return "blank"
    try:
        emitted = compile_formula(analysis, env)
    except Exception:
        return "blank"
    try:
        value = evaluate(emitted, reader, {})
    except Exception:
        return "blank"
    return _show(value)


def as_words(text: str, env: FormulaEnv) -> str:
    """The formula with each widget's object name replaced by its display name."""
    if not text or not env.widgets:
        return text
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return _replace_names(text, env)
    parts = []
    for tok in tokens:
        if tok.type in (tokenize.ENCODING, tokenize.ENDMARKER, tokenize.NEWLINE, tokenize.NL):
            continue
        if tok.type == tokenize.NAME and tok.string in env.widgets:
            facts = env.widgets[tok.string]
            parts.append(facts.display or tok.string)
        else:
            parts.append(tok.string)
    return " ".join(parts)


def _replace_names(text: str, env: FormulaEnv) -> str:
    names = sorted(env.widgets, key=len, reverse=True)
    pattern = re.compile(r"\b(%s)\b" % "|".join(re.escape(name) for name in names))

    def swap(match: "re.Match[str]") -> str:
        facts = env.widgets[match.group(0)]
        return facts.display or match.group(0)

    return pattern.sub(swap, text)


def _has_error(analysis: Analysis) -> bool:
    for problem in analysis.problems:
        info = CODES.get(problem.code)
        if info is None or info.severity is Severity.ERROR:
            return True
    return False


def _show(value: object) -> str:
    if isinstance(value, EvalBlank):
        return value.reason
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "blank"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
