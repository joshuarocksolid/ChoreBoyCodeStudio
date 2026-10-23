"""The ``.ui`` tab-content provider (CONTRACTS.md section 11)."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.save import opening_diagnostics
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.reader import UiReadError
from app.features.form_builder.install import PROVIDER_ID
from app.features.form_builder.integration.content_source import (
    FormContentSource,
    form_scope,
    plain_read_error,
)
from app.features.form_builder.integration.form_commands import form_tab_menu
from app.features.form_builder.integration.surface import FormSurface
from app.shell.tab_content_providers import ProviderDeclined, TabMatchContext, TabMenu, TabSurfaceRequest


class FormTabProvider:
    """Matches ``*.ui`` unless the user forced a text tab."""

    provider_id = PROVIDER_ID
    priority = 100
    menu: Optional[TabMenu] = form_tab_menu()

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        if context.forced_text:
            return False
        return file_path.lower().endswith(".ui")

    def create_surface(self, request: TabSurfaceRequest) -> FormSurface:
        try:
            scope = form_scope(request.file_path, request.project_root)
            session = FormSession.open(request.initial_text, path=request.file_path, scope=scope)
        except UiReadError as exc:
            detail = plain_read_error(exc).rstrip(".")
            raise ProviderDeclined(
                f"This form can't be opened in the form builder: {detail}."
            ) from exc
        # Save republishes "codegen", which replaces this FB505 once the module is current.
        session.diagnostics.publish(
            "codegen",
            opening_diagnostics(session.scope, request.initial_text.encode("utf-8"), OsFileSystem()),
        )
        source = FormContentSource(
            session.log,
            request.initial_text,
            scope=session.scope,
            diagnostics=session.diagnostics,
        )
        return FormSurface(request, session, source)


__all__ = ["FormTabProvider"]
