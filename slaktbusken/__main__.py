"""Entry point for running Släktbusken as a module: python -m slaktbusken.

Creates the QApplication, instantiates the Application shell,
shows the main window, and runs the event loop.
"""

import sys

from PySide6.QtWidgets import QApplication

from slaktbusken.app import Application


def main() -> None:
    """Launch the Släktbusken genealogy application."""
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Släktbusken")
    qt_app.setApplicationVersion("0.1.0")
    qt_app.setOrganizationName("Släktbusken")

    app = Application()
    app.main_window.show()

    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
