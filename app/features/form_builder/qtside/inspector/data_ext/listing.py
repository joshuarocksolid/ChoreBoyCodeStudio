"""List-screen settings on the inspector Data tab."""

from __future__ import annotations

from app.features.form_builder.qtside.data_panel.listing_page import ListingPage
from app.features.form_builder.qtside.inspector.data_ext import DataSection
from app.qt.QtWidgets import QWidget


def _create(parent: QWidget) -> QWidget:
    return ListingPage(parent)


def _applies(class_name: str) -> bool:
    return class_name == "@form"


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if not callable(add):
        return
    add(DataSection("listing", 16, _create, _applies))
