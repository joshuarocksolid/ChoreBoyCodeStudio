"""The canvas hook for files dropped from the desktop (M5.2 registers a handler here).

A handler is ``handler(session, target_id, paths) -> Optional[str]``. ``session``
is the form session of the canvas that got the drop (several forms can be open
and node ids repeat across documents, so a handler answers only for its own
session). ``target_id`` is the node under the pointer (the form's root when the
pointer is over the page itself),
``paths`` are the local file paths. A handler that took the files, or refused them,
returns the sentence to say; one that does not know these files returns None and
the next handler is asked. With no handler registered the canvas ignores files, as
it does today.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.ids import NodeId

FileDropHandler = Callable[[object, NodeId, Sequence[str]], Optional[str]]

_HANDLERS: List[FileDropHandler] = []


def register_file_drop(handler: FileDropHandler) -> Callable[[], None]:
    """Add ``handler``. The returned function removes it again."""
    _HANDLERS.append(handler)

    def unregister() -> None:
        if handler in _HANDLERS:
            _HANDLERS.remove(handler)

    return unregister


def has_handlers() -> bool:
    return bool(_HANDLERS)


def local_paths(mime: object) -> Tuple[str, ...]:
    """The local file paths a drag carries; empty when it carries none."""
    urls = getattr(mime, "urls", None)
    if urls is None or not getattr(mime, "hasUrls")():
        return ()
    found = []
    for url in urls():
        if url.isLocalFile():
            found.append(url.toLocalFile())
    return tuple(found)


def dispatch(session: object, target_id: NodeId, paths: Sequence[str]) -> Optional[str]:
    """Ask each handler in turn. The first answer wins (``""`` means handled, nothing to say)."""
    for handler in tuple(_HANDLERS):
        sentence = handler(session, target_id, tuple(paths))
        if sentence is not None:
            return sentence
    return None
