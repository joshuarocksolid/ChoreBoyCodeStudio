"""Public codegen records. Split from ``api`` so the header module can share them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.diagnostics import FormDiagnostic

#: Bumped when generated output changes for the same input. Written in the header.
CODEGEN_VERSION = 1


@dataclass(frozen=True)
class CodegenOptions:
    """uic-flag equivalents (R3 322-330) that matter for Python, plus CBCS options.
    Stored in project settings (per-project default, per-form override) [M5.5b].

    ``connect_slots_by_name``: None follows the ``<ui connectslotsbyname>``
    attribute (default on); False is ``uic -a``.
    ``translate_function``: ``uic --tr``; default ``QCoreApplication.translate``.
    ``id_based``: ``uic --idbased``; None follows ``<ui idbasedtr>``.
    ``import_style``: ``uic --from-imports`` / ``--absolute-imports`` /
    ``--star-imports`` for resource modules; ``rc_prefix``: ``--rc-prefix``;
    ``python_paths``: ``--python-paths``.
    ``postfix``: ``uic --postfix`` appended to the ``Ui_`` class name.
    """

    connect_slots_by_name: Optional[bool] = None
    translate_function: Optional[str] = None
    id_based: Optional[bool] = None
    import_style: str = "plain"  # "plain" | "from" | "absolute" | "star"
    rc_prefix: bool = False
    python_paths: Tuple[str, ...] = ()
    postfix: str = ""


@dataclass(frozen=True)
class GeneratedHeader:
    """Parsed header of a generated file (see ``render_header``)."""

    codegen_version: int
    source_sha256: Optional[str]
    body_sha256: str


@dataclass(frozen=True)
class CodegenResult:
    """``text``: the whole ``ui_<name>.py`` (header + body), ``\\n`` newlines,
    trailing newline. ``text`` is None when generation was refused (an FB5xx
    Error in ``diagnostics``); the previous file on disk is then left alone.

    ``attribute_names``: every attribute ``setupUi`` sets on the Ui object, in
    creation order (widget, layout, spacer, action, button-group names): feeds
    Jedi completion of ``self.ui.<name>`` (pain 15, M1.4).
    ``resource_modules``: ``*_rc`` module names the file imports.
    ``uses_freecadgui``: the guarded FreeCADGui import is present.
    """

    text: Optional[str]
    diagnostics: Tuple[FormDiagnostic, ...]
    attribute_names: Tuple[str, ...]
    resource_modules: Tuple[str, ...]
    uses_freecadgui: bool
    header: Optional[GeneratedHeader]
