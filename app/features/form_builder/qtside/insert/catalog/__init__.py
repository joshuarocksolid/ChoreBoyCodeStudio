"""The Insert catalog (UX-CAT-001). Qt-free: the canvas core builds fragments from it.

Modules in this package are read in sorted name order; each non-underscore module
exposes ``register(registry)`` (CONTRACTS section 1.4). Category and entry order come
from ``_model.CATEGORY_ORDER`` and each module's registration order, never from file names.
"""

from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache
from types import ModuleType
from typing import List

from app.features.form_builder.qtside.insert.catalog._model import Catalog, Entry, Registry, build_registry, catalog_from


def _modules() -> List[ModuleType]:
    found = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name):
        if info.name.startswith("_"):
            continue
        found.append(importlib.import_module(__name__ + "." + info.name))
    return found


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    registry, _names = build_registry(_modules())
    return catalog_from(registry)


def in_sentence(title: str) -> str:
    """A friendly name inside a sentence: lower case, except acronyms ("Insert LCD number")."""
    return " ".join(word if len(word) > 1 and word.isupper() else word.lower() for word in title.split(" "))


def registry_for_tests() -> Registry:
    registry, _names = build_registry(_modules())
    return registry


__all__ = ["Catalog", "Entry", "in_sentence", "load_catalog", "registry_for_tests"]
