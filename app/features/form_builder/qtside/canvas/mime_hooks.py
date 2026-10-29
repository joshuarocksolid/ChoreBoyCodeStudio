"""Other panes' drags over the canvas: a hook answers hover, drop and leave for its own MIME type.

The Actions section drags rows (UX-MAIN-009); the menu glue registers here and draws the
landing line. A hook gets viewport pixels and whether Ctrl is held.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, Tuple


class MimeHook(Protocol):
    def accepts(self, mime: object) -> bool: ...

    def hover(self, mime: object, at: Tuple[int, int], copy: bool) -> None: ...

    def drop(self, mime: object, at: Tuple[int, int], copy: bool) -> None: ...

    def leave(self) -> None: ...


_HOOKS: List[MimeHook] = []


def register_mime_hook(hook: MimeHook) -> None:
    if hook not in _HOOKS:
        _HOOKS.append(hook)


def unregister_mime_hook(hook: MimeHook) -> None:
    if hook in _HOOKS:
        _HOOKS.remove(hook)


def hook_for(mime: object) -> Optional[MimeHook]:
    for hook in _HOOKS:
        if hook.accepts(mime):
            return hook
    return None


def leave_all() -> None:
    for hook in tuple(_HOOKS):
        hook.leave()
