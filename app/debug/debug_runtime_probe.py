"""Runtime-parity probe for debugger engine selection."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import inspect


@dataclass(frozen=True)
class DebugRuntimeDecision:
    """Evidence snapshot for debugger engine selection."""

    chosen_engine: str
    debugpy_available: bool
    debugpy_rejection_reason: str
    supports_python_threads: bool
    supports_qthread_breakpoints: bool


def probe_debug_runtime() -> DebugRuntimeDecision:
    """Inspect the active runtime and choose the supported debugger engine."""

    debugpy_spec = importlib.util.find_spec("debugpy")
    if debugpy_spec is None:
        return DebugRuntimeDecision(
            chosen_engine="bdb",
            debugpy_available=False,
            debugpy_rejection_reason=(
                "debugpy is not bundled in the active runtime, so the AppRun-safe "
                "adapter-free path cannot be shipped without a separate dependency "
                "and packaging story."
            ),
            supports_python_threads=True,
            supports_qthread_breakpoints=False,
        )

    try:
        import debugpy  # type: ignore[import-not-found]
    except Exception as exc:
        return DebugRuntimeDecision(
            chosen_engine="bdb",
            debugpy_available=False,
            debugpy_rejection_reason="debugpy import failed at runtime: %s" % (exc,),
            supports_python_threads=True,
            supports_qthread_breakpoints=False,
        )

    listen_signature = inspect.signature(debugpy.listen)
    if "in_process_debug_adapter" not in listen_signature.parameters:
        return DebugRuntimeDecision(
            chosen_engine="bdb",
            debugpy_available=True,
            debugpy_rejection_reason=(
                "debugpy is importable but does not expose the in-process adapter "
                "entrypoint required for ChoreBoy's no-extra-subprocess runtime."
            ),
            supports_python_threads=True,
            supports_qthread_breakpoints=False,
        )

    return DebugRuntimeDecision(
        chosen_engine="debugpy",
        debugpy_available=True,
        debugpy_rejection_reason="",
        supports_python_threads=True,
        supports_qthread_breakpoints=True,
    )
