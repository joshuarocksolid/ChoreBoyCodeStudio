"""UX-CAT-001 / "Your widgets": one entry per class the current form declares (per document)."""

from __future__ import annotations

import re
from typing import Callable, Optional, Sequence, Tuple

from app.features.form_builder.engine.project.custom_widgets import (
    RegistryEntry,
    declaration_spec,
    module_for_header,
)
from app.features.form_builder.engine.ui4.spec import Fragment
from app.features.form_builder.qtside.insert.catalog._build import declaration, fragment, widget
from app.features.form_builder.qtside.insert.catalog._model import WIDGET, Entry

CATEGORY = "Your widgets"
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+")


def derived_friendly(qt_class: str) -> str:
    """A friendly name from a class name the catalog does not know ("MyCard" -> "My card")."""
    local = qt_class.rsplit("::", 1)[-1]
    bare = local[1:] if local[:1] == "Q" and local[1:2].isupper() else local
    parts = [part.lower() for part in _CAMEL.findall(bare)] or [local.lower()]
    noun = " ".join(parts)
    return noun[:1].upper() + noun[1:]


def custom_entries(
    declarations: Sequence[Tuple[str, str, str]],
    registry: Sequence[RegistryEntry] = (),
) -> Tuple[Entry, ...]:
    """``declarations``: (class, base class, header) for each custom widget in the form.

    ``registry`` is the project's list of classes (UX-CUST-006). The form's own
    declarations come first; a registry class the form does not declare follows.
    A class whose header is a Python module is inserted with a local header,
    as the "Use my own class" popover writes it.
    """
    known = {item.class_name: item for item in registry}
    found = []
    seen = set()
    wanted = [(name, extends, header) for name, extends, header in declarations]
    wanted.extend((item.class_name, item.extends, item.header) for item in registry)
    for class_name, extends, header in wanted:
        if not class_name or class_name in seen:
            continue
        seen.add(class_name)
        local = class_name.rsplit("::", 1)[-1]
        object_name = local[:1].lower() + local[1:] if local else "customWidget"
        entry = known.get(class_name)
        module = module_for_header(header) if header else None
        if entry is None and module:
            entry = RegistryEntry(class_name, module, extends)
        description = entry.description if entry is not None and entry.description else ""
        found.append(
            Entry(
                "custom:" + class_name,
                derived_friendly(class_name),
                class_name,
                CATEGORY,
                object_name,
                description or "Your class %s, based on %s." % (class_name, extends),
                (),
                "custom",
                WIDGET,
                _builder(class_name, object_name, extends, header, entry),
                base_class=extends,
                header=header,
            )
        )
    return tuple(found)


def _builder(
    class_name: str, object_name: str, extends: str, header: str, entry: Optional[RegistryEntry] = None
) -> Callable[[], Fragment]:
    def build() -> Fragment:
        spec = declaration_spec(entry) if entry is not None else declaration(class_name, extends, header)
        return fragment(widget(class_name, object_name), customwidgets=(spec,))

    return build
