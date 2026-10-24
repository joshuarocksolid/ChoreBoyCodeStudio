"""Extra commands (CONTRACTS.md section 1.4).

Modules in this package are discovered in sorted module-name order. Each
defines ``register(registry)`` when it needs a process-wide registry.
``ApplySizing`` is imported by the Size group. It does not edit ``catalog.py``.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Callable, List


def load_extensions(register_into: Callable[[object], None]) -> None:
    """Call ``register(register_into)`` on each sibling that defines it."""
    prefix = __name__ + "."
    discovered = sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name)
    for info in discovered:
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(prefix + info.name)
        register = getattr(module, "register", None)
        if register is not None:
            register(register_into)


def extension_modules() -> List[str]:
    return [
        info.name
        for info in sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name)
        if not info.name.startswith("_")
    ]
