"""Feature registration seam (CONTRACTS.md sections 1 and 11).

Rules (enforced by the M2.0 dune rule ``feature-install-imports`` and by the
import-blocker test in section 13):

* Module-level imports here are limited to the standard library, ``typing``,
  ``app.bootstrap.qt_binding_choice`` and modules under
  ``app.features.form_builder.engine``. Everything Qt-side is imported inside
  ``install_form_builder``.
* ``form_builder_enabled`` never imports a Qt binding.

``app/features/spec.py`` registers::

    FeatureSpec(
        key="form-builder",
        ownership_globs=("app/features/form_builder/**",),
        install=install_form_builder,
        enabled=form_builder_enabled,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.shell.shell_composition_context import ShellCompositionContext

#: Environment kill switch. ``CBCS_FORM_BUILDER=0`` hides the feature on PySide6 too.
KILL_SWITCH_ENV = "CBCS_FORM_BUILDER"

#: The tab-content provider id registered by this feature.
PROVIDER_ID = "form-builder.ui"


def form_builder_enabled() -> bool:
    """True when the selected binding is PySide6 and the kill switch is not ``0``.

    Implementation: ``os.environ.get(KILL_SWITCH_ENV, "1") != "0" and
    app.bootstrap.qt_binding_choice.select_binding() == "PySide6"``. It is the
    import-free equivalent of ``app.qt.qt_compat.IS_QT6``. It must not raise:
    an ``ImportError`` from ``select_binding`` returns False.
    """
    ...


def install_form_builder(ctx: "ShellCompositionContext") -> None:
    """Register the ``.ui`` tab-content provider, Problems bridge, settings keys and
    theme hook with the shell. Called only when ``form_builder_enabled()`` is True.

    Must not create sessions, realize anything or start the preview child. Those
    happen lazily when the first ``.ui`` tab opens. Window fields it binds must be
    listed under the feature's ownership globs (dune composition rule).
    """
    ...
