"""Editor entrypoint with logging-aware startup handling."""

import logging

from app.bootstrap.logging_setup import configure_app_logging, get_subsystem_logger


def _start_editor() -> int:
    """Placeholder startup body for the editor shell."""
    return 0


def main() -> int:
    """Initialize logging first, then run editor startup safely."""
    try:
        configure_app_logging()
    except Exception:
        logging.getLogger(__name__).exception("Failed to initialize editor logging.")
        return 1

    logger = get_subsystem_logger("editor")
    try:
        logger.info("Editor startup initialized.")
        return _start_editor()
    except Exception:
        logger.exception("Editor startup failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
