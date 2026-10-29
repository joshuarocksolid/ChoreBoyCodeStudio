"""Where saved templates live, and the per-user choices about them (UX-TMPL-002, UX-TMPL-006).

Templates for "All my projects" are kept in ``form_templates/`` in the Code
Studio settings folder (``~/choreboy_code_studio_state``); "This project only"
ones in ``cbcs/form_builder/templates/``. The default place for a new template
is ``form_builder.template_scope`` in the user's settings (``user`` or
``project``), set on Settings > Form designer.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

from app.bootstrap.paths import resolve_global_state_root
from app.features.form_builder.engine.project import user_templates as ut
from app.persistence.settings_service import SettingsService

SETTINGS_KEY = "form_builder"
SCOPE_KEY = "template_scope"

_ROOT_OVERRIDE: Optional[str] = None


def use_state_root(root: Optional[str]) -> None:
    """Pin the settings folder (tests). ``None`` follows the product state root."""
    global _ROOT_OVERRIDE
    _ROOT_OVERRIDE = root


def state_root() -> str:
    if _ROOT_OVERRIDE:
        return _ROOT_OVERRIDE
    try:
        return str(resolve_global_state_root())
    except (OSError, ValueError):
        return ""


def settings_root() -> Optional[str]:
    """The pinned settings folder, or None for the product's own."""
    return _ROOT_OVERRIDE


def load_templates(project_root: Optional[str]) -> Tuple[ut.TemplateInfo, ...]:
    return ut.list_templates(state_root(), project_root)


def scope_from_payload(payload: Mapping[str, Any]) -> str:
    section = payload.get(SETTINGS_KEY)
    if isinstance(section, Mapping) and section.get(SCOPE_KEY) == ut.SCOPE_PROJECT:
        return ut.SCOPE_PROJECT
    return ut.SCOPE_USER


def payload_with_scope(payload: Mapping[str, Any], scope: str) -> dict[str, Any]:
    updated = dict(payload)
    section_raw = updated.get(SETTINGS_KEY)
    section = dict(section_raw) if isinstance(section_raw, Mapping) else {}
    section[SCOPE_KEY] = ut.SCOPE_PROJECT if scope == ut.SCOPE_PROJECT else ut.SCOPE_USER
    updated[SETTINGS_KEY] = section
    return updated


def default_scope() -> str:
    """Where "Save as template…" starts: the user's choice, else "All my projects"."""
    try:
        return scope_from_payload(SettingsService(state_root=settings_root()).load_global())
    except OSError:
        return ut.SCOPE_USER


__all__ = [
    "SCOPE_KEY",
    "default_scope",
    "load_templates",
    "payload_with_scope",
    "scope_from_payload",
    "settings_root",
    "state_root",
    "use_state_root",
]
