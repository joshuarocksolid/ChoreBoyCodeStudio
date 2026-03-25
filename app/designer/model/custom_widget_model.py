"""Custom widget promote metadata model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CustomWidgetModel:
    """Represents one promoted widget registration in `.ui`."""

    class_name: str
    extends: str
    header: str
