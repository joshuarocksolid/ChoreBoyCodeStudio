"""The form tab's TabContentSource (CONTRACTS.md sections 8.4 and 11.2). [M2.2]

Qt-free (it only touches the engine), so dirty/serialization behaviour is unit
testable without a QApplication.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.features.form_builder.engine.session import FormSession


class FormContentSource:
    """Two modes:

    Visual mode (default):
      ``current_text()`` = ``session.text()`` (memoized by document revision).
      ``is_dirty()`` = ``session.log.is_dirty()``.
      ``revision()`` = ``session.document.revision``.

    XML mode (View XML is showing and the user typed in it):
      ``current_text()`` = the XML editor's text verbatim (Save in XML mode writes
      exactly what is typed, even if it does not parse; codegen is then skipped
      with FB001 on the Problems panel).
      ``is_dirty()`` = log dirty OR xml text differs from the text shown on entry.
      ``revision()`` increases on every XML edit.
      Leaving XML mode: unchanged text -> back to visual, nothing recorded;
      changed text that parses -> one ReplaceDocument("xml_edit"); changed text
      that does not parse -> stay in XML mode with the error banner, both the old
      document and the typed text kept.

    ``mark_saved(text)``: visual mode -> ``session.log.mark_saved()``; XML mode ->
    record ``text`` as the XML baseline and, if it parses, ReplaceDocument +
    ``mark_saved`` so the visual side matches disk.
    """

    def __init__(self, session: FormSession) -> None:
        ...

    def current_text(self) -> str:
        ...

    def is_dirty(self) -> bool:
        ...

    def mark_saved(self, saved_text: str) -> None:
        ...

    def revision(self) -> int:
        ...

    def subscribe_changed(self, listener: Callable[[], None]) -> Callable[[], None]:
        ...

    # ----------------------------------------------------- XML mode control
    def enter_xml_mode(self, shown_text: str) -> None:
        ...

    def xml_text_changed(self, text: str) -> None:
        ...

    def leave_xml_mode(self) -> Optional[str]:
        """Returns None on success, else the plain-word parse error (with line)."""
        ...
