"""Diagnostic code modules. Importing a module registers its codes.

A lane declares its codes by adding a module here (``fb03x_resources.py``)
that calls ``declare(...)`` at import. ``discover()`` imports every public
module in sorted name order, so each code is declared once whichever module
runs first, and a new file needs no edit anywhere else. A module whose name
starts with an underscore is a helper and is not imported.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from types import ModuleType
from typing import Optional, Tuple


def discover(package: Optional[ModuleType] = None) -> Tuple[str, ...]:
    """Import each public module of ``package`` (default: this one). Returns their names, sorted.

    Safe to call again: an imported module declares its codes only once. A
    module that raises is not caught; a duplicate or malformed code is a bug
    the test run must show.
    """
    target = package if package is not None else sys.modules[__name__]
    names = sorted(info.name for info in pkgutil.iter_modules(target.__path__) if not info.name.startswith("_"))
    for name in names:
        importlib.import_module("%s.%s" % (target.__name__, name))
    return tuple(names)


__all__ = ["discover"]
