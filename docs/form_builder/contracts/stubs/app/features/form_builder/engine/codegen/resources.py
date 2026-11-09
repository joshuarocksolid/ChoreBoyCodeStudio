"""``.qrc`` -> ``*_rc.py`` and the in-editor resource tree (CONTRACTS.md section 9.3).
[M5.2]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from app.features.form_builder.engine.diagnostics import FormDiagnostic


@dataclass(frozen=True)
class QrcFile:
    """One ``<file alias="..">path</file>`` under a ``<qresource prefix=".." lang="..">``."""

    prefix: str
    path: str
    alias: Optional[str] = None
    lang: Optional[str] = None


@dataclass(frozen=True)
class QrcDocument:
    files: Tuple[QrcFile, ...]


def read_qrc(text: str) -> QrcDocument:
    """Same expat rules as the ui reader (no DOCTYPE). ValueError on bad input."""
    ...


@dataclass(frozen=True)
class ResourceTree:
    """The binary resource structure Qt's ``qRegisterResourceData`` accepts
    (format version 3): ``struct``, ``names``, ``data`` bytes. Files are stored
    uncompressed and with modification time 0, so output depends only on the
    file bytes (zlib versions differ between machines)."""

    version: int
    struct: bytes
    names: bytes
    data: bytes


def compile_resource_tree(
    qrc: QrcDocument,
    *,
    read_file: Callable[[str], bytes],
) -> Tuple[ResourceTree, Tuple[FormDiagnostic, ...]]:
    """Build the tree. ``read_file`` resolves a qrc-relative path (missing file:
    FB503 and the entry is skipped). Children are ordered exactly as rcc orders
    them (by Qt's name hash, then name) so lookup works."""
    ...


def render_rc_module(tree: ResourceTree, *, qrc_file_name: str) -> str:
    """``*_rc.py`` in the shape of ``rcc -g python`` (``qt_resource_data``,
    ``qt_resource_name``, ``qt_resource_struct``, ``qInitResources``,
    ``qCleanupResources``, ``from PySide6 import QtCore``) with the CBCS header
    (``render_header`` shape, no window line). Oracle: loading it registers the
    same paths with the same bytes as rcc's module (tree equality, not bytes)."""
    ...
