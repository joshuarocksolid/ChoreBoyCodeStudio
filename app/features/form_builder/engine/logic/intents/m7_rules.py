"""Rule intents for toggled → setEnabled / setVisible (UX E6). The write is not a step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

from app.features.form_builder.engine.logic.intents import Intent


@dataclass(frozen=True)
class Steer:
    key: str
    intent_id: str
    words: str


_ENABLE = Steer("cbcsEnabledWhen", "enable-only-when", "Enable {target} only when…")
_SHOW = Steer("cbcsVisibleWhen", "show-only-when", "Show {target} only when…")
_SENDERS = ("QCheckBox", "QRadioButton")


def steer_for(signal: str, slot: str) -> Optional[Steer]:
    """The rule a ``toggled`` slot should offer, or None."""
    if signal != "toggled":
        return None
    text = slot.strip()
    if text.startswith("setEnabled"):
        return _ENABLE
    if text.startswith("setVisible"):
        return _SHOW
    return None


def _no_steps(_sender: str, _target: Optional[str]) -> Tuple[Mapping[str, Any], ...]:
    return ()


def register(registry: object) -> None:
    add = getattr(registry, "add", None)
    if add is None:
        return
    for steer in (_ENABLE, _SHOW):
        add(
            Intent(
                steer.intent_id,
                steer.words,
                _no_steps,
                sender_classes=_SENDERS,
                event="toggled",
                needs_target=True,
            )
        )
