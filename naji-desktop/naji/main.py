"""Entry point do Naji Desktop (PySide6 + qasync)."""

from __future__ import annotations

import asyncio
import sys

import qasync
from PySide6.QtWidgets import QApplication

from naji.config import get_default_config_path, load_config


def setup_asyncio_policy() -> None:
    """Configura policy do asyncio para Windows (ProactorEventLoop)."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def main() -> int:
    setup_asyncio_policy()

    if sys.platform == "win32":
        from naji.platform.windows import set_process_dpi_aware
        set_process_dpi_aware()

    app = QApplication(sys.argv)
    app.setApplicationName("Naji")
    app.setApplicationVersion("0.2.0")
    app.setQuitOnLastWindowClosed(False)  # Permite rodar só no tray

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    config_path = get_default_config_path()
    config = load_config(config_path if config_path.exists() else None)

    with loop:
        from naji.ui.main_window import MainWindow
        window = MainWindow(config)
        if config.ui.start_minimized:
            window.hide()
        else:
            window.show()
        loop.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
