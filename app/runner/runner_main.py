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


def execute_manifest(manifest: RunManifest) -> int:
    """Execute a run manifest and return standardized exit codes."""
    try:
        execution_context = RunnerExecutionContext.from_manifest(manifest)
    except RunLifecycleError as exc:
        print(f"Runner bootstrap failed: {exc}", file=sys.stderr)
        return constants.RUN_EXIT_BOOTSTRAP_ERROR

    with redirect_output_to_log(manifest.log_file):
        print(f"[runner] run_id={manifest.run_id} mode={manifest.mode} entry={manifest.entry_file}")
        try:
            with apply_execution_context(execution_context):
                if manifest.mode in {
                    constants.RUN_MODE_PYTHON_SCRIPT,
                    constants.RUN_MODE_QT_APP,
                    constants.RUN_MODE_FREECAD_HEADLESS,
                }:
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
    console = code.InteractiveConsole(locals={"__name__": "__console__", "__package__": None})
    banner = (
        "ChoreBoy Python Console\n"
        f"Python {sys.version} on {sys.platform}\n"
        'Type "help", "copyright", "credits" or "license" for more information.\n'
        "Type exit() or Ctrl-D to quit."
    )
    console.interact(
        banner=banner,
        exitmsg="Python console session ended.",
    )


def run_from_manifest_path(manifest_path: str) -> int:
    """Load manifest from disk and execute it."""
    try:
        manifest = load_run_manifest(manifest_path)
    except RunManifestValidationError as exc:
        print(f"Invalid run manifest: {exc}", file=sys.stderr)
        return constants.RUN_EXIT_INVALID_MANIFEST

    return execute_manifest(manifest)
