"""Editor zoom, indent detection, and preference application."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.editors.editorconfig import resolve_editorconfig_indentation
from app.editors.indentation import detect_indentation_style_and_size
from app.shell.editor_tab_host_protocols import EditorTabPreferencesHost


class EditorTabPreferencesWorkflow:
    """Owns zoom handlers, indent detection, and editor preference application."""

    def __init__(
        self,
        *,
        host: EditorTabPreferencesHost,
        editor_manager: EditorManager,
        editor_widgets_by_path: Callable[[], dict[str, CodeEditorWidget]],
        status_controller: Callable[[], Any | None],
        loaded_project: Callable[[], Any | None],
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._editor_widgets_by_path = editor_widgets_by_path
        self._status_controller = status_controller
        self._loaded_project = loaded_project

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def effective_font_size(self) -> int:
        return max(8, min(72, self._host.editor_font_size() + self._host.zoom_delta()))

    def apply_editor_preferences_to_open_editors(self) -> None:
        effective_size = self.effective_font_size()
        for file_path, editor_widget in self._editor_widgets_by_path().items():
            editor_widget.set_editor_preferences(
                tab_width=self._host.editor_tab_width(),
                font_point_size=effective_size,
                font_family=self._host.editor_font_family(),
                indent_style=self._host.editor_indent_style(),
                indent_size=self._host.editor_indent_size(),
                hover_tooltip_enabled=self._host.editor_hover_tooltip_enabled(),
                auto_reindent_flat_python_paste=self._host.editor_auto_reindent_flat_python_paste(),
            )
            self.apply_detected_indentation_for_widget(file_path, editor_widget, editor_widget.toPlainText())
            editor_widget.set_completion_preferences(
                enabled=self._host.completion_enabled(),
                auto_trigger=self._host.completion_auto_trigger(),
                min_chars=self._host.completion_min_chars(),
            )

    def apply_runtime_intelligence_preferences_to_open_editors(self) -> None:
        for editor_widget in self._editor_widgets_by_path().values():
            self.apply_runtime_intelligence_preferences_to_editor(editor_widget)

    def apply_runtime_intelligence_preferences_to_editor(self, editor_widget: CodeEditorWidget) -> None:
        runtime_settings = self._host.intelligence_runtime_settings()
        editor_widget.set_highlighting_policy(
            adaptive_mode=runtime_settings.highlighting_adaptive_mode,
            reduced_threshold_chars=runtime_settings.highlighting_reduced_threshold_chars,
            lexical_only_threshold_chars=runtime_settings.highlighting_lexical_only_threshold_chars,
        )

    def apply_detected_indentation_for_widget(
        self,
        file_path: str,
        editor_widget: CodeEditorWidget,
        source_text: str,
    ) -> None:
        loaded_project = self._loaded_project()
        project_root = None if loaded_project is None else loaded_project.project_root
        editorconfig_indent = resolve_editorconfig_indentation(file_path, project_root=project_root)
        if editorconfig_indent is not None:
            effective_style = editorconfig_indent.indent_style
            effective_size = max(1, editorconfig_indent.indent_size)
            editor_widget.set_editor_preferences(
                tab_width=max(1, editorconfig_indent.tab_width),
                font_point_size=self.effective_font_size(),
                font_family=self._host.editor_font_family(),
                indent_style=effective_style,
                indent_size=effective_size,
                hover_tooltip_enabled=self._host.editor_hover_tooltip_enabled(),
                auto_reindent_flat_python_paste=self._host.editor_auto_reindent_flat_python_paste(),
            )
            self.record_indent_source(file_path, effective_style, effective_size, "editorconfig")
            return
        if not self._host.editor_detect_indentation_from_file() or not file_path.lower().endswith(
            (".py", ".json", ".md", ".txt")
        ):
            self.record_indent_source(
                file_path, self._host.editor_indent_style(), self._host.editor_indent_size(), "user"
            )
            return
        detected = detect_indentation_style_and_size(source_text)
        if detected is None:
            self.record_indent_source(
                file_path, self._host.editor_indent_style(), self._host.editor_indent_size(), "user"
            )
            return
        style, size = detected
        editor_widget.set_editor_preferences(
            tab_width=self._host.editor_tab_width(),
            font_point_size=self.effective_font_size(),
            font_family=self._host.editor_font_family(),
            indent_style=style,
            indent_size=size,
            hover_tooltip_enabled=self._host.editor_hover_tooltip_enabled(),
            auto_reindent_flat_python_paste=self._host.editor_auto_reindent_flat_python_paste(),
        )
        self.record_indent_source(file_path, style, size, "auto")

    def record_indent_source(
        self,
        file_path: str,
        style: str,
        size: int,
        source: str,
    ) -> None:
        self._host.indent_source_by_path()[file_path] = (style, int(size), source)
        active_tab = self._editor_manager.active_tab()
        if active_tab is not None and active_tab.file_path == file_path:
            self.update_indent_status_for_path(file_path)

    def update_indent_status_for_path(self, file_path: str | None) -> None:
        status_controller = self._status_controller()
        if status_controller is None:
            return
        if file_path is None:
            status_controller.set_indent_status(style=None, size=None, source=None)
            return
        record = self._host.indent_source_by_path().get(file_path)
        if record is None:
            status_controller.set_indent_status(style=None, size=None, source=None)
            return
        style, size, source = record
        status_controller.set_indent_status(style=style, size=size, source=source)

    def handle_zoom_in(self) -> None:
        if self._host.editor_font_size() + self._host.zoom_delta() < 72:
            self._host.set_zoom_delta(self._host.zoom_delta() + 1)
            self.apply_editor_preferences_to_open_editors()

    def handle_zoom_out(self) -> None:
        if self._host.editor_font_size() + self._host.zoom_delta() > 8:
            self._host.set_zoom_delta(self._host.zoom_delta() - 1)
            self.apply_editor_preferences_to_open_editors()

    def handle_zoom_reset(self) -> None:
        if self._host.zoom_delta() != 0:
            self._host.set_zoom_delta(0)
            self.apply_editor_preferences_to_open_editors()


__all__ = ["EditorTabPreferencesWorkflow"]
