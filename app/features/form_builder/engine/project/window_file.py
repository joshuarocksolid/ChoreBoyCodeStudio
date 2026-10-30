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
import re
import stat
import threading
import tokenize
from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Tuple

from app.features.form_builder.engine.project.custom_widgets import module_file
from app.features.form_builder.engine.project.fs import inside_project
from app.features.form_builder.engine.project.window_facts import (
    MethodFacts,
    ReadStatus,
    WindowFacts,
    WindowRead,
)

MAX_BYTES = 1_000_000
_TOKEN_LIMIT = 2000
_BRACKET_LIMIT = 100
_INDENT_LIMIT = 100
_CACHE_LIMIT = 64
_CHAIN_LIMIT = 3
_FOLLOW_LIMIT = 8
_FIELD_LIMIT = 2000
_DECORATOR_TEXT = 200
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_PYSIDE = ("PySide6", "PySide2", "PySide", "shiboken6", "shiboken2")

_CACHE_LOCK = threading.Lock()
_FILE_CACHE: Dict[Tuple[str, int, int], Tuple["WindowRead", Tuple[object, ...]]] = {}
_TEXT_CACHE: Dict[str, Tuple["WindowRead", Tuple[object, ...]]] = {}


class _Follow:
    """Base files one read may still open, and the ones it opened.

    Without a total, a class with hundreds of project bases, each with
    hundreds more, would read the same 1 MB file over and over.
    """

    def __init__(self) -> None:
        self.left = _FOLLOW_LIMIT
        self.files: List[str] = []


def _empty(status: ReadStatus, reason: str, line: int, relative: str) -> WindowRead:
    return WindowRead(status, reason, line, WindowFacts(), relative)


def source_lines(text: str, keepends: bool = False) -> List[str]:
    """Lines as Python numbers them: split on CRLF, CR and LF only.

    ``str.splitlines`` also splits on form feed, NEL and U+2028, which would
    put a stub inside the last method of a file with one of those in it.
    """
    lines: List[str] = []
    start = 0
    for match in _LINE_BREAK.finditer(text):
        end = match.end() if keepends else match.start()
        lines.append(text[start:end])
        start = match.end()
    if start < len(text):
        lines.append(text[start:])
    return lines


def file_label(relative: str) -> str:
    name = relative.replace("\\", "/").rsplit("/", 1)[-1]
    return name or relative or "the window file"


