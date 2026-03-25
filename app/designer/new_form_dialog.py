"""New form dialog contract for Designer workflow (placeholder)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewFormRequest:
    """User selections for creating a new form."""

    form_class_name: str
    root_widget_class: str
    root_object_name: str

