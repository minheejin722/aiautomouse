from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from aiautomouse.services.desktop import DesktopAutomationService
from aiautomouse.gui.main_window import MainWindow


def launch_gui(settings_path: str = "config/app.yaml") -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    service = DesktopAutomationService(settings_path=settings_path)
    app.aboutToQuit.connect(service.shutdown)
    window = MainWindow(service)
    window.show()
    return app.exec()
