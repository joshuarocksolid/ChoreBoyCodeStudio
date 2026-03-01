"""Editor entrypoint with logging-aware startup handling."""

import logging
import importlib
import sys
from typing import Optional

from app.bootstrap.capability_probe import run_startup_capability_probe
from app.bootstrap.logging_setup import configure_app_logging, get_subsystem_logger
from app.core.models import CapabilityProbeReport

_LAST_STARTUP_CAPABILITY_REPORT: Optional[CapabilityProbeReport] = None


def _start_editor() -> int:
    """Launch the Qt shell window and start the UI event loop."""
    application_class, main_window_class = _load_qt_runtime()

    application = application_class.instance()
    if application is None:
        application = application_class(sys.argv)

    window = main_window_class(startup_report=_LAST_STARTUP_CAPABILITY_REPORT)
    window.show()
    return application.exec_()


def _load_qt_runtime() -> tuple[object, object]:
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


def main() -> int:
    """Initialize logging first, then run editor startup safely."""
    global _LAST_STARTUP_CAPABILITY_REPORT
    try:
        configure_app_logging()
    except Exception:
        logging.getLogger(__name__).exception("Failed to initialize editor logging.")
        return 1

    logger = get_subsystem_logger("editor")
    try:
        _LAST_STARTUP_CAPABILITY_REPORT = run_startup_capability_probe()
        _log_capability_probe_results(logger, _LAST_STARTUP_CAPABILITY_REPORT)

        logger.info("Editor startup initialized.")
        return _start_editor()
    except Exception:
        logger.exception("Editor startup failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
