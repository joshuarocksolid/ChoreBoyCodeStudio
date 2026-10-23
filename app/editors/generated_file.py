"""Generated Python modules the shell opens read-only (UX-GEN-001..003).

A module is generated when it carries the Code Studio header or a sibling
form or resource file. A name like ``ui_helpers.py`` is ordinary source.
The form builder does not have to be loaded. PySide2 still shows the banner.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

_HEADER_SOURCE = re.compile(r"^## Generated from (.+) by ChoreBoy Code Studio", re.MULTILINE)
_META_FRAGMENT = "/cbcs/form_builder/"
_PEEK_CHARS = 512


@dataclass(frozen=True)
class GeneratedBanner:
    """Copy and the two files the banner can open."""

    message: str
    source_path: str
    logic_path: str


def is_form_builder_meta_path(path: str) -> bool:
    """``cbcs/form_builder/**`` is not user code."""
    normalized = path.replace("\\", "/")
    if not normalized.endswith("/"):
        normalized = normalized + "/"
    return _META_FRAGMENT in normalized or normalized.endswith("/cbcs/form_builder/")


def generated_source_basename(path: str, text: Optional[str] = None) -> str:
    """Sibling form or resource name, or empty when this is ordinary source.

    ``text is None`` reads the start of the file. An explicit string, including
    ``""``, does not.
    """
    if is_form_builder_meta_path(path):
        return ""
    header = _header_source(path, text)
    if header:
        return os.path.basename(header)
    sibling = _sibling_name(os.path.basename(path))
    if not sibling:
        return ""
    folder = os.path.dirname(path)
    sibling_path = os.path.join(folder, sibling) if folder else sibling
    if os.path.isfile(sibling_path):
        return sibling
    return ""


def is_generated_python_path(path: str) -> bool:
    """Path-only check. Peeks the file for a header or a sibling form."""
    return is_generated_module(path)


def is_generated_module(path: str, text: Optional[str] = None) -> bool:
    """True when ``generated_source_basename`` names a form or resource."""
    return bool(generated_source_basename(path, text))


def excluded_from_lint(path: str, text: str = "") -> bool:
    if is_form_builder_meta_path(path):
        return True
    return is_generated_module(path, text)


def generated_banner(path: str, text: str = "") -> Optional[GeneratedBanner]:
    """The read-only banner, or None when this buffer is ordinary source."""
    if is_form_builder_meta_path(path):
        return None
    source_name = generated_source_basename(path, text)
    if not source_name:
        return None
    folder = os.path.dirname(path)
    header = _header_source(path, text)
    if header:
        source_path = header if os.path.isabs(header) else os.path.join(folder, header)
    else:
        source_path = os.path.join(folder, source_name) if folder else source_name
    if source_name.endswith(".qrc"):
        message = (
            "Generated from %s. Code Studio rewrites this file every time the resources change."
            % os.path.basename(source_path)
        )
        return GeneratedBanner(message=message, source_path=source_path, logic_path="")
    logic_name = os.path.splitext(os.path.basename(source_path))[0] + "_window.py"
    logic_path = os.path.join(os.path.dirname(source_path) or folder, logic_name)
    message = (
        "Generated from %s. Code Studio rewrites this file every time the form is saved. "
        "Put your code in %s."
        % (os.path.basename(source_path), os.path.basename(logic_path))
    )
    return GeneratedBanner(message=message, source_path=source_path, logic_path=logic_path)


def _header_source(path: str, text: Optional[str]) -> str:
    sample = _peek(path) if text is None else text
    if not sample:
        return ""
    match = _HEADER_SOURCE.search(sample)
    if match is None:
        return ""
    return match.group(1).strip()


def _peek(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(_PEEK_CHARS)
    except OSError:
        return ""


def _sibling_name(name: str) -> str:
    if name.startswith("ui_") and name.endswith(".py") and len(name) > len("ui_") + len(".py"):
        return name[len("ui_") : -len(".py")] + ".ui"
    if name.endswith("_rc.py") and len(name) > len("_rc.py"):
        return name[: -len("_rc.py")] + ".qrc"
    return ""


__all__ = [
    "GeneratedBanner",
    "excluded_from_lint",
    "generated_banner",
    "generated_source_basename",
    "is_form_builder_meta_path",
    "is_generated_module",
    "is_generated_python_path",
]
