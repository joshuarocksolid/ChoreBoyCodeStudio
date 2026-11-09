"""What a command would write onto live objects, for a preview that never touches the document.

The preview is derived from the commands a release would commit, so the two
cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from app.features.form_builder.engine.commands.base import Command
from app.features.form_builder.engine.commands.catalog import SetGeometry, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.sizing import ApplySizing
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.values import Value

PropKey = Tuple[NodeId, str]


@dataclass(frozen=True)
class LiveProp:
    """One value shown on a live object. ``value`` None shows the default a deleted property gets."""

    owner: NodeId
    name: str
    value: Optional[Value]

    @property
    def key(self) -> PropKey:
        return (self.owner, self.name)


def live_props(commands: Sequence[Command]) -> Tuple[LiveProp, ...]:
    """SetProperty, ApplySizing and SetGeometry preview. Every other command waits for release."""
    found: List[LiveProp] = []
    for command in commands:
        if isinstance(command, SetProperty) and command.kind == "property":
            found.append(LiveProp(command.owner, command.name, command.value))
        elif isinstance(command, ApplySizing):
            if command.touch_policy:
                found.append(LiveProp(command.owner, "sizePolicy", command.policy))
            if command.touch_minimum:
                found.append(LiveProp(command.owner, "minimumSize", command.minimum))
            if command.touch_maximum:
                found.append(LiveProp(command.owner, "maximumSize", command.maximum))
        elif isinstance(command, SetGeometry):
            found.append(LiveProp(command.id, "geometry", command.rect))
    return tuple(found)
