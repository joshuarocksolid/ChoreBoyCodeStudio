"""Dirty state and lazy XML for one form tab (CONTRACTS.md sections 8.4 and 11.2).

Qt-free. One ``CommandLog`` owns the document. This object is the shell's
``TabContentSource``. Visual mode serves the opened file text until the
document revision changes, then memoized ``write_ui`` text. XML mode serves
the text the user typed.
"""

from __future__ import annotations

from typing import Callable, Iterable, List, Literal, Optional, Set, Tuple

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import ReplaceDocument
from app.features.form_builder.engine.commands.log import CommandLog, SelectionSnapshot, Subscription
from app.features.form_builder.engine.diagnostics import DiagnosticsStore
from app.features.form_builder.engine.events import PRIORITY_SELECTION_NOTIFY
from app.features.form_builder.engine.ids import IdAllocator
from app.features.form_builder.engine.project.adoption import scope_for
from app.features.form_builder.engine.project.forms import FormScope, classify_form
from app.features.form_builder.engine.project.fs import OsFileSystem
from app.features.form_builder.engine.project.save import HandEdit, find_hand_edits
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.engine.ui4.writer import SerializationCache
from app.features.form_builder.integration.save_pipeline import SaveNotice, finish_save

Mode = Literal["visual", "xml"]


def open_document_log(text: str) -> CommandLog:
    """A command log for ``text``. Raises ``UiReadError`` when it will not parse."""
    allocator = IdAllocator()
    document = read_ui(text, allocator=allocator).document
    holder = {"snap": SelectionSnapshot((), None)}

    def provider() -> SelectionSnapshot:
        return holder["snap"]

    log = CommandLog(document, allocator, selection_provider=provider)

    def remember(_change_set: object) -> None:
        holder["snap"] = log.selection

    log.subscribe(remember, priority=PRIORITY_SELECTION_NOTIFY)
    return log


def form_scope(path: str, project_root: Optional[str]) -> FormScope:
    """Project and adopted forms generate. Anything else is external."""
    if project_root:
        return scope_for(path, project_root, OsFileSystem())
    return classify_form(path, project_root=None)


def plain_read_error(exc: BaseException) -> str:
    """Plain words for a reader or command refusal, with a line when one exists."""
    error = exc.error if isinstance(exc, CommandRejected) and exc.error is not None else exc
    message = str(exc)
    line = getattr(error, "line", 0)
    if isinstance(line, int) and line > 0:
        return f"{message} (line {line})"
    return message


