"""Feature ownership registry.

``FEATURE_SPECS`` stays a literal tuple of ``FeatureSpec(...)`` calls.
``enabled`` is ``None`` when the feature is always installed. Install callables
import their feature modules inside the function so ``import app.features``
does not import a Qt binding.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from app.shell.shell_composition_context import ShellCompositionContext

FeatureInstall = Callable[["ShellCompositionContext"], None]
FeatureEnabled = Callable[[], bool]

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    ownership_globs: tuple[str, ...]
    install: Optional[FeatureInstall] = None
    enabled: Optional[FeatureEnabled] = None


def feature_is_enabled(spec: FeatureSpec) -> bool:
    """Return whether ``spec`` should be installed.

    ``enabled is None`` means always enabled. A predicate exception is logged
    and treated as disabled. The predicate must not import a Qt binding.
    """
    predicate = spec.enabled
    if predicate is None:
        return True
    try:
        return bool(predicate())
    except Exception:
        _LOGGER.exception("Feature %s enabled() failed; skipping install", spec.key)
        return False


def _install_markdown(ctx: "ShellCompositionContext") -> None:
    from app.features.markdown.install import install_markdown

    install_markdown(ctx)


def _install_editor_groups(ctx: "ShellCompositionContext") -> None:
    from app.features.editor_groups.install import install_editor_groups

    install_editor_groups(ctx)


def _form_builder_enabled() -> bool:
    # feature-install-imports forbids a module-level import of a feature package.
    from app.features.form_builder.install import form_builder_enabled

    return form_builder_enabled()


def _install_form_builder(ctx: "ShellCompositionContext") -> None:
    from app.features.form_builder.install import install_form_builder

    install_form_builder(ctx)


FEATURE_SPECS: tuple[FeatureSpec, ...] = (
    FeatureSpec(
        key="markdown",
        ownership_globs=("app/features/markdown/**",),
        install=_install_markdown,
    ),
    FeatureSpec(
        key="shop-lan-state",
        ownership_globs=("app/features/shop-lan-state/**",),
    ),
    FeatureSpec(
        key="editor-groups",
        ownership_globs=("app/features/editor_groups/**",),
        install=_install_editor_groups,
    ),
    FeatureSpec(
        key="hidden-path-policy",
        ownership_globs=("app/features/hidden-path-policy/**",),
    ),
    FeatureSpec(
        key="form-builder",
        ownership_globs=("app/features/form_builder/**",),
        install=_install_form_builder,
        enabled=_form_builder_enabled,
    ),
)

__all__ = ["FEATURE_SPECS", "FeatureEnabled", "FeatureInstall", "FeatureSpec", "feature_is_enabled"]
