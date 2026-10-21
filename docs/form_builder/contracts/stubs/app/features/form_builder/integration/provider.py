"""The ``.ui`` tab-content provider (CONTRACTS.md section 11.4). [M2.1, M2.2]"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.shell.tab_content_providers import TabMatchContext, TabSurface, TabSurfaceRequest


class FormTabProvider:
    """``provider_id`` = ``install.PROVIDER_ID``; ``priority`` = 100.

    ``matches``: path ends with ``.ui`` (case-insensitive) and
    ``context.forced_text`` is False.

    ``create_surface``: ``FormSession.open(request.initial_text, path=..., scope=
    classify_form(...))``. On UiReadError: raise ``ProviderDeclined`` with the
    error's plain words and line, so the shell opens the file as text (AT-32
    behaviour) with an info bar offering "Open in form builder" after a fix.
    On success: the surface widget (workbench: outline, canvas, inspector) with
    View XML created lazily through ``request.create_source_editor``.

    Save sequence (``EditorManager.save_tab`` on a sourced tab, then the provider's
    ``on_saved`` hook): 1. bytes = current_text() -> atomic write .ui;
    2. mark_saved; 3. if scope generates and the text parses: codegen from the
    in-memory document with ``source_bytes``; hand-edit check; atomic write
    ``ui_<name>.py`` (and ``*_rc.py`` for changed .qrc). Codegen failure never
    fails the save; it reports FB5xx. Budget for 1-3: 50 ms CPU at 300 widgets.
    """

    provider_id: str
    priority: int

    def matches(self, file_path: str, context: "TabMatchContext") -> bool:
        ...

    def create_surface(self, request: "TabSurfaceRequest") -> "TabSurface":
        ...
