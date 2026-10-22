"""Rewrite import sites when a form module changes path.

Rope's project object writes a ``.ropeproject`` directory. That is a hidden
path this engine does not create. ``ast`` reports the import spans, and
``tokenize`` slices those spans without eating comments.
"""

from __future__ import annotations

import ast
import io
import os
import tokenize
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.features.form_builder.engine.project.fs import OsFileSystem, inside_project

_SKIP_DIRS = frozenset({"cbcs", "__pycache__", "vendor", "node_modules", ".git"})


@dataclass(frozen=True)
class ImportRewrite:
    """``parsed`` is false when the file was left unchanged because it could not be parsed."""

    text: str
    changed: bool
    parsed: bool


@dataclass(frozen=True)
class _Alias:
    name: str
    asname: Optional[str]
    start: int
    end: int


class _Source:
    """Character offsets. Line breaks are ``\\n`` only, matching ``ast`` and ``tokenize``."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.line_starts = [0]  # type: List[int]
        index = 0
        while index < len(source):
            if source[index] == "\n":
                self.line_starts.append(index + 1)
            index += 1

    def char_at(self, line: int, col: int) -> int:
        if line < 1 or line > len(self.line_starts):
            return len(self.source)
        return self.line_starts[line - 1] + col

    def ast_at(self, line: int, byte_col: int) -> int:
        """``ast`` columns are UTF-8 byte offsets on the ``\\n``-split line."""
        if line < 1 or line > len(self.line_starts):
            return len(self.source)
        start = self.line_starts[line - 1]
        end = self.line_starts[line] if line < len(self.line_starts) else len(self.source)
        body = self.source[start:end]
        if body.endswith("\n"):
            body = body[:-1]
        char_col = len(body.encode("utf-8")[:byte_col].decode("utf-8"))
        return start + char_col

    def span(self, node: ast.AST) -> Tuple[int, int]:
        return (
            self.ast_at(node.lineno, node.col_offset),
            self.ast_at(node.end_lineno, node.end_col_offset),
        )

    def indent(self, line: int) -> str:
        start = self.line_starts[line - 1]
        end = self.line_starts[line] if line < len(self.line_starts) else len(self.source)
        text = self.source[start:end]
        return text[: len(text) - len(text.lstrip(" \t"))]


def python_files(project_root: str, fs: OsFileSystem) -> Tuple[str, ...]:
    """``.py`` files under the project, skipping ``cbcs``, hidden names, and symlinks."""
    root = os.path.abspath(project_root)
    found = []  # type: List[str]
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            names = fs.listdir(current)
        except OSError:
            continue
        for name in names:
            if name.startswith(".") or name in _SKIP_DIRS:
                continue
            path = os.path.join(current, name)
            if os.path.islink(path) or not inside_project(path, root):
                continue
            if fs.is_dir(path):
                stack.append(path)
            elif name.endswith(".py") and fs.is_file(path):
                found.append(path)
    return tuple(found)


def package_of(project_root: str, file_path: str) -> Tuple[str, ...]:
    rel = os.path.relpath(os.path.abspath(file_path), os.path.abspath(project_root))
    parts = rel.split(os.sep)[:-1]
    return tuple(part for part in parts if part not in (".", ""))


def rewrite_imports(source: str, mapping: Dict[str, str], package: Tuple[str, ...]) -> ImportRewrite:
    """Point imported modules in ``mapping`` at their new absolute module paths.

    A name imported with no alias keeps its old binding (``from forms import
    ui_bill as ui_invoice``). A bare ``import forms.ui_invoice`` keeps working
    by moving the ``forms.ui_invoice`` attribute uses onto the new module.
    A file that does not parse, or whose rewrite would not parse, is unchanged.
    """
    if not mapping or not source:
        return ImportRewrite(source, False, True)
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return ImportRewrite(source, False, False)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return ImportRewrite(source, False, False)
    located = _Source(source)
    spans = []  # type: List[Tuple[int, int, str]]
    chains = {}  # type: Dict[str, str]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _edit_import(node, source, located, tokens, mapping, spans, chains)
        elif isinstance(node, ast.ImportFrom):
            _edit_from(node, source, located, tokens, mapping, package, spans)
    _edit_chains(tree, source, located, chains, spans)
    if not spans:
        return ImportRewrite(source, False, True)
    if _overlaps(spans):
        return ImportRewrite(source, False, False)
    rewritten = _apply(source, spans)
    try:
        ast.parse(rewritten)
    except (SyntaxError, ValueError):
        return ImportRewrite(source, False, False)
    return ImportRewrite(rewritten, rewritten != source, True)


def _edit_import(
    node: ast.Import,
    source: str,
    located: _Source,
    tokens: List[tokenize.TokenInfo],
    mapping: Dict[str, str],
    spans: List[Tuple[int, int, str]],
    chains: Dict[str, str],
) -> None:
    start, end = located.span(node)
    aliases = _aliases_after_import(located, _tokens_inside(located, tokens, start, end))
    for alias in aliases:
        target = mapping.get(alias.name)
        if target is None or target == alias.name:
            continue
        if alias.asname:
            rendered = "%s as %s" % (target, alias.asname)
        else:
            # The bare import binds the dotted path, so later attributes have to move too.
            rendered = target
            chains[alias.name] = target
        if source[alias.start : alias.end] != rendered:
            spans.append((alias.start, alias.end, rendered))


def _edit_from(
    node: ast.ImportFrom,
    source: str,
    located: _Source,
    tokens: List[tokenize.TokenInfo],
    mapping: Dict[str, str],
    package: Tuple[str, ...],
    spans: List[Tuple[int, int, str]],
) -> None:
    base = _resolve(node.level, node.module or "", package)
    if base is None:
        return
    start, end = located.span(node)
    stmt_tokens = _tokens_inside(located, tokens, start, end)
    if base in mapping and mapping[base] != base:
        module_span = _module_span(located, stmt_tokens)
        if module_span is None:
            return
        rendered = _render_module(mapping[base], package, node.level)
        if source[module_span[0] : module_span[1]] != rendered:
            spans.append((module_span[0], module_span[1], rendered))
        return
    aliases = _aliases_after_import(located, stmt_tokens)
    if not aliases:
        return
    stay = []  # type: List[Tuple[int, int, str]]
    moved = {}  # type: Dict[str, List[str]]
    moved_spans = []  # type: List[Tuple[int, int]]
    for alias in aliases:
        full = base + "." + alias.name if base else alias.name
        target = mapping.get(full)
        if target is None or target == full:
            continue
        parent, leaf = _split_module(target)
        rendered = _render_alias(leaf, alias.asname, alias.name)
        if parent == base:
            if source[alias.start : alias.end] != rendered:
                stay.append((alias.start, alias.end, rendered))
            continue
        moved.setdefault(parent, []).append(rendered)
        moved_spans.append((alias.start, alias.end))
    if not stay and not moved:
        return
    if not moved:
        spans.extend(stay)
        return
    if len(moved_spans) == len(aliases) and len(moved) == 1:
        _retarget_module(source, located, stmt_tokens, node.level, package, next(iter(moved)), spans)
        for alias in aliases:
            full = base + "." + alias.name if base else alias.name
            target = mapping.get(full)
            if target is None:
                continue
            _parent, leaf = _split_module(target)
            rendered = _render_alias(leaf, alias.asname, alias.name)
            if source[alias.start : alias.end] != rendered:
                spans.append((alias.start, alias.end, rendered))
        return
    _rebuild_from(source, located, node, stmt_tokens, aliases, mapping, base, package, moved, start, end, spans)


def _retarget_module(
    source: str,
    located: _Source,
    stmt_tokens: List[tokenize.TokenInfo],
    level: int,
    package: Tuple[str, ...],
    parent: str,
    spans: List[Tuple[int, int, str]],
) -> None:
    module_span = _module_span(located, stmt_tokens)
    if module_span is None:
        return
    rendered = _render_module(parent, package, level)
    if source[module_span[0] : module_span[1]] != rendered:
        spans.append((module_span[0], module_span[1], rendered))


def _rebuild_from(
    source: str,
    located: _Source,
    node: ast.ImportFrom,
    stmt_tokens: List[tokenize.TokenInfo],
    aliases: List[_Alias],
    mapping: Dict[str, str],
    base: str,
    package: Tuple[str, ...],
    moved: Dict[str, List[str]],
    start: int,
    end: int,
    spans: List[Tuple[int, int, str]],
) -> None:
    """One import became several. Continuation lines keep the original indent."""
    module_span = _module_span(located, stmt_tokens)
    module_text = source[module_span[0] : module_span[1]] if module_span else "." * max(node.level, 1)
    remaining = []  # type: List[str]
    for alias in aliases:
        full = base + "." + alias.name if base else alias.name
        target = mapping.get(full)
        if target is None or target == full:
            remaining.append(source[alias.start : alias.end])
            continue
        parent, _leaf = _split_module(target)
        if parent == base:
            remaining.append(_render_alias(_leaf, alias.asname, alias.name))
    indent = located.indent(node.lineno)
    lines = []  # type: List[str]
    if remaining:
        lines.append("from %s import %s" % (module_text, ", ".join(remaining)))
    lines.extend(_from_line(parent, names, package, node.level) for parent, names in moved.items())
    comments = [tok.string for tok in stmt_tokens if tok.type == tokenize.COMMENT]
    if comments and lines:
        lines[0] = lines[0] + "  " + " ".join(comments)
    if not lines:
        return
    replacement = lines[0] + "".join("\n" + indent + line for line in lines[1:])
    spans.append((start, end, replacement))


def _from_line(parent: str, names: List[str], package: Tuple[str, ...], level: int) -> str:
    module = _render_module(parent, package, level) if parent else "." * max(level, 1)
    return "from %s import %s" % (module, ", ".join(names))


def _edit_chains(
    tree: ast.AST,
    source: str,
    located: _Source,
    chains: Dict[str, str],
    spans: List[Tuple[int, int, str]],
) -> None:
    if not chains:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        dotted = _dotted(node)
        if dotted is None or dotted not in chains:
            continue
        start, end = located.span(node)
        rendered = chains[dotted]
        if source[start:end] != rendered:
            spans.append((start, end, rendered))


def _dotted(node: ast.AST) -> Optional[str]:
    parts = []  # type: List[str]
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    parts.reverse()
    return ".".join(parts)


def _tokens_inside(
    located: _Source,
    tokens: List[tokenize.TokenInfo],
    start: int,
    end: int,
) -> List[tokenize.TokenInfo]:
    found = []
    for tok in tokens:
        tok_start = located.char_at(tok.start[0], tok.start[1])
        if start <= tok_start < end:
            found.append(tok)
    return found


def _aliases_after_import(located: _Source, tokens: List[tokenize.TokenInfo]) -> List[_Alias]:
    index = 0
    while index < len(tokens):
        tok = tokens[index]
        index += 1
        if tok.type == tokenize.NAME and tok.string == "import":
            break
    else:
        return []
    found = []  # type: List[_Alias]
    while index < len(tokens):
        tok = tokens[index]
        if tok.type in (
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.COMMENT,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENCODING,
            tokenize.ENDMARKER,
        ) or tok.string in (",", "(", ")"):
            index += 1
            continue
        if tok.type != tokenize.NAME:
            index += 1
            continue
        start = located.char_at(tok.start[0], tok.start[1])
        parts = [tok.string]
        end = located.char_at(tok.end[0], tok.end[1])
        index += 1
        while index < len(tokens) and tokens[index].string == ".":
            index += 1
            if index < len(tokens) and tokens[index].type == tokenize.NAME:
                parts.append(tokens[index].string)
                end = located.char_at(tokens[index].end[0], tokens[index].end[1])
                index += 1
            else:
                break
        asname = None
        if index < len(tokens) and tokens[index].type == tokenize.NAME and tokens[index].string == "as":
            index += 1
            if index < len(tokens) and tokens[index].type == tokenize.NAME:
                asname = tokens[index].string
                end = located.char_at(tokens[index].end[0], tokens[index].end[1])
                index += 1
        found.append(_Alias(".".join(parts), asname, start, end))
    return found


def _module_span(located: _Source, tokens: List[tokenize.TokenInfo]) -> Optional[Tuple[int, int]]:
    index = 0
    while index < len(tokens) and not (tokens[index].type == tokenize.NAME and tokens[index].string == "from"):
        index += 1
    if index >= len(tokens):
        return None
    index += 1
    start = None  # type: Optional[int]
    end = None  # type: Optional[int]
    while index < len(tokens):
        tok = tokens[index]
        if tok.type == tokenize.NAME and tok.string == "import":
            break
        if tok.string == "." or tok.type == tokenize.NAME:
            tok_start = located.char_at(tok.start[0], tok.start[1])
            tok_end = located.char_at(tok.end[0], tok.end[1])
            if start is None:
                start = tok_start
            end = tok_end
        index += 1
    if start is None or end is None:
        return None
    return start, end


def _resolve(level: int, dotted: str, package: Tuple[str, ...]) -> Optional[str]:
    if level == 0:
        return dotted or None
    if level - 1 > len(package):
        return None
    base = package[: len(package) - (level - 1)]
    parts = list(base)
    if dotted:
        parts.extend(part for part in dotted.split(".") if part)
    if not parts:
        return ""
    return ".".join(parts)


def _render_alias(leaf: str, alias: Optional[str], old: str) -> str:
    if alias:
        return "%s as %s" % (leaf, alias)
    if leaf != old:
        return "%s as %s" % (leaf, old)
    return leaf


def _split_module(module: str) -> Tuple[str, str]:
    if "." not in module:
        return "", module
    parent, leaf = module.rsplit(".", 1)
    return parent, leaf


def _render_module(module: str, package: Tuple[str, ...], level: int) -> str:
    if level <= 0:
        return module
    if not module:
        return "." * level
    if level - 1 > len(package):
        return module
    base = package[: len(package) - (level - 1)]
    parts = tuple(module.split("."))
    if parts[: len(base)] != base:
        return module
    rest = parts[len(base) :]
    dots = "." * level
    if not rest:
        return dots
    return dots + ".".join(rest)


def _apply(source: str, spans: List[Tuple[int, int, str]]) -> str:
    ordered = sorted(spans, key=lambda item: (item[0], item[1]), reverse=True)
    text = source
    for start, end, replacement in ordered:
        text = text[:start] + replacement + text[end:]
    return text


def _overlaps(spans: List[Tuple[int, int, str]]) -> bool:
    ordered = sorted(spans, key=lambda item: (item[0], item[1]))
    last = -1
    for start, end, _replacement in ordered:
        if start < last:
            return True
        last = max(last, end)
    return False
