"""Property editor registry.

Modules in this package are discovered in sorted name order. Each one exposes
``register(registrar)``. A module whose name starts with an underscore is a
helper and is not imported. A public module with no ``register`` is skipped.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sys
import warnings
from functools import lru_cache
from types import ModuleType

from app.features.form_builder.qtside.inspector.catalog import Catalog, Registrations


def load_catalog(*packages: ModuleType) -> Catalog:
    found = Registrations()
    for package in packages:
        for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda item: item.name):
            if info.name.startswith("_"):
                continue
            module = importlib.import_module("%s.%s" % (package.__name__, info.name))
            register = getattr(module, "register", None)
            if not callable(register):
                _warn_missing_register(module.__name__)
                continue
            register(found.scope(module.__name__))
    return found.freeze()


def _warn_missing_register(module_name: str) -> None:
    if os.environ.get("CBCS_FB_DEV") != "1":
        return
    warnings.warn(
        "%s has no register(registrar). Helper modules start with an underscore and are not loaded."
        % module_name,
        UserWarning,
        stacklevel=3,
    )


@lru_cache(maxsize=None)
def default_catalog() -> Catalog:
    return load_catalog(sys.modules[__name__])
