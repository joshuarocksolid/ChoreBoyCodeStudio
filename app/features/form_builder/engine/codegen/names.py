"""Object-name checks for generated Python (CONTRACTS.md section 9.3)."""

from __future__ import annotations

import keyword
import re
import unicodedata
from typing import Optional

# C++ identifier, optionally scoped. ASCII only: a Unicode lookalike is not a
# Python name we can emit, and it is not a token we can paste into source.
_CPP_NAME = re.compile(r"[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*\Z", re.ASCII)
_UI_BASENAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\.ui\Z")

# ``self`` cannot be the setupUi parameter: ``def setupUi(self, self)`` is a syntax error.
_RESERVED = frozenset({"setupUi", "retranslateUi", "self"})


def check_cpp_name(text: str) -> bool:
    """True when ``text`` is a C++ name safe to paste into generated Python.

    ``Gui::Dialog::RemoteDebugger`` matches. A call, a quote, or a space does not.
    Neither does a Python keyword in any part: ``Qt::None`` becomes ``Qt.None``,
    which does not parse.
    """
    if not text or _CPP_NAME.fullmatch(text) is None:
        return False
    return not any(keyword.iskeyword(part) for part in text.split("::"))


def check_py_attr(text: str) -> bool:
    """True when ``text`` can follow a dot in generated Python: no ``::``, no keyword."""
    return check_cpp_name(text) and "::" not in text


def check_enum_set(text: str) -> bool:
    """True for ``0``, an empty set, or ``|``-separated C++ names."""
    raw = text.strip()
    if raw == "" or raw == "0":
        return True
    for piece in raw.split("|"):
        token = piece.strip()
        if not token or token == "0":
            continue
        if not check_cpp_name(token):
            return False
    return True


def ui_basename_ok(basename: str) -> bool:
    """True when the ``.ui`` file name is ``<identifier>.ui`` and the stem can be a module."""
    if _UI_BASENAME.fullmatch(basename) is None:
        return False
    return module_stem_ok(basename[:-3])


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
    The stem is NFKC, so a compatibility character cannot spell a second class.
    """
    return unicodedata.normalize("NFKC", text).replace("::", "_")


def python_attr(text: str) -> str:
    """uic's Python attribute. Each colon becomes an underscore.

    ``Gui::Dialog::RemoteDebugger`` becomes ``Gui__Dialog__RemoteDebugger``.
    NFKC runs first, so ``ﬁx`` and ``fix`` share one spelling before the
    uniqueness suffix is chosen.
    """
    return unicodedata.normalize("NFKC", text).replace(":", "_")


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
