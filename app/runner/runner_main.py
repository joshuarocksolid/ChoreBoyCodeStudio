"""Runner process entrypoint implementation."""

from __future__ import annotations

import code
import runpy
import sys

from app.core import constants
from app.core.errors import RunLifecycleError, RunManifestValidationError
from app.run.run_manifest import RunManifest, load_run_manifest
from app.runner.debug_runner import run_debug_session
from app.runner.execution_context import RunnerExecutionContext, apply_execution_context
from app.runner.output_bridge import redirect_output_to_log
from app.runner.traceback_formatter import format_current_exception


class _QuietConsole(code.InteractiveConsole):
    """InteractiveConsole that suppresses prompt output to stdout.

    interact() writes >>> / ... to sys.stdout before each readline.
    Since sys.stdout is piped to the editor process, pipe buffering
    concatenates the prompt with the next result chunk, making per-line
    filtering on the editor side unreliable.
    """

    def raw_input(self, prompt: str = "") -> str:
        sys.stdout.flush()
        line = sys.stdin.readline()
        if not line:
            raise EOFError
        return line.rstrip("\n")


def _make_clear_helper() -> object:
    """Return a callable that tells the user how to clear the console."""

    class _ClearHint:
        def __repr__(self) -> str:
            return "Use Run \u2192 Clear Console to clear the Python Console display."

        def __call__(self) -> None:
            print("Use Run \u2192 Clear Console to clear the Python Console display.")

    return _ClearHint()


def _ensure_line_buffering() -> None:
    """Force line buffering on stdout/stderr to guarantee pipe delivery."""
    stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(stdout_reconfigure):
        try:
            stdout_reconfigure(line_buffering=True)
        except Exception:
            pass
    stderr_reconfigure = getattr(sys.stderr, "reconfigure", None)
    if callable(stderr_reconfigure):
        try:
            stderr_reconfigure(line_buffering=True)
        except Exception:
            pass


def execute_manifest(manifest: RunManifest) -> int:
    """Execute a run manifest and return standardized exit codes."""
    _ensure_line_buffering()
    with redirect_output_to_log(manifest.log_file):
        try:
            execution_context = RunnerExecutionContext.from_manifest(manifest)
        except RunLifecycleError as exc:
            print(f"Runner bootstrap failed: {exc}", file=sys.stderr)
            return constants.RUN_EXIT_BOOTSTRAP_ERROR

        print(f"[runner] run_id={manifest.run_id} mode={manifest.mode} entry={manifest.entry_file}")
        try:
            with apply_execution_context(execution_context):
                if manifest.mode == constants.RUN_MODE_PYTHON_SCRIPT:
                    _run_entry_script(execution_context.entry_script_path)
                elif manifest.mode == constants.RUN_MODE_PYTHON_REPL:
                    _run_interactive_repl()
                elif manifest.mode == constants.RUN_MODE_PYTHON_DEBUG:
                    return run_debug_session(manifest, _run_entry_script, execution_context.entry_script_path)
                else:
                    print(f"Unsupported run mode: {manifest.mode}", file=sys.stderr)
                    return constants.RUN_EXIT_BOOTSTRAP_ERROR
        except SystemExit as exc:
            code = exc.code
            if code is None:
                return constants.RUN_EXIT_SUCCESS
            if isinstance(code, int):
                return code
            print(str(code), file=sys.stderr)
            return constants.RUN_EXIT_USER_CODE_ERROR
        except Exception:
            print(format_current_exception(), file=sys.stderr)
            return constants.RUN_EXIT_USER_CODE_ERROR

        return constants.RUN_EXIT_SUCCESS


def _run_entry_script(entry_script_path: str) -> None:
    runpy.run_path(entry_script_path, run_name="__main__")


def _run_interactive_repl() -> None:
    console = _QuietConsole(locals={
        "__name__": "__console__",
        "__package__": None,
        "clear": _make_clear_helper(),
    })
    banner = (
        "ChoreBoy Python Console (runner process). "
        "Type exit() or Ctrl-D to close."
    )
    console.interact(banner=banner, exitmsg="")


def run_from_manifest_path(manifest_path: str) -> int:
    """Load manifest from disk and execute it."""
    try:
        manifest = load_run_manifest(manifest_path)
    except RunManifestValidationError as exc:
        print(f"Invalid run manifest: {exc}", file=sys.stderr)
        return constants.RUN_EXIT_INVALID_MANIFEST

    return execute_manifest(manifest)