def method_source_hash(text: str) -> str:
    """sha256 of method lines from ``def`` to the last line, LF-normalised."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def read_window(
    project_root: str, relative: str, text: Optional[str] = None, token: Optional[str] = None
) -> WindowRead:
    """The window class and its methods. Never imports or runs the file."""
    relative = relative.replace("\\", "/")
    if text is None:
        cached = _cached_file(project_root, relative)
        if cached is not None:
            _seed_text_cache(project_root, relative, cached)
            return cached
        follow = _Follow()
        read = _stamp_followed(
            _read_path(project_root, relative, chain=(), budget=follow), follow
        )
        _store_file(project_root, relative, read, follow.files)
        _seed_text_cache(project_root, relative, read)
        return read
    if token:
        peeked = peek_window(project_root, relative, token)
        if peeked is not None:
            return peeked
    digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
    digest_key = "%s\0%s\0%s" % (project_root, relative, digest)
    # The token is part of the key, and so is the text. A new revision of
    # different text cannot reuse the scan stored for the previous text.
    key = ("%s\0%s\0token:%s\0%s" % (project_root, relative, token, digest)) if token else digest_key
    with _CACHE_LOCK:
        cached_text = _TEXT_CACHE.get(key)
        if cached_text is None and key != digest_key:
            cached_text = _TEXT_CACHE.get(digest_key)
    if cached_text is not None and _fresh(project_root, cached_text[1]):
        if token and key != digest_key:
            with _CACHE_LOCK:
                _remember(_TEXT_CACHE, key, cached_text)
        return cached_text[0]
    follow = _Follow()
    read = _stamp_followed(
        _read_text(project_root, relative, text, chain=(), budget=follow), follow
    )
    stamped = (read, _stamps(project_root, follow.files))
    with _CACHE_LOCK:
        _remember(_TEXT_CACHE, key, stamped)
        if key != digest_key:
            _remember(_TEXT_CACHE, digest_key, stamped)
    return read


def _stamp_followed(read: WindowRead, follow: "_Follow") -> WindowRead:
    files = tuple(follow.files)
    if not files:
        return read
    return replace(read, followed=files)


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
        entry = _FILE_CACHE.get(key)
    if entry is None:
        return None
    read, stamps = entry
    if not _fresh(project_root, stamps):
        return None
    return read


def _fresh(project_root: str, stamps: Tuple[object, ...]) -> bool:
    files = [str(item[0]) for item in stamps if isinstance(item, tuple)]
    return stamps == _stamps(project_root, files)


def _stamps(project_root: str, files: Sequence[str]) -> Tuple[object, ...]:
    """``(relative, mtime_ns, size)`` of followed base files, so editing one
    misses the cache of the window file that inherits from it."""
    found: List[object] = []
    for relative in files:
        full = os.path.join(project_root, *relative.split("/"))
        try:
            info = os.stat(full)
            found.append((relative, info.st_mtime_ns, info.st_size))
        except OSError:
            found.append((relative, 0, -1))
    return tuple(found)


def _store_file(
    project_root: str, relative: str, read: WindowRead, files: Sequence[str] = ()
) -> None:
    full = os.path.join(project_root, *relative.split("/"))
    try:
        info = os.stat(full)
    except OSError:
        return
    key = (os.path.abspath(full), getattr(info, "st_mtime_ns", 0), info.st_size)
    with _CACHE_LOCK:
        _remember(_FILE_CACHE, key, (read, _stamps(project_root, files)))


def _token_key(project_root: str, relative: str, token: str) -> str:
    return "%s\0%s\0rev:%s" % (project_root, relative.replace("\\", "/"), token)


def peek_window(project_root: str, relative: str, token: str) -> Optional[WindowRead]:
    """The reading stored for this buffer token. None when the token is new.

    The token changes when the buffer text changes, so a hit is the same
    characters the editor holds. A miss reparses.
    """
    if not token:
        return None
    with _CACHE_LOCK:
        hit = _TEXT_CACHE.get(_token_key(project_root, relative, token))
    if hit is None or not _fresh(project_root, hit[1]):
        return None
    return hit[0]


def install_inserted_method(
    project_root: str,
    relative: str,
    read: WindowRead,
    plan: object,
    token: Optional[str],
) -> WindowRead:
    """Remember a stub the bridge just inserted, without parsing the file again.

    Line numbers below the edit shift by the net line count, and the new method
    is placed where it sits in the class. A replacement that cuts through a
    method is parsed instead of patched. A later edit misses this entry
    because its buffer token is different.
    """
    source = read.source if isinstance(read.source, str) else ""
    edit = getattr(plan, "edit")
    start = int(edit.start)
    end = int(edit.end)
    inserted = str(edit.text)
    if not (0 <= start <= end <= len(source)):
        return read
    new_source = source[:start] + inserted + source[end:]
    name = str(getattr(plan, "method_name"))
    patched = _patch_inserted(read, source, new_source, start, end, inserted, name)
    if patched is None:
        return read_window(project_root, relative, text=new_source, token=token)
    _store_text(project_root, relative, patched, token, new_source)
    return patched


def _patch_inserted(
    read: WindowRead,
    source: str,
    new_source: str,
    start: int,
    end: int,
    inserted: str,
    name: str,
) -> Optional[WindowRead]:
    """The reading after the edit, or None when the lines cannot be shifted exactly."""
    facts = read.facts
    if read.status != "ok" or not facts.class_name:
        return None
    if not _at_line_boundary(source, start) or not _at_line_boundary(source, end):
        return None
    at = inserted.find("def %s" % name)
    if at < 0:
        return None
    line_break = max(inserted.rfind("\n", 0, at), inserted.rfind("\r", 0, at))
    prefix = inserted[line_break + 1 : at] if line_break >= 0 else inserted[:at]
    if prefix.strip():
        return None
    edit_line = _breaks(source[:start]) + 1
    after_line = _breaks(source[:end]) + 1
    shift = _breaks(inserted) - _breaks(source[start:end])
    def_line = edit_line + _breaks(inserted[:at])
    method_text = inserted[at:]
    body = method_text.splitlines()
    while body and not body[-1].strip():
        body.pop()
    if not body:
        return None
    end_line = def_line + len(body) - 1
    header = method_text.splitlines()[0] if method_text.splitlines() else ""
    parsed = _stub_params(header)
    if parsed is None:
        return None
    params, required, has_varargs = parsed
    shifted = []
    for method in facts.methods:
        if method.name == name:
            return None
        overlaps = method.line < after_line and method.end_line >= edit_line
        inside = end == start and method.line < edit_line <= method.end_line
        if overlaps or inside:
            return None
        if method.line >= after_line:
            shifted.append(replace(method, line=method.line + shift, end_line=method.end_line + shift))
        else:
            shifted.append(method)
    lines = source_lines(new_source)
    if not (1 <= def_line <= end_line <= len(lines)):
        return None
    chunk = "\n".join(lines[def_line - 1 : end_line])
    added = MethodFacts(
        name=name,
        line=def_line,
        end_line=end_line,
        params=params,
        required=required,
        has_varargs=has_varargs,
        body_is_empty=_stub_body_empty(lines[def_line:end_line]),
        source_hash=method_source_hash(chunk),
    )
    shifted.append(added)
    shifted.sort(key=lambda item: item.line)
    class_end = facts.end_line
    if class_end and edit_line <= class_end + 1:
        if end > start and after_line > class_end + 1:
            return None
        class_end += shift
    patched_facts = replace(facts, end_line=class_end, methods=tuple(shifted))
    return replace(read, facts=patched_facts, source=new_source)


def _breaks(text: str) -> int:
    return sum(1 for _ in _LINE_BREAK.finditer(text))


def _at_line_boundary(text: str, offset: int) -> bool:
    if offset == 0 or offset == len(text):
        return True
    previous = text[offset - 1]
    if previous == "\n":
        return True
    return previous == "\r" and text[offset : offset + 1] != "\n"


def _stub_params(header: str) -> Optional[Tuple[Tuple[str, ...], int, bool]]:
    """``(params, required, has_varargs)`` for a plain ``def`` header, else None."""
    open_paren = header.find("(")
    close_paren = header.rfind(")")
    if open_paren < 0 or close_paren <= open_paren:
        return None
    raw = header[open_paren + 1 : close_paren]
    if any(char in raw for char in "*[]{}:()"):
        return None
    names: List[str] = []
    required = 0
    skipped_self = False
    for part in raw.split(","):
        piece = part.strip()
        if not piece or piece == "/":
            continue
        if not skipped_self:
            skipped_self = True
            continue
        name = piece.split("=", 1)[0].strip()
        if not name.isidentifier():
            return None
        names.append(name)
        if "=" not in piece:
            required += 1
    return tuple(names), required, False


def _stub_body_empty(lines: Sequence[str]) -> bool:
    """True when the body is only ``pass``, ``...``, or a docstring."""
    quote: Optional[str] = None
    for line in lines:
        stripped = line.strip()
        if quote is not None:
            if quote in stripped:
                quote = None
            continue
        if not stripped or stripped in ("pass", "..."):
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            mark = stripped[:3]
            if mark not in stripped[3:]:
                quote = mark
            continue
        return False
    return quote is None


def _seed_text_cache(project_root: str, relative: str, read: WindowRead) -> None:
    """A disk read answers a later read of the same characters without parsing again."""
    text = read.source
    if isinstance(text, str):
        _store_text(project_root, relative, read, None, text)


def _store_text(
    project_root: str,
    relative: str,
    read: WindowRead,
    token: Optional[str],
    text: str,
) -> None:
    digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
    relative = relative.replace("\\", "/")
    digest_key = "%s\0%s\0%s" % (project_root, relative, digest)
    stamped = (read, _stamps(project_root, read.followed))
    with _CACHE_LOCK:
        _remember(_TEXT_CACHE, digest_key, stamped)
        if token:
            _remember(_TEXT_CACHE, _token_key(project_root, relative, token), stamped)


def _remember(cache: Dict, key: object, read: object) -> None:
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
    budget: Optional["_Follow"] = None,
) -> WindowRead:
    full = os.path.join(project_root, *relative.split("/")) if project_root else relative
    if not project_root or not inside_project(full, project_root):
        return _empty("refused", "it is outside the project", 0, relative)
    if not os.path.lexists(full):
        return _empty("missing", "the file is missing", 0, relative)
    data = _read_regular(full, project_root)
    if data is None:
        if os.path.islink(full) and not inside_project(os.path.realpath(full), project_root):
            return _empty("refused", "it is outside the project", 0, relative)
        if os.path.isfile(full):
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            if size > MAX_BYTES:
                return _empty("refused", "it is larger than 1 MB", 0, relative)
        return _empty("refused", "it is not a regular file", 0, relative)
    decoded = _decode(data)
    if decoded is None:
        return _empty("refused", "it isn't UTF-8 text", 0, relative)
    text, _encoding = decoded
    return _read_text(project_root, relative, text, chain, focus, budget)


def _read_regular(full: str, project_root: str = "") -> Optional[bytes]:
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
        if project_root and not _same_file_inside(full, project_root, info):
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


def _same_file_inside(full: str, project_root: str, info: os.stat_result) -> bool:
    """The opened file is the one the path names now, and that is in the project.

    Closes the gap between the symlink check and the open: a link swapped to
    point outside the project in between is refused.
    """
    real = os.path.realpath(full)
    if not inside_project(real, os.path.realpath(project_root)):
        return False
    try:
        now = os.stat(real)
    except OSError:
        return False
    return (now.st_dev, now.st_ino) == (info.st_dev, info.st_ino)


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
    budget: Optional["_Follow"] = None,
) -> WindowRead:
    if budget is None:
        budget = _Follow()
    if "\0" in text:
        return _empty("refused", "it contains a NUL byte", 0, relative)
    scanned = _prescan(text)
    if scanned is not None:
        status, line, reason = scanned
        return _empty(status, reason, line, relative)
    try:
        tree = ast.parse(text, type_comments=False)
    except (SyntaxError, ValueError) as exc:
        line = exc.lineno or 0 if isinstance(exc, SyntaxError) else 0
        return _empty("syntax_error", "", line, relative)
    except (RecursionError, MemoryError):
        return _empty("refused", "the file is too deeply nested to read", 0, relative)
    except Exception:
        return _empty("refused", "it can't be read", 0, relative)
    lines = source_lines(text)
    ending = _line_ending(text)
    window = _find_window(tree, lines, ending)
    target = window
    if focus:
        node = next(
            (
                item
                for item in tree.body
                if isinstance(item, ast.ClassDef) and item.name == focus
            ),
            None,
        )
        target = _class_facts(node, lines, ending) if node is not None else None
    base_methods: List[MethodFacts] = []
    unread: List[str] = []
    if target is not None and len(chain) + 1 < _CHAIN_LIMIT:
        imports = _top_imports(tree)
        seen = chain + (relative,)
        for base in target.bases:
            _follow_base(
                project_root, base, imports, seen, base_methods, unread, budget,
            )
    elif target is not None:
        imports = _top_imports(tree)
        for base in target.bases:
            if _is_project_base(base, imports):
                unread.append(base)
    shown = target if focus else window
    if shown is None:
        shown = WindowFacts()
    facts = replace(
        shown,
        base_methods=tuple(base_methods),
        unread_bases=tuple(unread),
    )
    return WindowRead("ok", "", 0, facts, relative, text)


def _follow_base(
    project_root: str,
    base: str,
    imports: Dict[str, Tuple[str, str]],
    seen: Tuple[str, ...],
    methods: List[MethodFacts],
    unread: List[str],
    budget: "_Follow",
) -> None:
    binding = imports.get(base)
    if binding is None:
        return
    module, class_name = binding
    if module.split(".", 1)[0] in _PYSIDE:
        return
    relative = module_file(project_root, module)
    if not relative or relative in seen or budget.left <= 0:
        unread.append(base)
        return
    budget.left -= 1
    budget.files.append(relative)
    read = _read_path(project_root, relative, seen, focus=class_name, budget=budget)
    facts = read.facts
    if read.status != "ok" or facts.class_name != class_name:
        unread.append(base)
        return
    methods.extend(facts.methods)
    methods.extend(facts.base_methods)
    for name in facts.unread_bases:
        if name not in unread:
            unread.append(name)


def _is_project_base(base: str, imports: Dict[str, Tuple[str, str]]) -> bool:
    binding = imports.get(base)
    if binding is None:
        return False
    return binding[0].split(".", 1)[0] not in _PYSIDE


def _prescan(text: str) -> Optional[Tuple[ReadStatus, int, str]]:
    try:
        # The C tokenizer ends a line at a lone CR; ``tokenize`` would read on
        # (inside a comment, say) and miss what the parser will see.
        flat = text.replace("\r\n", "\n").replace("\r", "\n")
        tokens = tokenize.generate_tokens(io.StringIO(flat).readline)
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
            elif tok.type == tokenize.STRING and _field_chars(tok.string) > _FIELD_LIMIT:
                return ("refused", line, "an f-string holds too much code")
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


def _field_chars(token: str) -> int:
    """Characters of code inside an f-string's ``{}`` fields; 0 for other strings.

    Python 3.9 parses those fields with no stack limit, and ``tokenize`` sees
    the whole f-string as one token, so a long ``{a.b.b...}`` would crash
    ``ast.parse``. Quotes inside a field are skipped so a ``'}'`` there can't
    end the count early; an unclosed quote counts the rest of the token.
    """
    head = 0
    while head < len(token) and token[head] not in "'\"":
        head += 1
    if "f" not in token[:head].lower():
        return 0
    body = token[head:]
    quote = body[:3] if body[:3] in ('"""', "'''") else body[:1]
    body = body[len(quote) : len(body) - len(quote)]
    total = 0
    depth = 0
    index = 0
    size = len(body)
    while index < size:
        ch = body[index]
        if depth == 0:
            if body.startswith("{{", index):
                index += 2
                continue
            if ch == "{":
                depth = 1
            index += 1
            continue
        if ch in "'\"":
            inner = body[index : index + 3] if body[index : index + 3] in ('"""', "'''") else ch
            close = body.find(inner, index + len(inner))
            stop = size if close < 0 else close + len(inner)
            total += stop - index
            index = stop
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                index += 1
                continue
        total += 1
        index += 1
    return total


