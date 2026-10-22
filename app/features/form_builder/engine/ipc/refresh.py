"""Decide whether a form edit is an UpdateForm or a full LoadForm.

CONTRACTS.md section 10.2: property patches are sent only for nodes whose
object name is unique in the document. A structural change, a rename, a
duplicate name, or a name that is missing becomes a full load. The caller
builds the message. This function only chooses the path.
"""

from __future__ import annotations

from typing import Literal, Sequence

RefreshKind = Literal["patch", "load"]


def select_form_refresh(
    *,
    names: Sequence[str],
    patched_names: Sequence[str],
    structural: bool,
) -> RefreshKind:
    """Return ``patch`` only when every patched name occurs exactly once."""
    if structural or not patched_names:
        return "load"
    counts = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    for name in patched_names:
        if counts.get(name, 0) != 1:
            return "load"
    return "patch"
