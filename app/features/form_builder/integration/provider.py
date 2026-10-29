"""The ``.ui`` tab-content provider (CONTRACTS.md section 11)."""

from __future__ import annotations

from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.reader import UiReadError
from app.features.form_builder.install import PROVIDER_ID
from app.features.form_builder.integration.content_source import (
    FormContentSource,
    form_scope,
    plain_read_error,
)
from app.features.form_builder.integration.qrc_provider import QrcTabProvider, attach_picture_checks, is_qrc
from app.features.form_builder.integration.surface import FormSurface
from app.shell.tab_content_providers import ProviderDeclined, TabMatchContext, TabSurfaceRequest


class FormTabProvider:
    """Matches ``*.ui`` unless the user forced a text tab."""

    provider_id = PROVIDER_ID
    priority = 100

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        if context.forced_text:
            return False
        return file_path.lower().endswith(".ui") or is_qrc(file_path)

    def create_surface(self, request: TabSurfaceRequest) -> object:
        if is_qrc(request.file_path):
            return QrcTabProvider().create_surface(request)
        try:
            scope = form_scope(request.file_path, request.project_root)
            session = FormSession.open(request.initial_text, path=request.file_path, scope=scope)
        except UiReadError as exc:
            detail = plain_read_error(exc).rstrip(".")
            raise ProviderDeclined(
                f"This form can't be opened in the form builder: {detail}."
            ) from exc
        source = FormContentSource(
            session.log,
            request.initial_text,
            scope=session.scope,
            diagnostics=session.diagnostics,
        )
        if request.project_root:
            attach_picture_checks(session, request.project_root)
        return FormSurface(request, session, source)


__all__ = ["FormTabProvider"]