def _token_line(exc: tokenize.TokenError) -> int:
    if len(exc.args) > 1 and isinstance(exc.args[1], tuple) and exc.args[1]:
        line = exc.args[1][0]
        if isinstance(line, int):
            return line
    return 0


def _line_ending(text: str) -> str:
    match = _LINE_BREAK.search(text)
    if match is None:
        return "\n"
    return match.group(0)


def _find_window(tree: ast.AST, lines: Sequence[str], ending: str) -> Optional[WindowFacts]:
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
    calls: List[ast.Call] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            calls.append(child)
        elif isinstance(child, ast.Assign):
            if _is_ui_call(child.value, stems):
                for target in child.targets:
                    assigned.add(_expr_key(target))
        elif isinstance(child, ast.AnnAssign) and _is_ui_call(child.value, stems):
            assigned.add(_expr_key(child.target))
    for child in calls:
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
    """``self.ui`` for that expression; "" for anything but names and dots.

    A loop, not recursion: a 1,000-deep ``a.b.b...`` passes the pre-scan.
    """
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        parts.append("")
    return ".".join(reversed(parts))


def _class_facts(node: ast.ClassDef, lines: Sequence[str], ending: str) -> WindowFacts:
    methods = tuple(
        _method_facts(child, lines)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return WindowFacts(
        class_name=node.name,
        line=node.lineno,
        bases=_base_names(node),
        end_line=_class_last_line(node, lines),
        indent=_indent_unit(node, lines),
        blank_lines=_blank_style(node, lines),
        newline=ending,
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
    decorators = tuple(_decorator_text(item, lines) for item in node.decorator_list)
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
    while isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _decorator_text(node: ast.AST, lines: Sequence[str]) -> str:
    """The decorator as written when it is one short line, else ``@name``.

    Taken from the source, not ``ast.unparse``, which is recursive and slow
    on thousands of deep decorators.
    """
    number = getattr(node, "lineno", 0)
    end = getattr(node, "end_lineno", None)
    if number and end == number and 1 <= number <= len(lines):
        raw = lines[number - 1].encode("utf-8", "surrogatepass")
        start = getattr(node, "col_offset", 0)
        stop = getattr(node, "end_col_offset", None)
        if stop is not None and 0 <= start < stop <= len(raw) and stop - start <= _DECORATOR_TEXT:
            return "@%s" % raw[start:stop].decode("utf-8", "replace")
    return "@%s" % _decorator_name(node)


def _slot_types(node: ast.AST) -> Optional[Tuple[str, ...]]:
    """Argument types of the first ``@Slot``, or None when the method has none.

    ``()`` is ``@Slot()``. A later ``@Slot`` on the same method is ignored.
    """
    for item in node.decorator_list:  # type: ignore[attr-defined]
        if _decorator_name(item) != "Slot":
            continue
        if isinstance(item, ast.Call):
            return tuple(_type_name(arg) for arg in item.args)
        return ()
    return None


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
        if index == 0 and skip_first:
            # The instance, whatever it is called (``this``, ``window``).
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
    """The leading whitespace of the class's first statement.

    "" when that statement sits on the ``class`` line, where no method can go.
    A continued header (``class A(\\n        QWidget):``) or a string's inner
    lines must not set it, or a stub would land inside the last method.
    """
    first = node.body[0]
    decorators = getattr(first, "decorator_list", None) or []
    number = min([first.lineno] + [item.lineno for item in decorators])
    if number <= node.lineno or number > len(lines):
        return ""
    line = lines[number - 1]
    return line[: len(line) - len(line.lstrip(" \t"))]


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
