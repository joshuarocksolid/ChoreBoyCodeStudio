"""Outline debounce, symbol cache, async refresh, and go-to-symbol navigation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.editors.code_editor_widget import CodeEditorWidget
from app.editors.editor_manager import EditorManager
from app.intelligence.outline_service import OutlineSymbol, build_outline_from_source, flatten_symbols
from app.shell.editor_stale_result_policy import deliver_revision_gated_editor_result
from app.shell.editor_tab_host_protocols import EditorTabOutlineHost


class EditorTabOutlineWorkflow:
    """Owns outline panel refresh, symbol cache, and line navigation."""

    def __init__(
        self,
        *,
        host: EditorTabOutlineHost,
        editor_manager: EditorManager,
        editor_widgets_by_path: Callable[[], dict[str, CodeEditorWidget]],
        editor_tab_factory: Any,
        buffer_revision: Callable[[str], int | None],
    ) -> None:
        self._host = host
        self._editor_manager = editor_manager
        self._editor_widgets_by_path = editor_widgets_by_path
        self._editor_tab_factory = editor_tab_factory
        self._buffer_revision = buffer_revision
        self._outline_revision_by_path: dict[str, int] = {}

    def set_editor_manager(self, editor_manager: EditorManager) -> None:
        self._editor_manager = editor_manager

    def schedule_refresh(self) -> None:
        self._host.start_outline_refresh_timer()

    def stop_refresh_timer(self) -> None:
        self._host.stop_outline_refresh_timer()

    def handle_active_tab_changed(self) -> None:
        self.stop_refresh_timer()
        self.refresh_for_active_tab()

    def refresh_for_active_tab(self) -> None:
        outline_panel = self._host.outline_panel()
        if outline_panel is None:
            return
        active_tab = self._editor_manager.active_tab()
        if active_tab is None:
            outline_panel.set_unsupported_language("python")
            return
        file_path = active_tab.file_path
        if Path(file_path).suffix.lower() not in {".py", ".pyw", ".pyi"}:
            outline_panel.set_unsupported_language(
                Path(file_path).suffix.lstrip(".") or "this"
            )
            self._host.outline_symbols_by_path().pop(file_path, None)
            self._outline_revision_by_path.pop(file_path, None)
            return
        editor_widget = self._editor_widgets_by_path().get(
            str(Path(file_path).expanduser().resolve())
        )
        source = editor_widget.toPlainText() if editor_widget is not None else active_tab.current_content
        self._schedule_outline_parse(
            file_path=file_path,
            source=source or "",
            editor_widget=editor_widget,
            deliver_to_panel=True,
        )

    def flat_symbols_for_path(self, file_path: str, *, fallback_source: str) -> tuple[OutlineSymbol, ...]:
        symbols = self._cached_symbols_for_revision(file_path)
        if symbols is not None:
            return flatten_symbols(symbols)
        self._schedule_outline_parse(
            file_path=file_path,
            source=fallback_source or "",
            editor_widget=self._editor_widgets_by_path().get(
                str(Path(file_path).expanduser().resolve())
            ),
            deliver_to_panel=False,
        )
        return ()

    def request_flat_outline_symbols_async(
        self,
        file_path: str,
        *,
        fallback_source: str,
        on_success: Callable[[tuple[OutlineSymbol, ...]], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        symbols = self._cached_symbols_for_revision(file_path)
        if symbols is not None:
            on_success(flatten_symbols(symbols))
            return
        editor_widget = self._editor_widgets_by_path().get(
            str(Path(file_path).expanduser().resolve())
        )
        self._schedule_outline_parse(
            file_path=file_path,
            source=fallback_source or "",
            editor_widget=editor_widget,
            deliver_to_panel=False,
            on_flat_success=on_success,
            on_error=on_error,
        )

    def handle_symbol_activated(self, file_path: str, line_number: int) -> None:
        self.open_file_at_line(file_path, line_number)

    def open_file_at_line(self, file_path: str, line_number: int | None, *, preview: bool = False) -> None:
        if not self._editor_tab_factory.open_file_in_editor(file_path, preview=preview):
            return
        editor_widget = self._editor_widgets_by_path().get(
            str(Path(file_path).expanduser().resolve())
        )
        if editor_widget is None or line_number is None:
            return
        editor_widget.go_to_line(line_number)

    def highlight_symbol_at_line(self, line_number: int) -> None:
        outline_panel = self._host.outline_panel()
        if outline_panel is not None and self._host.outline_follow_cursor():
            outline_panel.highlight_symbol_at_line(line_number)

    def _cached_symbols_for_revision(self, file_path: str) -> tuple[OutlineSymbol, ...] | None:
        symbols = self._host.outline_symbols_by_path().get(file_path)
        if symbols is None:
            return None
        cached_revision = self._outline_revision_by_path.get(file_path)
        current_revision = self._buffer_revision(file_path)
        if cached_revision is None or cached_revision != current_revision:
            return None
        return symbols

    def _schedule_outline_parse(
        self,
        *,
        file_path: str,
        source: str,
        editor_widget: CodeEditorWidget | None,
        deliver_to_panel: bool,
        on_flat_success: Callable[[tuple[OutlineSymbol, ...]], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        requested_revision = None if editor_widget is None else self._buffer_revision(file_path)
        key = f"outline::{file_path}"

        def task(_cancel_event: object) -> tuple[OutlineSymbol, ...]:
            return build_outline_from_source(source)

        def on_success(symbols: tuple[OutlineSymbol, ...]) -> None:
            def deliver() -> None:
                self._host.outline_symbols_by_path()[file_path] = symbols
                if requested_revision is not None:
                    self._outline_revision_by_path[file_path] = requested_revision
                if deliver_to_panel:
                    outline_panel = self._host.outline_panel()
                    if outline_panel is not None:
                        outline_panel.set_outline(symbols, file_path)
                        if editor_widget is not None and self._host.outline_follow_cursor():
                            line_number = editor_widget.textCursor().blockNumber() + 1
                            outline_panel.highlight_symbol_at_line(line_number)
                if on_flat_success is not None:
                    on_flat_success(flatten_symbols(symbols))

            if editor_widget is None:
                deliver()
                return

            deliver_revision_gated_editor_result(
                file_path=file_path,
                editor_widget=editor_widget,
                requested_revision=requested_revision,
                editor_widget_for_path=lambda path: self._editor_widgets_by_path().get(
                    str(Path(path).expanduser().resolve())
                ),
                buffer_revision=self._buffer_revision,
                deliver=deliver,
            )

        def on_error_handler(exc: Exception) -> None:
            if on_error is not None:
                on_error(exc)

        self._host.background_tasks().run(
            key=key,
            task=task,
            on_success=on_success,
            on_error=on_error_handler,
        )


__all__ = ["EditorTabOutlineWorkflow"]
