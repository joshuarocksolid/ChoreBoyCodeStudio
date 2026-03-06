"""Editor entrypoint with logging-aware startup handling."""

import faulthandler
import logging
import importlib
import sys
from typing import Any, Optional

from app.bootstrap.capability_probe import run_startup_capability_probe
from app.bootstrap.logging_setup import configure_app_logging, get_subsystem_logger, TIER_STDERR
from app.core.models import CapabilityProbeReport
from app.treesitter.loader import initialize_tree_sitter_runtime, runtime_traceback

_LAST_STARTUP_CAPABILITY_REPORT: Optional[CapabilityProbeReport] = None


def _start_editor() -> int:
    """Launch the Qt shell window and start the UI event loop."""
    application_class, main_window_class = _load_qt_runtime()

    application = application_class.instance()
    if application is None:
        application = application_class(sys.argv)

    window = main_window_class(startup_report=_LAST_STARTUP_CAPABILITY_REPORT)
    window.showMaximized()
    return application.exec_()


def _load_qt_runtime() -> tuple[Any, Any]:
    """Load runtime-only Qt dependencies lazily."""
    application_class = importlib.import_module("PySide2.QtWidgets").QApplication
    main_window_class = importlib.import_module("app.shell.main_window").MainWindow
    return application_class, main_window_class


def get_last_startup_capability_report() -> Optional[CapabilityProbeReport]:
    """Return the latest startup probe report for diagnostics/UI wiring."""
    return _LAST_STARTUP_CAPABILITY_REPORT


def _log_capability_probe_results(logger: logging.Logger, report: CapabilityProbeReport) -> None:
    """Emit startup capability results with clear pass/fail messaging."""
    if report.all_available:
        logger.info("Startup capability probe passed: %s/%s checks available.", report.available_count, report.total_count)
    else:
        logger.warning(
            "Startup capability probe reported issues: %s/%s checks available. Failed checks: %s",
            report.available_count,
            report.total_count,
            ",".join(report.failed_check_ids),
        )

    for check in report.checks:
        if check.is_available:
            logger.info("Capability check passed [%s]: %s", check.check_id, check.message)
            continue
        logger.warning("Capability check failed [%s]: %s", check.check_id, check.message)


def _install_unhandled_exception_hook(logger: logging.Logger) -> None:
    previous_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_traceback) -> None:
        logger.critical(
            "Unhandled exception in editor process.",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        try:
            previous_hook(exc_type, exc_value, exc_traceback)
        except Exception:
            pass

    sys.excepthook = _hook


def _enable_fault_handler(logger: logging.Logger) -> None:
    try:
        faulthandler.enable()
    except Exception:
        logger.warning("Failed to enable faulthandler.", exc_info=True)


def main() -> int:
    """Initialize logging first, then run editor startup safely."""
    global _LAST_STARTUP_CAPABILITY_REPORT
    logging_result = configure_app_logging()

    logger = get_subsystem_logger("editor")
    _enable_fault_handler(logger)
    _install_unhandled_exception_hook(logger)

    for warning in logging_result.warnings:
        logger.warning(warning)

    if logging_result.tier == TIER_STDERR:
        print(
            "WARNING: Could not create log file. Logging to stderr only. "
            "Check directory permissions.",
            file=sys.stderr,
        )

    try:
        _LAST_STARTUP_CAPABILITY_REPORT = run_startup_capability_probe()
        _log_capability_probe_results(logger, _LAST_STARTUP_CAPABILITY_REPORT)
        tree_sitter_status = initialize_tree_sitter_runtime()
        if tree_sitter_status.is_available:
            logger.info("Tree-sitter runtime initialized: %s", tree_sitter_status.message)
        else:
            logger.warning("Tree-sitter runtime unavailable: %s", tree_sitter_status.message)
            failure_traceback = runtime_traceback()
            if failure_traceback:
                logger.debug("Tree-sitter initialization traceback:\n%s", failure_traceback)

        logger.info("Editor startup initialized.")
        return _start_editor()
    except Exception:
        logger.exception("Editor startup failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
