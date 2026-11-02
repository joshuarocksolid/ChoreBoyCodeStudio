"""Extra pages for the Settings dialog, registered by features.

A feature registers a page once (at import or install time)::

    register_settings_page(SettingsPage(key="form_builder", title="Form designer",
                                        build=make_page, apply=write_page))

The dialog adds one tab per registered page, in registration order, after its
own tabs. ``scope`` is ``"global"`` unless the page says ``"project"``. A
project page is left out when no project is open, and its ``build`` receives
the project root as a third argument.

* A global page's ``apply(page, payload)`` runs once, after OK, with the
  global payload the shell is about to save. It returns that payload with the
  page's keys written. The shell saves the result once.
* A project page's ``apply(widget, project_root)`` runs once, inside OK,
  before the dialog closes. It writes its own project files and returns None,
  or ``SettingsRefusal`` to keep the dialog open and show the sentence.
  Nothing is written for the project pages after a refusal. Project pages
  never touch the global payload, and they are not applied again after OK.

A page whose ``build`` or ``apply`` raises is logged and skipped: it never stops
the dialog from opening or the shell's settings from saving. Registering the
same ``key`` again replaces the earlier page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from app.qt.QtWidgets import QTabWidget, QWidget

_LOGGER = logging.getLogger(__name__)

BuildPage = Callable[..., QWidget]
ApplyPage = Callable[..., Any]

SCOPE_GLOBAL = "global"
SCOPE_PROJECT = "project"


@dataclass(frozen=True)
class SettingsRefusal:
    """``apply`` returns this to keep Settings open and show ``sentence``."""

    sentence: str


@dataclass(frozen=True)
class SettingsPage:
    key: str
    title: str
    build: BuildPage
    apply: ApplyPage
    scope: str = SCOPE_GLOBAL


_PAGES: Dict[str, SettingsPage] = {}


def register_settings_page(page: SettingsPage) -> None:
    _PAGES[page.key] = page


def unregister_settings_page(key: str) -> None:
    _PAGES.pop(key, None)


def registered_settings_pages() -> Tuple[SettingsPage, ...]:
    return tuple(_PAGES.values())


def build_registered_pages(
    tabs: QTabWidget,
    payload: Mapping[str, Any],
    project_root: Optional[str] = None,
) -> List[Tuple[SettingsPage, QWidget]]:
    """Add a tab for every registered page the open scope can show.

    A project-scope page is left out when no project is open. Its ``build`` is
    called with the project root as a third argument.
    """
    built: List[Tuple[SettingsPage, QWidget]] = []
    for page in registered_settings_pages():
        if page.scope == SCOPE_PROJECT and not project_root:
            continue
        try:
            if page.scope == SCOPE_PROJECT:
                widget = page.build(tabs, dict(payload), project_root)
            else:
                widget = page.build(tabs, dict(payload))
        except Exception:  # noqa: BLE001 - a feature page must never stop Settings from opening
            _LOGGER.exception("Settings page %r could not be built", page.key)
            continue
        tabs.addTab(widget, page.title)
        built.append((page, widget))
    return built


def apply_project_pages(built: List[Tuple[SettingsPage, QWidget]], project_root: str) -> str:
    """Write each project page once. The sentence of the first refusal, or ``""``.

    Pages after a refusal are not called.
    """

    for page, widget in built:
        if page.scope != SCOPE_PROJECT:
            continue
        try:
            result = page.apply(widget, project_root)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Settings page %r could not be applied", page.key)
            continue
        if isinstance(result, SettingsRefusal) and result.sentence:
            return result.sentence
    return ""


def apply_built_pages(built: List[Tuple[SettingsPage, QWidget]], payload: Mapping[str, Any]) -> Dict[str, Any]:
    """``payload`` with every global page's keys written, in tab order.

    Project-scope pages are skipped. They already ran inside the dialog.
    """
    result: Dict[str, Any] = dict(payload)
    for page, widget in built:
        if page.scope == SCOPE_PROJECT:
            continue
        try:
            written = page.apply(widget, dict(result))
        except Exception:  # noqa: BLE001 - a feature page must never stop the shell's save
            _LOGGER.exception("Settings page %r could not be applied", page.key)
            continue
        if isinstance(written, SettingsRefusal):
            _LOGGER.error("Settings page %r refused after the dialog closed: %s", page.key, written.sentence)
            continue
        result = dict(written)
    return result


__all__ = [
    "ApplyPage",
    "BuildPage",
    "SettingsPage",
    "SettingsRefusal",
    "SCOPE_GLOBAL",
    "SCOPE_PROJECT",
    "apply_built_pages",
    "apply_project_pages",
    "build_registered_pages",
    "register_settings_page",
    "registered_settings_pages",
    "unregister_settings_page",
]
