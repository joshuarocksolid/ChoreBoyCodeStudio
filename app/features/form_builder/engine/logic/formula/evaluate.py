"""Design-time evaluation of a compiled formula."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional

from app.features.form_builder.engine.logic.formula.runtime import live_helpers


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvalBlank:
    reason: str


class _NeedsValue(Exception):
    pass


class _FormProxy(object):
    def __init__(self, values: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_values", values)

    def __getattr__(self, name: str) -> Any:
        values = object.__getattribute__(self, "_values")
        if name not in values:
            def _missing(*_args: Any, **_kwargs: Any) -> Any:
                raise _NeedsValue()

            return _missing

        def _present(*_args: Any, **_kwargs: Any) -> Any:
            return values[name]

        return _present


class _ReaderProxy(object):
    def __init__(self, reader: Any, form: _FormProxy) -> None:
        object.__setattr__(self, "_reader", reader)
        object.__setattr__(self, "_form_obj", form)

    def __getattr__(self, name: str) -> Any:
        if name == "_form":
            return object.__getattribute__(self, "_form_obj")
        reader = object.__getattribute__(self, "_reader")
        return getattr(reader, name)


def evaluate(emitted: Any, reader: Any, window_values: Optional[Mapping[str, Any]]) -> Any:
    values = {} if window_values is None else window_values
    proxy = _ReaderProxy(reader, _FormProxy(values))
    globs = {**live_helpers(), "Decimal": Decimal, "__builtins__": {}}  # type: Dict[str, Any]
    real_matches = globs["_cbcs_matches"]

    def _capped_matches(text: Any, pattern: Any) -> Any:
        # Design-time cap lives here; the helper caps the pattern at 200.
        if isinstance(text, str):
            text = text[:1000]
        return real_matches(text, pattern)

    globs["_cbcs_matches"] = _capped_matches
    # Re-insert so __builtins__ stays the last key after the matches wrapper.
    builtins = globs.pop("__builtins__")
    globs["__builtins__"] = builtins
    try:
        return eval(compile(emitted.source, "<formula>", "eval"), globs, {"self": proxy})  # noqa: S307
    except _NeedsValue:
        return EvalBlank("needs a window value")
    except Exception as exc:
        logger.debug("formula evaluation failed: %s", exc, exc_info=True)
        return EvalBlank(str(exc))
