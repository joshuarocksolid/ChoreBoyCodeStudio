"""Verbatim XML preserved for unknown content (CONTRACTS.md section 2.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Union


@dataclass(frozen=True)
class OpaqueElement:
    """An element subtree kept exactly as parsed.

    ``attrs`` keeps input order. ``children`` interleaves ``OpaqueElement`` and
    ``str`` text runs in input order, including whitespace-only runs inside
    mixed content. Comments and processing instructions inside a preserved
    subtree are kept as ``OpaqueComment``/``OpaquePI``. Comments outside any
    preserved subtree are dropped (Designer drops them too).
    """

    tag: str
    attrs: Tuple[Tuple[str, str], ...] = ()
    children: Tuple["OpaqueChild", ...] = ()


@dataclass(frozen=True)
class OpaqueComment:
    text: str


@dataclass(frozen=True)
class OpaquePI:
    target: str
    data: str


OpaqueChild = Union[OpaqueElement, OpaqueComment, OpaquePI, str]
