"""Resource reference model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceModel:
    """Represents one `<include>` in `.ui` `<resources>`."""

    location: str

