"""Compile all .ui and .qrc files to Python modules."""

import subprocess
from pathlib import Path

FORMS_DIR = Path("slaktbusken/ui/forms")
GENERATED_DIR = Path("slaktbusken/ui/generated")
RESOURCES_DIR = Path("slaktbusken/ui/resources")


def compile_ui_files() -> None:
    """Compile all Qt Designer .ui files to Python modules via pyside6-uic."""
    for ui_file in FORMS_DIR.glob("*.ui"):
        output = GENERATED_DIR / f"ui_{ui_file.stem}.py"
        subprocess.run(["pyside6-uic", str(ui_file), "-o", str(output)], check=True)
        print(f"Compiled: {ui_file.name} \u2192 {output.name}")


def compile_resources() -> None:
    """Compile all .qrc resource files to Python modules via pyside6-rcc."""
    for qrc_file in RESOURCES_DIR.glob("*.qrc"):
        output = GENERATED_DIR / f"{qrc_file.stem}_rc.py"
        subprocess.run(["pyside6-rcc", str(qrc_file), "-o", str(output)], check=True)
        print(f"Compiled: {qrc_file.name} \u2192 {output.name}")


if __name__ == "__main__":
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    compile_ui_files()
    compile_resources()
