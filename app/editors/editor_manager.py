"""Editor tab manager for deterministic open/dedupe behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.editors.editor_tab import EditorTabState


@dataclass(frozen=True)
class OpenedTabResult:
    """Result payload when opening a file in the editor."""

    tab: EditorTabState
    was_already_open: bool
    closed_preview_path: str | None = None
    promoted_from_preview: bool = False


class EditorManager:
    """Owns open-tab state and file-backed read/save operations."""

    def __init__(self) -> None:
        self._tabs_by_path: dict[str, EditorTabState] = {}
        self._open_order: list[str] = []
        self._active_file_path: str | None = None
        self._preview_file_path: str | None = None

    def open_file(self, file_path: str, *, preview: bool = False) -> OpenedTabResult:
        """Open a file or activate existing tab when already open."""
        normalized_path = str(Path(file_path).expanduser().resolve())

        existing_tab = self._tabs_by_path.get(normalized_path)
        if existing_tab is not None:
            promoted_from_preview = False
            if not preview and existing_tab.is_preview:
                existing_tab.promote()
                promoted_from_preview = True
                if self._preview_file_path == normalized_path:
                    self._preview_file_path = None
            self._active_file_path = normalized_path
            return OpenedTabResult(
                tab=existing_tab,
                was_already_open=True,
                promoted_from_preview=promoted_from_preview,
            )

        closed_preview_path: str | None = None
        if preview:
            closed_preview_path = self._close_existing_preview_tab()
        content = self._read_file_contents(normalized_path)
        tab = EditorTabState.from_file(
            normalized_path,
            content,
            last_known_mtime=self._read_file_mtime(normalized_path),
            is_preview=preview,
        )
        self._tabs_by_path[normalized_path] = tab
        self._open_order.append(normalized_path)
        self._active_file_path = normalized_path
        if preview:
            self._preview_file_path = normalized_path
        return OpenedTabResult(
            tab=tab,
            was_already_open=False,
            closed_preview_path=closed_preview_path,
        )

    def open_paths(self) -> list[str]:
        """Return open file paths in deterministic tab order."""
        return list(self._open_order)

    def all_tabs(self) -> list[EditorTabState]:
        """Return tabs in tab-order sequence."""
        return [self._tabs_by_path[path] for path in self._open_order]

    def get_tab(self, file_path: str) -> EditorTabState | None:
        """Return tab by file path, if open."""
        normalized_path = str(Path(file_path).expanduser().resolve())
        return self._tabs_by_path.get(normalized_path)

    def set_active_file(self, file_path: str) -> None:
        """Set the active file path if already open."""
        normalized_path = str(Path(file_path).expanduser().resolve())
        if normalized_path in self._tabs_by_path:
            self._active_file_path = normalized_path

    def active_tab(self) -> EditorTabState | None:
        """Return active tab, if any."""
        if self._active_file_path is None:
            return None
        return self._tabs_by_path.get(self._active_file_path)

    def update_tab_content(self, file_path: str, content: str) -> EditorTabState:
        """Update tab content and return resulting state."""
        tab = self._require_tab(file_path)
        tab.update_content(content)
        return tab

    def save_tab(self, file_path: str) -> EditorTabState:
        """Save current content for an open tab back to disk."""
        tab = self._require_tab(file_path)
        path = Path(tab.file_path)
        path.write_text(tab.current_content, encoding="utf-8")
        tab.mark_saved(last_known_mtime=self._read_file_mtime(tab.file_path))
        return tab

    def current_disk_mtime(self, file_path: str) -> float | None:
        """Return latest on-disk mtime for file path, if available."""
        normalized_path = str(Path(file_path).expanduser().resolve())
        return self._read_file_mtime(normalized_path)

    def preview_tab(self) -> EditorTabState | None:
        """Return current preview tab, if one exists."""
        if self._preview_file_path is None:
            return None
        return self._tabs_by_path.get(self._preview_file_path)

    def promote_tab(self, file_path: str) -> EditorTabState | None:
        """Promote a preview tab to permanent, if open."""
        normalized_path = str(Path(file_path).expanduser().resolve())
        tab = self._tabs_by_path.get(normalized_path)
        if tab is None:
            return None
        if tab.is_preview:
            tab.promote()
            if self._preview_file_path == normalized_path:
                self._preview_file_path = None
        return tab

    def acknowledge_disk_mtime(self, file_path: str, mtime: float | None) -> EditorTabState:
        """Record observed disk mtime for an open tab."""
        tab = self._require_tab(file_path)
        tab.set_last_known_mtime(mtime)
        return tab

    def stale_open_paths(self) -> list[str]:
        """Return open file paths whose disk mtime changed since last snapshot."""
        stale_paths: list[str] = []
        for path in self._open_order:
            tab = self._tabs_by_path[path]
            current_mtime = self._read_file_mtime(path)
            if current_mtime is None:
                continue
            if tab.last_known_mtime is None:
                tab.set_last_known_mtime(current_mtime)
                continue
            if current_mtime != tab.last_known_mtime:
                stale_paths.append(path)
        return stale_paths

    def save_all(self) -> list[EditorTabState]:
        """Save every dirty tab in tab order and return saved tabs."""
        saved_tabs: list[EditorTabState] = []
        for path in self._open_order:
            tab = self._tabs_by_path[path]
            if not tab.is_dirty:
                continue
            self.save_tab(path)
            saved_tabs.append(tab)
        return saved_tabs

    def close_file(self, file_path: str) -> None:
        """Close an open file tab if it exists."""
        normalized_path = str(Path(file_path).expanduser().resolve())
        if normalized_path not in self._tabs_by_path:
            return
        self._tabs_by_path.pop(normalized_path, None)
        self._open_order = [path for path in self._open_order if path != normalized_path]
        if self._preview_file_path == normalized_path:
            self._preview_file_path = None
        if self._active_file_path == normalized_path:
            self._active_file_path = self._open_order[-1] if self._open_order else None

    def remap_paths_for_move(self, source_path: str, destination_path: str) -> dict[str, str]:
        """Remap open tab paths after file/folder move and return old->new map."""
        source = str(Path(source_path).expanduser().resolve())
        destination = str(Path(destination_path).expanduser().resolve())
        remapped: dict[str, str] = {}
        existing_paths = list(self._tabs_by_path.keys())
        for old_path in existing_paths:
            if old_path != source and not old_path.startswith(f"{source}/"):
                continue
            suffix = old_path[len(source) :]
            new_path = f"{destination}{suffix}"
            tab = self._tabs_by_path.pop(old_path)
            tab.file_path = new_path
            tab.display_name = Path(new_path).name
            self._tabs_by_path[new_path] = tab
            remapped[old_path] = new_path
            self._open_order = [new_path if path == old_path else path for path in self._open_order]
            if self._active_file_path == old_path:
                self._active_file_path = new_path
            if self._preview_file_path == old_path:
                self._preview_file_path = new_path
        return remapped

    def _close_existing_preview_tab(self) -> str | None:
        if self._preview_file_path is None:
            return None
        preview_path = self._preview_file_path
        if preview_path not in self._tabs_by_path:
            self._preview_file_path = None
            return None
        self._tabs_by_path.pop(preview_path, None)
        self._open_order = [path for path in self._open_order if path != preview_path]
        if self._active_file_path == preview_path:
            self._active_file_path = self._open_order[-1] if self._open_order else None
        self._preview_file_path = None
        return preview_path

    def _require_tab(self, file_path: str) -> EditorTabState:
        normalized_path = str(Path(file_path).expanduser().resolve())
        tab = self._tabs_by_path.get(normalized_path)
        if tab is None:
            raise ValueError(f"File is not open in editor tabs: {normalized_path}")
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
