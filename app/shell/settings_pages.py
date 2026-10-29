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
from typing import Any, Callable, Dict, List, Mapping, Tuple

from app.qt.QtWidgets import QTabWidget, QWidget

_LOGGER = logging.getLogger(__name__)

BuildPage = Callable[[QWidget, Mapping[str, Any]], QWidget]
ApplyPage = Callable[[QWidget, Dict[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class SettingsPage:
    key: str
    title: str
    build: BuildPage
    apply: ApplyPage


_PAGES: Dict[str, SettingsPage] = {}


def register_settings_page(page: SettingsPage) -> None:
    _PAGES[page.key] = page


def unregister_settings_page(key: str) -> None:
    _PAGES.pop(key, None)


def registered_settings_pages() -> Tuple[SettingsPage, ...]:
    return tuple(_PAGES.values())


def build_registered_pages(tabs: QTabWidget, payload: Mapping[str, Any]) -> List[Tuple[SettingsPage, QWidget]]:
    """Add a tab for every registered page; returns the pages that built."""
    built: List[Tuple[SettingsPage, QWidget]] = []
    for page in registered_settings_pages():
        try:
            widget = page.build(tabs, dict(payload))
        except Exception:  # noqa: BLE001 - a feature page must never stop Settings from opening
            _LOGGER.exception("Settings page %r could not be built", page.key)
            continue
        tabs.addTab(widget, page.title)
        built.append((page, widget))
    return built


def apply_built_pages(built: List[Tuple[SettingsPage, QWidget]], payload: Mapping[str, Any]) -> Dict[str, Any]:
    """``payload`` with every built page's keys written, in tab order."""
    result: Dict[str, Any] = dict(payload)
    for page, widget in built:
        try:
            result = dict(page.apply(widget, dict(result)))
        except Exception:  # noqa: BLE001 - a feature page must never stop the shell's save
            _LOGGER.exception("Settings page %r could not be applied", page.key)
    return result


__all__ = [
    "ApplyPage",
    "BuildPage",
    "SettingsPage",
    "apply_built_pages",
    "build_registered_pages",
    "register_settings_page",
    "registered_settings_pages",
    "unregister_settings_page",
]
