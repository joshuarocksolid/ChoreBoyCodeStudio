"""Read the builder back in the words already on its menus.

Formula mode keeps ``as_words``. This is only for the builder's status line,
so a non-programmer never sees ``x if c else y``. The sentences come from
``engine.logic.formula.speak``.
"""

from __future__ import annotations

from app.features.form_builder.engine.logic.formula.env import FormulaEnv
from app.features.form_builder.engine.logic.formula.speak import speak_text
from app.features.form_builder.qtside.formula.builder.model import (
    Condition,
    Model,
    write_formula,
)


def speak(model: Model, env: FormulaEnv) -> str:
    """The status line for one builder model. Empty when there is nothing to read."""

    text = write_formula(model).strip()
    if not text:
        return ""
    kind = "condition" if isinstance(model, Condition) else "value"
    return speak_text(text, env, kind)
