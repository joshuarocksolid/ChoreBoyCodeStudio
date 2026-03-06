from __future__ import annotations

from collections.abc import Callable
from typing import Any


class CommandBroker:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(
        self,
        command_id: str,
        handler: Callable[..., Any],
        *,
        replace: bool = False,
    ) -> None:
        if not command_id.strip():
            raise ValueError("command_id must be non-empty.")
        if command_id in self._handlers and not replace:
            raise ValueError(f"command already registered: {command_id}")
        self._handlers[command_id] = handler

    def unregister(self, command_id: str) -> None:
        self._handlers.pop(command_id, None)

    def has(self, command_id: str) -> bool:
        return command_id in self._handlers

    def invoke(self, command_id: str, *args: Any, **kwargs: Any) -> Any:
        handler = self._handlers.get(command_id)
        if handler is None:
            raise KeyError(f"command not registered: {command_id}")
        return handler(*args, **kwargs)
