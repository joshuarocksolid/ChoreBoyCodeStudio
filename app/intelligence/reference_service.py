"""Project-wide read-only symbol reference discovery."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import tokenize

from app.core import constants
from app.intelligence.semantic_facade import SemanticFacade
from app.intelligence.semantic_models import (
    SemanticOperationMetadata,
    approximate_metadata,
    unsupported_metadata,
)

_FACADE_BY_PROJECT_ROOT: dict[str, SemanticFacade] = {}


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
    metadata: SemanticOperationMetadata | None = None

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
        return ReferenceSearchResult(symbol_name="", hits=[], metadata=None)

    try:
        semantic_result = _facade(project_root).find_references(
            project_root=project_root,
            current_file_path=current_file_path,
            source_text=source_text,
            cursor_position=cursor_position,
        )
    except Exception as exc:
        return ReferenceSearchResult(
            symbol_name=symbol_name,
            hits=[],
            metadata=unsupported_metadata(
                "jedi",
                source="semantic_unavailable",
                unsupported_reason=f"runtime_unavailable: {exc.__class__.__name__}: {exc}",
            ),
        )

    if semantic_result is not None and (semantic_result.found or semantic_result.metadata.unsupported_reason):
        return ReferenceSearchResult(
            symbol_name=semantic_result.symbol_name,
            hits=[
                ReferenceHit(
                    symbol_name=hit.symbol_name,
                    file_path=hit.file_path,
                    line_number=hit.line_number,
                    column_number=hit.column_number,
                    line_text=hit.line_text,
                    is_definition=hit.is_definition,
                )
                for hit in semantic_result.hits
            ],
            metadata=semantic_result.metadata,
        )

    return _find_references_heuristic(project_root=project_root, source_text=source_text, cursor_position=cursor_position)


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


def _find_references_heuristic(
    *,
    project_root: str,
    source_text: str,
    cursor_position: int,
) -> ReferenceSearchResult:
    symbol_name = extract_symbol_under_cursor(source_text, cursor_position)
    if not symbol_name:
        return ReferenceSearchResult(symbol_name="", hits=[], metadata=None)

    root = Path(project_root).expanduser().resolve()
    if not root.exists():
        return ReferenceSearchResult(
            symbol_name=symbol_name,
            hits=[],
            metadata=approximate_metadata("token_scan", source="approximate", fallback_reason="missing_project_root"),
        )

    hits: list[ReferenceHit] = []
    for file_path in _iter_python_files(root):
        hits.extend(_collect_references_from_file(file_path=file_path, symbol_name=symbol_name))
    hits.sort(key=lambda item: (item.file_path, item.line_number, item.column_number))
    return ReferenceSearchResult(
        symbol_name=symbol_name,
        hits=hits,
        metadata=approximate_metadata("token_scan", source="approximate", fallback_reason="heuristic_lookup"),
    )


def _collect_file_definitions(
    file_path: Path,
    *,
    source: str,
    symbol_name: str,
) -> set[tuple[str, int, int]]:
    try:
        syntax_tree = ast.parse(source)
    except SyntaxError:
        return set()

    source_lines = source.splitlines()
    positions: set[tuple[str, int, int]] = set()
    file_path_text = str(file_path)
    for node in ast.walk(syntax_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_name:
            column = _line_symbol_column(source_lines, int(node.lineno), symbol_name)
            positions.add((file_path_text, int(node.lineno), column))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol_name:
                    positions.add((file_path_text, int(target.lineno), int(target.col_offset)))
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == symbol_name:
                positions.add((file_path_text, int(target.lineno), int(target.col_offset)))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                alias_name = alias.asname or alias.name.split(".")[0]
                if alias_name == symbol_name:
                    column = _line_symbol_column(source_lines, int(node.lineno), symbol_name)
                    positions.add((file_path_text, int(node.lineno), column))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                alias_name = alias.asname or alias.name
                if alias_name == symbol_name:
                    column = _line_symbol_column(source_lines, int(node.lineno), symbol_name)
                    positions.add((file_path_text, int(node.lineno), column))
    return positions


def _collect_references_from_file(
    *,
    file_path: Path,
    symbol_name: str,
) -> list[ReferenceHit]:
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return []

    definition_positions = _collect_file_definitions(
        file_path,
        source=source,
        symbol_name=symbol_name,
    )
    line_lookup = source.splitlines()
    hits: list[ReferenceHit] = []
    try:
        token_stream = tokenize.generate_tokens(iter(source.splitlines(keepends=True)).__next__)
    except (tokenize.TokenError, IndentationError):
        return []

    file_path_text = str(file_path)
    for token in token_stream:
        if token.type != tokenize.NAME or token.string != symbol_name:
            continue
        line_number, column = token.start
        line_text = line_lookup[line_number - 1] if 0 < line_number <= len(line_lookup) else ""
        position_key = (file_path_text, int(line_number), int(column))
        hits.append(
            ReferenceHit(
                symbol_name=symbol_name,
                file_path=file_path_text,
                line_number=int(line_number),
                column_number=int(column),
                line_text=line_text.strip(),
                is_definition=position_key in definition_positions,
            )
        )
    return hits


def _iter_python_files(project_root: Path) -> list[Path]:
    return [
        file_path
        for file_path in sorted(project_root.rglob("*.py"))
        if constants.PROJECT_META_DIRNAME not in file_path.parts
    ]


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


def _facade(project_root: str) -> SemanticFacade:
    normalized_root = str(Path(project_root).expanduser().resolve())
    cached = _FACADE_BY_PROJECT_ROOT.get(normalized_root)
    if cached is None:
        cache_db_path = str((Path(normalized_root) / constants.PROJECT_META_DIRNAME / constants.PROJECT_CACHE_DIRNAME / "semantic.sqlite3").resolve())
        cached = SemanticFacade(cache_db_path=cache_db_path)
        _FACADE_BY_PROJECT_ROOT[normalized_root] = cached
    return cached
