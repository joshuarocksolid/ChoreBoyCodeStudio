"""Editor tab manager for deterministic open/dedupe behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.bootstrap.paths import cached_resolve
from app.editors.editor_tab import EditorTabState
from app.persistence.atomic_write import atomic_write_text


@dataclass(frozen=True)
class OpenedTabResult:
    """Result payload when opening a file in the editor."""

    tab: EditorTabState
    was_already_open: bool
    closed_preview_tab: EditorTabState | None = None
    promoted_from_preview: bool = False


def normalized_path(file_path: str) -> str:
    """The resolved path, remembered for the session so a later caller does not stat again."""
    return cached_resolve(file_path)


def _normalize(file_path: str) -> str:
    return normalized_path(file_path)


class EditorManager:
    """Owns open-tab state and file-backed read/save operations.

    Tabs are identified by ``buffer_id``; the file path is a mutable attribute
    indexed through ``_ids_by_path`` so a rename or move keeps the same buffer.
    """

    def __init__(self) -> None:
        self._tabs_by_id: dict[str, EditorTabState] = {}
        self._ids_by_path: dict[str, str] = {}
        self._open_order: list[str] = []
        self._active_buffer_id: str | None = None
        self._preview_buffer_id: str | None = None

    def open_file(self, file_path: str, *, preview: bool = False) -> OpenedTabResult:
        """Open a file or activate existing tab when already open."""
        normalized_path = _normalize(file_path)
        existing = self._activate_existing(normalized_path, preview=preview)
        if existing is not None:
            return existing

        content = self._read_file_contents(normalized_path)
        tab = EditorTabState.from_file(
            normalized_path,
            content,
            last_known_mtime=self._read_file_mtime(normalized_path),
            is_preview=preview,
        )
        return self._add_tab(tab, preview=preview)

    def open_file_with_content(
        self,
        file_path: str,
        content: str,
        *,
        preview: bool = False,
        original_content: Optional[str] = None,
        last_known_mtime: Optional[float] = None,
    ) -> OpenedTabResult:
        """Open a tab from provided content instead of reading from disk."""
        normalized_path = _normalize(file_path)
        existing = self._activate_existing(normalized_path, preview=preview)
        if existing is not None:
            return existing

        tab = EditorTabState(
            file_path=normalized_path,
            display_name=Path(normalized_path).name,
            original_content=content if original_content is None else original_content,
            current_content=content,
            last_known_mtime=last_known_mtime,
            is_preview=preview,
        )
        return self._add_tab(tab, preview=preview)

    def open_paths(self) -> list[str]:
        """Return open file paths in deterministic tab order."""
        return [self._tabs_by_id[buffer_id].file_path for buffer_id in self._open_order]

    def all_tabs(self) -> list[EditorTabState]:
        """Return tabs in tab-order sequence."""
        return [self._tabs_by_id[buffer_id] for buffer_id in self._open_order]

    def reorder_buffers(self, buffer_ids: list[str]) -> None:
        """Put open buffers in ``buffer_ids`` order; unknown ids are ignored.

        Open buffers missing from ``buffer_ids`` keep their relative order after
        the listed ones.
        """
        listed: list[str] = []
        for buffer_id in buffer_ids:
            if buffer_id in self._tabs_by_id and buffer_id not in listed:
                listed.append(buffer_id)
        rest = [buffer_id for buffer_id in self._open_order if buffer_id not in listed]
        self._open_order = listed + rest

    def get_tab(self, file_path: str) -> EditorTabState | None:
        """Return tab by file path, if open."""
        buffer_id = self._ids_by_path.get(_normalize(file_path))
        return None if buffer_id is None else self._tabs_by_id.get(buffer_id)

    def get_tab_by_id(self, buffer_id: str) -> EditorTabState | None:
        """Return tab by buffer id, if open."""
        return self._tabs_by_id.get(buffer_id)

    def set_active_file(self, file_path: str) -> None:
        """Set the active file path if already open."""
        tab = self.get_tab(file_path)
        if tab is not None:
            self._active_buffer_id = tab.buffer_id

    def active_tab(self) -> EditorTabState | None:
        """Return active tab, if any."""
        if self._active_buffer_id is None:
            return None
        return self._tabs_by_id.get(self._active_buffer_id)

    def active_file_path(self) -> str | None:
        """Return the active tab's file path, if an active tab is still open."""
        active_tab = self.active_tab()
        if active_tab is None:
            return None
        return active_tab.file_path

    def update_tab_content(self, file_path: str, content: str) -> EditorTabState:
        """Update tab content and return resulting state."""
        return self.replace_tab_content(file_path, content, mark_dirty=True)

    def replace_tab_content(
        self,
        file_path: str,
        content: str,
        *,
        mark_dirty: bool = True,
    ) -> EditorTabState:
        """Replace tab buffer content authoritatively."""
        tab = self._require_tab(file_path)
        tab.update_content(content)
        if tab.is_preview and tab.is_dirty:
            self._promote(tab)
        if not mark_dirty:
            tab.mark_saved(last_known_mtime=tab.last_known_mtime)
        return tab

    def save_tab(self, file_path: str) -> EditorTabState:
        """Save current content for an open tab back to disk."""
        tab = self._require_tab(file_path)
        path = Path(tab.file_path)
        text = tab.current_content
        atomic_write_text(path, text)
        tab.mark_saved(last_known_mtime=self._read_file_mtime(tab.file_path), saved_text=text)
        source = tab.content_source
        after_save = getattr(source, "after_save", None)
        if callable(after_save):
            after_save()
        return tab

    def current_disk_mtime(self, file_path: str) -> float | None:
        """Return latest on-disk mtime for file path, if available."""
        return self._read_file_mtime(_normalize(file_path))

    def preview_tab(self) -> EditorTabState | None:
        """Return current preview tab, if one exists."""
        if self._preview_buffer_id is None:
            return None
        return self._tabs_by_id.get(self._preview_buffer_id)

    def promote_tab(self, file_path: str) -> EditorTabState | None:
        """Promote a preview tab to permanent, if open."""
        tab = self.get_tab(file_path)
        if tab is None:
            return None
        if tab.is_preview:
            self._promote(tab)
        return tab

    def acknowledge_disk_mtime(self, file_path: str, mtime: float | None) -> EditorTabState:
        """Record observed disk mtime for an open tab."""
        tab = self._require_tab(file_path)
        tab.set_last_known_mtime(mtime)
        return tab

    def stale_open_paths(self) -> list[str]:
        """Return open file paths whose disk copy diverged from the tab snapshot."""
        stale_paths: list[str] = []
        for tab in self.all_tabs():
            path = tab.file_path
            current_mtime = self._read_file_mtime(path)
            if current_mtime is None:
                continue
            if tab.last_known_mtime is None:
                try:
                    disk_content = self._read_file_contents(path)
                except (OSError, ValueError):
                    continue
                if disk_content == tab.current_content:
                    tab.set_last_known_mtime(current_mtime)
                    continue
                stale_paths.append(path)
                continue
            if current_mtime != tab.last_known_mtime:
                stale_paths.append(path)
        return stale_paths

    def missing_open_paths(self) -> list[str]:
        """Return open file paths whose file no longer exists on disk."""
        return [tab.file_path for tab in self.all_tabs() if self._read_file_mtime(tab.file_path) is None]

    def save_all(self) -> list[EditorTabState]:
        """Save every dirty tab in tab order and return saved tabs."""
        saved_tabs: list[EditorTabState] = []
        for tab in self.all_tabs():
            if not tab.is_dirty:
                continue
            self.save_tab(tab.file_path)
            saved_tabs.append(tab)
        return saved_tabs

    def close_file(self, file_path: str) -> None:
        """Close an open file tab if it exists."""
        tab = self.get_tab(file_path)
        if tab is not None:
            tab.drop_content_source_subscription()
            self._remove_tab(tab)

    def remap_paths_for_move(self, source_path: str, destination_path: str) -> dict[str, str]:
        """Remap open tab paths after file/folder move and return old->new map."""
        source = _normalize(source_path)
        destination = _normalize(destination_path)
        moved = [
            (old_path, buffer_id)
            for old_path, buffer_id in self._ids_by_path.items()
            if old_path == source or old_path.startswith(f"{source}/")
        ]
        remapped: dict[str, str] = {}
        for old_path, _buffer_id in moved:
            del self._ids_by_path[old_path]
        for old_path, buffer_id in moved:
            new_path = f"{destination}{old_path[len(source):]}"
            tab = self._tabs_by_id[buffer_id]
            tab.file_path = new_path
            tab.display_name = Path(new_path).name
            self._ids_by_path[new_path] = buffer_id
            remapped[old_path] = new_path
        return remapped

    def _activate_existing(self, normalized_path: str, *, preview: bool) -> OpenedTabResult | None:
        existing_tab = self.get_tab(normalized_path)
        if existing_tab is None:
            return None
        promoted_from_preview = False
        if not preview and existing_tab.is_preview:
            self._promote(existing_tab)
            promoted_from_preview = True
        self._active_buffer_id = existing_tab.buffer_id
        return OpenedTabResult(
            tab=existing_tab,
            was_already_open=True,
            promoted_from_preview=promoted_from_preview,
        )

    def _add_tab(self, tab: EditorTabState, *, preview: bool) -> OpenedTabResult:
        closed_preview_tab = self._close_existing_preview_tab() if preview else None
        self._tabs_by_id[tab.buffer_id] = tab
        self._ids_by_path[tab.file_path] = tab.buffer_id
        self._open_order.append(tab.buffer_id)
        self._active_buffer_id = tab.buffer_id
        if preview:
            self._preview_buffer_id = tab.buffer_id
        return OpenedTabResult(
            tab=tab,
            was_already_open=False,
            closed_preview_tab=closed_preview_tab,
        )

    def _promote(self, tab: EditorTabState) -> None:
        tab.promote()
        if self._preview_buffer_id == tab.buffer_id:
            self._preview_buffer_id = None

    def _remove_tab(self, tab: EditorTabState) -> None:
        self._tabs_by_id.pop(tab.buffer_id, None)
        self._ids_by_path.pop(tab.file_path, None)
        self._open_order = [buffer_id for buffer_id in self._open_order if buffer_id != tab.buffer_id]
        if self._preview_buffer_id == tab.buffer_id:
            self._preview_buffer_id = None
        if self._active_buffer_id == tab.buffer_id:
            self._active_buffer_id = self._open_order[-1] if self._open_order else None

    def _close_existing_preview_tab(self) -> EditorTabState | None:
        preview_tab = self.preview_tab()
        self._preview_buffer_id = None
        if preview_tab is None:
            return None
        preview_tab.drop_content_source_subscription()
        self._remove_tab(preview_tab)
        return preview_tab

    def _require_tab(self, file_path: str) -> EditorTabState:
        tab = self.get_tab(file_path)
        if tab is None:
            raise ValueError(f"File is not open in editor tabs: {_normalize(file_path)}")
        return tab

    def _read_file_contents(self, file_path: str) -> str:
        path = Path(file_path)
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"File is not valid UTF-8 text: {file_path}") from exc

    def _read_file_mtime(self, file_path: str) -> float | None:
        path = Path(file_path)
        try:
            return path.stat().st_mtime
        except OSError:
            return None
