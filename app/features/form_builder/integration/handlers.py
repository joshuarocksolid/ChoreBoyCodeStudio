"""The handler service: how a form event gets code (CONTRACTS.md section 1.4, M6.0s).

The pickers, the canvas link and the double-click ask this protocol to make
a method for an event, to show a method and to list the window class's methods.
They never touch the window file themselves, so the code half (M6.2b's
``integration/handlers_code.py``) can arrive later without changing them.

``HandlerService`` has three calls, all on the GUI thread and all taking the
form tab (``surface``):

* ``make_method(surface, request) -> HandlerOutcome``. ``request.commands`` are
  the engine commands that wire the event (``SetEventSteps``); ``request.label``
  names the undo step; ``request.method`` is the method to create in the window
  class, or ``""`` when the event calls no new method. The **default**
  service only commits ``commands`` in one transaction and creates no code, so
  every flow works on a form that has no code yet (UX-CODE-017).
* ``go_to(surface, method) -> bool``. The default opens the form's window file
  at its first line, through the code bridge, and says False when the form has
  none. ``method`` is ``""`` for the class itself.
* ``methods(surface) -> Tuple[MethodInfo, ...]``. The default knows none.

Discovery: ``service()`` returns the service set with ``set_service``; when none
was set it imports ``integration.handlers_code`` if that module exists and uses
its ``SERVICE``; else the default. M6.2b ships that module and edits nothing
here. A module that fails to import is logged, recorded in
``engine/contributors.FAILURES`` and the default is used, so a bug in the
code half never stops plain steps.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)

CODE_MODULE = "app.features.form_builder.integration.handlers_code"


@dataclass(frozen=True)
class MethodRequest:
    """``method`` and ``params`` (what follows ``self``, e.g. ``"checked"``) are for the code half."""

    label: str
    commands: Tuple[Any, ...] = ()
    method: str = ""
    params: str = ""
    sender: str = ""
    event_words: str = ""


@dataclass(frozen=True)
class HandlerOutcome:
    """``ok`` False means nothing changed; ``reason`` is the sentence to show."""

    ok: bool
    reason: str = ""
    created_method: bool = False


@dataclass(frozen=True)
class MethodInfo:
    name: str
    line: int
    params: Tuple[str, ...] = ()


class HandlerService(Protocol):
    def make_method(self, surface: Any, request: MethodRequest) -> HandlerOutcome:
        ...

    def go_to(self, surface: Any, method: str = "") -> bool:
        ...

    def methods(self, surface: Any) -> Tuple[MethodInfo, ...]:
        ...


class DefaultHandlerService:
    """Commits steps and opens files. Writes no code."""

    def make_method(self, surface: Any, request: MethodRequest) -> HandlerOutcome:
        from app.features.form_builder.engine.commands.base import CommandRejected

        log = surface.session.log
        try:
            with log.transaction(request.label):
                for command in request.commands:
                    log.execute(command)
        except CommandRejected as exc:
            return HandlerOutcome(False, str(exc))
        return HandlerOutcome(True)

    def go_to(self, surface: Any, method: str = "") -> bool:
        del method
        scope = surface.session.scope
        path = getattr(scope, "window_path", None)
        bridge = getattr(surface, "code_bridge", None)
        if not path or bridge is None:
            return False
        import os

        if not os.path.isfile(path):
            return False
        return bool(bridge.open_at(path, 1))

    def methods(self, surface: Any) -> Tuple[MethodInfo, ...]:
        del surface
        return ()


_DEFAULT = DefaultHandlerService()
_SET: Optional[HandlerService] = None
_CODE: Optional[HandlerService] = None
_CODE_LOOKED = False


def _failed(exc: BaseException) -> None:
    # Recorded like every other M6 seam (engine/contributors.FAILURES), so the seam test fails on it.
    from app.features.form_builder.engine.contributors import FAILURES

    FAILURES[CODE_MODULE] = "handler service: %s: %s" % (type(exc).__name__, exc)
    logger.exception("handlers_code could not be imported")


def set_service(service: Optional[HandlerService]) -> Optional[HandlerService]:
    """Install ``service`` (None restores discovery). Returns the previous one."""
    global _SET
    previous = _SET
    _SET = service
    return previous


def service() -> HandlerService:
    if _SET is not None:
        return _SET
    global _CODE, _CODE_LOOKED
    if not _CODE_LOOKED:
        _CODE_LOOKED = True
        try:
            module = importlib.import_module(CODE_MODULE)
            found = getattr(module, "SERVICE", None)
            if found is not None:
                _CODE = found
        except ModuleNotFoundError as exc:
            if exc.name != CODE_MODULE:
                _failed(exc)
        except Exception as exc:
            _failed(exc)
    return _CODE if _CODE is not None else _DEFAULT


__all__ = [
    "CODE_MODULE",
    "DefaultHandlerService",
    "HandlerOutcome",
    "HandlerService",
    "MethodInfo",
    "MethodRequest",
    "service",
    "set_service",
]
