"""Post-render enhancements for the Markdown preview document."""

from __future__ import annotations

from PySide2.QtGui import (
    QColor,
    QFont,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextTable,
)

from app.shell.theme_tokens import ShellThemeTokens

_EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:")
_EXTERNAL_LINK_MARKER = " \u2197"
_MONOSPACE_FAMILIES = ("monospace", "Courier", "Courier New", "Consolas", "DejaVu Sans Mono")


def _is_external_href(href: str) -> bool:
    lowered = href.strip().lower()
    return lowered.startswith(_EXTERNAL_LINK_PREFIXES)


def _merge_char_format(cursor: QTextCursor, extra: QTextCharFormat) -> None:
    merged = QTextCharFormat(cursor.charFormat())
    merged.merge(extra)
    cursor.mergeCharFormat(merged)


def _apply_external_link_markers(document: QTextDocument, tokens: ShellThemeTokens) -> None:
    marker_format = QTextCharFormat()
    marker_format.setForeground(QColor(tokens.text_muted))

    insert_positions: list[int] = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                char_format = fragment.charFormat()
                if char_format.isAnchor():
                    href = char_format.anchorHref()
                    if href and _is_external_href(href):
                        insert_positions.append(fragment.position() + fragment.length())
            it += 1
        block = block.next()

    for position in sorted(insert_positions, reverse=True):
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        cursor.insertText(_EXTERNAL_LINK_MARKER, marker_format)


def _apply_monospace_to_code_blocks(document: QTextDocument) -> None:
    mono_format = QTextCharFormat()
    mono_format.setFontFamily("monospace")
    mono_format.setFontFixedPitch(True)

    for block in _iter_blocks(document):
        block_format = block.blockFormat()
        if block_format.hasProperty(QTextFormat.BlockCodeLanguage):
            cursor = QTextCursor(document)
            cursor.setPosition(block.position())
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            _merge_char_format(cursor, mono_format)
            continue

        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                char_format = fragment.charFormat()
                font = char_format.font()
                if font.family() in _MONOSPACE_FAMILIES or font.fixedPitch():
                    cursor = QTextCursor(document)
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.KeepAnchor)
                    _merge_char_format(cursor, mono_format)
            it += 1


def _apply_table_header_fallback(document: QTextDocument, tokens: ShellThemeTokens) -> None:
    header_format = QTextCharFormat()
    header_format.setFontWeight(QFont.Bold)
    header_format.setBackground(QColor(tokens.row_alt_bg))

    root = document.rootFrame()
    for table in root.childFrames():
        if not isinstance(table, QTextTable):
            continue
        if table.rows() <= 0 or table.columns() <= 0:
            continue
        for column in range(table.columns()):
            cell = table.cellAt(0, column)
            if cell.isValid():
                cursor = cell.firstCursorPosition()
                cursor.movePosition(QTextCursor.EndOfCell, QTextCursor.KeepAnchor)
                _merge_char_format(cursor, header_format)


def _iter_blocks(document: QTextDocument):
    block = document.begin()
    while block.isValid():
        yield block
        block = block.next()


def enhance_preview_document(
    document: QTextDocument,
    *,
    tokens: ShellThemeTokens,
    base_file_path: str | None = None,
) -> None:
    """Apply post-render visual enhancements that Qt document CSS cannot express reliably."""
    del base_file_path  # reserved for future local-link affordances
    _apply_monospace_to_code_blocks(document)
    _apply_table_header_fallback(document, tokens)
    _apply_external_link_markers(document, tokens)
