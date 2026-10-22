"""Object-name checks for generated Python (CONTRACTS.md section 9.3)."""

from __future__ import annotations

import keyword
from typing import Optional

# ``self`` cannot be the setupUi parameter: ``def setupUi(self, self)`` is a syntax error.
_RESERVED = frozenset({"setupUi", "retranslateUi", "self"})


def unusable_reason(name: str) -> Optional[str]:
    """None when ``name`` can be a generated attribute or parameter.

    Empty names are missing, not unusable: the emitter assigns one.
    """
    if not name:
        return None
    if not name.isidentifier() or keyword.iskeyword(name):
        return "not a Python name"
    if name in _RESERVED or name.startswith("_cbcs_") or name.startswith("cbcs_"):
        return "reserved"
    return None


def python_class_stem(text: str) -> str:
    """uic's ``Ui_`` stem. A C++ scope ``::`` becomes one underscore.

    ``Gui::Dialog::RemoteDebugger`` becomes ``Gui_Dialog_RemoteDebugger``.
    """
    return text.replace("::", "_")


def python_attr(text: str) -> str:
    """uic's Python attribute. Each colon becomes an underscore.

    ``Gui::Dialog::RemoteDebugger`` becomes ``Gui__Dialog__RemoteDebugger``.
    """
    return text.replace(":", "_")


def module_stem_ok(stem: str) -> bool:
    """True when a ``.ui`` stem can be a module name (``ui_<stem>``)."""
    if not stem or not stem.isidentifier() or keyword.iskeyword(stem):
        return False
    if stem in _RESERVED or stem.startswith("_cbcs_") or stem.startswith("cbcs_"):
        return False
    return True


def header_module(header: str) -> Optional[str]:
    """Designer header path to a Python module, or None when it isn't one.

    ``mypackage/widget.h`` becomes ``mypackage.widget``. A ``.h`` / ``.hpp`` /
    ``.hh`` suffix is stripped. Slashes and dots both separate module parts, so
    a header that is already ``shop.widgets.invoice_header`` stays that import.
    """
    text = header.strip().replace("\\", "/")
    if not text:
        return None
    lower = text.lower()
    for suffix in (".hpp", ".hh", ".h"):
        if lower.endswith(suffix):
            text = text[: -len(suffix)]
            break
    text = text.strip("/")
    if not text:
        return None
    parts = []
    for slash_part in text.split("/"):
        parts.extend(slash_part.split("."))
    if not parts or any(not part.isidentifier() or keyword.iskeyword(part) for part in parts):
        return None
    return ".".join(parts)
