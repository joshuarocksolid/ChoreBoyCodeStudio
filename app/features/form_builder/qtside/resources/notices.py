"""Sentences for steps whose files are not on the undo stack (UX-M5-008, UX-RES-002).

"Add picture logo.png" writes a copied file and a ``.qrc`` first and the form
second. Undo takes back only the form part, so the toast has to say so. The
step's label is all the toast sees, so the editor records the sentence here
under that label and the toast asks for it with ``sentence_for``.
"""

from __future__ import annotations

from typing import Dict, Optional

_LIMIT = 16
_BY_LABEL: Dict[str, str] = {}


def remember(label: str, sentence: str) -> None:
    """Keep ``sentence`` for the step named ``label`` (the last sentence wins)."""
    _BY_LABEL.pop(label, None)
    _BY_LABEL[label] = sentence
    while len(_BY_LABEL) > _LIMIT:
        _BY_LABEL.pop(next(iter(_BY_LABEL)))


def sentence_for(label: str) -> Optional[str]:
    """The sentence recorded for ``label``, or None."""
    return _BY_LABEL.get(label)


def forget_all() -> None:
    _BY_LABEL.clear()


__all__ = ["forget_all", "remember", "sentence_for"]
