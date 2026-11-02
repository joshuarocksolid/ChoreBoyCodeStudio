"""Extra pages for the Settings dialog, registered by features.

A feature registers a page once (at import or install time)::

    register_settings_page(SettingsPage(key="form_builder", title="Form designer",
                                        build=make_page, apply=write_page))

The dialog adds one tab per registered page, in registration order, after its
own tabs.

* ``build(parent, payload)`` returns the page widget, filled from ``payload``:
  the global settings payload the dialog was opened with.
* ``apply(page, payload)`` is called after OK with the global payload the shell
  is about to save (re-read from disk and already holding the dialog's own
  values). It returns that payload with the page's keys written. The shell
  saves the result once, so a page never races the shell's own save.

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


def project_page_refusal(built: List[Tuple[SettingsPage, QWidget]], payload: Mapping[str, Any]) -> str:
    """The sentence a project-scope page refused with, or an empty string."""

    for page, widget in built:
        if page.scope != SCOPE_PROJECT:
            continue
        try:
            result = page.apply(widget, dict(payload))
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Settings page %r could not be checked", page.key)
            continue
        if isinstance(result, SettingsRefusal) and result.sentence:
            return result.sentence
    return ""


def apply_built_pages(built: List[Tuple[SettingsPage, QWidget]], payload: Mapping[str, Any]) -> Dict[str, Any]:
    """``payload`` with every built page's keys written, in tab order."""
    result: Dict[str, Any] = dict(payload)
    for page, widget in built:
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
    "build_registered_pages",
    "project_page_refusal",
    "register_settings_page",
    "registered_settings_pages",
    "unregister_settings_page",
]