class FormContentSource:
    """Visual mode by default. XML mode starts when View XML is shown.

    ``_saved_text`` is the last text written to disk. ``_applied_text`` is the
    last text the document actually parsed. A rejected XML save updates only
    the first, so Design still has to parse and an unchanged save does not
    push an undo step. ``_consent`` holds the hand edits the user agreed a save
    may overwrite, until a save overwrites their file.
    """

    def __init__(
        self,
        log: CommandLog,
        source_text: str,
        *,
        scope: Optional[FormScope] = None,
        diagnostics: Optional[DiagnosticsStore] = None,
    ) -> None:
        self._log = log
        self._scope = scope
        self._diagnostics = diagnostics
        self._notice = SaveNotice("idle", "", False)
        self._cache = SerializationCache()
        self._mode: Mode = "visual"
        self._source_text = source_text
        self._source_rev = log.document.revision
        self._saved_text = source_text
        self._applied_text = source_text
        self._saved_applied = True
        self._typed = ""
        self._stamp = log.document.revision
        self._listeners: List[Callable[[], None]] = []
        self._consent: Set[HandEdit] = set()
        self._subscription: Subscription = log.subscribe(self._on_log, priority=0)

    @property
    def log(self) -> CommandLog:
        return self._log

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def serialize_count(self) -> int:
        return self._cache.serialize_count

    def current_text(self) -> str:
        if self._mode == "xml":
            return self._typed
        if self._log.document.revision == self._source_rev:
            return self._source_text
        return self._cache.text(self._log.document)

    def is_dirty(self) -> bool:
        if self._mode == "xml" and self._typed != self._saved_text:
            return True
        if self._log.is_dirty():
            return True
        return not self._saved_applied

    def mark_saved(self, saved_text: str) -> None:
        self._saved_text = saved_text
        if self._mode == "xml":
            self._typed = saved_text
            if saved_text != self._applied_text:
                self._apply_saved_xml(saved_text)
            else:
                self._log.mark_saved()
                self._saved_applied = True
                self._remember_saved_text(saved_text)
        else:
            self._log.mark_saved()
            self._saved_applied = True
            self._remember_saved_text(saved_text)
        self._notice = SaveNotice("idle", "", False)
        self._notify()

    def after_save(self) -> None:
        """Step 3 of save. Reload and sync call ``mark_saved`` and stop there."""
        self._notice = finish_save(self._scope, self._log.document, self._saved_text)
        replaced = set(self._notice.files)
        self._consent = {edit for edit in self._consent if edit.path not in replaced}
        if self._diagnostics is not None:
            self._diagnostics.publish("codegen", self._notice.diagnostics)
        self._notify()

    def save_hold(self, unsaved_text: Callable[[str], Optional[str]]) -> Tuple[HandEdit, ...]:
        """Hand edits the next save would overwrite that the user has not agreed to replace.

        ``unsaved_text`` returns an open buffer's text when it has unsaved changes, else None.
        """
        scope = self._scope
        if scope is None or not scope.generates:
            return ()
        try:
            edits = find_hand_edits(scope, self._log.document, OsFileSystem(), unsaved_text)
        except OSError:
            # The save's own write then reports FB509 and replaces nothing.
            return ()
        return tuple(edit for edit in edits if edit not in self._consent)

    def replace_hand_edits(self, edits: Iterable[HandEdit]) -> None:
        """Let the next save overwrite exactly these edits."""
        self._consent.update(edits)

    def saved_text(self) -> str:
        """The text last marked as what is on disk."""
        return self._saved_text

    @property
    def save_notice(self) -> SaveNotice:
        return self._notice

    def set_scope(self, scope: Optional[FormScope]) -> None:
        self._scope = scope

    def revision(self) -> int:
        return self._stamp

    def subscribe_changed(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                return

        return unsubscribe

    def enter_xml_mode(self, shown_text: str) -> None:
        self._mode = "xml"
        self._applied_text = shown_text
        self._typed = shown_text

    def has_unapplied_xml(self) -> bool:
        """True in XML mode when the typed text differs from what the document last took."""
        return self._mode == "xml" and self._typed != self._applied_text

    def xml_text_changed(self, text: str) -> None:
        if self._mode != "xml" or text == self._typed:
            return
        self._typed = text
        self._stamp += 1
        self._notify()

    def leave_xml_mode(self) -> Optional[str]:
        """None when Design is showing again. Otherwise the parse error, and XML stays."""
        if self._mode != "xml":
            return None
        if self._typed == self._applied_text:
            self._mode = "visual"
            self._notify()
            return None
        try:
            self._log.execute(ReplaceDocument(self._typed, reason="xml_edit"))
        except CommandRejected as exc:
            return plain_read_error(exc)
        self._applied_text = self._typed
        self._mode = "visual"
        self._notify()
        return None

    def cancel_xml_mode(self) -> None:
        """Drop the XML buffer without a command. The document stays as it is."""
        if self._mode != "xml":
            return
        self._mode = "visual"
        self._typed = ""
        self._notify()

    def _apply_saved_xml(self, saved_text: str) -> None:
        try:
            self._log.execute(ReplaceDocument(saved_text, reason="xml_edit"))
        except CommandRejected:
            self._saved_applied = False
            return
        self._applied_text = saved_text
        self._log.mark_saved()
        self._saved_applied = True
        self._remember_saved_text(saved_text)

    def _remember_saved_text(self, saved_text: str) -> None:
        self._source_text = saved_text
        self._source_rev = self._log.document.revision

    def close(self) -> None:
        self._subscription.close()
        self._listeners.clear()

    def _on_log(self, _change_set: object) -> None:
        self._stamp += 1
        self._notify()

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()


__all__ = [
    "form_scope",
    "FormContentSource",
    "open_document_log",
    "plain_read_error",
]
