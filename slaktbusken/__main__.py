"""Entry point for running Släktbusken as a module: python -m slaktbusken.

Creates the QApplication, instantiates the Application shell,
shows the main window, and runs the event loop.
"""

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from slaktbusken.app import Application


def _get_app_icon() -> QIcon:
    """Load the application icon, handling both normal and frozen (PyInstaller) mode."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    icon_path = base / "assets" / "slaktbusken.ico"
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()


def main() -> None:
    """Launch the Släktbusken genealogy application."""
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Släktbusken")
    qt_app.setApplicationVersion("0.2.0")
    qt_app.setOrganizationName("Släktbusken")
    qt_app.setWindowIcon(_get_app_icon())

    app = Application()
    app.main_window.show()

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
