"""Form tab: workbench, Design | XML, history, and the save notice.

One tab owns one ``FormSession``. Closing the tab disposes that session.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Sequence, Tuple

from app.qt.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from app.qt.QtGui import QKeySequence
from app.qt.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTreeWidget,
    QShortcut,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import wrapper_is_valid

from app.editors.code_editor_widget import CodeEditorWidget
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import ReplaceDocument
from app.features.form_builder.engine.commands.log import Subscription
from app.features.form_builder.engine.events import PRIORITY_VIEWS
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.layout_actions import (
    Current,
    Done,
    OfferSheet,
    OpenWrap,
    PickWrap,
    Refused,
    gate,
    offers,
    request_for,
    transact,
)
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.shell_commands import (
    FORM_COMMANDS,
    INERT_SHORTCUTS,
    INERT_STATUS,
    is_widget_shortcut,
    normalize_form_shortcut,
)
from app.features.form_builder.engine.ui4.reader import UiReadError, kept_as_is_spans, read_ui
from app.features.form_builder.integration.chrome_text import (
    external_change_sentence,
    mixed_parent_sentence,
    recovered_draft_sentence,
    selection_sentence,
    status_sentence,
    undo_menu_text,
)
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.engine.clipboard import command_enabled
from app.features.form_builder.integration.clipboard_actions import (
    SHORTCUT_COMMAND_IDS,
    apply_command,
    clipboard_has_fragment,
)
from app.features.form_builder.integration.context_menu import add_clipboard_actions, fill_context_menu, paint_menu
from app.features.form_builder.integration.popover import ProblemPopover, open_layout_menu, tree_contains
from app.features.form_builder.integration.problems_bridge import code_diagnostics_for_form
from app.features.form_builder.integration.content_source import (
    FormContentSource,
    form_scope,
    plain_read_error,
)
from app.features.form_builder.integration.layout import (
    TOOLBAR_HEIGHT,
    LayoutPlan,
    WorkbenchMemory,
    plan_workbench,
)
from app.features.form_builder.integration.memory import WorkbenchMemoryStore
from app.features.form_builder.integration.pieces import SavedPieceStore
from app.features.form_builder.integration.run_action import run_open_form
from app.features.form_builder.integration.toast import (
    CommandToast,
    ToastNote,
    names_from_entry,
    notice_sentence,
    undo_matches,
)
from app.features.form_builder.integration.workbench import FormToolbar, FormWorkbench, NoticeBar
from app.features.form_builder.integration.wrap_popover import WrapPopover
from app.features.form_builder.qtside.canvas.core.gesture import EditTextAsked, ZoomAsked
from app.features.form_builder.qtside.canvas.core.structure import effective_selection
from app.features.form_builder.qtside.canvas.core.text import enter_opens_editor
from app.features.form_builder.qtside.canvas.core.words import hover_sentence
from app.features.form_builder.qtside.canvas.core.space import ZoomFit, ZoomStep, ZoomTo
from app.features.form_builder.qtside.layout_gestures import ask, beside, measure, perform, properties_for
from app.features.form_builder.qtside.realize.api import Realizer
from app.intelligence.diagnostics_models import CodeDiagnostic
from app.shell.tab_content_providers import RestoreReason, TabSurfaceRequest
from app.shell.theme_tokens import ShellThemeTokens

XML_APPLY_HINT = "Edits here apply to the design when you switch back."
XML_DISCARD_LABEL = "Discard XML edits"
VIEW_XML_TOOLTIP = "View XML (Ctrl+Shift+V)"

_RESTORE_REASON = {
    "draft": "draft",
    "history": "history",
    "external_reload": "reload",
}
_SAVED_FADE_MS = 4000
_KEPT_REFRESH_MS = 300


def plain_banner_error(error: str) -> str:
    """``Line 42: the tag is not closed. Fix it, or`` (then the Discard button) when a line is known."""
    message = error.strip()
    line = ""
    marker = " (line "
    if message.endswith(")") and marker in message:
        message, _, tail = message.rpartition(marker)
        line = tail[:-1].strip()
    message = message.strip().rstrip(".")
    if message:
        message = message[0].lower() + message[1:]
    if line:
        # The Discard XML edits button beside this text is the "or".
        return "Line %s: %s. Fix it, or" % (line, message)
    if not message:
        return error
    return message[0].upper() + message[1:] + "."


_RENAME_ACTION = "shell.action.edit.renameSymbol"
# Window actions on Ctrl+1 and Ctrl+2. While either is enabled, the canvas
# shortcut on the same key is ambiguous and neither fires.
_EDITOR_GROUP_ACTIONS = (
    "shell.action.view.focusFirstEditorGroup",
    "shell.action.view.focusSecondEditorGroup",
)


def _shell_registry(window: QWidget) -> object:
    """``menu_registry`` is a property on MainWindow and a method on test doubles."""
    registry_fn = getattr(window, "menu_registry", None)
    if registry_fn is None:
        return None
    return registry_fn() if callable(registry_fn) else registry_fn


def _silence(window: QWidget, holder: object, action_ids: Tuple[str, ...]) -> None:
    """Force shell actions off for ``holder``. Each keeps the flag it had before the first silence."""
    registry = _shell_registry(window)
    if registry is None:
        return
    held = _silenced(window)
    for action_id in action_ids:
        action = registry.action(action_id)  # type: ignore[attr-defined]
        if action is None:
            continue
        prior = held[action_id][0] if action_id in held else bool(action.isEnabled())
        held[action_id] = (prior, holder)
        action.setEnabled(False)


def _restore(window: QWidget, holder: object, action_ids: Tuple[str, ...]) -> None:
    """Give back the actions ``holder`` silenced. Another holder's silence stays."""
    held = _silenced(window)
    registry = _shell_registry(window)
    for action_id in action_ids:
        entry = held.get(action_id)
        if entry is None or entry[1] is not holder:
            continue
        del held[action_id]
        action = None if registry is None else registry.action(action_id)  # type: ignore[attr-defined]
        if action is not None:
            action.setEnabled(entry[0])


def _silenced(window: QWidget) -> Dict[str, Tuple[bool, object]]:
    held = getattr(window, "_form_silenced", None)
    if not isinstance(held, dict):
        held = {}
        window._form_silenced = held  # type: ignore[attr-defined]
    return held


def _outline_mode(change_set: object) -> str:
    if getattr(change_set, "replaced", False):
        return "rebuild"
    if (
        getattr(change_set, "structure_dirty", ())
        or getattr(change_set, "added", ())
        or getattr(change_set, "removed", ())
    ):
        return "rebuild"
    if getattr(change_set, "renamed", ()):
        return "patch"
    return "keep"


def _shell_history(window: QWidget, redo: bool) -> None:
    surface = getattr(window, "_form_undo_surface", None)
    if not isinstance(surface, FormSurface):
        return
    if redo:
        surface.redo()
    else:
        surface.undo()


