from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from app.shell.shell_composition_context import ShellCompositionContext

FeatureInstall = Callable[["ShellCompositionContext"], None]


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    ownership_globs: tuple[str, ...]
    install: Optional[FeatureInstall] = None


FEATURE_SPECS: tuple[FeatureSpec, ...] = ()


__all__ = ["FEATURE_SPECS", "FeatureInstall", "FeatureSpec"]
