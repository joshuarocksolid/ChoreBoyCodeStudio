"""FormSession: everything one open form owns (CONTRACTS.md section 3.7).

One session per editor tab. Two tabs never share a session, a document, a
command log or a selection. The clipboard is the only cross-form channel and it
carries XML text, never node objects or ids.
"""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.commands.log import CommandLog
from app.features.form_builder.engine.diagnostics import DiagnosticsStore
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.query.selection import SelectionModel
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.writer import SerializationCache


class FormSession:
    """Construction: ``FormSession.open(text, path=..., scope=...)`` reads the text
    (UiReadError propagates to the caller, who shows View XML), wires the log,
    selection and diagnostics, and publishes the reader's diagnostics.

    Disposal: ``dispose()`` closes every subscription; afterwards every method
    raises RuntimeError. The Qt side disposes the session when the tab closes.
    """

    @classmethod
    def open(cls, text: str, *, path: str, scope: FormScope) -> "FormSession":
        ...

    @property
    def path(self) -> str:
        ...

    @property
    def scope(self) -> FormScope:
        ...

    @property
    def document(self) -> UiDocument:
        ...

    @property
    def log(self) -> CommandLog:
        ...

    @property
    def selection(self) -> SelectionModel:
        ...

    @property
    def diagnostics(self) -> DiagnosticsStore:
        ...

    @property
    def serializer(self) -> SerializationCache:
        ...

    @property
    def allocator(self) -> IdAllocator:
        ...

    def text(self) -> str:
        """``serializer.text(document)``: the lazily serialized XML."""
        ...

    def logic_read_only(self) -> bool:
        """True when the document's ``cbcsLogic`` is newer than supported (FB402)."""
        ...

    def set_path(self, new_path: str, scope: Optional[FormScope] = None) -> None:
        """Rename/move of the file (not a document change)."""
        ...

    def dispose(self) -> None:
        ...
