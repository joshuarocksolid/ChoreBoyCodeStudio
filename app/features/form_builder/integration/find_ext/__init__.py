"""Find contributors. A module exposes ``register(window)``."""

from __future__ import annotations

import sys
from types import ModuleType

from app.features.form_builder.engine.contributors import run_contributors


def install_find(window: object) -> None:
    package = sys.modules[__name__]

    def call(_module: ModuleType, hook: object) -> None:
        hook(window)  # type: ignore[operator]

    run_contributors("find", (package,), "register", call)


__all__ = ["install_find"]
