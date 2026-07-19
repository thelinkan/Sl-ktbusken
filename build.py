"""Build script for creating a standalone Släktbusken executable.

Usage:
    python build.py

Produces a distributable folder at dist/Slaktbusken/ containing
the .exe and all required runtime files.
"""

import PyInstaller.__main__


def build() -> None:
    """Run PyInstaller with the project spec."""
    PyInstaller.__main__.run([
        "slaktbusken/__main__.py",
        "--name=Slaktbusken",
        "--windowed",
        "--onedir",
        "--noconfirm",
        "--clean",
        # Application icon (shown on .exe and taskbar)
        "--icon=assets/slaktbusken.ico",
        # Bundle the .ico for Qt window icon at runtime
        "--add-data=assets/slaktbusken.ico;assets",
        # Bundle SVG icon directories
        "--add-data=slaktbusken/ui/icons/events;slaktbusken/ui/icons/events",
        "--add-data=slaktbusken/ui/icons/gender;slaktbusken/ui/icons/gender",
        "--add-data=slaktbusken/ui/icons/misc;slaktbusken/ui/icons/misc",
        # Ensure PySide6 plugins are collected
        "--collect-all=PySide6",
    ])


if __name__ == "__main__":
    build()
