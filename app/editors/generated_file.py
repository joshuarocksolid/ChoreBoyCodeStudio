"""Generated Python modules the shell opens read-only (UX-GEN-001..003).

The form builder does not have to be loaded. PySide2 still shows the banner.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

_HEADER_SOURCE = re.compile(r"^## Generated from (.+) by ChoreBoy Code Studio", re.MULTILINE)
_META_FRAGMENT = "/cbcs/form_builder/"


@dataclass(frozen=True)
class GeneratedBanner:
    """Copy and the two files the banner can open."""

    message: str
    source_path: str
    logic_path: str


def is_generated_python_path(path: str) -> bool:
    """``ui_<name>.py`` and ``*_rc.py``."""
    name = os.path.basename(path)
    if not name.endswith(".py"):
        return False
    return name.startswith("ui_") or name.endswith("_rc.py")


def is_form_builder_meta_path(path: str) -> bool:
    """``cbcs/form_builder/**`` is not user code."""
    normalized = path.replace("\\", "/")
    if not normalized.endswith("/"):
        normalized = normalized + "/"
    return _META_FRAGMENT in normalized or normalized.endswith("/cbcs/form_builder/")


def is_generated_module(path: str, text: str = "") -> bool:
    """Path pattern, the metadata tree, or a generated header."""
    if is_form_builder_meta_path(path) or is_generated_python_path(path):
        return True
    return bool(text) and _HEADER_SOURCE.search(text) is not None


def excluded_from_lint(path: str, text: str = "") -> bool:
    return is_generated_module(path, text)


def generated_banner(path: str, text: str = "") -> Optional[GeneratedBanner]:
    """The read-only banner, or None when this buffer is ordinary source."""
    if is_form_builder_meta_path(path):
        return None
    header_source = ""
    match = _HEADER_SOURCE.search(text) if text else None
    if match is not None:
        header_source = match.group(1).strip()
    if not is_generated_python_path(path) and not header_source:
        return None
    folder = os.path.dirname(path)
    name = os.path.basename(path)
    if name.endswith("_rc.py"):
        source_name = header_source or (name[: -len("_rc.py")] + ".qrc")
        source_path = source_name if os.path.isabs(source_name) else os.path.join(folder, source_name)
        message = (
            "Generated from %s. Code Studio rewrites this file every time the resources change."
            % os.path.basename(source_path)
        )
        return GeneratedBanner(message=message, source_path=source_path, logic_path="")
    stem = name[len("ui_") : -len(".py")] if name.startswith("ui_") and name.endswith(".py") else ""
    source_name = header_source or (stem + ".ui" if stem else "")
    if not source_name:
        return None
    source_path = source_name if os.path.isabs(source_name) else os.path.join(folder, os.path.basename(source_name))
    logic_name = os.path.splitext(os.path.basename(source_path))[0] + "_window.py"
    logic_path = os.path.join(os.path.dirname(source_path) or folder, logic_name)
    message = (
        "Generated from %s. Code Studio rewrites this file every time the form is saved. "
        "Put your code in %s."
        % (os.path.basename(source_path), os.path.basename(logic_path))
    )
    return GeneratedBanner(message=message, source_path=source_path, logic_path=logic_path)


__all__ = [
    "GeneratedBanner",
    "excluded_from_lint",
    "generated_banner",
    "is_form_builder_meta_path",
    "is_generated_module",
    "is_generated_python_path",
]
