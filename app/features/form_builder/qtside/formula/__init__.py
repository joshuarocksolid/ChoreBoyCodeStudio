"""Formula field. ``FormulaEditor`` loads on first use so ``words.speak`` stays Qt-free."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.features.form_builder.qtside.formula.editor import FormulaEditor as FormulaEditor

__all__ = ["FormulaEditor"]


def __getattr__(name: str) -> Any:
    if name == "FormulaEditor":
        from app.features.form_builder.qtside.formula.editor import FormulaEditor

        return FormulaEditor
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
