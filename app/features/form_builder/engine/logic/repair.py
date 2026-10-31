"""Broken formula, label, and step references after a rename or delete outside Code Studio.

The dialog that offers these fixes is M7.2b. This module only lists them.
A missing name whose old class has one or more new widgets of that class is a
fix. A missing name with no new widget of that class is not a fix: Problems
already reports it, and nothing is removed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Mapping, Tuple

from app.features.form_builder.engine.logic.formula.env import reserved_names
from app.features.form_builder.engine.logic.refs import formula_names, step_target_names
from app.features.form_builder.engine.logic.storage import FORMULA_KEYS, LABEL_KEYS, is_signal_property, text_kind
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import CStringValue, StringValue

_ASSIGNED = re.compile(r"self\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:QtWidgets\.)?([A-Za-z_][A-Za-z0-9_]*)\(")


@dataclass(frozen=True)
class RepairFix:
    """One stored name that no longer matches a widget, and the new widgets of its old class."""

    owner: str
    key: str
    missing: str
    candidates: Tuple[str, ...]


def widget_classes(source: str) -> Dict[str, str]:
    """Object name to class, from ``self.name = QtWidgets.Class(`` in a generated module."""
    found: Dict[str, str] = {}
    for name, class_name in _ASSIGNED.findall(source or ""):
        found[name] = class_name
    return found


def repair_references(doc: UiDocument, previous: Mapping[str, str]) -> Tuple[RepairFix, ...]:
    """``previous`` maps a name from the last generated module to its class.

    Names that are still on the form are left alone. Candidates are widgets of
    the missing name's old class that were not in ``previous``.
    """
    current: Dict[str, str] = {}
    try:
        widgets = tuple(doc.iter_widgets())
    except Exception:
        return ()
    for node in widgets:
        name = node.object_name or ""
        if name:
            current[name] = (node.class_name or "").rsplit(".", 1)[-1]
    fresh: Dict[str, List[str]] = {}
    for name, class_name in current.items():
        if name not in previous:
            fresh.setdefault(class_name, []).append(name)
    reserved = reserved_names()
    fixes: List[RepairFix] = []
    seen = set()
    for node in widgets:
        owner = node.object_name or ""
        if not owner:
            continue
        try:
            props = node.properties()
        except Exception:
            continue
        for entry in props:
            key = entry.name
            if not _is_reference_key(key):
                continue
            value = entry.value
            if not isinstance(value, (StringValue, CStringValue)):
                continue
            for missing in _mentions(key, value.text):
                if not missing or missing in current or missing in reserved:
                    continue
                identity = (owner, key, missing)
                if identity in seen:
                    continue
                seen.add(identity)
                old_class = previous.get(missing, "")
                candidates = tuple(fresh.get(old_class, ())) if old_class else ()
                if not candidates:
                    continue
                fixes.append(RepairFix(owner=owner, key=key, missing=missing, candidates=candidates))
    return tuple(fixes)


def _is_reference_key(key: str) -> bool:
    if key in FORMULA_KEYS or key in LABEL_KEYS:
        return True
    return is_signal_property(key)


def _mentions(key: str, text: str) -> Tuple[str, ...]:
    kind = text_kind(key)
    if kind == "formula":
        return formula_names(text)
    if kind == "label":
        name = text.strip()
        return (name,) if name else ()
    if kind == "steps":
        try:
            return step_target_names(text)
        except Exception:
            return ()
    return ()
