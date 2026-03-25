"""Project-wide read-only symbol reference discovery."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import tokenize

from app.core import constants


@dataclass(frozen=True)
class ReferenceHit:
    """One symbol reference location."""

    symbol_name: str
    file_path: str
    line_number: int
    column_number: int
    line_text: str
    is_definition: bool = False


@dataclass(frozen=True)
class ReferenceSearchResult:
    """Search result payload for find-references action."""

    symbol_name: str
    hits: list[ReferenceHit]

    @property
    def found(self) -> bool:
        return bool(self.hits)


def find_references(
    *,
    project_root: str,
    current_file_path: str,
    source_text: str,
    cursor_position: int,
) -> ReferenceSearchResult:
    """Find symbol references across project Python files."""
    symbol_name = extract_symbol_under_cursor(source_text, cursor_position)
    if not symbol_name:
        return ReferenceSearchResult(symbol_name="", hits=[])

    root = Path(project_root).expanduser().resolve()
    if not root.exists():
        return ReferenceSearchResult(symbol_name=symbol_name, hits=[])

    definition_positions = _collect_definition_positions(root, symbol_name=symbol_name)
    hits: list[ReferenceHit] = []
    for file_path in sorted(root.rglob("*.py")):
        if constants.PROJECT_META_DIRNAME in file_path.parts:
            continue
        hits.extend(
            _collect_references_from_file(
                file_path=file_path.resolve(),
                symbol_name=symbol_name,
                definition_positions=definition_positions,
            )
        )
    hits.sort(key=lambda item: (item.file_path, item.line_number, item.column_number))
    return ReferenceSearchResult(symbol_name=symbol_name, hits=hits)


def extract_symbol_under_cursor(source_text: str, cursor_position: int) -> str:
    """Return symbol token at cursor location."""
    safe_cursor = max(0, min(cursor_position, len(source_text)))
    left = safe_cursor
    while left > 0 and _is_symbol_character(source_text[left - 1]):
        left -= 1
    right = safe_cursor
    while right < len(source_text) and _is_symbol_character(source_text[right]):
        right += 1
    symbol = source_text[left:right].strip()
    if not symbol.isidentifier():
        return ""
    return symbol


def _collect_definition_positions(project_root: Path, *, symbol_name: str) -> set[tuple[str, int, int]]:
    positions: set[tuple[str, int, int]] = set()
    for file_path in sorted(project_root.rglob("*.py")):
        if constants.PROJECT_META_DIRNAME in file_path.parts:
            continue
        positions.update(_collect_file_definitions(file_path.resolve(), symbol_name=symbol_name))
    return positions


def _collect_file_definitions(file_path: Path, *, symbol_name: str) -> set[tuple[str, int, int]]:
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    try:
        syntax_tree = ast.parse(source)
    except SyntaxError:
        return set()

    source_lines = source.splitlines()
    positions: set[tuple[str, int, int]] = set()
    for node in ast.walk(syntax_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_name:
            column = _line_symbol_column(source_lines, int(node.lineno), symbol_name)
            positions.add((str(file_path), int(node.lineno), column))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol_name:
                    positions.add((str(file_path), int(target.lineno), int(target.col_offset)))
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == symbol_name:
                positions.add((str(file_path), int(target.lineno), int(target.col_offset)))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                alias_name = alias.asname or alias.name.split(".")[0]
                if alias_name == symbol_name:
                    column = _line_symbol_column(source_lines, int(node.lineno), symbol_name)
                    positions.add((str(file_path), int(node.lineno), column))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                alias_name = alias.asname or alias.name
                if alias_name == symbol_name:
                    column = _line_symbol_column(source_lines, int(node.lineno), symbol_name)
                    positions.add((str(file_path), int(node.lineno), column))
    return positions


def _collect_references_from_file(
    *,
    file_path: Path,
    symbol_name: str,
    definition_positions: set[tuple[str, int, int]],
) -> list[ReferenceHit]:
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return []

    line_lookup = source.splitlines()
    hits: list[ReferenceHit] = []
    try:
        token_stream = tokenize.generate_tokens(iter(source.splitlines(keepends=True)).__next__)
    except (tokenize.TokenError, IndentationError):
        return []

    for token in token_stream:
        if token.type != tokenize.NAME or token.string != symbol_name:
            continue
        line_number, column = token.start
        line_text = line_lookup[line_number - 1] if 0 < line_number <= len(line_lookup) else ""
        position_key = (str(file_path), int(line_number), int(column))
        hits.append(
            ReferenceHit(
                symbol_name=symbol_name,
                file_path=str(file_path),
                line_number=int(line_number),
                column_number=int(column),
                line_text=line_text.strip(),
                is_definition=position_key in definition_positions,
            )
        )
    return hits


def _is_symbol_character(character: str) -> bool:
    return character.isalnum() or character == "_"


def _line_symbol_column(source_lines: list[str], line_number: int, symbol_name: str) -> int:
    if line_number <= 0 or line_number > len(source_lines):
        return 0
    line = source_lines[line_number - 1]
    column = line.find(symbol_name)
    if column < 0:
        return 0
    return column
