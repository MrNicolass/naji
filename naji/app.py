"""Desktop entry point: tray-first, single instance, floating bar."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import logging
import sys
from pathlib import Path

import qasync
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from naji import __version__
from naji.config import load_or_create_config
from naji.controller import AppController
from naji.i18n import Translator
from naji.logging_setup import setup_logging
from naji.paths import asset_path
from naji.single_instance import SingleInstanceServer, notify_running_instance
from naji.ui.bar import NajiBar
from naji.ui.theme import build_qss, get_tokens, load_application_fonts
from naji.ui.tray import NajiTray

log = logging.getLogger(__name__)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="naji", description="Naji voice assistant")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    parser.add_argument("--show", action="store_true", help="Open the bar on startup")
    parser.add_argument("--minimized", action="store_true", help="Start in the tray only")
    parser.add_argument("--debug", action="store_true", help="Verbose logging")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Open the bar briefly and exit (used by CI).",
    )
    return parser.parse_args(argv)


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Naji.Desktop")
    except Exception:
        log.debug("Could not set AppUserModelID", exc_info=True)


def run(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))

    if sys.platform == "win32":
        from naji.platform.windows import set_process_dpi_aware

        set_process_dpi_aware()

    _set_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName("Naji")
    app.setApplicationDisplayName("Naji")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    loaded_fonts = load_application_fonts()
    if not loaded_fonts:
        log.warning("Could not load bundled Geist fonts; using system fallbacks")

    icon_path = asset_path("icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    config_path = Path(args.config) if args.config else None
    setup_logging(debug=args.debug, log_dir=(config_path.parent / "logs") if config_path else None)

    try:
        config, config_path = load_or_create_config(config_path)
    except Exception:
        log.exception("Could not load configuration")
        QMessageBox.critical(None, "Naji", "Não foi possível carregar a configuração.")
        return 1

    if notify_running_instance():
        log.info("Naji is already running; asked the existing instance to show the bar")
        return 0

    translator = Translator(config.ui.locale)
    tokens = get_tokens(config.ui.theme)
    app.setStyleSheet(build_qss(tokens))

    server = SingleInstanceServer()
    if not server.listening:
        log.warning("Continuing without single-instance protection")

    bar = NajiBar(config, translator, tokens)
    tray = NajiTray(config, translator, tokens)
    controller = AppController(app, config, config_path, translator, bar, tray)
    server.activated.connect(controller.show_bar)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    app.aboutToQuit.connect(controller.shutdown)
    app.aboutToQuit.connect(loop.stop)

    controller.start(announce=not args.smoke_test)

    if args.smoke_test:

        def _smoke_exit() -> None:
            log.info("Smoke test finished")
            app.quit()
            loop.stop()

        QTimer.singleShot(200, controller.show_bar)
        QTimer.singleShot(1500, _smoke_exit)
    elif args.show or (not config.ui.start_minimized and not args.minimized):
        QTimer.singleShot(0, controller.show_bar)

    log.info(
        "Naji %s ready (config=%s, theme=%s, fonts=%s)",
        __version__,
        config_path,
        config.ui.theme,
        ", ".join(loaded_fonts) or "system fallback",
    )

    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        return 130
    finally:
        controller.shutdown()
        server.close()

    return 0
