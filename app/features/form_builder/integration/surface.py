"""Form tab: workbench, Design | XML, history, and the save notice.

One tab owns one ``FormSession``. Closing the tab disposes that session.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from app.qt.QtCore import Qt, QTimer
from app.qt.QtGui import QKeySequence
from app.qt.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QShortcut,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.editors.code_editor_widget import CodeEditorWidget
from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.commands.catalog import ReplaceDocument
from app.features.form_builder.engine.commands.log import Subscription
from app.features.form_builder.engine.diagnostics import parse_problem_detail
from app.features.form_builder.engine.events import PRIORITY_VIEWS
from app.features.form_builder.engine.ids import IdAllocator, NodeId
from app.features.form_builder.engine.project.save import HandEdit
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.engine.ui4.reader import UiReadError, read_ui
from app.features.form_builder.integration.adopt_flow import adopt_from_tree
from app.features.form_builder.integration.chrome_text import (
    external_change_sentence,
    hand_edit_sentence,
    problem_property_sentence,
    problem_summary,
    recovered_draft_sentence,
    selection_sentence,
    undo_menu_text,
)
from app.features.form_builder.integration.content_source import (
    FormContentSource,
    form_scope,
    plain_read_error,
)
from app.features.form_builder.integration.form_commands import bound_keys, unavailable_claims
from app.features.form_builder.integration.layout import (
    TOOLBAR_HEIGHT,
    LayoutPlan,
    WorkbenchMemory,
    plan_workbench,
)
from app.features.form_builder.integration.memory import WorkbenchMemoryStore
from app.features.form_builder.integration.problems_bridge import ProblemsBridge
from app.features.form_builder.integration.run_action import run_open_form
from app.features.form_builder.integration.workbench import FormToolbar, FormWorkbench, NoticeBar
from app.features.form_builder.qtside.realize.api import Realizer
from app.intelligence.diagnostics_models import CodeDiagnostic
from app.shell.tab_content_providers import CommandState, RestoreReason, SurfaceShellState, TabSurfaceRequest
from app.shell.theme_tokens import ShellThemeTokens

XML_APPLY_HINT = "Edits here apply to the design when you switch back."
XML_DISCARD_LABEL = "Discard XML edits"

_SHELL_UNDO = "shell.action.edit.undo"
_SHELL_REDO = "shell.action.edit.redo"
_SHELL_TOGGLE_SOURCE = "shell.action.view.markdownTogglePreview"

_RESTORE_REASON = {
    "draft": "draft",
    "history": "history",
    "external_reload": "reload",
}
_SAVED_FADE_MS = 4000


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


class FormSurface(QWidget):
    """``TabSurface`` for one ``.ui`` tab."""

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
        self._shell_listeners: List[Callable[[], None]] = []
        self._store: Optional[WorkbenchMemoryStore] = None
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
            self._stack,
        )
        self._stack.addWidget(self._workbench)
        layout.addWidget(self._stack, 1)

        self._load_memory()
        self._workbench.inspector.show_problems.clicked.connect(request.show_problems)
        self._problems = ProblemsBridge(request.file_path, session.diagnostics, self._publish_problems)
        self._changes: Subscription = session.log.subscribe(self._on_log, priority=PRIORITY_VIEWS)
        self._selection_unsub = session.selection.subscribe(self._on_selection)
        self._source_unsub = source.subscribe_changed(self._on_source_changed)
        self._saved_timer = QTimer(self)
        self._saved_timer.setSingleShot(True)
        self._saved_timer.timeout.connect(self._fade_saved)
        self._commands: Dict[str, Callable[[], object]] = {
            "form.viewXml": self._toggle_xml,
            _SHELL_TOGGLE_SOURCE: self._toggle_xml,
            "form.createWindowClass": self._create_window_class,
            "form.escape": self._workbench.close_drawers,
            "form.focus.outline": partial(self._focus, self._workbench.focus_outline),
            "form.focus.insert": partial(self._focus, self._workbench.focus_insert),
            "form.focus.canvas": partial(self._focus, self._workbench.canvas_view().setFocus),
            "form.focus.inspector": partial(self._focus, self._workbench.focus_inspector),
            _SHELL_UNDO: self.undo,
            _SHELL_REDO: self.redo,
        }
        self._shortcuts: Dict[str, QShortcut] = {}
        for command_id, key in bound_keys():
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(getattr(Qt, "WidgetWithChildrenShortcut"))
            shortcut.activated.connect(partial(self.run_command, command_id))
            self._shortcuts[command_id] = shortcut
        self._sync_drawer_escape()
        self._workbench.set_drawer_listener(self._sync_drawer_escape)
        self._order_focus()
        self._refresh_design()
        self.apply_theme(request.theme)

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

    def set_diagnostics(self, diagnostics: Sequence[CodeDiagnostic]) -> None:
        del diagnostics

    def reveal(self, line: int, detail: Optional[Mapping[str, str]]) -> bool:
        ref = None if detail is None else parse_problem_detail(detail)
        document = self._session.document
        matches = document.by_name(ref.object_name) if ref is not None and ref.object_name else ()
        if ref is None or not matches or self._source.has_unapplied_xml():
            return self._reveal_line(line)
        node_id = matches[0]
        if self._toolbar.xml.isChecked():
            self._toolbar.xml.setChecked(False)
        self._session.selection.set((node_id,), source=SelectionSource.PROGRAM)
        sentence = problem_property_sentence(ref.property) if ref.property else ""
        self._workbench.inspector.show_problem(document, node_id, sentence)
        self._workbench.focus_inspector()
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

    def ready_to_save(self) -> bool:
        """False, with Replace / Open / Cancel save, while the save would overwrite a hand edit."""
        held = self._source.save_hold(self._request.unsaved_text)
        if not held:
            return True
        self._offer_hand_edit_replace(held)
        return False

    def file_path_changed(self, new_path: str) -> None:
        self._path = new_path
        self._apply_scope()
        self._problems.set_path(new_path)
        self._refresh_save_state()
        self._notify_shell()

    def focus_primary(self) -> None:
        editor = self._editor
        if self._source.mode == "xml" and editor is not None:
            editor.setFocus()
            return
        self._workbench.outline.tree.setFocus()

    def shell_state(self) -> SurfaceShellState:
        """Design claims Undo, Redo and the Edit rows the form owns. XML leaves them to the XML editor."""
        if self._released:
            return SurfaceShellState()
        design = self._source.mode == "visual"
        claims = unavailable_claims(design)
        claims["form.viewXml"] = CommandState(True, checked=not design)
        claims[_SHELL_TOGGLE_SOURCE] = CommandState(True)
        claims["form.createWindowClass"] = CommandState(not self._session.scope.generates)
        if not design:
            return SurfaceShellState(None, claims)
        log = self._session.log
        claims[_SHELL_UNDO] = CommandState(log.can_undo(), label=undo_menu_text("Undo", log.undo_label()))
        claims[_SHELL_REDO] = CommandState(log.can_redo(), label=undo_menu_text("Redo", log.redo_label()))
        sentence = selection_sentence(self._session.document, self._session.selection.state)
        return SurfaceShellState(sentence, claims)

    def subscribe_shell_state(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._shell_listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._shell_listeners:
                self._shell_listeners.remove(listener)

        return unsubscribe

    def run_command(self, command_id: str) -> bool:
        handler = self._commands.get(command_id)
        if handler is None or self._released:
            return False
        handler()
        return True

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._notify_shell()
        self._shell_listeners.clear()
        self._problems.close()
        self._selection_unsub()
        self._source_unsub()
        self._changes.close()
        self._workbench.canvas_view().dispose()
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
        return done

    def redo(self) -> bool:
        if self._source.mode != "visual":
            return False
        done = self._session.log.redo()
        self._refresh_undo_buttons()
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

    def _offer_hand_edit_replace(self, held: Sequence[HandEdit]) -> None:
        first = held[0].path

        def replace() -> None:
            self._notice.dismiss()
            self._source.replace_hand_edits(held)
            self._request.save_file(self._path)

        names = list(dict.fromkeys(Path(edit.path).name for edit in held))
        self._notice.show_choices(
            hand_edit_sentence(names),
            (
                ("Replace", replace),
                ("Open %s" % Path(first).name, partial(self._request.open_linked_file, first)),
                ("Cancel save", self._notice.dismiss),
            ),
        )

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        self._apply_responsive()

    def resizeEvent(self, event: object) -> None:  # noqa: N802
        super().resizeEvent(event)  # type: ignore[arg-type]
        self._apply_responsive()

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
            self._show_banner(XML_APPLY_HINT, error=False)
        self._stack.setCurrentWidget(editor)
        self._workbench.outline.tree.hide()
        self._notify_shell()
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

    def _discard_xml(self) -> None:
        self._source.cancel_xml_mode()
        self._set_xml_checked(False)
        self._hide_banner()
        self._stack.setCurrentWidget(self._workbench)
        self._refresh_design()
        self._workbench.outline.tree.setFocus()

    def _reveal_line(self, line: int) -> bool:
        if line < 1:
            return False
        if not self._toolbar.xml.isChecked():
            self._toolbar.xml.setChecked(True)
        self._ensure_editor().go_to_line(line)
        return True

    def _publish_problems(self, path: str, rows: List[CodeDiagnostic]) -> None:
        self._request.publish_problems(path, rows)
        self._workbench.inspector.set_problem_summary(problem_summary(rows))

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

    def _on_log(self, _change_set: object) -> None:
        if self._source.mode != "visual":
            self._refresh_undo_buttons()
            return
        self._refresh_design()

    def _on_source_changed(self) -> None:
        self._save_faded = False
        self._refresh_save_state()
        self._refresh_undo_buttons()
        self._notify_shell()

    def _on_selection(self, change: object) -> None:
        current = getattr(getattr(change, "after", None), "current", None)
        self._workbench.inspector.show_selection(self._session.document, current)
        self._workbench.outline.rebuild(self._session.document, current)
        self._notify_shell()

    def _notify_shell(self) -> None:
        for listener in tuple(self._shell_listeners):
            listener()

    def _toggle_xml(self) -> None:
        self._toolbar.xml.setChecked(not self._toolbar.xml.isChecked())

    def _apply_scope(self) -> None:
        scope = form_scope(self._path, self._request.project_root)
        self._session.set_path(self._path, scope)
        self._source.set_scope(scope)

    def _create_window_class(self) -> None:
        adopt_from_tree(self.window(), self._path)
        self._apply_scope()
        self._notify_shell()

    def _focus(self, move: Callable[[], None]) -> None:
        if self._source.mode != "visual":
            return
        move()
        self._sync_drawer_escape()

    def _on_outline_pick(self, node_id: NodeId) -> None:
        self._session.selection.set((node_id,), source=SelectionSource.OUTLINE)

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
        self._source.xml_text_changed(text)
        self._set_xml_checked(True)
        self._stack.setCurrentWidget(editor)
        self._workbench.outline.tree.hide()
        self._show_banner(error, error=True)
        self._notify_shell()

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

    def _fade_saved(self) -> None:
        self._save_faded = True
        if self._source.is_dirty() or self._source.save_notice.error:
            return
        self._toolbar.set_save("", error=False, tokens=self._tokens)

    def _apply_responsive(self) -> None:
        width = self.width()
        height = self.height()
        if width < 1 or height < 1:
            return
        self._plan = plan_workbench(width, height, self._memory)
        self._toolbar.set_compact(self._plan.toolbar_compact)
        self._workbench.apply_plan(self._plan)
        self._sync_drawer_escape()

    def _load_memory(self) -> None:
        window = self.window()
        root = getattr(window, "_state_root", None)
        if root:
            self._store = WorkbenchMemoryStore(str(root))
            self._memory = self._store.load()
        else:
            self._store = None
            memory = getattr(window, "_form_workbench_memory", None)
            if not isinstance(memory, WorkbenchMemory):
                memory = WorkbenchMemory()
                setattr(window, "_form_workbench_memory", memory)
            self._memory = memory
        workbench = getattr(self, "_workbench", None)
        if workbench is not None:
            workbench.outline.set_collapsed(self._memory.outline_collapsed)
            workbench.insert.set_collapsed(self._memory.insert_collapsed)

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

    def _sync_drawer_escape(self) -> None:
        self._shortcuts["form.escape"].setEnabled(self._workbench.drawer_open())

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
            self._workbench.insert.body,
            self._workbench.canvas_view(),
            self._workbench.inspector.header,
            self._workbench.inspector.tabs,
            self._workbench.inspector.show_problems,
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


__all__ = ["XML_APPLY_HINT", "XML_DISCARD_LABEL", "FormSurface"]
