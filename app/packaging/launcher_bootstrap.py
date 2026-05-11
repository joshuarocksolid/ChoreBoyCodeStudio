"""Shared AppRun launcher bootstrap builders for packaged artifacts.

This module is intentionally dependency-light because installable artifacts copy it
beside ``installer/install.py`` and load it from there on target machines.
"""

from __future__ import annotations

from pathlib import Path

_UNSAFE_ENTRY_CHARS = {'"', "'", "\n", "\r", "\t", "\x00"}
_APP_FILES_DIRNAME = "app_files"


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
    return (
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


def build_desktop_path_shell_wrapper(
    *,
    app_run_path: str,
    entry_relative_path: str,
    missing_location_message: str,
    allow_cwd_fallback: bool,
) -> str:
    """Return a `/bin/sh -c` wrapper that passes `%k` location into AppRun."""
    entry_relative_path = validate_packaged_entry_relative_path(entry_relative_path)
    safe_message = _safe_double_quoted_literal(missing_location_message)
    fallback = "root=root or os.getcwd();" if allow_cwd_fallback else f'sys.exit("{safe_message}") if not root else None;'
    python_code = (
        "import os,runpy,sys;"
        'root=os.environ.get("CBCS_PACKAGE_ROOT", "");'
        + fallback
        + "root=os.path.abspath(root);"
        + f'entry_rel="{entry_relative_path}";'
        + "entry=os.path.abspath(os.path.join(root, entry_rel));"
        + 'sys.exit("Invalid package root") if not os.path.isdir(root) else None;'
        + 'sys.exit("Invalid package entry") if os.path.commonpath([root, entry]) != root or not os.path.isfile(entry) else None;'
        + f'runtime_root=os.path.abspath(os.path.join(root, "{_APP_FILES_DIRNAME}")) if entry_rel == "{_APP_FILES_DIRNAME}" or entry_rel.startswith("{_APP_FILES_DIRNAME}/") else os.path.dirname(entry);'
        + 'sys.exit("Invalid package runtime root") if os.path.commonpath([root, runtime_root]) != root or not os.path.isdir(runtime_root) else None;'
        + "sys.path.insert(0, runtime_root) if runtime_root not in sys.path else None;"
        + "os.chdir(runtime_root);"
        + 'runpy.run_path(entry, run_name="__main__")'
    )
    shell_script = (
        'desktop_path="$1";'
        'if [ -n "$desktop_path" ]; then root="${desktop_path%/*}"; [ "$root" = "$desktop_path" ] && root="."; else root=""; fi;'
        f'CBCS_PACKAGE_ROOT="$root" exec {app_run_path} -c \'{python_code}\''
    )
    return shell_script.replace('"', '\\"')


def _safe_double_quoted_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