def _key_text(event: object) -> str:
    """Portable text of a key event, with Backtab spelled Shift+Tab."""
    key = int(getattr(event, "key")())
    mods = getattr(event, "modifiers")()
    shift = getattr(Qt, "ShiftModifier")
    if key == int(getattr(Qt, "Key_Backtab")):
        key = int(getattr(Qt, "Key_Tab"))
        mods = mods | shift
    flags = getattr(mods, "value", mods)
    try:
        sequence = QKeySequence(int(flags) | key)
    except TypeError:
        return ""
    return normalize_form_shortcut(sequence.toString(QKeySequence.SequenceFormat.PortableText))


class _ShellKeyGuard(QObject):
    """Keeps shell window keys that mean nothing here off the builder chrome.

    Installed on the workbench and toolbar widgets, never on the XML editor.
    Accepting ``ShortcutOverride`` sends an inert key (Ctrl+H, Ctrl+G, ...) to
    the focused widget instead of a window action; its key press is then
    swallowed and the status bar says it is not used (UX-KEY-004). The shell
    keeps Tab and Shift+Tab out of window actions outside code editors.

    The shell also binds the inert keys, so a QShortcut of the same key would
    be ambiguous and fire nothing.
    """

    def __init__(
        self,
        inert_keys: frozenset,
        on_inert: Callable[[], None],
        parent: QObject,
    ) -> None:
        super().__init__(parent)
        self._inert_keys = inert_keys
        self._on_inert = on_inert
        self._pending = ""

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802
        del watched
        kind = getattr(event, "type")()
        if kind == QEvent.Type.ShortcutOverride:
            text = _key_text(event)
            if text in self._inert_keys:
                self._pending = text
                getattr(event, "accept")()
                return True
            return False
        if kind == QEvent.Type.KeyPress and self._pending:
            text = _key_text(event)
            if text == self._pending:
                self._pending = ""
                getattr(event, "accept")()
                self._on_inert()
                return True
        return False


