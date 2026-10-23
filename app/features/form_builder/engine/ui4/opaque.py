"""Verbatim XML preserved for unknown content (CONTRACTS.md section 2.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple, Union


@dataclass(frozen=True)
class OpaqueElement:
    """An element subtree kept exactly as parsed.

    ``attrs`` keeps input order. ``children`` interleaves ``OpaqueElement`` and
    ``str`` text runs in input order, including whitespace-only runs inside
    mixed content. Comments and processing instructions inside a preserved
    subtree are kept as ``OpaqueComment``/``OpaquePI``. Comments outside any
    preserved subtree are dropped (Designer drops them too).

    An empty ``tag`` is an internal text carrier used when a known element has
    non-whitespace text between its children. The writer emits the text and no
    wrapper element.

    ``line`` is the 1-based source line of the start tag, or 0 when the element
    was not read from text. It is not content: equality and hashing ignore it.
    """

    tag: str
    attrs: Tuple[Tuple[str, str], ...] = ()
    children: Tuple["OpaqueChild", ...] = ()
    line: int = field(default=0, compare=False, repr=False)


@dataclass(frozen=True)
class OpaqueComment:
    text: str


@dataclass(frozen=True)
class OpaquePI:
    target: str
    data: str


OpaqueChild = Union[OpaqueElement, OpaqueComment, OpaquePI, str]
