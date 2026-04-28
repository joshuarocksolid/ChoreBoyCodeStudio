"""List model holding :class:`CompletionItem` rows for the popup view.

Exposes the raw item, the precomputed fuzzy match ranges for the label, and
the kind style as custom roles so the delegate can render rows without
re-parsing the underlying data on every paint.
"""

from __future__ import annotations

from PySide2.QtCore import QAbstractListModel, QModelIndex, Qt

from app.editors.completion_popup.completion_kind_style import (
    KindGlyphStyle,
    kind_style_for,
)
from app.intelligence.completion_models import CompletionItem
from app.shell.theme_tokens import ShellThemeTokens


# Custom item roles, namespaced into the user-role band.
ItemRole = Qt.UserRole + 1
MatchRangesRole = Qt.UserRole + 2
KindStyleRole = Qt.UserRole + 3


def compute_match_ranges(label: str, prefix: str) -> list[tuple[int, int]]:
    """Return ``(start, length)`` ranges within ``label`` that match ``prefix``.

    Two strategies, in order:

    1. Case-insensitive prefix match -> single contiguous range from index 0.
    2. Case-insensitive subsequence match -> one range per matched character.

    Returns an empty list when no match is found.
    """

    if not prefix:
        return []
    if not label:
        return []

    lower_label = label.lower()
    lower_prefix = prefix.lower()

    if lower_label.startswith(lower_prefix):
        return [(0, len(prefix))]

    ranges: list[tuple[int, int]] = []
    label_index = 0
    for ch in lower_prefix:
        found = lower_label.find(ch, label_index)
        if found == -1:
            return []
        if ranges and ranges[-1][0] + ranges[-1][1] == found:
            start, length = ranges[-1]
            ranges[-1] = (start, length + 1)
        else:
            ranges.append((found, 1))
        label_index = found + 1
    return ranges


class CompletionItemModel(QAbstractListModel):
    """Read-only list of completion items with precomputed render metadata."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._items: list[CompletionItem] = []
        self._prefix: str = ""
        self._match_ranges: list[list[tuple[int, int]]] = []
        self._kind_styles: dict = {}
        self._tokens: ShellThemeTokens | None = None

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object:
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._items):
            return None
        item = self._items[row]
        if role == Qt.DisplayRole:
            return item.label
        if role == ItemRole:
            return item
        if role == MatchRangesRole:
            return self._match_ranges[row]
        if role == KindStyleRole:
            return self._resolve_kind_style(item)
        return None

    def set_items(self, items: list[CompletionItem], prefix: str) -> None:
        """Replace the model contents; precompute match ranges for each row."""
        self.beginResetModel()
        self._items = list(items)
        self._prefix = prefix
        self._match_ranges = [compute_match_ranges(item.label, prefix) for item in self._items]
        self.endResetModel()

    def replace_item(self, item: CompletionItem) -> bool:
        """Replace one row by item identity without rebuilding the full list."""

        for row, existing in enumerate(self._items):
            if not _same_completion_identity(existing, item):
                continue
            self._items[row] = item
            self._match_ranges[row] = compute_match_ranges(item.label, self._prefix)
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [Qt.DisplayRole, ItemRole, MatchRangesRole])
            return True
        return False

    def clear(self) -> None:
        """Drop all rows."""
        if not self._items:
            return
        self.beginResetModel()
        self._items = []
        self._match_ranges = []
        self.endResetModel()

    def set_theme_tokens(self, tokens: ShellThemeTokens | None) -> None:
        """Update the theme tokens used to resolve per-kind styles."""
        self._tokens = tokens
        self._kind_styles = {}
        if not self._items:
            return
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self._items) - 1, 0)
        self.dataChanged.emit(top_left, bottom_right, [KindStyleRole])

    def item_at(self, row: int) -> CompletionItem | None:
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row]

    def items(self) -> list[CompletionItem]:
        return list(self._items)

    def prefix(self) -> str:
        return self._prefix

    def _resolve_kind_style(self, item: CompletionItem) -> KindGlyphStyle | None:
        if self._tokens is None:
            return None
        cached = self._kind_styles.get(item.kind)
        if cached is not None:
            return cached
        style = kind_style_for(item.kind, self._tokens)
        self._kind_styles[item.kind] = style
        return style


def _same_completion_identity(left: CompletionItem, right: CompletionItem) -> bool:
    if left.item_id and right.item_id:
        return left.item_id == right.item_id
    return (
        left.label == right.label
        and left.insert_text == right.insert_text
        and left.kind == right.kind
        and left.source == right.source
    )
