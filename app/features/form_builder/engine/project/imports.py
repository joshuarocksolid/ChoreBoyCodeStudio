"""Rewrite import sites when a form module changes path.

Rope's project object writes a ``.ropeproject`` directory. That is a hidden
path this engine does not create. Parso reports the import spans, and the
rename plan stores the resulting text edits.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import parso

from app.features.form_builder.engine.project.fs import OsFileSystem

_SKIP_DIRS = frozenset({"cbcs", "__pycache__", "vendor", "node_modules", ".git"})


def python_files(project_root: str, fs: OsFileSystem) -> Tuple[str, ...]:
    """``.py`` files under the project, skipping ``cbcs`` and hidden directories."""
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
            if fs.is_dir(path):
                stack.append(path)
            elif name.endswith(".py") and fs.is_file(path):
                found.append(path)
    return tuple(found)


def package_of(project_root: str, file_path: str) -> Tuple[str, ...]:
    rel = os.path.relpath(os.path.abspath(file_path), os.path.abspath(project_root))
    parts = rel.split(os.sep)[:-1]
    return tuple(part for part in parts if part not in (".", ""))


def rewrite_imports(source: str, mapping: Dict[str, str], package: Tuple[str, ...]) -> str:
    """Return ``source`` with imported modules in ``mapping`` pointed at the new path.

    ``mapping`` keys and values are absolute module paths (``forms.ui_invoice``).
    A file that does not parse is returned unchanged.
    """
    if not mapping or not source:
        return source
    tree = parso.parse(source)
    if _has_error(tree):
        return source
    spans = []  # type: List[Tuple[int, int, str]]
    for node in _walk(tree):
        if node.type == "import_name":
            _rewrite_import_name(node, source, mapping, spans)
        elif node.type == "import_from":
            _rewrite_import_from(node, source, mapping, package, spans)
    if not spans:
        return source
    return _apply(source, spans)


def _rewrite_import_name(node: parso.tree.NodeOrLeaf, source: str, mapping: Dict[str, str], spans: List[Tuple[int, int, str]]) -> None:
    for child in _walk(node):
        if child.type != "dotted_name" and child.type != "name":
            continue
        if child.type == "name" and child.parent is not None and child.parent.type == "dotted_name":
            continue
        text = child.get_code().strip()
        if text in mapping and mapping[text] != text:
            spans.append((_offset(source, child.start_pos), _offset(source, child.end_pos), mapping[text]))


def _rewrite_import_from(
    node: parso.tree.NodeOrLeaf,
    source: str,
    mapping: Dict[str, str],
    package: Tuple[str, ...],
    spans: List[Tuple[int, int, str]],
) -> None:
    level, dotted = _from_prefix(node)
    resolved = _resolve(level, dotted, package)
    if resolved and resolved in mapping:
        start, end = _module_bounds(node)
        if start is None or end is None:
            return
        rendered = _render_module(mapping[resolved], package, level)
        if rendered != source[_offset(source, start) : _offset(source, end)]:
            spans.append((_offset(source, start), _offset(source, end), rendered))
        return
    names = _imported_names(node)
    if not names or resolved is None:
        return
    stay = []  # type: List[str]
    moved = {}  # type: Dict[str, List[str]]
    changed = False
    for leaf, alias in names:
        full = resolved + "." + leaf if resolved else leaf
        target = mapping.get(full)
        if target is None:
            stay.append(_render_alias(leaf, alias))
            continue
        parent, new_leaf = _split_module(target)
        if parent == resolved:
            stay.append(_render_alias(new_leaf, alias))
            if new_leaf != leaf:
                changed = True
            continue
        moved.setdefault(parent, []).append(_render_alias(new_leaf, alias))
        changed = True
    if not changed:
        return
    lines = []
    if stay:
        lines.append("from %s import %s" % (_render_module(resolved, package, level), ", ".join(stay)))
    for parent, leaves in moved.items():
        lines.append("from %s import %s" % (parent, ", ".join(leaves)))
    spans.append((_offset(source, node.start_pos), _offset(source, node.end_pos), "\n".join(lines)))


def _from_prefix(node: parso.tree.NodeOrLeaf) -> Tuple[int, str]:
    level = 0
    dotted = ""
    for child in node.children:
        if child.type == "keyword" and child.value == "import":
            break
        if child.type == "keyword":
            continue
        if child.type == "operator" and child.value == ".":
            level += 1
            continue
        if child.type in ("name", "dotted_name"):
            dotted = child.get_code().strip()
    return level, dotted


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


def _module_bounds(node: parso.tree.NodeOrLeaf) -> Tuple[Optional[tuple], Optional[tuple]]:
    start = None
    end = None
    for child in node.children:
        if child.type == "keyword" and child.value == "from":
            continue
        if child.type == "keyword" and child.value == "import":
            break
        if start is None:
            start = child.start_pos
        end = child.end_pos
    return start, end


def _imported_names(node: parso.tree.NodeOrLeaf) -> List[Tuple[str, Optional[str]]]:
    found = []  # type: List[Tuple[str, Optional[str]]]
    seen = False
    pending = []  # type: List[parso.tree.NodeOrLeaf]
    for child in node.children:
        if child.type == "keyword" and child.value == "import":
            seen = True
            continue
        if seen:
            pending.append(child)
    for child in pending:
        pieces = [child]
        if child.type == "import_as_names":
            pieces = list(child.children)
        for piece in pieces:
            if piece.type == "name":
                found.append((piece.value, None))
            elif piece.type == "import_as_name":
                found.append((piece.children[0].value, piece.children[2].value))
    return found


def _render_alias(leaf: str, alias: Optional[str]) -> str:
    if alias:
        return "%s as %s" % (leaf, alias)
    return leaf


def _split_module(module: str) -> Tuple[str, str]:
    if "." not in module:
        return "", module
    parent, leaf = module.rsplit(".", 1)
    return parent, leaf


def _render_module(module: str, package: Tuple[str, ...], level: int) -> str:
    if level <= 0:
        return module
    if level - 1 > len(package):
        return module
    base = package[: len(package) - (level - 1)]
    parts = tuple(module.split(".")) if module else ()
    if parts[: len(base)] != base:
        return module
    rest = parts[len(base) :]
    dots = "." * level
    if not rest:
        return dots
    return dots + ".".join(rest)


def _apply(source: str, spans: List[Tuple[int, int, str]]) -> str:
    ordered = sorted(spans, key=lambda item: item[0], reverse=True)
    text = source
    for start, end, replacement in ordered:
        text = text[:start] + replacement + text[end:]
    return text


def _offset(source: str, pos: tuple) -> int:
    line, col = pos
    lines = source.splitlines(keepends=True)
    return sum(len(item) for item in lines[: line - 1]) + col


def _walk(node: parso.tree.NodeOrLeaf):
    yield node
    for child in getattr(node, "children", ()) or ():
        for item in _walk(child):
            yield item


def _has_error(node: parso.tree.NodeOrLeaf) -> bool:
    if node.type in ("error_node", "error_leaf"):
        return True
    for child in getattr(node, "children", ()) or ():
        if _has_error(child):
            return True
    return False
