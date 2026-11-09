"""List-screen body on the left Data tab."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.qtside.data_panel.listing_page import ListingPage
from app.features.form_builder.qtside.data_panel.model import list_source
from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection


def _create(host: Any) -> ListingPage:
    return ListingPage(host)


def _applies(doc: Any) -> bool:
    return list_source(doc) is not None


def register(registry: Any) -> None:
    registry.add(PanelSection("listing", 25, _create, _applies))
