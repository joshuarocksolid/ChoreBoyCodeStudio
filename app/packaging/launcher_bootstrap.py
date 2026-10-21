"""Shared AppRun launcher bootstrap builders for packaged artifacts.

This module is intentionally dependency-light because installable artifacts copy it
beside ``installer/install.py`` and load it from there on target machines.
"""

from __future__ import annotations

import io
from pathlib import Path
import tokenize

_UNSAFE_ENTRY_CHARS = {'"', "'", "\n", "\r", "\t", "\x00"}
_APP_FILES_DIRNAME = "app_files"

# FreeCAD 1.1 runs std::filesystem::status() on each command-line argument,
# so an ``AppRun -c`` payload with a '/'-free run longer than NAME_MAX (255
# bytes) aborts FreeCAD with "File name too long". FreeCAD 1.0 accepts it.
APPRUN_PAYLOAD_NAME_MAX = 255
_APPRUN_PAYLOAD_SPLIT_AT = 200
_APPRUN_PAYLOAD_SPACER = "'/';"


def longest_slash_free_run(payload: str) -> int:
    """Return the longest '/'-free run of ``payload`` in UTF-8 bytes."""
    return max(len(part.encode("utf-8")) for part in payload.split("/"))


def apprun_safe_python(code: str) -> str:
    """Return ``code`` with no-op ``'/'`` statements breaking long '/'-free runs.

    The spacer goes after a top-level ``;`` so the program is unchanged. Raises
    ``ValueError`` if a single statement is still too long to pass to AppRun.
    """
    if longest_slash_free_run(code) <= _APPRUN_PAYLOAD_SPLIT_AT:
        return code
    line_starts = [0]
    for line in code.splitlines(keepends=True):
        line_starts.append(line_starts[-1] + len(line))
    cut_offsets = [
        line_starts[token.end[0] - 1] + token.end[1]
        for token in tokenize.generate_tokens(io.StringIO(code).readline)
        if token.type == tokenize.OP and token.string == ";"
    ]
    pieces: list[str] = []
    previous = 0
    for offset in cut_offsets:
        pieces.append(code[previous:offset])
        previous = offset
    pieces.append(code[previous:])

    result = ""
    trailing_run = 0
    for piece in pieces:
        leading_run = len(piece.split("/", 1)[0].encode("utf-8"))
        if result and trailing_run + leading_run > _APPRUN_PAYLOAD_SPLIT_AT:
            result += _APPRUN_PAYLOAD_SPACER
            trailing_run = len("';")
        result += piece
        if "/" in piece:
            trailing_run = len(piece.rsplit("/", 1)[1].encode("utf-8"))
        else:
            trailing_run += len(piece.encode("utf-8"))
    if longest_slash_free_run(result) > APPRUN_PAYLOAD_NAME_MAX:
        raise ValueError(
            "AppRun -c payload has a statement longer than "
            f"{APPRUN_PAYLOAD_NAME_MAX} bytes without '/'; FreeCAD 1.1 would abort on it."
        )
    return result


def validate_packaged_entry_relative_path(entry_relative_path: str) -> str:
    """Return a normalized package entry path or raise for unsafe values."""
    normalized = entry_relative_path.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("entry_relative_path must be a non-empty relative path.")
    if any(char in normalized for char in _UNSAFE_ENTRY_CHARS):
        raise ValueError("entry_relative_path contains unsafe shell or control characters.")
    path = Path(normalized)
    if path.is_absolute():
        raise ValueError("entry_relative_path must be relative.")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("entry_relative_path must not contain empty, current, or parent segments.")
    return path.as_posix()


def build_fixed_root_bootstrap(root_path: str, entry_relative_path: str) -> str:
    """Return Python code that runs a package entry from a fixed install root."""
    entry_relative_path = validate_packaged_entry_relative_path(entry_relative_path)
    return apprun_safe_python(
        "import os,runpy,sys;"
        f"root={root_path!r};"
        "root=os.path.abspath(root);"
        f"entry_rel={entry_relative_path!r};"
        "entry=os.path.abspath(os.path.join(root, entry_rel));"
        "sys.exit('Invalid package root') if not os.path.isdir(root) else None;"
        "sys.exit('Invalid package entry') if os.path.commonpath([root, entry]) != root or not os.path.isfile(entry) else None;"
        f"runtime_root=os.path.abspath(os.path.join(root, {_APP_FILES_DIRNAME!r})) if entry_rel == {_APP_FILES_DIRNAME!r} or entry_rel.startswith({_APP_FILES_DIRNAME + '/'!r}) else os.path.dirname(entry);"
        "sys.exit('Invalid package runtime root') if os.path.commonpath([root, runtime_root]) != root or not os.path.isdir(runtime_root) else None;"
        "sys.path.insert(0, runtime_root) if runtime_root not in sys.path else None;"
        "os.chdir(runtime_root);"
        "runpy.run_path(entry, run_name='__main__')"
    )


def build_path_key_installer_exec(app_run_path: str) -> str:
    """Return the direct AppRun command for a Path-keyed installer launcher."""
    python_code = apprun_safe_python(
        "import os,runpy,sys;"
        "root=os.getcwd();"
        "os.environ['CBCS_PACKAGE_ROOT']=root;"
        "entry=os.path.join(root,'installer','bootstrap.py');"
        "sys.path.insert(0,os.path.dirname(entry)) if os.path.dirname(entry) not in sys.path else None;"
        "runpy.run_path(entry, run_name='__main__')"
    )
    return f'{app_run_path} -c "{python_code}"'
