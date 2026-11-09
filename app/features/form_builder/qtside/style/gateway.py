"""How an inspector row, a menu item or a Problems button opens the style sheet drawer.

The drawer belongs to the workbench (``integration/workbench_ext/style.py``
builds it and registers an opener here, keyed by the form's session). The rows
live in ``qtside`` and cannot import the workbench, so they ask this module.
"""

from __future__ import annotations

import weakref
from typing import Callable, Optional

from app.features.form_builder.engine.ids import NodeId

#: ``open(node_id)`` shows the drawer for that widget (None: the selection, or the form). Returns False when it could not open.
Opener = Callable[[Optional[NodeId]], bool]

_OPENERS: "weakref.WeakKeyDictionary[object, Opener]" = weakref.WeakKeyDictionary()


def register_opener(session: object, opener: Opener) -> None:
    _OPENERS[session] = opener


def forget_opener(session: object) -> None:
    _OPENERS.pop(session, None)


def open_drawer(session: object, node_id: Optional[NodeId] = None) -> bool:
    opener = _OPENERS.get(session)
    if opener is None:
        return False
    return bool(opener(node_id))
