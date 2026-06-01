"""Shell layout restore, persist, and outline splitter state."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from app.shell.layout_persistence import (
    DEFAULT_EXPLORER_SPLITTER_SIZES,
    DEFAULT_OUTLINE_COLLAPSED,
    DEFAULT_OUTLINE_FOLLOW_CURSOR,
    DEFAULT_OUTLINE_SORT_MODE,
    DEFAULT_TOP_SPLITTER_SIZES,
    DEFAULT_VERTICAL_SPLITTER_SIZES,
    ShellLayoutState,
    merge_layout_into_settings,
    parse_shell_layout_state,
)


class ShellLayoutHost(Protocol):
    def settings_service(self) -> Any:
        ...

    def width(self) -> int:
        ...

    def height(self) -> int:
        ...

    def resize(self, width: int, height: int) -> None:
        ...

    def top_splitter(self) -> Any | None:
        ...

    def vertical_splitter(self) -> Any | None:
        ...

    def explorer_splitter(self) -> Any | None:
        ...

    def outline_panel(self) -> Any | None:
        ...

    def outline_collapsed(self) -> bool:
        ...

    def set_outline_collapsed(self, collapsed: bool) -> None:
        ...

    def outline_follow_cursor(self) -> bool:
        ...

    def set_outline_follow_cursor(self, follow: bool) -> None:
        ...

    def outline_sort_mode(self) -> str:
        ...

    def set_outline_sort_mode(self, mode: str) -> None:
        ...

    def refresh_outline_for_active_tab(self) -> None:
        ...


class ShellLayoutWorkflow:
    """Owns splitter sizes, outline layout flags, and layout persistence."""

    def __init__(self, host: ShellLayoutHost) -> None:
        self._host = host

    def restore_from_settings(self) -> None:
        settings_payload = self._host.settings_service().load_global()
        layout_state = parse_shell_layout_state(settings_payload)
        self._host.resize(layout_state.width, layout_state.height)
        top_splitter = self._host.top_splitter()
        if top_splitter is not None:
            top_splitter.setSizes(list(layout_state.top_splitter_sizes))
        vertical_splitter = self._host.vertical_splitter()
        if vertical_splitter is not None:
            vertical_splitter.setSizes(list(layout_state.vertical_splitter_sizes))
        explorer_splitter = self._host.explorer_splitter()
        if explorer_splitter is not None:
            explorer_sizes = layout_state.explorer_splitter_sizes or DEFAULT_EXPLORER_SPLITTER_SIZES
            explorer_splitter.setSizes(list(explorer_sizes))
        self._host.set_outline_collapsed(bool(layout_state.outline_collapsed))
        self._host.set_outline_follow_cursor(bool(layout_state.outline_follow_cursor))
        self._host.set_outline_sort_mode(layout_state.outline_sort_mode)
        self.apply_outline_layout_state()

    def persist_to_settings(self) -> None:
        top_splitter = self._host.top_splitter()
        vertical_splitter = self._host.vertical_splitter()
        top_sizes = tuple(top_splitter.sizes()) if top_splitter is not None else DEFAULT_TOP_SPLITTER_SIZES
        vertical_sizes = (
            tuple(vertical_splitter.sizes())
            if vertical_splitter is not None
            else DEFAULT_VERTICAL_SPLITTER_SIZES
        )
        if len(top_sizes) != 2:
            top_sizes = DEFAULT_TOP_SPLITTER_SIZES
        if len(vertical_sizes) != 2:
            vertical_sizes = DEFAULT_VERTICAL_SPLITTER_SIZES
        explorer_sizes_tuple: tuple[int, int] | None = None
        explorer_splitter = self._host.explorer_splitter()
        if explorer_splitter is not None:
            raw_explorer = tuple(explorer_splitter.sizes())
            if len(raw_explorer) == 2:
                explorer_sizes_tuple = (int(raw_explorer[0]), int(raw_explorer[1]))

        layout_state = ShellLayoutState(
            width=self._host.width(),
            height=self._host.height(),
            top_splitter_sizes=(int(top_sizes[0]), int(top_sizes[1])),
            vertical_splitter_sizes=(int(vertical_sizes[0]), int(vertical_sizes[1])),
            explorer_splitter_sizes=explorer_sizes_tuple,
            outline_collapsed=bool(self._host.outline_collapsed()),
            outline_follow_cursor=bool(self._host.outline_follow_cursor()),
            outline_sort_mode=self._host.outline_sort_mode(),
        )
        self._host.settings_service().update_global(
            lambda settings_payload: merge_layout_into_settings(settings_payload, layout_state)
        )

    def reset_layout(self) -> None:
        default = ShellLayoutState()
        self._host.resize(default.width, default.height)
        top_splitter = self._host.top_splitter()
        if top_splitter is not None:
            top_splitter.setSizes(list(DEFAULT_TOP_SPLITTER_SIZES))
        vertical_splitter = self._host.vertical_splitter()
        if vertical_splitter is not None:
            vertical_splitter.setSizes(list(DEFAULT_VERTICAL_SPLITTER_SIZES))
        explorer_splitter = self._host.explorer_splitter()
        if explorer_splitter is not None:
            explorer_splitter.setSizes(list(DEFAULT_EXPLORER_SPLITTER_SIZES))
        self._host.set_outline_collapsed(DEFAULT_OUTLINE_COLLAPSED)
        self._host.set_outline_follow_cursor(DEFAULT_OUTLINE_FOLLOW_CURSOR)
        self._host.set_outline_sort_mode(DEFAULT_OUTLINE_SORT_MODE)
        self.apply_outline_layout_state()
        self.persist_to_settings()

    def apply_outline_layout_state(self) -> None:
        outline_panel = self._host.outline_panel()
        if outline_panel is None:
            return
        outline_panel.set_follow_cursor(self._host.outline_follow_cursor())
        outline_panel.set_sort_mode(self._host.outline_sort_mode())
        outline_panel.set_collapsed(self._host.outline_collapsed())
        self.apply_explorer_splitter_handle_state()

    def apply_explorer_splitter_handle_state(self) -> None:
        explorer_splitter = self._host.explorer_splitter()
        if explorer_splitter is None:
            return
        collapsed = bool(self._host.outline_collapsed())
        explorer_splitter.setHandleWidth(0 if collapsed else 1)
        handle = explorer_splitter.handle(1)
        if handle is not None:
            handle.setEnabled(not collapsed)

    def handle_outline_collapsed_changed(self, collapsed: bool) -> None:
        if bool(collapsed) == self._host.outline_collapsed():
            return
        self._host.set_outline_collapsed(bool(collapsed))
        self.apply_explorer_splitter_handle_state()
        self.persist_to_settings()

    def handle_outline_follow_cursor_changed(self, follow: bool) -> None:
        if bool(follow) == self._host.outline_follow_cursor():
            return
        self._host.set_outline_follow_cursor(bool(follow))
        self.persist_to_settings()
        if follow:
            self._host.refresh_outline_for_active_tab()

    def handle_outline_sort_mode_changed(self, mode: str) -> None:
        if not isinstance(mode, str) or mode == self._host.outline_sort_mode():
            return
        self._host.set_outline_sort_mode(mode)
        self.persist_to_settings()

    def handle_outline_hide_requested(self) -> None:
        outline_panel = self._host.outline_panel()
        if outline_panel is None:
            return
        if not self._host.outline_collapsed():
            outline_panel.set_collapsed(True)


class MainWindowShellLayoutHost:
    """Host ports for ``ShellLayoutWorkflow`` backed by a MainWindow instance."""

    def __init__(self, window: Any) -> None:
        self._window = window

    def settings_service(self) -> Any:
        return self._window._settings_service

    def width(self) -> int:
        return self._window.width()

    def height(self) -> int:
        return self._window.height()

    def resize(self, width: int, height: int) -> None:
        self._window.resize(width, height)

    def top_splitter(self) -> Any | None:
        return self._window._top_splitter

    def vertical_splitter(self) -> Any | None:
        return self._window._vertical_splitter

    def explorer_splitter(self) -> Any | None:
        return self._window._explorer_splitter

    def outline_panel(self) -> Any | None:
        return self._window._outline_panel

    def outline_collapsed(self) -> bool:
        return self._window._outline_collapsed

    def set_outline_collapsed(self, collapsed: bool) -> None:
        self._window._outline_collapsed = collapsed

    def outline_follow_cursor(self) -> bool:
        return self._window._outline_follow_cursor

    def set_outline_follow_cursor(self, follow: bool) -> None:
        self._window._outline_follow_cursor = follow

    def outline_sort_mode(self) -> str:
        return self._window._outline_sort_mode

    def set_outline_sort_mode(self, mode: str) -> None:
        self._window._outline_sort_mode = mode

    def refresh_outline_for_active_tab(self) -> None:
        self._window._editor_tab_workflow.refresh_outline_for_active_tab()


def build_shell_layout_workflow(window: Any) -> ShellLayoutWorkflow:
    return ShellLayoutWorkflow(MainWindowShellLayoutHost(window))
