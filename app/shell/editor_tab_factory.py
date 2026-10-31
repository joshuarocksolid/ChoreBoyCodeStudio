"""Editor tab materialization for the shell workspace."""

from __future__ import annotations

import time
from contextlib import nullcontext
from typing import Any, Callable, Optional

from app.qt.QtCore import Qt, QTimer
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from app.bootstrap.qt_binding_choice import select_binding

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import OpenedTabResult
from app.editors.editor_tab import EditorTabState
from app.editors.tab_content_source import TabContentSource
from app.shell.editor_tab_bindings_workflow import EditorTabBindingsHost
from app.shell.editor_tab_page import EditorTabPage
from app.shell.tab_content_providers import (
    ProviderDeclined,
    TabContentProviderRegistry,
    TabMatchContext,
    TabSurface,
    TabSurfaceRequest,
    focus_primary_surface,
)


def _drop_focus_restore() -> None:
    """A failed open must not leave Quick Open's restore flag for the next file."""
    from app.editors.quick_open_dialog import take_focus_restore

    take_focus_restore()


def _focus_opened_tab(window: Any, file_path: str) -> None:
    """Focus the opened tab after Quick Open's focus restore.

    Hiding the dialog posts a restore to the widget that was focused before it.
    A timer started from that restore's turn runs after it, so the tab keeps
    the keyboard.
    """
    registry = window._tab_content_registry
    focus_primary_surface(registry, file_path, force=True)
    from app.editors.quick_open_dialog import take_focus_restore

    if not take_focus_restore():
        return

    def later() -> None:
        # Quick Open restores the activity bar on its own timer. Take the
        # keyboard back only from that restore, not from a later click.
        from app.qt.QtWidgets import QApplication

        focus = QApplication.focusWidget()
        name = focus.objectName() if focus is not None else ""
        if name.startswith("shell.activityBar") or name.startswith("quickOpen"):
            focus_primary_surface(registry, file_path, force=False)

    def after_restore() -> None:
        QTimer.singleShot(0, later)

    QTimer.singleShot(0, after_restore)


def _schedule_buffer_warmup(window: Any) -> None:
    from app.shell.completion_warmup import schedule_open_buffer_warmup

    schedule_open_buffer_warmup(window)


