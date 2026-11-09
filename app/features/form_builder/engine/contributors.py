"""Contributor discovery shared by the M5 seams (M5.0s). Qt-free.

A seam is a package whose modules each add something to a registry: Form menu
items, keys, left sections, canvas layers, fix buttons, inspector form groups.
``run_contributors`` imports every public module of the packages in sorted
name order (a name starting with ``_`` is a helper and is skipped) and calls
the module's hook, so the result does not depend on the file system's listing
order. Importing again is cheap: Python keeps each module once.

A module that fails to import or whose hook raises is logged and skipped, so
one lane's mistake never takes down the menu or the canvas. The failure is
also kept in ``FAILURES``, and the product test loads every seam and asserts
that no product module is there, so a broken contributor fails the test run
instead of quietly disappearing.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from types import ModuleType
from typing import Any, Callable, Dict, Tuple

logger = logging.getLogger(__name__)

#: Module name -> ``"<seam>: <error>"`` for every contributor that failed in this process.
FAILURES: Dict[str, str] = {}


def module_names(package: ModuleType) -> Tuple[str, ...]:
    """The public module names of ``package``, sorted."""
    return tuple(sorted(info.name for info in pkgutil.iter_modules(package.__path__) if not info.name.startswith("_")))


def run_contributors(
    seam: str,
    packages: Tuple[ModuleType, ...],
    hook: str,
    call: Callable[[ModuleType, Callable[..., Any]], None],
) -> None:
    """For each public module that defines ``hook``, run ``call(module, hook function)``."""
    for package in packages:
        for name in module_names(package):
            full = "%s.%s" % (package.__name__, name)
            try:
                module = importlib.import_module(full)
                found = getattr(module, hook, None)
                if callable(found):
                    call(module, found)
            except Exception as exc:
                FAILURES[full] = "%s: %s: %s" % (seam, type(exc).__name__, exc)
                logger.exception("%s contributor %s failed", seam, full)


__all__ = ["FAILURES", "module_names", "run_contributors"]
