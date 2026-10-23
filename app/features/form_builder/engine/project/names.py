"""Whether a new form stem can be a module name."""

from __future__ import annotations

import keyword
import os
import re
from typing import Optional

from app.features.form_builder.engine.codegen.names import module_stem_ok
from app.features.form_builder.engine.project.fs import OsFileSystem

#: Shown under the name field when the characters themselves are illegal.
NAME_PATTERN_MESSAGE = "Use letters, digits and _, starting with a letter."

_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def explain_form_name(name: str, *, folder: str, fs: OsFileSystem) -> Optional[str]:
    """Plain-words reason a stem or object-name prefix cannot be used, or None.

    The name has to be a Python identifier, not a keyword, not a ``ui_`` or
    ``cbcs_`` prefix, and not the name of a module already in ``folder``.
    Create and rename both call this before they write.
    """
    stem = name.strip()
    if not stem:
        return "A form needs a name."
    if stem.startswith("ui_"):
        return (
            'The name "%s" starts with ui_. That prefix is reserved for the generated module.'
            % stem
        )
    if stem.startswith("cbcs_") or stem.startswith("_cbcs"):
        return 'The name "%s" starts with cbcs_. That prefix is reserved.' % stem
    if keyword.iskeyword(stem):
        return 'The name "%s" is a Python keyword. Pick another name.' % stem
    if not stem.isidentifier() or not module_stem_ok(stem):
        if not stem.isidentifier():
            return (
                'The name "%s" is not a Python name. Use a letter or underscore, then letters, digits and underscores.'
                % stem
            )
        return 'The name "%s" is reserved. Pick another name.' % stem
    clash = _clash(folder, stem, fs)
    if clash is not None:
        return (
            "The folder already has %s. Pick a name that does not match an existing module."
            % clash
        )
    return None


def name_row_reason(name: str, *, folder: str, fs: OsFileSystem) -> Optional[str]:
    """Message under the New form name field, or None when the name can be created.

    Character-class failures use the Start screen sentence. Keywords, reserved
    prefixes and folder clashes keep the project-layer wording.
    """
    reason = explain_form_name(name, folder=folder, fs=fs)
    if reason is None:
        return None
    stem = name.strip()
    if stem and _NAME_PATTERN.fullmatch(stem) is None:
        return NAME_PATTERN_MESSAGE
    return reason


def unique_form_stem(folder: str, fs: OsFileSystem, base: str = "new_form") -> str:
    """``base``, or ``base_2``, ``base_3``, … until the folder can hold it."""
    if explain_form_name(base, folder=folder, fs=fs) is None:
        return base
    number = 2
    while number < 10000:
        candidate = "%s_%d" % (base, number)
        if explain_form_name(candidate, folder=folder, fs=fs) is None:
            return candidate
        number += 1
    return "%s_form" % base


def class_name_for_stem(stem: str) -> str:
    """``new_form`` becomes ``NewForm``. The ``<class>`` and root object name."""
    parts = [part for part in stem.split("_") if part]
    joined = "".join(part[:1].upper() + part[1:] for part in parts)
    return joined or "Form"


def creation_caption(folder_display: str, stem: str) -> str:
    """Live caption under the name row. ``folder_display`` may end in ``/``."""
    folder = folder_display.strip().strip("/") or "forms"
    leaf = stem.strip() or "new_form"
    return "Creates %s/%s.ui, ui_%s.py and %s_window.py." % (folder, leaf, leaf, leaf)


def _clash(folder: str, stem: str, fs: OsFileSystem) -> Optional[str]:
    for leaf in (stem + ".py", "ui_" + stem + ".py", stem + "_window.py", stem + ".ui"):
        if fs.is_file(os.path.join(folder, leaf)):
            return leaf
    for leaf in (stem, "ui_" + stem):
        if fs.is_dir(os.path.join(folder, leaf)):
            return leaf + "/"
    return None
