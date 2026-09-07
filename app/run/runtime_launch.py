"""Shared FreeCAD/AppRun launch helpers used by editor-side supervisors."""

from __future__ import annotations

import errno
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import time
from typing import IO, Mapping, Sequence

from app.core import constants

_APPRUN_ENV_KEYS_TO_DROP = ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT")
_FREECAD_EXECUTABLE_NAMES = {"AppRun", "freecad", "FreeCAD"}


def is_freecad_runtime_executable(runtime_executable: str) -> bool:
    runtime_path = Path(runtime_executable)
    return runtime_path.name in _FREECAD_EXECUTABLE_NAMES or runtime_path.suffix == ".AppImage"


def is_running_inside_freecad_runtime(
    *,
    executable: str | None = None,
    modules: Mapping[str, object] | None = None,
    environ: Mapping[str, str] | None = None,
    argv: Sequence[str] | None = None,
) -> bool:
    current_executable = sys.executable if executable is None else executable
    current_modules = sys.modules if modules is None else modules
    current_environ = os.environ if environ is None else environ
    current_argv = list(sys.argv if argv is None else argv)
    if "FreeCAD" in current_modules:
        return True
    if is_freecad_runtime_executable(current_executable):
        return True
    if current_argv and is_freecad_runtime_executable(current_argv[0]):
        return True
    appdir = current_environ.get("APPDIR")
    if appdir and (Path(appdir) / "AppRun").exists():
        return True
    return False


def should_reexec_runtime(
    runtime_executable: str,
    *,
    inside_freecad: bool | None = None,
) -> bool:
    if not is_freecad_runtime_executable(runtime_executable):
        return False
    if inside_freecad is None:
        inside_freecad = is_running_inside_freecad_runtime()
    return not inside_freecad


def format_nested_runtime_exec_error(
    exc: BaseException,
    runtime_path: str | None = None,
) -> str:
    path = runtime_path or constants.APP_RUN_PATH
    cause = exc.__cause__ if exc.__cause__ is not None else exc
    errno_value = getattr(cause, "errno", None)
    filename = getattr(cause, "filename", None)
    if filename:
        path = str(filename)
    if errno_value == errno.EACCES or isinstance(cause, PermissionError):
        return (
            f"Cannot execute {path} (PermissionError errno {errno.EACCES}). "
            "Plugin host and runner child processes need a working nested runtime."
        )
    return f"Failed to launch plugin host via {path}: {exc}"


class ForkedInterpreterProcess:
    def __init__(
        self,
        pid: int,
        stdin: IO[str],
        stdout: IO[str],
        stderr: IO[str],
    ) -> None:
        self.pid = pid
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.returncode: int | None = None

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        finished_pid, status = os.waitpid(self.pid, os.WNOHANG)
        if finished_pid == 0:
            return None
        self.returncode = _wait_status_to_returncode(status)
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is not None:
            return self.returncode
        if timeout is None:
            _finished_pid, status = os.waitpid(self.pid, 0)
            self.returncode = _wait_status_to_returncode(status)
            return self.returncode
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.poll()
            if result is not None:
                return result
            time.sleep(0.01)
        raise subprocess.TimeoutExpired(str(self.pid), timeout)

    def send_signal(self, sig: int) -> None:
        os.kill(self.pid, sig)

    def terminate(self) -> None:
        self.send_signal(signal.SIGTERM)

    def kill(self) -> None:
        self.send_signal(signal.SIGKILL)


def fork_interpreter_script(
    *,
    script_path: str,
    argv: Sequence[str],
    cwd: str,
    env: Mapping[str, str] | None = None,
) -> ForkedInterpreterProcess:
    stdin_read, stdin_write = os.pipe()
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            os.setsid()
            os.close(stdin_write)
            os.close(stdout_read)
            os.close(stderr_read)
            os.dup2(stdin_read, 0)
            os.dup2(stdout_write, 1)
            os.dup2(stderr_write, 2)
            os.close(stdin_read)
            os.close(stdout_write)
            os.close(stderr_write)
            sys.stdin = os.fdopen(0, "r")
            sys.stdout = os.fdopen(1, "w", buffering=1)
            sys.stderr = os.fdopen(2, "w", buffering=1)
            os.chdir(cwd)
            if env is not None:
                os.environ.clear()
                os.environ.update(env)
            resolved_script = str(Path(script_path).expanduser().resolve())
            script_parent = str(Path(resolved_script).parent)
            if script_parent not in sys.path:
                sys.path.insert(0, script_parent)
            sys.argv = [str(item) for item in argv]
            runpy.run_path(resolved_script, run_name="__main__")
        except SystemExit as exc:
            _flush_stdio()
            code = exc.code
            if code is None:
                os._exit(0)
            if isinstance(code, int):
                os._exit(code)
            os._exit(1)
        except BaseException:
            _flush_stdio()
            os._exit(1)
        _flush_stdio()
        os._exit(0)
    os.close(stdin_read)
    os.close(stdout_write)
    os.close(stderr_write)
    return ForkedInterpreterProcess(
        pid,
        os.fdopen(stdin_write, "w", buffering=1),
        os.fdopen(stdout_read, "r", buffering=1),
        os.fdopen(stderr_read, "r", buffering=1),
    )


def _flush_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except OSError:
            continue


def _wait_status_to_returncode(status: int) -> int:
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return -os.WTERMSIG(status)
    return status


def resolve_runtime_executable(runtime_executable: str | None) -> str:
    if runtime_executable:
        return str(Path(runtime_executable).expanduser().resolve())
    default_runtime = Path(constants.APP_RUN_PATH)
    if default_runtime.exists():
        return str(default_runtime.resolve())
    return sys.executable


def sanitize_apprun_child_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return an AppRun child environment without parent virtualenv activation."""
    resolved = dict(os.environ if env is None else env)
    for key in _APPRUN_ENV_KEYS_TO_DROP:
        resolved.pop(key, None)
    return resolved


def build_runpy_bootstrap_payload(
    *,
    script_path: str,
    path_entry: str | None = None,
    path_entries: tuple[str, ...] | None = None,
    argv: list[str] | None = None,
) -> str:
    resolved_script = str(Path(script_path).expanduser().resolve())
    statements: list[str] = ["import runpy, sys;"]
    resolved_entries: list[str] = []
    if path_entries:
        resolved_entries.extend(str(Path(entry).expanduser().resolve()) for entry in path_entries)
    elif path_entry:
        resolved_entries.append(str(Path(path_entry).expanduser().resolve()))
    for resolved_path_entry in reversed(resolved_entries):
        statements.append(
            f"sys.path.insert(0, {resolved_path_entry!r}) if {resolved_path_entry!r} not in sys.path else None;"
        )
    if argv is not None:
        statements.append(f"sys.argv={[str(a) for a in argv]!r};")
    statements.append(f"runpy.run_path({resolved_script!r}, run_name='__main__')")
    return "".join(statements)
