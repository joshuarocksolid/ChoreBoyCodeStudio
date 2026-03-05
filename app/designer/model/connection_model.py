"""Signal/slot connection model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectionModel:
    """Represents one Qt Designer `<connection>` mapping."""

    sender: str
    signal: str
    receiver: str
    slot: str

