"""PROPOSED change to ``app/features/spec.py`` by M2.0 (CONTRACTS.md section 11.3).

Shown as a separate stub file so the proposal is reviewable; M2.0 edits
``spec.py`` itself.

* ``FeatureSpec`` gains ``enabled: Optional[Callable[[], bool]] = None``.
  None means always enabled.
* The composition loop calls ``spec.enabled()`` before ``spec.install(ctx)``
  and skips install when it returns False. ``enabled`` is called once per
  process, must not import a Qt binding, must not raise (an exception counts as
  False and is logged).
* ``FEATURE_SPECS`` stays a literal tuple of ``FeatureSpec(...)`` calls with
  literal ``key`` and ``ownership_globs`` (``tools/dune/composition.py`` parses it).
* ``spec.py``'s module-level imports of install functions stay, which is why every
  feature ``install.py`` must be light at module level (dune rule
  ``feature-install-imports``). Markdown's ``install.py`` moves its
  ``MarkdownEditorPane`` / registry imports inside ``install_markdown``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional, Tuple

if TYPE_CHECKING:  # pragma: no cover
    from app.shell.shell_composition_context import ShellCompositionContext

FeatureInstall = Callable[["ShellCompositionContext"], None]
FeatureEnabled = Callable[[], bool]


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    ownership_globs: Tuple[str, ...]
    install: Optional[FeatureInstall] = None
    enabled: Optional[FeatureEnabled] = None
