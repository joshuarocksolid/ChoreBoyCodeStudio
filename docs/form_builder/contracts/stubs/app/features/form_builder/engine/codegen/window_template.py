"""The user-owned window class file (CONTRACTS.md section 9.5). [M1.4, M6.2]

Created once, never overwritten. After creation the builder only inserts empty
method stubs on request (and removes one on undo while it is still exactly the
text it inserted).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.ui4.document import UiDocument


def render_window_class(doc: UiDocument, *, scope: FormScope) -> str:
    """Initial ``<stem>_window.py``::

        from PySide6.QtWidgets import QDialog

        from forms.ui_invoice import Ui_Invoice


        class InvoiceWindow(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.ui = Ui_Invoice()
                self.ui.setupUi(self)

    Base class: the root's class, or a promoted root's ``extends``. Class name:
    ``<class>`` + ``Window``. Import is absolute from the project root
    (``scope.window_module_name``'s package); ``forms/__init__.py`` is created
    by the project layer if missing. Python 3.9-parseable.
    """
    ...


@dataclass(frozen=True)
class TextEdit:
    """Replace ``[start, end)`` (character offsets) of the file text with ``text``."""

    start: int
    end: int
    text: str


@dataclass(frozen=True)
class StubPlan:
    """``edit``: where to insert. ``stub_text``: exactly what is inserted; its
    sha256 is kept by the M6.2 compound command so undo removes the stub only
    while the method's current text still hashes the same."""

    edit: TextEdit
    stub_text: str
    method_name: str


def plan_stub(window_source: str, *, class_name: str, method_name: str,
              params: Tuple[str, ...], decorator: Optional[str]) -> StubPlan:
    """Pure: parse ``window_source`` with ``ast`` (never execute it), find the class,
    append the method after the last method with the file's indentation, ending
    in ``pass``. ValueError when the class is missing or the method exists."""
    ...
