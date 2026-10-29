"""Read a window file without importing it (CONTRACTS section 16.1).

The pre-scan exists because a crafted line under the 1 MB cap overflows the
C stack inside ``ast.parse`` on Python 3.9 and kills the editor. Token limits
run first, and only a file that passes them is parsed.
"""

from __future__ import annotations

import ast
import hashlib
import io
import os
import stat
import threading
import tokenize
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.project.custom_widgets import module_file
from app.features.form_builder.engine.project.fs import inside_project

MAX_BYTES = 1_000_000
_TOKEN_LIMIT = 2000
_BRACKET_LIMIT = 100
_INDENT_LIMIT = 100
_CACHE_LIMIT = 64
_CHAIN_LIMIT = 3
_PYSIDE = ("PySide6", "PySide2", "PySide", "shiboken6", "shiboken2")

_CACHE_LOCK = threading.Lock()
_FILE_CACHE: Dict[Tuple[str, int, int], "WindowRead"] = {}
_TEXT_CACHE: Dict[str, "WindowRead"] = {}


@dataclass(frozen=True)
class MethodFacts:
    """One method the reader found. ``source_hash`` ignores line endings."""

    name: str
    line: int
    end_line: int
    params: Tuple[str, ...]
    required: int
    has_varargs: bool
    decorators: Tuple[str, ...]
    slot_types: Tuple[Tuple[str, ...], ...]
    kind: str
    body_is_empty: bool
    source_hash: str


@dataclass(frozen=True)
class ClassFacts:
    """The window class, plus the line where a new method is inserted."""

    name: str
    line: int
    base_names: Tuple[str, ...]
    last_line: int
    indent_unit: str
    blank_line_style: int
    line_ending: str
    methods: Tuple[MethodFacts, ...]


@dataclass(frozen=True)
class WindowFacts:
    """What ``read_window`` keeps. M6.0s's ``window_facts.py`` is the shared stub.

    Until that module lands, these dataclasses are the types the checks use.
    ``base_methods`` are methods of project base classes that were read.
    ``unread_bases`` are project bases that were not.
    """

    window: Optional[ClassFacts]
    classes: Tuple[ClassFacts, ...] = ()
    base_methods: Tuple[MethodFacts, ...] = ()
    unread_bases: Tuple[str, ...] = ()
    relative: str = ""


@dataclass(frozen=True)
class WindowRead:
    """``status`` is ``ok``, ``missing``, ``refused`` or ``syntax_error``."""

    status: str
    reason: str
    line: int
    facts: Optional[WindowFacts]
    relative: str = ""
    source: Optional[str] = None


def file_label(relative: str) -> str:
    name = relative.replace("\\", "/").rsplit("/", 1)[-1]
    return name or relative or "the window file"


