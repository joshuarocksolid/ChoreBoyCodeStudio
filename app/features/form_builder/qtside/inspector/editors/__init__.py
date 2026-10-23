"""Each public module here defines register(registrar). A new lane adds a module and edits nothing else."""

from __future__ import annotations

import importlib
import pkgutil
import sys
from functools import lru_cache
from types import ModuleType

from app.features.form_builder.qtside.inspector.catalog import Catalog, Registrations


def load_catalog(*packages: ModuleType) -> Catalog:
    """Load each package's public modules in sorted name order, then freeze one catalog.

    Packages load in argument order. Names starting with "_" are never imported.
    A public module without ``register`` raises TypeError, because a silent skip
    would hide a lane's missing editors.
    """
    found = Registrations()
    for package in packages:
        for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda item: item.name):
            if info.name.startswith("_"):
                continue
            module = importlib.import_module("%s.%s" % (package.__name__, info.name))
            register = getattr(module, "register", None)
            if not callable(register):
                raise TypeError("%s has no register(registrar)" % module.__name__)
            register(found.scope(module.__name__))
    return found.freeze()


@lru_cache(maxsize=None)
def default_catalog() -> Catalog:
    """This package's catalog, loaded once per process."""
    return load_catalog(sys.modules[__name__])