class MainWindowEditorBindingsHost:
    """Binding ports for :class:`EditorTabFactory` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def semantic_navigation_workflow(self) -> Any:
        return self._window._semantic_navigation_workflow

    def enable_auto_reindent_flat_python_paste_from_hint(self) -> Any:
        return self._window._editor_tabs_coordinator.enable_auto_reindent_flat_python_paste_from_hint

    def handle_paste_hint_repair_result(self) -> Any:
        return self._window._editor_tabs_coordinator.handle_paste_hint_repair_result


#: Shown once per file on a PySide2 runtime. UX-PS2-001. No action button.
PYSIDE2_UI_HINT = (
    "Visual form editing needs FreeCAD 1.1 or later. "
    "This form opens as text here; your changes are kept."
)


class EditorTabFactory:
    """Creates editor widgets and registers them with the shell workspace."""

    def __init__(self, window: Any) -> None:
        self._window = window
        self._shown_ui_hints: set[str] = set()

    def open_file_in_editor(self, file_path: str, *, preview: bool = False, restore_draft: bool = True) -> bool:
        window = self._window
        if window._editor_tabs_widget is None:
            _drop_focus_restore()
            return False

        started_at = time.perf_counter()
        try:
            use_preview = preview and window._editor_enable_preview
            opened_result = window._editor_manager.open_file(file_path, preview=use_preview)
        except ValueError as exc:
            _drop_focus_restore()
            QMessageBox.warning(window, "Unable to open file", str(exc))
            return False
        opened = self._materialize_opened_editor_tab(
            opened_result,
            started_at=started_at,
            restore_draft=restore_draft,
        )
        if not opened:
            _drop_focus_restore()
        return opened

    def open_restored_history_buffer(self, file_path: str, content: str) -> bool:
        window = self._window
        if window._editor_tabs_widget is None:
            return False
        opened_result = window._editor_manager.open_file_with_content(
            file_path,
            content,
            original_content="",
            preview=False,
            last_known_mtime=None,
        )
        return self._materialize_opened_editor_tab(opened_result, started_at=None, restore_draft=False)

    def _materialize_opened_editor_tab(
        self,
        opened_result: OpenedTabResult,
        *,
        started_at: Optional[float],
        restore_draft: bool,
    ) -> bool:
        # The status bar is read once, after the tab is in place.
        hold = getattr(self._window._editor_tab_workflow, "hold_status_updates", None)
        with hold() if callable(hold) else nullcontext():
            return self._materialize_held(opened_result, started_at=started_at, restore_draft=restore_draft)

    def _materialize_held(
        self,
        opened_result: OpenedTabResult,
        *,
        started_at: Optional[float],
        restore_draft: bool,
    ) -> bool:
        window = self._window
        if window._editor_tabs_widget is None:
            return False

        closed_preview = opened_result.closed_preview_tab
        if closed_preview is not None:
            window._editor_tab_workflow.remove_tab_widget_for_buffer_id(
                closed_preview.buffer_id,
                file_path=closed_preview.file_path,
            )

        if opened_result.was_already_open:
            groups = getattr(window, "_editor_groups", None)
            if groups is not None:
                revealed = groups.reveal_buffer(opened_result.tab.buffer_id)
            else:
                existing_index = window._editor_tab_workflow.tab_index_for_path(opened_result.tab.file_path)
                revealed = existing_index >= 0
                if revealed:
                    window._editor_tabs_widget.setCurrentIndex(existing_index)
            if revealed:
                window._editor_tab_workflow.refresh_tab_presentation(opened_result.tab.file_path)
                if not opened_result.tab.is_preview:
                    _focus_opened_tab(window, opened_result.tab.file_path)
            window._refresh_save_action_states()
            window._editor_tab_workflow.update_editor_status_for_path(opened_result.tab.file_path)
            return True

        tab_file_path = opened_result.tab.file_path
        theme_tokens = window._shell_theme_workflow.resolve_theme_tokens()
        loaded_project = getattr(window, "_loaded_project", None)
        project_root = None if loaded_project is None else loaded_project.project_root
        created_editor: dict[str, Optional[CodeEditorWidget]] = {"widget": None}

        def create_source_editor() -> CodeEditorWidget:
            if created_editor["widget"] is not None:
                raise RuntimeError("create_source_editor may be called at most once per surface")
            editor_widget = self._build_bound_source_editor(
                opened_result,
                parent=window._editor_tabs_widget,
                theme_tokens=theme_tokens,
            )
            created_editor["widget"] = editor_widget
            return editor_widget

        registry: TabContentProviderRegistry = window._tab_content_registry
        provider = registry.provider_for(
            tab_file_path,
            TabMatchContext(project_root=project_root, forced_text=False),
        )
        surface: Optional[TabSurface] = None
        editor_widget: Optional[CodeEditorWidget]
        if provider is None:
            editor_widget = create_source_editor()
            hint = self._pyside2_ui_hint(tab_file_path)
            if hint is None:
                tab_content: QWidget = editor_widget
            else:
                tab_content = _PySide2UiHint(
                    editor_widget,
                    hint,
                    theme_tokens,
                    window._editor_tabs_widget,
                )
        else:

            def open_linked_file(linked_path: str) -> None:
                self.open_file_in_editor(linked_path, preview=False)

            request = TabSurfaceRequest(
                file_path=tab_file_path,
                initial_text=opened_result.tab.current_content,
                parent=window._editor_tabs_widget,
                theme=theme_tokens,
                create_source_editor=create_source_editor,
                open_linked_file=open_linked_file,
                project_root=project_root,
            )
            try:
                surface = provider.create_surface(request)
            except ProviderDeclined as exc:
                editor_widget = created_editor["widget"] or create_source_editor()
                tab_content = _DeclinedTextTab(editor_widget, exc.reason, window._editor_tabs_widget)
            except Exception:
                window._logger.exception(
                    "Tab provider %s failed for %s",
                    provider.provider_id,
                    tab_file_path,
                )
                editor_widget = created_editor["widget"] or create_source_editor()
                tab_content = _DeclinedTextTab(
                    editor_widget,
                    "Couldn't open this view. Opened as text.",
                    window._editor_tabs_widget,
                )
            else:
                editor_widget = surface.source_editor() or created_editor["widget"]
                content_source = surface.content_source()
                if content_source is not None:
                    self._attach_content_source(opened_result.tab, content_source)
                registry.bind(tab_file_path, surface, provider.provider_id)
                tab_content = surface.widget()

        page = self.build_tab_page(tab_content, opened_result.tab.buffer_id)
        self.attach_generated_banner(
            page,
            opened_result.tab.file_path,
            opened_result.tab.current_content,
        )
        tab_index = window._editor_tabs_widget.addTab(page, opened_result.tab.display_name)
        window._editor_tabs_coordinator.present_tab_at(tab_index, opened_result.tab)
        window._editor_tab_workflow.refresh_tab_presentation(opened_result.tab.file_path)
        window._editor_tabs_widget.setCurrentIndex(tab_index)
        if restore_draft:
            window._local_history_workflow.maybe_restore_draft(opened_result.tab, editor_widget)
        if editor_widget is not None:
            window._editor_tab_workflow.apply_detected_indentation_for_widget(
                opened_result.tab.file_path,
                editor_widget,
                editor_widget.toPlainText(),
            )
        window._editor_tab_workflow.handle_editor_tab_changed(tab_index)
        window._refresh_save_action_states()
        window._editor_tab_workflow.update_editor_status_for_path(opened_result.tab.file_path)
        if not opened_result.tab.is_preview:
            _focus_opened_tab(window, opened_result.tab.file_path)
        if started_at is not None:
            window._logger.info(
                "File open telemetry: file=%s elapsed_ms=%.2f",
                opened_result.tab.file_path,
                (time.perf_counter() - started_at) * 1000.0,
            )
        return True

    def _configure_editor_widget(self, editor_widget: CodeEditorWidget) -> None:
        window = self._window
        editor_widget.setObjectName("shell.editorTabs.textEditor")
        editor_widget.set_editor_preferences(
            tab_width=window._editor_tab_width,
            font_point_size=window._editor_tab_workflow.effective_font_size(),
            font_family=window._editor_font_family,
            indent_style=window._editor_indent_style,
            indent_size=window._editor_indent_size,
            hover_tooltip_enabled=window._editor_hover_tooltip_enabled,
            auto_reindent_flat_python_paste=window._editor_auto_reindent_flat_python_paste,
        )
        editor_widget.set_completion_preferences(
            mode=window._shell_preferences_runtime.completion_mode(),
            min_chars=window._completion_min_chars,
        )
        window._editor_tab_workflow.apply_runtime_intelligence_preferences_to_editor(editor_widget)
        editor_widget.apply_theme(window._shell_theme_workflow.resolve_theme_tokens())
        editor_widget.cursorPositionChanged.connect(lambda: _schedule_buffer_warmup(window))

    def _build_bound_source_editor(
        self,
        opened_result: OpenedTabResult,
        *,
        parent: QWidget,
        theme_tokens: Any,
    ) -> CodeEditorWidget:
        del theme_tokens
        window = self._window
        editor_widget = CodeEditorWidget(parent)
        self._configure_editor_widget(editor_widget)
        editor_widget.setPlainText(opened_result.tab.current_content)
        editor_widget.set_language_for_path(opened_result.tab.file_path)
        bindings_host: EditorTabBindingsHost = MainWindowEditorBindingsHost(window)
        window._editor_tab_workflow.attach_editor_bindings(bindings_host, editor_widget, opened_result.tab)
        window._workspace_controller.register_editor(opened_result.tab.buffer_id, editor_widget)
        return editor_widget

    def _attach_content_source(self, tab_state: EditorTabState, source: TabContentSource) -> None:
        tab_state.content_source = source

        def on_changed() -> None:
            self._window._editor_tab_workflow.handle_content_source_changed(tab_state)

        tab_state.content_source_unsubscribe = source.subscribe_changed(on_changed)

    def create_buffer_view(
        self,
        tab: EditorTabState,
        source_editor: CodeEditorWidget,
        *,
        parent: QWidget,
    ) -> CodeEditorWidget:
        """A second editor for an open buffer. It shares the source document."""
        window = self._window
        view = CodeEditorWidget(parent)
        self._configure_editor_widget(view)
        view.share_buffer_with(source_editor)
        view.set_editor_preferences(
            tab_width=source_editor._tab_width,
            font_point_size=window._editor_tab_workflow.effective_font_size(),
            font_family=window._editor_font_family,
            indent_style=source_editor._indent_style,
            indent_size=source_editor._indent_size,
            hover_tooltip_enabled=window._editor_hover_tooltip_enabled,
            auto_reindent_flat_python_paste=window._editor_auto_reindent_flat_python_paste,
        )
        window._editor_tab_workflow.attach_editor_bindings(MainWindowEditorBindingsHost(window), view, tab)
        view.setTextCursor(source_editor.textCursor())
        scroll_value = source_editor.verticalScrollBar().value()
        horizontal_value = source_editor.horizontalScrollBar().value()

        def restore_scroll() -> None:
            view.verticalScrollBar().setValue(scroll_value)
            view.horizontalScrollBar().setValue(horizontal_value)

        QTimer.singleShot(0, restore_scroll)
        return view

    def _pyside2_ui_hint(self, file_path: str) -> Optional[str]:
        """The FreeCAD 1.1 hint, or None.

        The form builder is not installed on PySide2, and the shell must not
        import that package. This is the text-tab notice for that case.
        """
        if not file_path.lower().endswith(".ui"):
            return None
        try:
            if select_binding() == "PySide6":
                return None
        except ImportError:
            return None
        if file_path in self._shown_ui_hints:
            return None
        self._shown_ui_hints.add(file_path)
        return PYSIDE2_UI_HINT

    def build_tab_page(self, content: QWidget, buffer_id: str) -> EditorTabPage:
        """Wrap tab content with the disk-conflict info bar and wire its buttons."""
        window = self._window
        page = EditorTabPage(content, buffer_id=buffer_id)
        page.info_bar.apply_theme(window._shell_theme_workflow.resolve_theme_tokens())
        conflicts = window._external_file_change_workflow

        def path() -> str | None:
            return window._editor_tab_workflow.path_for_buffer_id(buffer_id)

        def run(action: Callable[[str], object]) -> None:
            file_path = path()
            if file_path is not None:
                action(file_path)

        page.info_bar.reload_requested.connect(lambda: run(conflicts.reload_from_disk))
        page.info_bar.compare_requested.connect(lambda: run(conflicts.compare_with_disk))
        page.info_bar.save_as_requested.connect(lambda: run(conflicts.save_buffer_as))
        page.info_bar.close_tab_requested.connect(lambda: run(window._editor_tab_workflow.close_tab_for_path))
        return page

    def attach_generated_banner(self, page: EditorTabPage, file_path: str, text: str) -> None:
        """Show the generated-file banner when this buffer is one, and wire its buttons."""
        window = self._window
        page.generated_bar.apply_theme(window._shell_theme_workflow.resolve_theme_tokens())
        page.show_generated(file_path, text)

        def open_linked(linked: str) -> None:
            self.open_file_in_editor(linked, preview=False)

        page.generated_bar.open_source_requested.connect(open_linked)
        page.generated_bar.open_logic_requested.connect(open_linked)
        page.generated_bar.edit_anyway_requested.connect(page.make_generated_editable)


class _DeclinedTextTab(QWidget):
    """Text fallback after a provider declines, so a split can share the editor.

    No ``apply_theme``, ``set_mode``, or ``toggle_preview``. Tab chrome treats
    a widget with those as a second-group markdown pane.
    """

    def __init__(self, editor: CodeEditorWidget, reason: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._editor = editor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 0)
        layout.setSpacing(4)
        notice = QLabel(reason, self)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        layout.addWidget(editor, 1)

    def source_editor(self) -> CodeEditorWidget:
        return self._editor


class _DismissibleHint(QLabel):
    """Click hides the notice. Keyboard users use the focusable Dismiss button."""

    def __init__(self, text: str, on_dismiss: Callable[[], None], parent: QWidget) -> None:
        super().__init__(text, parent)
        self._on_dismiss = on_dismiss

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        self._on_dismiss()
        super().mousePressEvent(event)


class _PySide2UiHint(QWidget):
    """Text editor plus the dismissible FreeCAD 1.1 notice."""

    def __init__(
        self,
        editor: CodeEditorWidget,
        reason: str,
        tokens: Any,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._editor = editor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 0)
        layout.setSpacing(4)
        # One notice box: the hint, and Dismiss at its right.
        self._notice_frame = QFrame(self)
        self._notice_frame.setObjectName("shell.editorTabs.uiTextHintFrame")
        row = QHBoxLayout(self._notice_frame)
        row.setContentsMargins(8, 4, 4, 4)
        self._notice = _DismissibleHint(reason, self._hide_notice, self._notice_frame)
        self._notice.setObjectName("shell.editorTabs.uiTextHint")
        self._notice.setWordWrap(True)
        self._notice.setCursor(Qt.PointingHandCursor)
        row.addWidget(self._notice, 1)
        self._dismiss = QPushButton("Dismiss", self._notice_frame)
        self._dismiss.setObjectName("shell.editorTabs.uiTextHintDismiss")
        self._dismiss.clicked.connect(self._hide_notice)
        row.addWidget(self._dismiss, 0, Qt.AlignTop)
        layout.addWidget(self._notice_frame)
        layout.addWidget(editor, 1)
        self.apply_theme(tokens)

    def source_editor(self) -> CodeEditorWidget:
        return self._editor

    def apply_theme(self, tokens: Any) -> None:
        if tokens is None:
            return
        width = tokens.focus_border_width
        self._notice_frame.setStyleSheet(
            "QFrame#shell\\.editorTabs\\.uiTextHintFrame {"
            f" background: {tokens.panel_bg}; border: 1px solid {tokens.border};"
            f" border-left: {width}px solid {tokens.accent}; }}"
            "QLabel#shell\\.editorTabs\\.uiTextHint {"
            f" color: {tokens.text_primary}; background: transparent; border: none; }}"
        )
        self._dismiss.setStyleSheet(
            "QPushButton#shell\\.editorTabs\\.uiTextHintDismiss {"
            f" color: {tokens.text_primary}; background: {tokens.input_bg};"
            f" border: {width}px solid {tokens.border}; padding: 2px 8px; }}"
            "QPushButton#shell\\.editorTabs\\.uiTextHintDismiss:focus {"
            f" border: {width}px solid {tokens.accent}; }}"
        )

    def _hide_notice(self) -> None:
        self._notice_frame.hide()


__all__ = ["EditorTabFactory", "MainWindowEditorBindingsHost", "PYSIDE2_UI_HINT"]
