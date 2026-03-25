from __future__ import annotations

from typing import Any, Mapping

from app.plugins.runtime_serializers import serialize_templates
from app.templates.template_service import TemplateService


def handle_templates_query(_provider_key: str, request: Mapping[str, Any]) -> list[dict[str, Any]]:
    _ = request
    service = TemplateService()
    return serialize_templates(service.list_templates())