def method_source_hash(text: str) -> str:
    """sha256 of method lines from ``def`` to the last line, LF-normalised."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def read_window(project_root: str, relative: str, text: Optional[str] = None) -> WindowRead:
    """The window class and its methods. Never imports or runs the file."""
    relative = relative.replace("\\", "/")
    if text is None:
        cached = _cached_file(project_root, relative)
        if cached is not None:
            return cached
        read = _read_path(project_root, relative, chain=())
        _store_file(project_root, relative, read)
        return read
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with _CACHE_LOCK:
        cached_text = _TEXT_CACHE.get(digest)
    if cached_text is not None and cached_text.relative == relative:
        return cached_text
    read = _read_text(project_root, relative, text, chain=())
    with _CACHE_LOCK:
        _remember(_TEXT_CACHE, digest, read)
    return read


def _cached_file(project_root: str, relative: str) -> Optional[WindowRead]:
    full = os.path.join(project_root, *relative.split("/"))
    if not inside_project(full, project_root) or not os.path.isfile(full):
        return None
    try:
        info = os.stat(full)
    except OSError:
        return None
    key = (os.path.abspath(full), info.st_mtime_ns, info.st_size)
    with _CACHE_LOCK:
        return _FILE_CACHE.get(key)


def _store_file(project_root: str, relative: str, read: WindowRead) -> None:
    full = os.path.join(project_root, *relative.split("/"))
    try:
        info = os.stat(full)
    except OSError:
        return
    key = (os.path.abspath(full), getattr(info, "st_mtime_ns", 0), info.st_size)
    with _CACHE_LOCK:
        _remember(_FILE_CACHE, key, read)


def _remember(cache: Dict, key: object, read: WindowRead) -> None:
    if key in cache:
        cache.pop(key)
    cache[key] = read
    while len(cache) > _CACHE_LIMIT:
        cache.pop(next(iter(cache)))


def _read_path(
    project_root: str,
    relative: str,
    chain: Tuple[str, ...],
    focus: Optional[str] = None,
) -> WindowRead:
    label = file_label(relative)
    full = os.path.join(project_root, *relative.split("/")) if project_root else relative
    if not project_root or not inside_project(full, project_root):
        return WindowRead("refused", "it is outside the project", 0, None, relative)
    if not os.path.lexists(full):
        return WindowRead("missing", "the file is missing", 0, None, relative)
    data = _read_regular(full)
    if data is None:
        if os.path.islink(full) and not inside_project(os.path.realpath(full), project_root):
            return WindowRead("refused", "it is outside the project", 0, None, relative)
        if os.path.isfile(full):
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            if size > MAX_BYTES:
                return WindowRead("refused", "it is larger than 1 MB", 0, None, relative)
        return WindowRead("refused", "it is not a regular file", 0, None, relative)
    decoded = _decode(data)
    if decoded is None:
        return WindowRead("refused", "it isn't UTF-8 text", 0, None, relative)
    text, _encoding = decoded
    return _read_text(project_root, relative, text, chain, focus)


def _read_regular(full: str) -> Optional[bytes]:
    """Bytes of a regular file of at most 1 MB, opened non-blocking.

    Same rules as the custom-widget reader. This copy does not use that
    reader's cache, which returns empty bytes on a hit.
    """
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(full, flags)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            return None
        chunks: List[bytes] = []
        size = 0
        while size <= MAX_BYTES:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if size > MAX_BYTES:
            return None
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(fd)


def _decode(data: bytes) -> Optional[Tuple[str, str]]:
    try:
        encoding, _consumed = tokenize.detect_encoding(io.BytesIO(data).readline)
    except (SyntaxError, LookupError, ValueError):
        return None
    allowed = encoding.lower().replace("_", "-")
    if allowed not in ("utf-8", "utf-8-sig", "ascii"):
        return None
    try:
        text = data.decode(encoding)
    except (UnicodeError, LookupError):
        return None
    if "\0" in text:
        return None
    return text, encoding


def _read_text(
    project_root: str,
    relative: str,
    text: str,
    chain: Tuple[str, ...],
    focus: Optional[str] = None,
) -> WindowRead:
    if "\0" in text:
        return WindowRead("refused", "it contains a NUL byte", 0, None, relative)
    scanned = _prescan(text)
    if scanned is not None:
        status, line, reason = scanned
        return WindowRead(status, reason, line, None, relative)
    try:
        tree = ast.parse(text, type_comments=False)
    except (SyntaxError, ValueError) as exc:
        line = exc.lineno or 0 if isinstance(exc, SyntaxError) else 0
        return WindowRead("syntax_error", "", line, None, relative)
    except (RecursionError, MemoryError):
        return WindowRead("refused", "the file is too deeply nested to read", 0, None, relative)
    lines = text.splitlines()
    ending = _line_ending(text)
    classes = tuple(
        _class_facts(node, lines, ending)
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    )
    window = _find_window(tree, lines, ending)
    target = window
    if focus:
        target = next((item for item in classes if item.name == focus), None)
    base_methods: List[MethodFacts] = []
    unread: List[str] = []
    if target is not None and len(chain) + 1 < _CHAIN_LIMIT:
        imports = _top_imports(tree)
        seen = chain + (relative,)
        for base in target.base_names:
            _follow_base(
                project_root, base, imports, seen, base_methods, unread,
            )
    elif target is not None:
        imports = _top_imports(tree)
        for base in target.base_names:
            if _is_project_base(base, imports):
                unread.append(base)
    shown = target if focus else window
    facts = WindowFacts(
        window=shown,
        classes=classes,
        base_methods=tuple(base_methods),
        unread_bases=tuple(unread),
        relative=relative,
    )
    return WindowRead("ok", "", 0, facts, relative, text)


def _follow_base(
    project_root: str,
    base: str,
    imports: Dict[str, Tuple[str, str]],
    seen: Tuple[str, ...],
    methods: List[MethodFacts],
    unread: List[str],
) -> None:
    binding = imports.get(base)
    if binding is None:
        return
    module, class_name = binding
    if module.split(".", 1)[0] in _PYSIDE:
        return
    relative = module_file(project_root, module)
    if not relative or relative in seen:
        unread.append(base)
        return
    read = _read_path(project_root, relative, seen, focus=class_name)
    if read.status != "ok" or read.facts is None:
        unread.append(base)
        return
    found = _class_named(read, class_name)
    if found is None:
        unread.append(base)
        return
    methods.extend(found.methods)
    methods.extend(read.facts.base_methods)
    for name in read.facts.unread_bases:
        if name not in unread:
            unread.append(name)


def _class_named(read: WindowRead, class_name: str) -> Optional[ClassFacts]:
    if read.facts is None:
        return None
    for item in read.facts.classes:
        if item.name == class_name:
            return item
    window = read.facts.window
    if window is not None and window.name == class_name:
        return window
    return None


def _is_project_base(base: str, imports: Dict[str, Tuple[str, str]]) -> bool:
    binding = imports.get(base)
    if binding is None:
        return False
    return binding[0].split(".", 1)[0] not in _PYSIDE


def _prescan(text: str) -> Optional[Tuple[str, int, str]]:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        count = 0
        depth = 0
        level = 0
        line = 1
        for tok in tokens:
            line = tok.start[0] or line
            if tok.type == tokenize.INDENT:
                level += 1
                if level > _INDENT_LIMIT:
                    return ("refused", line, "the indentation is too deep")
                continue
            if tok.type == tokenize.DEDENT:
                level = max(0, level - 1)
                continue
            if tok.type == tokenize.OP and tok.string in "([{":
                depth += 1
                if depth > _BRACKET_LIMIT:
                    return ("refused", line, "the brackets are nested too deeply")
            elif tok.type == tokenize.OP and tok.string in ")]}":
                depth = max(0, depth - 1)
            if tok.type in (
                tokenize.NEWLINE,
                tokenize.ENDMARKER,
                tokenize.NL,
                tokenize.COMMENT,
                tokenize.ENCODING,
                tokenize.INDENT,
                tokenize.DEDENT,
            ):
                if tok.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
                    if count > _TOKEN_LIMIT:
                        return ("refused", line, "a line has too many tokens")
                    count = 0
                continue
            count += 1
            if count > _TOKEN_LIMIT:
                return ("refused", line, "a line has too many tokens")
    except tokenize.TokenError as exc:
        return ("syntax_error", _token_line(exc), "")
    except (IndentationError, TabError) as exc:
        return ("syntax_error", getattr(exc, "lineno", 0) or 0, "")
    return None


def _token_line(exc: tokenize.TokenError) -> int:
    if len(exc.args) > 1 and isinstance(exc.args[1], tuple) and exc.args[1]:
        line = exc.args[1][0]
        if isinstance(line, int):
            return line
    return 0


def _line_ending(text: str) -> str:
    newline = text.find("\n")
    if newline < 0:
        return "\n"
    if newline > 0 and text[newline - 1] == "\r":
        return "\r\n"
    return "\n"


def _find_window(tree: ast.AST, lines: Sequence[str], ending: str) -> Optional[ClassFacts]:
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    stems = _ui_stems(tree)
    for node in classes:
        if _calls_setup_ui(node, stems):
            return _class_facts(node, lines, ending)
    for node in classes:
        for stem in stems:
            if node.name == "%sWindow" % stem:
                return _class_facts(node, lines, ending)
    return None


def _ui_stems(tree: ast.AST) -> Tuple[str, ...]:
    found: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name.startswith("Ui_") and len(name) > 3:
                found.append(name[3:])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name.startswith("Ui_") and len(alias.name) > 3:
                    found.append(alias.name[3:])
    ordered: List[str] = []
    for stem in found:
        if stem not in ordered:
            ordered.append(stem)
    return tuple(ordered)


def _calls_setup_ui(node: ast.ClassDef, stems: Sequence[str]) -> bool:
    assigned = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Assign):
            if _is_ui_call(child.value, stems):
                for target in child.targets:
                    assigned.add(_expr_key(target))
        elif isinstance(child, ast.AnnAssign) and _is_ui_call(child.value, stems):
            assigned.add(_expr_key(child.target))
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if not isinstance(func, ast.Attribute) or func.attr != "setupUi":
            continue
        if not child.args or _expr_key(child.args[0]) != "self":
            continue
        key = _expr_key(func.value)
        if key == "self.ui" or key in assigned:
            return True
    return False


def _is_ui_call(value: Optional[ast.AST], stems: Sequence[str]) -> bool:
    if not isinstance(value, ast.Call):
        return False
    name = _call_name(value.func)
    if not name.startswith("Ui_"):
        return False
    if not stems:
        return True
    return name[3:] in stems


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _expr_key(node: Optional[ast.AST]) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return "%s.%s" % (_expr_key(node.value), node.attr)
    return ""


def _class_facts(node: ast.ClassDef, lines: Sequence[str], ending: str) -> ClassFacts:
    methods = tuple(
        _method_facts(child, lines)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return ClassFacts(
        name=node.name,
        line=node.lineno,
        base_names=_base_names(node),
        last_line=_class_last_line(node, lines),
        indent_unit=_indent_unit(node, lines),
        blank_line_style=_blank_style(node, lines),
        line_ending=ending,
        methods=methods,
    )


def _base_names(node: ast.ClassDef) -> Tuple[str, ...]:
    names = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return tuple(names)


def _top_imports(tree: ast.AST) -> Dict[str, Tuple[str, str]]:
    """Local name to ``(module, class name in that module)``."""
    found: Dict[str, Tuple[str, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        for alias in node.names:
            local = alias.asname or alias.name
            found[local] = (node.module, alias.name)
    return found


def _method_facts(node: ast.AST, lines: Sequence[str]) -> MethodFacts:
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    kind = _kind(node)
    params, required, has_varargs = _params(node, kind)
    end_line = node.end_lineno or node.lineno
    start = node.lineno
    chunk = "\n".join(lines[start - 1 : end_line])
    decorators = tuple(_decorator_text(item) for item in node.decorator_list)
    return MethodFacts(
        name=node.name,
        line=start,
        end_line=end_line,
        params=params,
        required=required,
        has_varargs=has_varargs,
        decorators=decorators,
        slot_types=_slot_types(node),
        kind=kind,
        body_is_empty=_body_is_empty(node),
        source_hash=method_source_hash(chunk),
    )


def _kind(node: ast.AST) -> str:
    for item in node.decorator_list:  # type: ignore[attr-defined]
        name = _decorator_name(item)
        if name in ("staticmethod", "classmethod", "property"):
            return name
    return "method"


def _decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _decorator_text(node: ast.AST) -> str:
    try:
        return "@%s" % ast.unparse(node)
    except Exception:
        return "@%s" % _decorator_name(node)


def _slot_types(node: ast.AST) -> Tuple[Tuple[str, ...], ...]:
    found = []
    for item in node.decorator_list:  # type: ignore[attr-defined]
        name = _decorator_name(item)
        if name != "Slot":
            continue
        if isinstance(item, ast.Call):
            found.append(tuple(_type_name(arg) for arg in item.args))
        else:
            found.append(())
    return tuple(found)


def _type_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _body_is_empty(node: ast.AST) -> bool:
    body = node.body  # type: ignore[attr-defined]
    if not body:
        return True
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            continue
        return False
    return True


def _params(node: ast.AST, kind: str) -> Tuple[Tuple[str, ...], int, bool]:
    args = node.args  # type: ignore[attr-defined]
    positional = list(args.posonlyargs) + list(args.args)
    skip_first = kind != "staticmethod"
    names: List[str] = []
    required = 0
    defaulted = len(args.defaults)
    required_positional = len(positional) - defaulted
    for index, arg in enumerate(positional):
        if index == 0 and skip_first and arg.arg in ("self", "cls"):
            continue
        names.append(arg.arg)
        if index < required_positional:
            required += 1
    kw_defaults = list(args.kw_defaults)
    for index, arg in enumerate(args.kwonlyargs):
        names.append(arg.arg)
        default = kw_defaults[index] if index < len(kw_defaults) else None
        if default is None:
            required += 1
    return tuple(names), required, args.vararg is not None


def _class_last_line(node: ast.ClassDef, lines: Sequence[str]) -> int:
    last = node.end_lineno or node.lineno
    class_indent = _indent_len(lines[node.lineno - 1] if node.lineno <= len(lines) else "")
    index = last
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped == "":
            if _comment_follows(lines, index + 1, class_indent):
                index += 1
                continue
            break
        if _indent_len(line) <= class_indent:
            break
        if stripped.startswith("#"):
            index += 1
            continue
        break
    return index


def _comment_follows(lines: Sequence[str], start: int, class_indent: int) -> bool:
    for index in range(start, len(lines)):
        line = lines[index]
        stripped = line.strip()
        if stripped == "":
            continue
        if _indent_len(line) <= class_indent:
            return False
        return stripped.startswith("#")
    return False


def _indent_unit(node: ast.ClassDef, lines: Sequence[str]) -> str:
    end = node.end_lineno or node.lineno
    class_indent = _indent_len(lines[node.lineno - 1] if node.lineno <= len(lines) else "")
    for number in range(node.lineno + 1, end + 1):
        if number > len(lines):
            break
        line = lines[number - 1]
        if line.strip() and _indent_len(line) > class_indent:
            return line[: len(line) - len(line.lstrip(" \t"))]
    return "    "


def _blank_style(node: ast.ClassDef, lines: Sequence[str]) -> int:
    methods = [
        child
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    if len(methods) <= 1:
        return 1
    gaps = []
    for earlier, later in zip(methods, methods[1:]):
        start = later.lineno
        if later.decorator_list:
            start = min(item.lineno for item in later.decorator_list)
        blanks = 0
        end = earlier.end_lineno or earlier.lineno
        for number in range(end + 1, start):
            if 1 <= number <= len(lines) and lines[number - 1].strip() == "":
                blanks += 1
        gaps.append(blanks)
    twos = sum(1 for gap in gaps if gap >= 2)
    if twos > len(gaps) / 2:
        return 2
    return 1


def _indent_len(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))
