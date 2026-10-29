"""FB033 and FB034 for the form's style sheets (UX-STYLE-005, UX-STYLE-008).

* FB033 (warning): a sheet Qt can't read. Qt ignores all of it; the file keeps the text as typed.
* FB034 (info): a rule that matches no widget in its scope. The form can still be saved.

Both are published as the ``style`` producer, coalesced to idle, and only
when the form has a style sheet at all.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from app.features.form_builder.engine.diagnostics import DiagnosticLocation, FormDiagnostic, Severity
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.style.selectors import StyleIndex, match_sheet
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.qtside.style.verdict import check_text
from app.qt.QtCore import QTimer

SOURCE = "style"
IDLE_MS = 250


def unreadable_message(name: str) -> str:
    return "The style sheet of %s can't be read, so Qt ignores all of it." % name


def no_match_message(selector: str) -> str:
    return "This rule matches nothing on the form: %s." % " ".join(selector.split())


def style_diagnostics(document: UiDocument) -> Tuple[FormDiagnostic, ...]:
    """One FB033 for each unreadable sheet and one FB034 for each rule with no match."""
    owners: List[Tuple[WidgetNode, str]] = []
    for node in document.iter_widgets():
        entry = node.prop("styleSheet")
        text = getattr(entry.value, "text", "") if entry is not None else ""
        if isinstance(text, str) and text.strip():
            owners.append((node, text))
    if not owners:
        return ()
    found: List[FormDiagnostic] = []
    index: Optional[StyleIndex] = None
    for node, text in owners:
        name = node.object_name or "widget"
        result = check_text(text)
        location = DiagnosticLocation(node_id=node.id, object_name=node.object_name, property="styleSheet")
        if not result.applies:
            found.append(FormDiagnostic("FB033", Severity.WARNING, unreadable_message(name), location, SOURCE))
            continue
        if index is None:
            index = StyleIndex(document)
        for match in match_sheet(index, node.id, result.sheet):
            if match.rule < 0 or (match.count > 0 and match.valid):
                continue
            rule_location = DiagnosticLocation(
                node_id=node.id,
                object_name=node.object_name,
                property="styleSheet",
                rule_path=(match.rule,),
                line=result.sheet.rules[match.rule].line,
            )
            found.append(
                FormDiagnostic("FB034", Severity.INFO, no_match_message(match.selector), rule_location, SOURCE)
            )
    return tuple(found)


class StyleProblems:
    """Keeps the ``style`` diagnostics of one session current."""

    def __init__(self, session: FormSession) -> None:
        self._session = session
        self._published: Tuple[FormDiagnostic, ...] = ()
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(IDLE_MS)
        self._timer.timeout.connect(self.publish)
        self._subscription = session.log.subscribe(self._changed, priority=950)
        self.publish()

    def dispose(self) -> None:
        try:
            self._timer.stop()
        except RuntimeError:
            # The tab's destroyed signal can arrive after Qt has deleted the timer at shutdown.
            pass
        self._subscription.close()

    def _changed(self, _change: object) -> None:
        self._timer.start()

    def publish(self) -> None:
        if self._session.disposed:
            return
        found = style_diagnostics(self._session.document)
        if found != self._published:
            self._published = found
            self._session.diagnostics.publish(SOURCE, found)
