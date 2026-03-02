"""Runtime execution context management for runner process."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import builtins
import io
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from typing import Any, Iterator

from app.core.errors import RunLifecycleError
from app.run.run_manifest import RunManifest


@dataclass(frozen=True)
class RunnerExecutionContext:
    """Resolved execution inputs derived from run manifest."""

    project_root: str
    working_directory: str
    entry_script_path: str
    argv: list[str]
    env_overrides: dict[str, str]
    safe_mode: bool

    @classmethod
    def from_manifest(cls, manifest: RunManifest) -> "RunnerExecutionContext":
        project_root = Path(manifest.project_root).expanduser().resolve()
        working_directory = Path(manifest.working_directory).expanduser().resolve()

        entry_candidate = Path(manifest.entry_file).expanduser()
        if not entry_candidate.is_absolute():
            entry_candidate = project_root / entry_candidate
        entry_script_path = entry_candidate.resolve()

        if not entry_script_path.exists():
            raise RunLifecycleError(f"Entry file not found: {entry_script_path}")
        if not entry_script_path.is_file():
            raise RunLifecycleError(f"Entry path must be a file: {entry_script_path}")
        if not working_directory.exists() or not working_directory.is_dir():
            raise RunLifecycleError(f"Working directory is invalid: {working_directory}")

        return cls(
            project_root=str(project_root),
            working_directory=str(working_directory),
            entry_script_path=str(entry_script_path),
            argv=list(manifest.argv),
            env_overrides=dict(manifest.env),
            safe_mode=manifest.safe_mode,
        )


@contextmanager
def apply_execution_context(execution_context: RunnerExecutionContext) -> Iterator[None]:
    """Apply and restore runner execution context around user code execution."""
    previous_cwd = Path.cwd()
    previous_argv = list(sys.argv)
    previous_path = list(sys.path)
    previous_env: dict[str, str | None] = {}
    removed_app_modules: dict[str, ModuleType] = {}
    safe_mode_originals: dict[str, object] = {}

    try:
        os.chdir(execution_context.working_directory)
        sys.argv = [execution_context.entry_script_path, *execution_context.argv]
        sys.path.insert(0, execution_context.project_root)

        for module_name in list(sys.modules.keys()):
            if module_name == "app" or module_name.startswith("app."):
                removed_app_modules[module_name] = sys.modules.pop(module_name)

        for key, value in execution_context.env_overrides.items():
            previous_env[key] = os.environ.get(key)
            os.environ[key] = value

        if execution_context.safe_mode:
            safe_mode_originals = _enable_safe_mode_guards(project_root=execution_context.project_root)

        yield
    finally:
        if safe_mode_originals:
            _restore_safe_mode_guards(safe_mode_originals)
        for key, old_value in previous_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
        for module_name, module in removed_app_modules.items():
            sys.modules[module_name] = module
        sys.argv = previous_argv
        sys.path[:] = previous_path
        os.chdir(previous_cwd)


def _enable_safe_mode_subprocess_guards() -> dict[str, object]:
    originals = {
        "run": subprocess.run,
        "call": subprocess.call,
        "check_call": subprocess.check_call,
        "check_output": subprocess.check_output,
        "Popen": subprocess.Popen,
    }

    def blocked(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise PermissionError("subprocess execution is disabled in safe mode.")

    subprocess_any: Any = subprocess
    subprocess_any.run = blocked
    subprocess_any.call = blocked
    subprocess_any.check_call = blocked
    subprocess_any.check_output = blocked
    subprocess_any.Popen = blocked
    return originals


def _restore_safe_mode_subprocess_guards(originals: dict[str, object]) -> None:
    subprocess_any: Any = subprocess
    subprocess_any.run = originals["run"]
    subprocess_any.call = originals["call"]
    subprocess_any.check_call = originals["check_call"]
    subprocess_any.check_output = originals["check_output"]
    subprocess_any.Popen = originals["Popen"]


def _enable_safe_mode_guards(*, project_root: str) -> dict[str, object]:
    originals = _enable_safe_mode_subprocess_guards()
    originals.update(_enable_safe_mode_file_write_guards(project_root=project_root))
    return originals


def _enable_safe_mode_file_write_guards(*, project_root: str) -> dict[str, object]:
    project_root_path = Path(project_root).expanduser().resolve()
    originals: dict[str, object] = {
        "builtins_open": builtins.open,
        "io_open": io.open,
        "os_open": os.open,
        "os_remove": os.remove,
        "os_unlink": os.unlink,
        "os_rename": os.rename,
        "os_replace": os.replace,
        "os_mkdir": os.mkdir,
        "os_makedirs": os.makedirs,
        "os_rmdir": os.rmdir,
    }

    def guarded_open(file, mode="r", *args, **kwargs):  # type: ignore[no-untyped-def]
        if _is_write_mode(str(mode)) and _is_disallowed_path(file, project_root_path):
            raise PermissionError("write outside project root is disabled in safe mode.")
        return originals["builtins_open"](file, mode, *args, **kwargs)  # type: ignore[misc]

    def guarded_os_open(file, flags, mode=0o777, *args, **kwargs):  # type: ignore[no-untyped-def]
        if _is_write_flags(int(flags)) and _is_disallowed_path(file, project_root_path):
            raise PermissionError("write outside project root is disabled in safe mode.")
        return originals["os_open"](file, flags, mode, *args, **kwargs)  # type: ignore[misc]

    def guarded_remove(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_allowed_path(path, project_root_path)
        return originals["os_remove"](path, *args, **kwargs)  # type: ignore[misc]

    def guarded_unlink(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_allowed_path(path, project_root_path)
        return originals["os_unlink"](path, *args, **kwargs)  # type: ignore[misc]

    def guarded_rename(src, dst, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_allowed_path(src, project_root_path)
        _assert_allowed_path(dst, project_root_path)
        return originals["os_rename"](src, dst, *args, **kwargs)  # type: ignore[misc]

    def guarded_replace(src, dst, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_allowed_path(src, project_root_path)
        _assert_allowed_path(dst, project_root_path)
        return originals["os_replace"](src, dst, *args, **kwargs)  # type: ignore[misc]

    def guarded_mkdir(path, mode=0o777, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_allowed_path(path, project_root_path)
        return originals["os_mkdir"](path, mode, *args, **kwargs)  # type: ignore[misc]

    def guarded_makedirs(name, mode=0o777, exist_ok=False):  # type: ignore[no-untyped-def]
        _assert_allowed_path(name, project_root_path)
        return originals["os_makedirs"](name, mode=mode, exist_ok=exist_ok)  # type: ignore[misc]

    def guarded_rmdir(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_allowed_path(path, project_root_path)
        return originals["os_rmdir"](path, *args, **kwargs)  # type: ignore[misc]

    builtins_any: Any = builtins
    builtins_any.open = guarded_open
    io_any: Any = io
    io_any.open = guarded_open
    os_any: Any = os
    os_any.open = guarded_os_open
    os_any.remove = guarded_remove
    os_any.unlink = guarded_unlink
    os_any.rename = guarded_rename
    os_any.replace = guarded_replace
    os_any.mkdir = guarded_mkdir
    os_any.makedirs = guarded_makedirs
    os_any.rmdir = guarded_rmdir

    return originals


def _restore_safe_mode_file_write_guards(originals: dict[str, object]) -> None:
    builtins_any: Any = builtins
    builtins_any.open = originals["builtins_open"]
    io_any: Any = io
    io_any.open = originals["io_open"]
    os_any: Any = os
    os_any.open = originals["os_open"]
    os_any.remove = originals["os_remove"]
    os_any.unlink = originals["os_unlink"]
    os_any.rename = originals["os_rename"]
    os_any.replace = originals["os_replace"]
    os_any.mkdir = originals["os_mkdir"]
    os_any.makedirs = originals["os_makedirs"]
    os_any.rmdir = originals["os_rmdir"]


def _restore_safe_mode_guards(originals: dict[str, object]) -> None:
    _restore_safe_mode_subprocess_guards(originals)
    _restore_safe_mode_file_write_guards(originals)


def _is_write_mode(mode: str) -> bool:
    return any(token in mode for token in ("w", "a", "x", "+"))


def _is_write_flags(flags: int) -> bool:
    write_flag_bits = (
        os.O_WRONLY,
        os.O_RDWR,
        os.O_CREAT,
        os.O_APPEND,
        os.O_TRUNC,
    )
    return any(flags & bit for bit in write_flag_bits)


def _assert_allowed_path(path_value: object, project_root: Path) -> None:
    if _is_disallowed_path(path_value, project_root):
        raise PermissionError("write outside project root is disabled in safe mode.")


def _is_disallowed_path(path_value: object, project_root: Path) -> bool:
    if isinstance(path_value, int):
        return False
    try:
        candidate = Path(path_value).expanduser()  # type: ignore[arg-type]
    except TypeError:
        return False
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return not _is_path_within(candidate, project_root)


def _is_path_within(candidate: Path, project_root: Path) -> bool:
    try:
        candidate.relative_to(project_root)
        return True
    except ValueError:
        return False
