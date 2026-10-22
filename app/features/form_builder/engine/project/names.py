"""Whether a new form stem can be a module name."""

from __future__ import annotations

import keyword
import os
from typing import Optional

from app.features.form_builder.engine.codegen.names import module_stem_ok
from app.features.form_builder.engine.project.fs import OsFileSystem


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


def _clash(folder: str, stem: str, fs: OsFileSystem) -> Optional[str]:
    for leaf in (stem + ".py", "ui_" + stem + ".py", stem + "_window.py", stem + ".ui"):
        if fs.is_file(os.path.join(folder, leaf)):
            return leaf
    for leaf in (stem, "ui_" + stem):
        if fs.is_dir(os.path.join(folder, leaf)):
            return leaf + "/"
    return None
