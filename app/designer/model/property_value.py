"""Property value model for Designer nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PropertyValue:
    """Represents one `.ui` property payload."""

    value_type: str
    value: Any

