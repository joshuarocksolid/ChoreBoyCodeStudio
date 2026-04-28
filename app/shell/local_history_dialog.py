"""Local history and draft-recovery dialogs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSplitter,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.persistence.history_models import LocalHistoryCheckpoint
from app.shell.dialog_chrome import (
    FOOTER_ROLE_DESTRUCTIVE_SECONDARY,
    FOOTER_ROLE_PRIMARY,
    FOOTER_ROLE_SECONDARY,
    add_footer_button,
    add_footer_stretch,
    add_meta_chip,
    build_dialog_chrome,
    clear_meta_chips,
)
from app.shell.diff_view import (
    DIFF_VIEW_MODE_INLINE,
    DIFF_VIEW_MODE_SIDE_BY_SIDE,
    DiffView,
    compute_diff_hunks,
)
from app.shell.icon_provider import history_icon
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette


def build_unified_diff(before_text: str, after_text: str, *, from_label: str, to_label: str) -> str:
    """Return unified diff text for two buffer snapshots.

    Kept for callers that want the raw diff without the full
    :class:`DiffView` widget; new UI surfaces should prefer
    :class:`DiffView` directly.
    """

    _, _, raw_text = compute_diff_hunks(
        before_text,
        after_text,
        from_label=from_label,
        to_label=to_label,
    )
    if raw_text:
        return raw_text
    return "No textual differences found."


def _resolve_tokens(dialog: QDialog, tokens: Optional[ShellThemeTokens]) -> ShellThemeTokens:
    if tokens is not None:
        return tokens
    parent = dialog.parent()
    accessor = getattr(parent, "current_theme_tokens", None)
    if callable(accessor):
        try:
            resolved = accessor()
        except Exception:  # pragma: no cover - defensive: parent in shutdown
            resolved = None
        if isinstance(resolved, ShellThemeTokens):
            return resolved
    return tokens_from_palette(dialog.palette())


def _format_relative(timestamp: Optional[str]) -> str:
    """Render a saved-at ISO timestamp as a short human-friendly label.

    Returns ``""`` when the timestamp cannot be parsed; callers should
    skip the meta chip in that case.
    """

    if not timestamp:
        return ""
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return ""
    now = datetime.now(parsed.tzinfo) if parsed.tzinfo else datetime.now()
    delta = now - parsed
    if delta < timedelta(0):
        return parsed.strftime("%b %d, %Y %H:%M")
    if delta < timedelta(seconds=45):
        return "just now"
    if delta < timedelta(minutes=60):
        minutes = max(1, int(delta.total_seconds() // 60))
        return f"{minutes} min ago"
    if delta < timedelta(hours=12):
        hours = int(delta.total_seconds() // 3600)
        return f"{hours} hr ago"
    if parsed.date() == now.date():
        return parsed.strftime("today at %H:%M")
    if parsed.date() == (now - timedelta(days=1)).date():
        return parsed.strftime("yesterday at %H:%M")
    return parsed.strftime("%b %d, %Y %H:%M")


def _parse_timestamp(value: str) -> Optional[datetime]:
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _disk_mtime_iso(file_path: str) -> Optional[str]:
    try:
        from pathlib import Path

        stat = Path(file_path).stat()
        return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone().isoformat()
    except OSError:
        return None


def _build_view_mode_toolbar(parent: QWidget) -> tuple[QWidget, QToolButton, QToolButton]:
    container = QWidget(parent)
    container.setObjectName("shell.diffView.modeToolbar")
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    inline_button = QToolButton(container)
    inline_button.setText("Inline")
    inline_button.setObjectName("shell.diffView.modeButton.inline")
    inline_button.setCheckable(True)
    inline_button.setChecked(True)
    inline_button.setProperty("modeButton", True)

    side_button = QToolButton(container)
    side_button.setText("Side by side")
    side_button.setObjectName("shell.diffView.modeButton.sideBySide")
    side_button.setCheckable(True)
    side_button.setProperty("modeButton", True)

    group = QButtonGroup(container)
    group.setExclusive(True)
    group.addButton(inline_button)
    group.addButton(side_button)

    layout.addWidget(inline_button)
    layout.addWidget(side_button)
    layout.addStretch(1)
    return container, inline_button, side_button


class DraftRecoveryDialog(QDialog):
    """Review dialog for comparing a saved file with a recovery draft."""

    def __init__(
        self,
        *,
        file_name: str,
        disk_text: str,
        draft_text: str,
        tokens: Optional[ShellThemeTokens] = None,
        disk_saved_at: Optional[str] = None,
        draft_saved_at: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._discard_draft = False
        self._tokens = _resolve_tokens(self, tokens)
        self._file_name = file_name
        self.setWindowTitle("Review Recovery Draft")
        self.resize(1000, 660)

        chrome = build_dialog_chrome(
            self,
            title=f"Unsaved draft for {file_name}",
            subtitle=(
                "A newer recovery draft was found. Review the changes "
                "and choose which version to keep."
            ),
            object_name="shell.draftRecoveryDialog",
            icon=history_icon(self._tokens.icon_muted or self._tokens.accent),
        )
        self._chrome = chrome

        body_layout = chrome.body.layout()
        assert isinstance(body_layout, QVBoxLayout)

        toolbar, inline_button, side_button = _build_view_mode_toolbar(chrome.body)
        body_layout.addWidget(toolbar)

        self._diff_view = DiffView(self._tokens, chrome.body)
        self._diff_view.set_texts(
            disk_text,
            draft_text,
            before_label="Saved on Disk",
            after_label="Recovery Draft",
        )
        body_layout.addWidget(self._diff_view, 1)

        inline_button.toggled.connect(self._handle_inline_toggled)
        side_button.toggled.connect(self._handle_side_toggled)

        self._populate_meta_chips(disk_saved_at, draft_saved_at)

        cancel_button = add_footer_button(chrome, "Cancel", role=FOOTER_ROLE_SECONDARY)
        add_footer_stretch(chrome)
        keep_disk_button = add_footer_button(
            chrome, "&Keep Disk Version", role=FOOTER_ROLE_DESTRUCTIVE_SECONDARY
        )
        restore_button = add_footer_button(
            chrome, "&Restore Draft to Buffer", role=FOOTER_ROLE_PRIMARY, default=True
        )

        cancel_button.clicked.connect(self.reject)
        keep_disk_button.clicked.connect(self._handle_keep_disk_version)
        restore_button.clicked.connect(self.accept)

        self._restore_button = restore_button
        self._update_restore_availability()

    @property
    def discard_draft(self) -> bool:
        """Return True when the user explicitly chose disk content over the draft."""
        return self._discard_draft

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self._diff_view.apply_theme(tokens)

    def _handle_keep_disk_version(self) -> None:
        self._discard_draft = True
        self.reject()

    def _handle_inline_toggled(self, checked: bool) -> None:
        if checked:
            self._diff_view.set_mode(DIFF_VIEW_MODE_INLINE)

    def _handle_side_toggled(self, checked: bool) -> None:
        if checked:
            self._diff_view.set_mode(DIFF_VIEW_MODE_SIDE_BY_SIDE)

    def _populate_meta_chips(
        self,
        disk_saved_at: Optional[str],
        draft_saved_at: Optional[str],
    ) -> None:
        clear_meta_chips(self._chrome.meta_row)
        stats = self._diff_view.stats()
        add_meta_chip(
            self._chrome.meta_row,
            f"+{stats.added}  -{stats.removed} lines",
        )
        draft_label = _format_relative(draft_saved_at)
        if draft_label:
            add_meta_chip(self._chrome.meta_row, f"Draft saved {draft_label}")
        disk_label = _format_relative(disk_saved_at)
        if disk_label:
            add_meta_chip(self._chrome.meta_row, f"Disk last saved {disk_label}")

    def _update_restore_availability(self) -> None:
        stats = self._diff_view.stats()
        if stats.is_empty:
            self._restore_button.setEnabled(False)
            self._restore_button.setToolTip(
                "Draft and disk content are identical — nothing to restore."
            )
            self._diff_view.set_message(
                "Draft matches the saved file. No restore is needed."
            )


class LocalHistoryDialog(QDialog):
    """Revision timeline dialog for one file."""

    def __init__(
        self,
        *,
        file_name: str,
        checkpoints: list[LocalHistoryCheckpoint],
        current_text: str,
        checkpoint_content_loader: Callable[[int], Optional[str]],
        restore_to_buffer: Callable[[str], None],
        tokens: Optional[ShellThemeTokens] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._checkpoints = list(checkpoints)
        self._current_text = current_text
        self._checkpoint_content_loader = checkpoint_content_loader
        self._restore_to_buffer = restore_to_buffer
        self._compare_mode = "current"
        self._loaded_checkpoint_contents: dict[int, Optional[str]] = {}
        self._tokens = _resolve_tokens(self, tokens)
        self._file_name = file_name

        self.setWindowTitle(f"Local History — {file_name}")
        self.resize(1100, 720)

        chrome = build_dialog_chrome(
            self,
            title=f"Local history for {file_name}",
            subtitle=(
                "Browse saved local-history entries, compare them against "
                "the current buffer or the previous revision, and restore "
                "any revision back into the editor."
            ),
            object_name="shell.localHistoryDialog",
            icon=history_icon(self._tokens.icon_muted or self._tokens.accent),
        )
        self._chrome = chrome

        body_layout = chrome.body.layout()
        assert isinstance(body_layout, QVBoxLayout)

        toolbar = QWidget(chrome.body)
        toolbar.setObjectName("shell.localHistoryDialog.toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)

        compare_label = QLabel("Compare against:", toolbar)
        compare_label.setObjectName("shell.localHistoryDialog.compareLabel")
        toolbar_layout.addWidget(compare_label)

        self._compare_current_button = QToolButton(toolbar)
        self._compare_current_button.setText("Current buffer")
        self._compare_current_button.setObjectName("shell.localHistoryDialog.compareCurrent")
        self._compare_current_button.setCheckable(True)
        self._compare_current_button.setChecked(True)
        self._compare_current_button.setProperty("modeButton", True)

        self._compare_previous_button = QToolButton(toolbar)
        self._compare_previous_button.setText("Previous revision")
        self._compare_previous_button.setObjectName("shell.localHistoryDialog.comparePrevious")
        self._compare_previous_button.setCheckable(True)
        self._compare_previous_button.setProperty("modeButton", True)

        compare_group = QButtonGroup(toolbar)
        compare_group.setExclusive(True)
        compare_group.addButton(self._compare_current_button)
        compare_group.addButton(self._compare_previous_button)

        toolbar_layout.addWidget(self._compare_current_button)
        toolbar_layout.addWidget(self._compare_previous_button)

        toolbar_spacer = QWidget(toolbar)
        toolbar_spacer.setSizePolicy(toolbar.sizePolicy().horizontalPolicy(), toolbar.sizePolicy().verticalPolicy())
        toolbar_layout.addWidget(toolbar_spacer, 1)

        view_toolbar, view_inline_button, view_side_button = _build_view_mode_toolbar(toolbar)
        toolbar_layout.addWidget(view_toolbar)

        body_layout.addWidget(toolbar)

        splitter = QSplitter(Qt.Horizontal, chrome.body)
        splitter.setObjectName("shell.localHistoryDialog.splitter")
        splitter.setChildrenCollapsible(False)

        revision_tree = QTreeWidget(splitter)
        revision_tree.setObjectName("shell.localHistoryDialog.revisionTree")
        revision_tree.setHeaderLabels(["Timestamp", "Label"])
        revision_tree.setAlternatingRowColors(True)
        revision_tree.setUniformRowHeights(True)
        revision_tree.itemSelectionChanged.connect(self._refresh_diff_view)
        self._revision_tree = revision_tree

        self._diff_view = DiffView(self._tokens, splitter)

        splitter.addWidget(revision_tree)
        splitter.addWidget(self._diff_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 800])
        body_layout.addWidget(splitter, 1)

        self._compare_current_button.toggled.connect(self._handle_compare_current_toggled)
        self._compare_previous_button.toggled.connect(self._handle_compare_previous_toggled)
        view_inline_button.toggled.connect(self._handle_inline_toggled)
        view_side_button.toggled.connect(self._handle_side_toggled)

        cancel_button = add_footer_button(chrome, "Close", role=FOOTER_ROLE_SECONDARY)
        add_footer_stretch(chrome)
        self._restore_button = add_footer_button(
            chrome, "&Restore Selected Revision", role=FOOTER_ROLE_PRIMARY, default=True
        )

        cancel_button.clicked.connect(self.reject)
        self._restore_button.clicked.connect(self._handle_restore)

        self._populate_revision_tree()
        self._refresh_button_states()
        self._refresh_diff_view()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self._diff_view.apply_theme(tokens)

    def _populate_revision_tree(self) -> None:
        self._revision_tree.clear()
        for checkpoint in self._checkpoints:
            label = checkpoint.label or checkpoint.source.replace("_", " ")
            item = QTreeWidgetItem([checkpoint.created_at, label])
            item.setData(0, Qt.UserRole, checkpoint.revision_id)
            self._revision_tree.addTopLevelItem(item)
        if self._revision_tree.topLevelItemCount() > 0:
            self._revision_tree.setCurrentItem(self._revision_tree.topLevelItem(0))

    def _selected_checkpoint(self) -> Optional[LocalHistoryCheckpoint]:
        current_item = self._revision_tree.currentItem()
        if current_item is None:
            return None
        revision_id = current_item.data(0, Qt.UserRole)
        for checkpoint in self._checkpoints:
            if checkpoint.revision_id == revision_id:
                return checkpoint
        return None

    def _checkpoint_before_selected(self, selected: LocalHistoryCheckpoint) -> Optional[LocalHistoryCheckpoint]:
        for index, checkpoint in enumerate(self._checkpoints):
            if checkpoint.revision_id != selected.revision_id:
                continue
            next_index = index + 1
            if next_index >= len(self._checkpoints):
                return None
            return self._checkpoints[next_index]
        return None

    def _handle_compare_current_toggled(self, checked: bool) -> None:
        if checked:
            self._compare_with_current()

    def _handle_compare_previous_toggled(self, checked: bool) -> None:
        if checked:
            self._compare_with_previous()

    def _handle_inline_toggled(self, checked: bool) -> None:
        if checked:
            self._diff_view.set_mode(DIFF_VIEW_MODE_INLINE)

    def _handle_side_toggled(self, checked: bool) -> None:
        if checked:
            self._diff_view.set_mode(DIFF_VIEW_MODE_SIDE_BY_SIDE)

    def _compare_with_current(self) -> None:
        self._compare_mode = "current"
        self._refresh_button_states()
        self._refresh_diff_view()

    def _compare_with_previous(self) -> None:
        selected = self._selected_checkpoint()
        if selected is None or self._checkpoint_before_selected(selected) is None:
            self._compare_current_button.setChecked(True)
            return
        self._compare_mode = "previous"
        self._refresh_button_states()
        self._refresh_diff_view()

    def _refresh_button_states(self) -> None:
        selected = self._selected_checkpoint()
        has_previous = selected is not None and self._checkpoint_before_selected(selected) is not None
        self._compare_previous_button.setEnabled(has_previous)
        self._restore_button.setEnabled(selected is not None)

    def _load_checkpoint_content(self, revision_id: int) -> Optional[str]:
        if revision_id not in self._loaded_checkpoint_contents:
            self._loaded_checkpoint_contents[revision_id] = self._checkpoint_content_loader(revision_id)
        return self._loaded_checkpoint_contents[revision_id]

    def _refresh_diff_view(self) -> None:
        self._refresh_button_states()
        selected = self._selected_checkpoint()
        if selected is None:
            self._diff_view.set_message("No revision selected.")
            return

        selected_content = self._load_checkpoint_content(selected.revision_id)
        if selected_content is None:
            self._diff_view.set_message("Could not load the selected revision.")
            return

        if self._compare_mode == "previous":
            previous_checkpoint = self._checkpoint_before_selected(selected)
            if previous_checkpoint is None:
                self._diff_view.set_message("No previous revision is available for comparison.")
                self._compare_current_button.setChecked(True)
                return
            previous_content = self._load_checkpoint_content(previous_checkpoint.revision_id)
            if previous_content is None:
                self._diff_view.set_message("Could not load the previous revision.")
                return
            self._diff_view.set_message(None)
            self._diff_view.set_texts(
                previous_content,
                selected_content,
                before_label=previous_checkpoint.created_at,
                after_label=selected.created_at,
            )
            return

        self._diff_view.set_message(None)
        self._diff_view.set_texts(
            self._current_text,
            selected_content,
            before_label="Current Buffer",
            after_label=selected.created_at,
        )

    def _handle_restore(self) -> None:
        selected = self._selected_checkpoint()
        if selected is None:
            return
        selected_content = self._load_checkpoint_content(selected.revision_id)
        if selected_content is None:
            QMessageBox.warning(self, "Local History", "Could not load the selected revision.")
            return
        self._restore_to_buffer(selected_content)
        self.accept()
