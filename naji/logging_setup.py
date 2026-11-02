"""Logging configuration for the desktop app."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from naji.config import get_log_dir


def setup_logging(*, debug: bool = False, log_dir: str | Path | None = None) -> Path:
    """Configure console + rotating file logging and return the log path."""
    directory = Path(log_dir) if log_dir else get_log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "naji.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    if not getattr(root, "_naji_configured", False):
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler._naji_handler = True  # type: ignore[attr-defined]

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler._naji_handler = True  # type: ignore[attr-defined]

        root.addHandler(file_handler)
        root.addHandler(stream_handler)
        root._naji_configured = True  # type: ignore[attr-defined]

        logging.captureWarnings(True)
        sys.excepthook = _log_uncaught

    return log_path


def _log_uncaught(exc_type, exc_value, exc_tb) -> None:
    logging.getLogger("naji").critical(
        "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb)
    )
    sys.__excepthook__(exc_type, exc_value, exc_tb)