class FormSurface(QWidget):
    """``TabSurface`` for one ``.ui`` tab."""

    @property
    def session(self) -> FormSession:
        return self._session

    def __init__(
        self,
        request: TabSurfaceRequest,
        session: FormSession,
        source: FormContentSource,
    ) -> None:
        super().__init__(request.parent)
        self._request = request
        self._session = session
        self._source = source
        self._path = request.file_path
        self._editor: Optional[CodeEditorWidget] = None
        self._released = False
        self._tokens = request.theme
        self._banner_is_error = False
        self._save_faded = True
        self._tab_widget: Optional[QTabWidget] = None
        self._store: Optional[WorkbenchMemoryStore] = None
        self._pieces: Optional[SavedPieceStore] = None
        self._plan = plan_workbench(0, 0, WorkbenchMemory())
        self._preview_request: Optional[str] = None
        self._preview_listener: Optional[Callable[[str], None]] = None
        self.setObjectName("formBuilder.surface")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._notice = NoticeBar(self)
        layout.addWidget(self._notice)

        self._toolbar = FormToolbar(
            self,
            on_design=self._on_design,
            on_xml=self._on_xml_toggled,
            on_undo=self._toolbar_undo,
            on_redo=self._toolbar_redo,
            on_zoom_out=self.zoom_out,
            on_zoom_in=self.zoom_in,
            on_zoom_to=self.zoom_to,
            on_zoom_fit=self.zoom_fit,
        )
        self._toolbar.setFixedHeight(TOOLBAR_HEIGHT)
        layout.addWidget(self._toolbar)

        self._banner_frame = QFrame(self)
        self._banner_frame.setObjectName("formBuilder.xmlBanner")
        banner_row = QHBoxLayout(self._banner_frame)
        banner_row.setContentsMargins(8, 4, 4, 4)
        self._banner = QLabel(self._banner_frame)
        self._banner.setObjectName("formBuilder.xmlBannerText")
        self._banner.setAccessibleName("XML notice")
        self._banner.setWordWrap(True)
        banner_row.addWidget(self._banner, 1)
        self._discard = QPushButton(XML_DISCARD_LABEL, self._banner_frame)
        self._discard.setObjectName("formBuilder.discardXml")
        self._discard.setFocusPolicy(getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus"))
        self._discard.clicked.connect(self._discard_xml)
        self._discard.hide()
        banner_row.addWidget(self._discard, 0, Qt.AlignmentFlag.AlignTop)
        self._banner_frame.hide()
        layout.addWidget(self._banner_frame)

        self._stack = QStackedWidget(self)
        self._realizer = Realizer(session)
        self._workbench = FormWorkbench(
            session,
            self._realizer,
            self._on_outline_pick,
            self._pin_left,
            self._pin_inspector,
            self._remember_widths,
            self._remember_collapsed,
            self,
            self._stack,
        )
        self._stack.addWidget(self._workbench)
        layout.addWidget(self._stack, 1)
        self._toolbar.attach_preview(self._workbench.canvas.preview)
        self._command_toast = CommandToast(self)
        self._problem_popover = ProblemPopover(self)
        self._layout_popover: Optional[QWidget] = None
        self._context_menu: Optional[QMenu] = None
        self._toast_held = False

        self._load_memory()
        self._changes: Subscription = session.log.subscribe(self._on_log, priority=PRIORITY_VIEWS)
        self._selection_unsub = session.selection.subscribe(self._on_selection)
        self._source_unsub = source.subscribe_changed(self._on_source_changed)
        self._inert_note = ""
        self._gesture_sentence = ""
        self._overlay_sentence = ""
        self._hover_sentence = ""
        self._problem_timer = QTimer(self)
        self._problem_timer.setSingleShot(True)
        self._problem_timer.timeout.connect(self._flush_problems)
        self._diagnostics_unsub = session.diagnostics.subscribe(self._schedule_problems)
        source.set_open_buffer_probe(self._open_buffer_state)
        self._install_widget_shortcuts()
        self._schedule_problems(())
        self._saved_timer = QTimer(self)
        self._saved_timer.setSingleShot(True)
        self._saved_timer.timeout.connect(self._fade_saved)
        # XML edits move lines. Read the shown text again once typing pauses.
        self._kept_timer = QTimer(self)
        self._kept_timer.setSingleShot(True)
        self._kept_timer.setInterval(_KEPT_REFRESH_MS)
        self._kept_timer.timeout.connect(self._refresh_kept_lines)
        self._alt_outline = QShortcut(QKeySequence("Alt+1"), self)
        self._alt_outline.setContext(getattr(Qt, "WidgetWithChildrenShortcut"))
        self._alt_outline.activated.connect(self._focus_outline)
        self._alt_insert = QShortcut(QKeySequence("Alt+2"), self)
        self._alt_insert.setContext(getattr(Qt, "WidgetWithChildrenShortcut"))
        self._alt_insert.activated.connect(self._focus_insert)
        self._alt_canvas = QShortcut(QKeySequence("Alt+3"), self)
        self._alt_canvas.setContext(getattr(Qt, "WidgetWithChildrenShortcut"))
        self._alt_canvas.activated.connect(self._focus_canvas)
        self._alt_inspector_key = QShortcut(QKeySequence("Alt+4"), self)
        self._alt_inspector_key.setContext(getattr(Qt, "WidgetWithChildrenShortcut"))
        self._alt_inspector_key.activated.connect(self._focus_inspector_pane)
        self._rename_key = QShortcut(QKeySequence("F2"), self)
        self._rename_key.setContext(getattr(Qt, "WidgetWithChildrenShortcut"))
        self._rename_key.activated.connect(self._rename_inert)
        self._widths_key = QShortcut(QKeySequence("Ctrl+K, W"), self)
        self._widths_key.setContext(getattr(Qt, "WidgetWithChildrenShortcut"))
        self._widths_key.activated.connect(self._workbench.canvas.preview.toggle_widths)
        self._esc = QShortcut(QKeySequence("Esc"), self)
        self._esc.setContext(getattr(Qt, "WidgetWithChildrenShortcut"))
        self._esc.setEnabled(False)
        self._esc.activated.connect(self._workbench.close_drawers)
        # The Menu key arrives as a context menu event. Qt does not turn Shift+F10 into one on X11.
        outline = self._workbench.outline
        outline.set_menu_target(self._open_outline_menu)
        self._menu_keys = []
        for host, opener in (
            (self._workbench.canvas, lambda: self.open_context_menu(None, None)),
            (outline.tree, outline.request_menu),
        ):
            menu_key = QShortcut(QKeySequence("Shift+F10"), host)
            menu_key.setContext(getattr(Qt, "WidgetWithChildrenShortcut"))
            menu_key.activated.connect(opener)
            self._menu_keys.append(menu_key)
        self._workbench.set_drawer_listener(self._sync_drawer_escape)
        self._order_focus()
        self._refresh_design()
        self.apply_theme(request.theme)
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)

    def widget(self) -> QWidget:
        return self

    def form_path(self) -> str:
        return self._path

    def current_text(self) -> str:
        return self._source.current_text()

    def mark_saved(self, saved_text: str) -> None:
        self._source.mark_saved(saved_text)

    def run_active_file(self, workflow: object) -> bool:
        return run_open_form(self, workflow)

    def request_preview(self, path: str) -> None:
        # The preview window is a later slice. F5 records the request here.
        self._preview_request = path
        listener = self._preview_listener
        if callable(listener):
            listener(path)

    def content_source(self) -> FormContentSource:
        return self._source

    def source_editor(self) -> Optional[CodeEditorWidget]:
        return self._editor

    def page_widget(self) -> Optional[QWidget]:
        return self._workbench.canvas_view().page_widget()

    def layout_plan(self) -> LayoutPlan:
        return self._plan

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self.setStyleSheet(
            "QWidget#formBuilder\\.surface { background: %s; color: %s; }"
            % (tokens.panel_bg, tokens.text_primary)
        )
        self._toolbar.apply_theme(tokens)
        self._workbench.apply_theme(tokens)
        self._paint_banner()
        self._toolbar.set_save(
            self._toolbar.save_state.text(),
            error=self._source.save_notice.error and not self._source.is_dirty(),
            tokens=tokens,
        )
        editor = self._editor
        if editor is not None:
            editor.apply_theme(tokens)
        self._command_toast.apply_theme(tokens)

    def set_diagnostics(self, diagnostics: Sequence[CodeDiagnostic]) -> None:
        del diagnostics

    def layout_offers(self, ids: Optional[Sequence[NodeId]] = None) -> OfferSheet:
        """What each layout request would do to ``ids`` (the selection by default), measured from the canvas."""
        document = self._session.document
        targets = self._session.selection.state.ids if ids is None else tuple(ids)
        return offers(
            document,
            targets,
            measure(document, targets, self._realizer.widget_for, self._realizer.layout_for),
            accepted=properties_for(document, targets),
        )

    def dispatch(self, command_id: str) -> None:
        """Run a form command. Clipboard ids run before the layout table."""
        if self._source.mode != "visual":
            return
        if apply_command(self, command_id):
            return
        request = request_for(command_id)
        if request is None:
            return
        if isinstance(request, OpenWrap):
            self._open_wrap_popover()
            return
        self.run_layout(request)

    def run_layout(self, request: object, ids: Optional[Sequence[NodeId]] = None) -> None:
        """One layout request on ``ids`` (the selection by default).

        A change toasts with Undo. A refusal goes to the status bar.
        """
        session = self._session
        targets = session.selection.state.ids if ids is None else tuple(ids)
        log = session.log
        before = log.entries()
        previous = before[-1] if before else None
        confirm = ask(self, chrome_for(self._tokens), lambda: self._place(targets))
        # The log listener toasts inside the commit, before the sentence is known.
        self._toast_held = True
        try:
            outcome = perform(
                session.document,
                targets,
                self._realizer.widget_for,
                transact(log),
                request,
                confirm,
                self._realizer.layout_for,
            )
        finally:
            self._toast_held = False
        entries = log.entries()
        top = entries[-1] if entries else None
        if isinstance(outcome, Done) and top is not None and top is not previous:
            note = ToastNote(outcome.sentence, "Undo", log.undo_label() or "", len(entries), top)
            self._command_toast.show_note(note, self._undo_announced)
        elif isinstance(outcome, Refused):
            self.narrate(outcome.reason)
        elif isinstance(outcome, Current):
            self.narrate("Nothing to change.")

    def editor_status_sentence(self) -> str:
        state = self._session.selection.state
        mixed = mixed_parent_sentence(self._session.document, state.ids)
        selection = mixed or selection_sentence(self._session.document, state.current, len(state.ids))
        return status_sentence(
            self._gesture_sentence,
            self._overlay_sentence,
            self._inert_note,
            self._hover_sentence,
            selection,
        )

    def reveal(self, line: int, detail: Optional[Mapping[str, str]]) -> bool:
        if detail and self._toolbar.xml.isChecked():
            # Apply the XML first: it replaces the document and every id.
            self._on_design()
            if self._toolbar.xml.isChecked():
                return False
        node_id = self._node_for_detail(detail)
        if node_id is not None:
            self._session.selection.set((node_id,), source=SelectionSource.PROGRAM)
            if self._session.selection.state.current != node_id:
                return False
            name = self._object_name(node_id)
            if name:
                self._workbench.canvas.ensure_widget_visible(name)
            QTimer.singleShot(0, self._focus_inspector)
            self._refresh_shell_status()
            return True
        editor = self._editor
        if editor is None or line < 1:
            return False
        if not self._toolbar.xml.isChecked():
            self._toolbar.xml.setChecked(True)
        editor.go_to_line(line)
        return True

    def restore_text(self, text: str, reason: RestoreReason) -> None:
        try:
            self._session.log.execute(ReplaceDocument(text, reason=_RESTORE_REASON[reason]))
        except CommandRejected as exc:
            self._show_unparsed(text, plain_banner_error(plain_read_error(exc)))
            return
        if self._source.mode == "xml":
            self._source.cancel_xml_mode()
            self._set_xml_checked(False)
            self._hide_banner()
            self._stack.setCurrentWidget(self._workbench)
        self._refresh_design()

    def close_blockers(self) -> tuple[str, ...]:
        return ()

    def file_path_changed(self, new_path: str) -> None:
        self._path = new_path
        scope = form_scope(new_path, self._request.project_root)
        self._session.set_path(new_path, scope)
        self._source.set_scope(scope)
        self._refresh_save_state()

    def toggle_source_view(self) -> None:
        """Switch Design and XML. The shell's Ctrl+Shift+V action calls this."""
        self._toolbar.xml.setChecked(not self._toolbar.xml.isChecked())

    def focus_primary(self) -> None:
        editor = self._editor
        if self._source.mode == "xml" and editor is not None:
            editor.setFocus()
            return
        self._workbench.outline.tree.setFocus()

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._problem_timer.stop()
        self._kept_timer.stop()
        self._saved_timer.stop()
        self._diagnostics_unsub()
        app = QApplication.instance()
        if app is not None:
            try:
                app.focusChanged.disconnect(self._on_focus_changed)
            except (RuntimeError, TypeError):
                pass
        self._clear_shell_undo()
        self._selection_unsub()
        self._source_unsub()
        self._changes.close()
        self._workbench.canvas_view().dispose()
        self._workbench.inspector.dispose()
        self._realizer.dispose()
        self._session.dispose()
        self._source.close()
        self.deleteLater()

    def undo(self) -> bool:
        """Undo the last command while Design is showing."""
        if self._source.mode != "visual":
            return False
        done = self._session.log.undo()
        self._refresh_undo_buttons()
        self._sync_shell_undo()
        return done

    def redo(self) -> bool:
        if self._source.mode != "visual":
            return False
        done = self._session.log.redo()
        self._refresh_undo_buttons()
        self._sync_shell_undo()
        return done

    def external_change_needs_bar(self, disk_text: str) -> bool:
        """Dirty buffer, or XML mode when the file on disk is not valid XML."""
        if self._source.is_dirty():
            return True
        return self._source.mode == "xml" and not _parses(disk_text)

    def offer_external_change(
        self,
        file_name: str,
        on_reload: Callable[[], None],
        on_keep: Callable[[], None],
        on_compare: Callable[[], None],
    ) -> None:
        def reload() -> None:
            self._notice.dismiss()
            on_reload()

        def keep() -> None:
            self._notice.dismiss()
            on_keep()

        self._notice.show_choices(
            external_change_sentence(file_name),
            (
                ("Reload from disk", reload),
                ("Keep mine", keep),
                ("Compare…", on_compare),
            ),
        )

    def offer_recovered_draft(
        self,
        saved_at: str,
        on_keep: Callable[[], None],
        on_discard: Callable[[], None],
    ) -> None:
        def keep() -> None:
            self._notice.dismiss()
            on_keep()

        def discard() -> None:
            self._notice.dismiss()
            disk = self._source.saved_text()
            try:
                self._session.log.execute(ReplaceDocument(disk, reason="history"))
            except CommandRejected:
                self._discard_xml()
            else:
                if self._source.mode == "xml":
                    self._source.cancel_xml_mode()
                    self._set_xml_checked(False)
                    self._hide_banner()
                    self._stack.setCurrentWidget(self._workbench)
                self._source.mark_saved(disk)
                self._refresh_design()
            on_discard()

        self._notice.show_choices(
            recovered_draft_sentence(saved_at),
            (("Keep recovered", keep), ("Discard", discard)),
        )

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._apply_responsive()
        self._attach_tab_watch()

    def focusInEvent(self, event: object) -> None:  # noqa: N802
        super().focusInEvent(event)  # type: ignore[arg-type]
        self._bind_shell_undo()

    def hideEvent(self, event: object) -> None:  # noqa: N802
        super().hideEvent(event)  # type: ignore[arg-type]
        self._clear_shell_undo()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._apply_responsive()
        self._command_toast.place()
        self._problem_popover.place()

    def _on_design(self) -> None:
        if self._toolbar.xml.isChecked():
            self._toolbar.xml.setChecked(False)
        self._toolbar.design.setChecked(not self._toolbar.xml.isChecked())

    def _on_xml_toggled(self, checked: bool) -> None:
        self._toolbar.design.setChecked(not checked)
        if checked:
            self._show_xml()
            return
        self._commit_xml()

    def _show_xml(self) -> None:
        editor = self._ensure_editor()
        if self._source.mode != "xml":
            editor.blockSignals(True)
            editor.setPlainText(self._source.current_text())
            shown = editor.toPlainText()
            editor.blockSignals(False)
            self._source.enter_xml_mode(shown)
            self._mark_kept_lines(editor)
            self._show_banner(XML_APPLY_HINT, error=False)
        self._stack.setCurrentWidget(editor)
        self._workbench.outline.tree.hide()
        self._sync_shell_undo()
        editor.setFocus()

    def _commit_xml(self) -> None:
        editor = self._editor
        if editor is not None and self._source.mode == "xml":
            self._source.xml_text_changed(editor.toPlainText())
        error = self._source.leave_xml_mode()
        if error is not None:
            self._set_xml_checked(True)
            line = _error_line(error)
            if line > 0 and editor is not None:
                editor.go_to_line(line)
            self._show_banner(plain_banner_error(error), error=True)
            return
        self._hide_banner()
        self._stack.setCurrentWidget(self._workbench)
        self._refresh_design()
        self._workbench.outline.tree.setFocus()
        self._sync_shell_undo()

    def _discard_xml(self) -> None:
        self._source.cancel_xml_mode()
        self._set_xml_checked(False)
        self._hide_banner()
        self._stack.setCurrentWidget(self._workbench)
        self._refresh_design()
        self._workbench.outline.tree.setFocus()

    def _set_xml_checked(self, checked: bool) -> None:
        self._toolbar.xml.blockSignals(True)
        self._toolbar.xml.setChecked(checked)
        self._toolbar.design.setChecked(not checked)
        self._toolbar.xml.blockSignals(False)

    def _show_banner(self, text: str, *, error: bool) -> None:
        self._banner.setText(text)
        self._banner_is_error = error
        self._paint_banner()
        self._discard.setVisible(error)
        self._banner_frame.show()

    def _hide_banner(self) -> None:
        self._banner_is_error = False
        self._banner_frame.hide()
        self._discard.hide()

    def _paint_banner(self) -> None:
        tokens = self._tokens
        if tokens is None:
            return
        width = tokens.focus_border_width
        if self._banner_is_error:
            color = tokens.diag_error_color or tokens.accent
            border = color
        else:
            color = tokens.text_primary
            border = tokens.border
        self._banner_frame.setStyleSheet(
            "QFrame#formBuilder\\.xmlBanner {"
            f" background: {tokens.editor_bg}; border: 1px solid {border}; }}"
            "QLabel#formBuilder\\.xmlBannerText {"
            f" color: {color}; background: transparent; border: none; }}"
        )
        self._discard.setStyleSheet(
            "QPushButton#formBuilder\\.discardXml {"
            f" color: {tokens.text_primary}; background: {tokens.input_bg};"
            f" border: 1px solid {tokens.border}; padding: 2px 8px; }}"
            "QPushButton#formBuilder\\.discardXml:focus {"
            f" border: {width}px solid {tokens.accent}; }}"
        )

    def _ensure_editor(self) -> CodeEditorWidget:
        editor = self._editor
        if editor is not None:
            return editor
        created = self._request.create_source_editor()
        self._editor = created
        created.textChanged.connect(self._on_xml_edited)
        self._stack.addWidget(created)
        return created

    def _on_xml_edited(self) -> None:
        editor = self._editor
        if editor is None:
            return
        self._source.xml_text_changed(editor.toPlainText())
        self._kept_timer.start()

    def _refresh_kept_lines(self) -> None:
        editor = self._editor
        if self._released or editor is None or self._source.mode != "xml":
            return
        if _parses(editor.toPlainText()):
            self._mark_kept_lines(editor)

    def _on_log(self, change_set: object) -> None:
        self._sync_toast(change_set)
        if self._source.mode != "visual":
            self._refresh_undo_buttons()
            return
        current = self._session.selection.state.current
        self._workbench.refresh(current, outline=_outline_mode(change_set))
        self._workbench.outline.show_for_design()
        self._refresh_undo_buttons()
        self._sync_shell_undo()
        self._refresh_save_state()
        self._command_toast.place()

    def _sync_toast(self, change_set: object) -> None:
        if self._toast_held:
            return
        origin = getattr(change_set, "origin", "")
        label = str(getattr(change_set, "label", "") or "")
        if origin != "do":
            self._command_toast.dismiss()
            return
        entries = self._session.log.entries()
        entry = entries[-1] if entries else None
        text = notice_sentence(label, names_from_entry(entry) if entry is not None else ())
        if text is None:
            self._command_toast.dismiss()
            return
        note = ToastNote(text, "Undo", label, len(entries), entry)
        self._command_toast.show_note(note, self._undo_announced)

    def _undo_announced(self, note: ToastNote) -> None:
        log = self._session.log
        entries = log.entries()
        top = entries[-1] if entries else None
        if not undo_matches(note, top):
            self._command_toast.dismiss()
            return
        self.undo()

    def _on_source_changed(self) -> None:
        self._save_faded = False
        self._refresh_save_state()
        self._refresh_undo_buttons()
        self._sync_shell_undo()

    def _on_selection(self, change: object) -> None:
        self._inert_note = ""
        self._gesture_sentence = ""
        current = getattr(getattr(change, "after", None), "current", None)
        self._workbench.outline.show_current(current)
        self._refresh_shell_status()

    def _on_outline_pick(self, node_id: NodeId) -> None:
        self._session.selection.set((node_id,), source=SelectionSource.OUTLINE)

    def canvas_pressed(self) -> None:
        workbench = getattr(self, "_workbench", None)
        if workbench is not None:
            workbench.close_drawers()

    def narrate(self, sentence: str) -> None:
        self._gesture_sentence = sentence
        self._refresh_shell_status()

    def show_paste_problem(self, text: str) -> None:
        """One toast action. Show opens Problems. Ctrl+Z still undoes the paste."""
        note = ToastNote(text, "Show", "", 0)
        self._command_toast.show_note(note, lambda _note: self._show_in_problems())

    def _clipboard_enabled(self, command_id: str) -> bool:
        return command_enabled(
            self._session.document,
            self._session.selection.state.ids,
            command_id,
            clipboard_has_fragment(),
        )

    def save_selected_piece(self) -> None:
        self._workbench.insert.save_selection(self._session)

    def _piece_notice(self, sentence: str, undo: Callable[[], None]) -> None:
        note = ToastNote(sentence, "Undo", "", 0)
        self._command_toast.show_note(note, lambda _note: undo())

    def show_plain(self, sentence: str) -> None:
        if not sentence:
            return
        note = ToastNote(sentence, None, "", 0)
        self._command_toast.show_note(note, lambda _note: None)

    def outline_target(self, global_pos: QPoint) -> object:
        workbench = getattr(self, "_workbench", None)
        if workbench is None:
            return None
        return workbench.outline.hit_global(global_pos)

    def hover_changed(self, node: Optional[NodeId]) -> None:
        self._workbench.outline.set_hover(node)
        if node is None:
            self._hover_sentence = ""
        else:
            edits = enter_opens_editor(self._session.document, node)
            self._hover_sentence = hover_sentence(self._session.document, node, edits)
        self._refresh_shell_status()

    def zoom_changed(self, label: str) -> None:
        self._toolbar.zoom_label.setText(label)

    def zoom_out(self) -> None:
        self._workbench.canvas.send(ZoomAsked(ZoomStep(-1)))

    def zoom_in(self) -> None:
        self._workbench.canvas.send(ZoomAsked(ZoomStep(1)))

    def zoom_to(self, factor: float) -> None:
        self._workbench.canvas.send(ZoomAsked(ZoomTo(factor)))

    def zoom_fit(self) -> None:
        self._workbench.canvas.send(ZoomAsked(ZoomFit()))

    def edit_text(self) -> None:
        self._workbench.canvas.send(EditTextAsked())

    def can_edit_text(self) -> bool:
        shown = effective_selection(self._session.document, self._session.selection.state)
        current = shown.current
        if current is None:
            return False
        return enter_opens_editor(self._session.document, current)

    def open_problem(self, node: NodeId) -> None:
        items = self._session.diagnostics.for_node(node)
        text = items[0].message if items else ""
        if not text:
            return
        if self._reveal_problem(text):
            self._problem_popover.hide()
            return
        self._problem_popover.show_message(text)

    def open_layout_popover(self, node: NodeId) -> None:
        targets = (node,)
        self._layout_popover = open_layout_menu(
            self,
            self.layout_offers(targets),
            lambda request: self.run_layout(request, targets),
            self._chip_anchor(node),
        )

    def open_context_menu(self, node: Optional[NodeId], at: Optional[QPoint]) -> None:
        if self._source.mode != "visual":
            return
        shown = self._context_menu
        if shown is not None and wrapper_is_valid(shown):
            if shown.isVisible():
                return
            shown.deleteLater()
        selection = self._session.selection
        if node is not None and node not in selection.state.ids:
            selection.set((node,), current=node, source=SelectionSource.CANVAS)
        menu = QMenu(self)
        menu.setObjectName("formBuilder.contextMenu")
        add_clipboard_actions(menu, self.dispatch, self._clipboard_enabled)
        fill_context_menu(menu, self.layout_offers(), self.run_layout)
        paint_menu(menu, chrome_for(self._tokens))
        if at is None:
            subject, bounds = self._place(selection.state.ids)
            at = beside(subject, menu.sizeHint(), bounds)
        menu.popup(at)
        self._context_menu = menu

    def _open_outline_menu(self, node: NodeId, at: QPoint) -> None:
        if node not in self._session.selection.state.ids:
            self._on_outline_pick(node)
        self.open_context_menu(node, at)

    def _open_wrap_popover(self) -> None:
        sheet = self.layout_offers()
        offer = gate(sheet, OpenWrap())
        if not offer.enabled:
            self.narrate(offer.reason)
            return
        ids = self._session.selection.state.ids
        popover = WrapPopover(
            self,
            sheet,
            len(ids),
            chrome_for(self._tokens),
            lambda kind_id: self.run_layout(PickWrap(kind_id)),
        )
        popover.open_beside(*self._place(ids))

    def _place(self, ids: Sequence[NodeId]) -> Tuple[QRect, QRect]:
        """``ids`` on screen and the visible canvas, both global, for a popover beside them."""
        canvas = self._workbench.canvas
        viewport = canvas.viewport()
        bounds = QRect(viewport.mapToGlobal(QPoint(0, 0)), viewport.size())
        drawn = canvas.viewport_rect(ids or (self._session.document.root.id,))
        if drawn is None:
            return QRect(bounds.center(), QSize(0, 0)), bounds
        return QRect(viewport.mapToGlobal(drawn.topLeft()), drawn.size()), bounds

    def focus_share(self, node: NodeId, axis: str) -> None:
        self._session.selection.set((node,), current=node, source=SelectionSource.CANVAS)
        self._workbench.focus_share(axis)

    def _chip_anchor(self, node: NodeId) -> QPoint:
        canvas = self._workbench.canvas
        for rect, chip_node in canvas.overlay().chips:
            if chip_node != node:
                continue
            local = canvas.mapFromScene(float(rect.x), float(rect.y + rect.height))
            return canvas.mapToGlobal(local)
        return self.mapToGlobal(self.rect().center())

    def _focus_canvas(self) -> None:
        if self._source.mode != "visual":
            return
        self._workbench.canvas.setFocus()

    def _focus_inspector_pane(self) -> None:
        if self._source.mode != "visual":
            return
        inspector = self._workbench.inspector
        inspector.setFocus()
        inspector.properties.setFocus()

    def _rename_inert(self) -> None:
        self._inert_note = "Rename on the form arrives in a later release."
        self._refresh_shell_status()

    def _reveal_problem(self, text: str) -> bool:
        window = self.window()
        panel = getattr(window, "_problems_panel", None)
        tabs = getattr(window, "_bottom_tabs_widget", None) or getattr(window, "_problems_tab_widget", None)
        reader = getattr(panel, "tree_widget", None)
        if panel is None or tabs is None or not callable(reader):
            return False
        tree = reader()
        if not isinstance(tree, QTreeWidget) or not tree_contains(tree, text):
            return False
        index = tabs.indexOf(panel)
        if index < 0:
            return False
        tabs.setCurrentIndex(index)
        return True

    def _refresh_design(self) -> None:
        current = self._session.selection.state.current
        self._workbench.refresh(current)
        if self._source.mode == "visual":
            self._workbench.outline.show_for_design()
        self._refresh_undo_buttons()
        self._refresh_save_state()

    def _show_unparsed(self, text: str, error: str) -> None:
        editor = self._ensure_editor()
        if self._source.mode != "xml":
            self._source.enter_xml_mode(self._source.current_text())
        editor.blockSignals(True)
        editor.setPlainText(text)
        editor.blockSignals(False)
        self._mark_kept_lines(editor)
        self._source.xml_text_changed(text)
        self._set_xml_checked(True)
        self._stack.setCurrentWidget(editor)
        self._workbench.outline.tree.hide()
        self._show_banner(error, error=True)

    def _toolbar_undo(self) -> None:
        self.undo()

    def _toolbar_redo(self) -> None:
        self.redo()

    def _refresh_undo_buttons(self) -> None:
        design = self._source.mode == "visual"
        log = self._session.log
        undo_tip = undo_menu_text("Undo", log.undo_label() if design else None)
        redo_tip = undo_menu_text("Redo", log.redo_label() if design else None)
        self._toolbar.set_undo(design and log.can_undo(), "%s (Ctrl+Z)" % undo_tip)
        self._toolbar.set_redo(design and log.can_redo(), "%s (Ctrl+Shift+Z)" % redo_tip)

    def _refresh_save_state(self) -> None:
        notice = self._source.save_notice
        if notice.kind == "hold":
            self._show_hold(notice.text)
            return
        timer = self._saved_timer
        if self._source.is_dirty():
            self._saved_timer.stop()
            missing = not Path(self._path).exists()
            self._toolbar.set_save(
                "Not saved yet" if missing else "Unsaved changes",
                error=False,
                tokens=self._tokens,
            )
            return
        if notice.error:
            self._saved_timer.stop()
            self._toolbar.set_save(notice.text, error=True, tokens=self._tokens)
            return
        if notice.kind in ("saved", "generated") and notice.text and not self._save_faded:
            self._toolbar.set_save(notice.text, error=False, tokens=self._tokens)
            self._saved_timer.start(_SAVED_FADE_MS)
            return
        self._saved_timer.stop()
        self._toolbar.set_save("", error=False, tokens=self._tokens)

    def _node_for_detail(self, detail: Optional[Mapping[str, str]]) -> Optional[NodeId]:
        if not detail:
            return None
        document = self._session.document
        key = detail.get("fb_key") or ""
        if key:
            for diagnostic in self._session.diagnostics.all():
                node_id = diagnostic.location.node_id
                # A row made before an XML apply can hold an id that is gone.
                if diagnostic.key == key and node_id is not None and document.get(node_id) is not None:
                    return node_id
        name = detail.get("fb_object") or ""
        if not name:
            return None
        ids = document.by_name(name)
        if not ids:
            return None
        return ids[0]

    def _object_name(self, node_id: NodeId) -> str:
        node = self._session.document.get(node_id)
        name = getattr(node, "object_name", "")
        return name if isinstance(name, str) else ""

    def _focus_inspector(self) -> None:
        if self._released:
            return
        self._workbench.inspector.properties.setFocus()

    def _install_widget_shortcuts(self) -> None:
        hosts = {
            "canvas": self._workbench.canvas,
            "outline": self._workbench.outline.tree,
            "inspector": self._workbench.inspector,
        }
        context = getattr(Qt, "WidgetWithChildrenShortcut")
        effective = getattr(self.window(), "_effective_shortcuts", None)
        keys: Mapping[str, str] = effective if isinstance(effective, Mapping) else {}
        handlers = self._widget_handlers()
        self._widget_shortcuts: list[QShortcut] = []
        for command in FORM_COMMANDS:
            if not is_widget_shortcut(command):
                continue
            # Settings may rebind the key. A command with no gesture yet keeps
            # its QShortcut disabled, so the key reaches the focused widget.
            key = keys.get(command.command_id, command.shortcut)
            handler = handlers.get(command.command_id)
            live = command.available and handler is not None
            for name in command.contexts:
                host = hosts.get(name)
                if host is None:
                    continue
                shortcut = QShortcut(QKeySequence(key), host)
                shortcut.setContext(context)
                shortcut.setObjectName(command.command_id)
                shortcut.setEnabled(live)
                if live and handler is not None:
                    shortcut.activated.connect(handler)
                self._widget_shortcuts.append(shortcut)
        self._key_guard = _ShellKeyGuard(
            frozenset(normalize_form_shortcut(key) for key in INERT_SHORTCUTS),
            self._note_inert,
            self,
        )
        # Every focusable builder widget, so the guard sees a key press before
        # the widget does. Widgets made later are covered by their ancestors.
        for root in (self._workbench, self._toolbar, self._notice, self._banner_frame):
            root.installEventFilter(self._key_guard)
            for child in root.findChildren(QWidget):
                child.installEventFilter(self._key_guard)

    def _widget_handlers(self) -> Mapping[str, Callable[[], None]]:
        """Gestures behind canvas, outline, and inspector keys."""
        return {
            command.command_id: lambda command_id=command.command_id: self.dispatch(command_id)
            for command in FORM_COMMANDS
            if request_for(command.command_id) is not None or command.command_id in SHORTCUT_COMMAND_IDS
        }

    def _note_inert(self) -> None:
        self._inert_note = INERT_STATUS
        self._refresh_shell_status()

    def _schedule_problems(self, _diagnostics: object) -> None:
        if self._released:
            return
        self._problem_timer.start(0)

    def _flush_problems(self) -> None:
        if self._released:
            return
        rows = code_diagnostics_for_form(self._path, self._session.diagnostics.all())
        window = self.window()
        controller = getattr(window, "_problems_controller", None)
        apply = getattr(controller, "apply_lint_diagnostics_result", None)
        if callable(apply):
            apply(self._path, rows)
        self._workbench.inspector.set_problem_summary(len(rows), self._show_in_problems)

    def _show_in_problems(self) -> None:
        window = self.window()
        tabs = getattr(window, "_bottom_tabs_widget", None) or getattr(window, "_problems_tab_widget", None)
        panel = getattr(window, "_problems_panel", None)
        if tabs is None or panel is None:
            return
        index = tabs.indexOf(panel)
        if index >= 0:
            tabs.setCurrentIndex(index)

    def _open_buffer_state(self, path: str) -> Optional[Tuple[str, bool]]:
        window = self.window()
        manager = getattr(window, "_editor_manager", None)
        get_tab = getattr(manager, "get_tab", None)
        if not callable(get_tab):
            return None
        tab = get_tab(path)
        if tab is None:
            return None
        return (str(getattr(tab, "current_content", "")), bool(getattr(tab, "is_dirty", False)))

    def _refresh_shell_status(self) -> None:
        window = self.window()
        workflow = getattr(window, "_editor_tab_workflow", None)
        update = getattr(workflow, "update_editor_status_for_path", None)
        if callable(update):
            update(self._path)

    def _mark_kept_lines(self, editor: object) -> None:
        setter = getattr(editor, "set_gutter_notes", None)
        if not callable(setter):
            return
        reader = getattr(editor, "toPlainText", None)
        text = reader() if callable(reader) else ""
        notes = {start: "Kept as is" for start, _end in kept_as_is_spans(text if isinstance(text, str) else "")}
        setter(notes)

    def _show_hold(self, text: str) -> None:
        held = self._source.hold_path()
        name = os.path.basename(held) if held else "the generated file"

        def replace() -> None:
            self._notice.dismiss()
            self._source.allow_next_replace()
            window = self.window()
            workflow = getattr(window, "_save_workflow", None)
            save = getattr(workflow, "save_tab", None)
            if callable(save):
                save(self._path)

        def open_held() -> None:
            self._notice.dismiss()
            if held:
                self._request.open_linked_file(held)

        def cancel() -> None:
            self._notice.dismiss()

        self._notice.show_choices(
            text,
            (
                ("Replace", replace),
                ("Open %s" % name, open_held),
                ("Cancel save", cancel),
            ),
        )

    def _fade_saved(self) -> None:
        self._save_faded = True
        if self._source.is_dirty() or self._source.save_notice.error:
            return
        self._toolbar.set_save("", error=False, tokens=self._tokens)

    def _focus_outline(self) -> None:
        if self._source.mode != "visual":
            return
        self._workbench.focus_outline()
        self._esc.setEnabled(self._workbench.drawer_open())

    def _focus_insert(self) -> None:
        if self._source.mode != "visual":
            return
        self._workbench.focus_insert()
        self._esc.setEnabled(self._workbench.drawer_open())

    def _apply_responsive(self) -> None:
        width = self.width()
        height = self.height()
        if width < 1 or height < 1:
            return
        self._plan = plan_workbench(width, height, self._memory)
        self._toolbar.set_compact(self._plan.toolbar_compact)
        self._workbench.apply_plan(self._plan)
        self._esc.setEnabled(self._workbench.drawer_open())

    def _load_memory(self) -> None:
        window = self.window()
        root = getattr(window, "_state_root", None)
        if root:
            self._store = WorkbenchMemoryStore(str(root))
            self._pieces = SavedPieceStore(str(root))
            self._memory = self._store.load()
        else:
            self._store = None
            self._pieces = None
            memory = getattr(window, "_form_workbench_memory", None)
            if not isinstance(memory, WorkbenchMemory):
                memory = WorkbenchMemory()
                setattr(window, "_form_workbench_memory", memory)
            self._memory = memory
        workbench = getattr(self, "_workbench", None)
        if workbench is not None:
            workbench.outline.set_collapsed(self._memory.outline_collapsed)
            workbench.insert.set_collapsed(self._memory.insert_collapsed)
            workbench.insert.bind_pieces(self._pieces)
            workbench.insert.set_paste(lambda: self.dispatch("form.action.paste"))
            workbench.insert.set_notice(self._piece_notice)
            if self._store is not None:
                workbench.inspector.bind_settings(self._store)

    def _save_memory(self) -> None:
        if self._store is not None:
            self._store.save(self._memory)
            return
        setattr(self.window(), "_form_workbench_memory", self._memory)

    def _remember_collapsed(self, which: str, collapsed: bool) -> None:
        outline = collapsed if which == "outline" else self._memory.outline_collapsed
        insert = collapsed if which == "insert" else self._memory.insert_collapsed
        self._memory = WorkbenchMemory(
            left=self._memory.left,
            inspector=self._memory.inspector,
            outline_share=self._memory.outline_share,
            outline_collapsed=outline,
            insert_collapsed=insert,
            pin_left=self._memory.pin_left,
            pin_inspector=self._memory.pin_inspector,
        )
        self._save_memory()

    def _remember_widths(self, left: int, inspector: int) -> None:
        self._memory = WorkbenchMemory(
            left=left,
            inspector=inspector,
            outline_share=self._memory.outline_share,
            outline_collapsed=self._memory.outline_collapsed,
            insert_collapsed=self._memory.insert_collapsed,
            pin_left=self._memory.pin_left,
            pin_inspector=self._memory.pin_inspector,
        )
        self._save_memory()

    def _pin_left(self) -> None:
        self._memory = WorkbenchMemory(
            left=self._memory.left,
            inspector=self._memory.inspector,
            outline_share=self._memory.outline_share,
            outline_collapsed=self._memory.outline_collapsed,
            insert_collapsed=self._memory.insert_collapsed,
            pin_left=True,
            pin_inspector=self._memory.pin_inspector,
        )
        self._save_memory()
        self._apply_responsive()

    def _pin_inspector(self) -> None:
        self._memory = WorkbenchMemory(
            left=self._memory.left,
            inspector=self._memory.inspector,
            outline_share=self._memory.outline_share,
            outline_collapsed=self._memory.outline_collapsed,
            insert_collapsed=self._memory.insert_collapsed,
            pin_left=self._memory.pin_left,
            pin_inspector=True,
        )
        self._save_memory()
        self._apply_responsive()

    def _on_focus_changed(self, _old: object, new: object) -> None:
        if self._released:
            return
        self._sync_editor_group_keys(new)
        if new is None:
            return
        if new is self or self.isAncestorOf(new):  # type: ignore[arg-type]
            self._bind_shell_undo()

    def _attach_tab_watch(self) -> None:
        widget: Optional[QWidget] = self.parentWidget()
        found: Optional[QTabWidget] = None
        while widget is not None:
            if isinstance(widget, QTabWidget):
                found = widget
                break
            widget = widget.parentWidget()
        if found is self._tab_widget:
            return
        previous = self._tab_widget
        if previous is not None:
            try:
                previous.currentChanged.disconnect(self._on_tab_activated)
            except (RuntimeError, TypeError):
                pass
        self._tab_widget = found
        if found is not None:
            found.currentChanged.connect(self._on_tab_activated)

    def _on_tab_activated(self, _index: int) -> None:
        tab = self._tab_widget
        if tab is None or self._released:
            return
        current = tab.currentWidget()
        if current is None:
            return
        if current is self or current.isAncestorOf(self) or self.isAncestorOf(current):
            self._bind_shell_undo()

    def _sync_drawer_escape(self) -> None:
        self._esc.setEnabled(self._workbench.drawer_open())

    def _bind_shell_undo(self) -> None:
        window = self.window()
        registry = _shell_registry(window)
        if registry is None:
            return
        undo = registry.action("shell.action.edit.undo")  # type: ignore[attr-defined]
        redo = registry.action("shell.action.edit.redo")  # type: ignore[attr-defined]
        if undo is None or redo is None:
            return
        if not getattr(window, "_form_undo_wired", False):
            undo.triggered.connect(lambda _checked=False, host=window: _shell_history(host, False))
            redo.triggered.connect(lambda _checked=False, host=window: _shell_history(host, True))
            window._form_undo_wired = True  # type: ignore[attr-defined]
        window._form_undo_surface = self  # type: ignore[attr-defined]
        _silence(window, self, (_RENAME_ACTION,))
        self._sync_shell_undo()

    def _sync_editor_group_keys(self, focused: object) -> None:
        """Ctrl+1 and Ctrl+2 belong to the canvas and outline while one of them has focus."""
        hosts = (self._workbench.canvas, self._workbench.outline.tree)
        inside = isinstance(focused, QWidget) and any(
            host is focused or host.isAncestorOf(focused) for host in hosts
        )
        if inside:
            _silence(self.window(), self, _EDITOR_GROUP_ACTIONS)
        else:
            _restore(self.window(), self, _EDITOR_GROUP_ACTIONS)

    def _clear_shell_undo(self) -> None:
        window = self.window()
        _restore(window, self, _EDITOR_GROUP_ACTIONS)
        if getattr(window, "_form_undo_surface", None) is not self:
            return
        _restore(window, self, (_RENAME_ACTION,))
        window._form_undo_surface = None  # type: ignore[attr-defined]
        self._set_shell_actions("Undo", False, "Redo", False)

    def _sync_shell_undo(self) -> None:
        window = self.window()
        if getattr(window, "_form_undo_surface", None) is not self:
            return
        design = self._source.mode == "visual" and self.isVisible()
        log = self._session.log
        if not design:
            self._set_shell_actions("Undo", False, "Redo", False)
            return
        self._set_shell_actions(
            undo_menu_text("Undo", log.undo_label()),
            log.can_undo(),
            undo_menu_text("Redo", log.redo_label()),
            log.can_redo(),
        )

    def _set_shell_actions(self, undo_text: str, undo_on: bool, redo_text: str, redo_on: bool) -> None:
        window = self.window()
        registry = _shell_registry(window)
        if registry is None:
            return
        undo = registry.action("shell.action.edit.undo")
        redo = registry.action("shell.action.edit.redo")
        if undo is not None:
            undo.setText(undo_text)
            undo.setEnabled(undo_on)
        if redo is not None:
            redo.setText(redo_text)
            redo.setEnabled(redo_on)

    def _order_focus(self) -> None:
        order = [
            self._toolbar.design,
            self._toolbar.xml,
            self._toolbar.tab_order,
            self._toolbar.buddies,
            self._toolbar.undo,
            self._toolbar.redo,
            self._toolbar.zoom_out,
            self._toolbar.zoom_label,
            self._toolbar.zoom_in,
            self._toolbar.text_size,
            self._toolbar.two_widths,
            self._toolbar.preview,
            self._workbench.outline.header,
            *self._workbench.outline.header.extra,
            self._workbench.outline.tree,
            self._workbench.insert.header,
            *self._workbench.insert.header.extra,
            self._workbench.insert.filter,
            self._workbench.insert.body,
            self._workbench.canvas_view(),
            self._workbench.inspector.header,
            self._workbench.inspector.tabs,
        ]
        previous = order[0]
        for widget in order[1:]:
            self.setTabOrder(previous, widget)
            previous = widget


def _error_line(error: str) -> int:
    message = error.strip()
    marker = " (line "
    if not message.endswith(")") or marker not in message:
        return 0
    tail = message.rpartition(marker)[2][:-1].strip()
    if tail.isdigit():
        return int(tail)
    return 0


def _parses(text: str) -> bool:
    try:
        read_ui(text, allocator=IdAllocator())
    except UiReadError:
        return False
    return True


__all__ = ["XML_APPLY_HINT", "XML_DISCARD_LABEL", "VIEW_XML_TOOLTIP", "FormSurface"]
