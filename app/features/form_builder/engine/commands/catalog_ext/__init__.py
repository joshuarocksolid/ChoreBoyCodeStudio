"""Extra commands (CONTRACTS.md section 1.4).

Modules in this package are discovered in sorted module-name order. Each
defines ``register(registry)``. A later work package adds its own module and
does not edit this file.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import List, Optional, Tuple, Type

from app.features.form_builder.engine.commands.base import Command


class CommandRegistry:
    def __init__(self) -> None:
        self._types: List[Type[Command]] = []

    def add(self, command_type: Type[Command]) -> None:
        if command_type not in self._types:
            self._types.append(command_type)

    def types(self) -> Tuple[Type[Command], ...]:
        return tuple(self._types)


def load_commands(registry: CommandRegistry) -> None:
    """Import ``register`` from each sibling module, in module-name order."""
    package = __name__
    prefix = package + "."
    discovered = sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name)
    for info in discovered:
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(prefix + info.name)
        register = getattr(module, "register", None)
        if register is not None:
            register(registry)


_DEFAULT: Optional[CommandRegistry] = None


def default_registry() -> CommandRegistry:
    """The process-wide registry. Built on first use."""
    global _DEFAULT
    if _DEFAULT is None:
        registry = CommandRegistry()
        load_commands(registry)
        _DEFAULT = registry
    return _DEFAULT
