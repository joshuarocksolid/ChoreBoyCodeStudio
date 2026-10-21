"""List model holding the ranked rows shown by the completion popup."""

from __future__ import annotations

from typing import Sequence, Tuple

from PySide2.QtCore import QAbstractListModel, QModelIndex, Qt

from app.editors.completion_popup.completion_kind_style import KindGlyphStyle, kind_style_for
from app.intelligence.completion_models import CompletionItem, CompletionKind
from app.shell.theme_tokens import ShellThemeTokens

ItemRole = Qt.UserRole + 1
MatchPositionsRole = Qt.UserRole + 2
KindStyleRole = Qt.UserRole + 3
ShortTypeRole = Qt.UserRole + 4

_RUNTIME_ENGINES = frozenset({"runtime_introspection", "runtime_dir"})


def row_short_type(item: CompletionItem) -> str:
    """Return the muted type shown at the right of a row (``method``, ``str``...)."""

    if item.engine in _RUNTIME_ENGINES and item.semantic_kind:
        return item.semantic_kind
    if item.kind == CompletionKind.TEXT:
        return ""
    return item.kind.value


class CompletionItemModel(QAbstractListModel):
    """Read-only ranked rows: an item plus the matched character positions."""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._items: list[CompletionItem] = []
        self._positions: list[Tuple[int, ...]] = []
        self._kind_styles: dict[CompletionKind, KindGlyphStyle] = {}
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
        if role == MatchPositionsRole:
            return self._positions[row]
        if role == KindStyleRole:
            return self._kind_style(item.kind)
        if role == ShortTypeRole:
            return row_short_type(item)
        return None

    def set_rows(self, items: Sequence[CompletionItem], positions: Sequence[Tuple[int, ...]]) -> None:
        """Replace every row."""

        self.beginResetModel()
        self._items = list(items)
        self._positions = list(positions)
        self.endResetModel()

    def replace_item(self, item: CompletionItem) -> bool:
        """Swap in lazily resolved metadata for the row with the same identity."""

        for row, existing in enumerate(self._items):
            if not same_completion_identity(existing, item):
                continue
            self._items[row] = item
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [ItemRole, ShortTypeRole])
            return True
        return False

    def clear(self) -> None:
        if not self._items:
            return
        self.beginResetModel()
        self._items = []
        self._positions = []
        self.endResetModel()

    def set_theme_tokens(self, tokens: ShellThemeTokens | None) -> None:
        self._tokens = tokens
        self._kind_styles = {}
        if self._items:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._items) - 1, 0), [KindStyleRole])

    def item_at(self, row: int) -> CompletionItem | None:
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row]

    def row_of_label(self, label: str) -> int:
        for row, item in enumerate(self._items):
            if item.label == label:
                return row
        return -1

    def labels(self) -> list[str]:
        return [item.label for item in self._items]

    def _kind_style(self, kind: CompletionKind) -> KindGlyphStyle | None:
        if self._tokens is None:
            return None
        style = self._kind_styles.get(kind)
        if style is None:
            style = kind_style_for(kind, self._tokens)
            self._kind_styles[kind] = style
        return style


def same_completion_identity(left: CompletionItem, right: CompletionItem) -> bool:
    # Rows are one per label; a later tier may have merged a different item id in.
    return left.label == right.label
