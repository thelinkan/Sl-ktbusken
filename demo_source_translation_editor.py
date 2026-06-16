"""Demo script to launch the Source Translation Editor with sample data.

Run from the workspace root:
    python demo_source_translation_editor.py
"""

import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Source
from slaktbusken.persistence.translation_io import (
    SourceMapping,
    TranslationData,
    write_sources,
)
from slaktbusken.services.translation_service import TranslationService
from slaktbusken.ui.editors.source_translation_editor import SourceTranslationEditor


def create_sample_project() -> ProjectData:
    """Create a ProjectData with some sample sources for the demo."""
    return ProjectData(
        project=ProjectMetadata(title="Demo-projekt"),
        sources=[
            Source(
                id="source_001",
                provider="ArkivDigital",
                source_type="church_book",
                title="Ljusdal AI:23d (1883-1887)",
                reference_text="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
            ),
            Source(
                id="source_002",
                provider="ArkivDigital",
                source_type="church_book",
                title="Ljusdal CI:12 (1870-1880)",
                reference_text="Ljusdal (X) CI:12 (1870-1880) Bild: 5 Sida: 42",
            ),
            Source(
                id="source_003",
                provider="Riksarkivet",
                source_type="census",
                title="Folkräkning 1890 Ljusdal",
            ),
            Source(
                id="source_004",
                provider="ArkivDigital",
                source_type="church_book",
                title="Delsbo FI:4 (1860-1880)",
                reference_text="Delsbo (X) FI:4 (1860-1880) Bild: 12 Sida: 88",
            ),
            Source(
                id="source_005",
                provider="Tidningar",
                source_type="newspaper",
                title="Hudiksvallsposten 1892-03-15",
            ),
        ],
    )


def create_sample_translations(translation_dir: Path) -> None:
    """Write some sample source translation mappings to disk."""
    mappings = [
        SourceMapping(
            gedcom_id="@S1@",
            app_id="source_001",
            title="Ljusdal AI:23d (1883-1887)",
        ),
        SourceMapping(
            gedcom_id="@S2@",
            app_id="source_002",
            title="Ljusdal CI:12 (1870-1880)",
        ),
        SourceMapping(
            gedcom_id="@S3@",
            app_id="source_003",
            title="Folkräkning 1890 Ljusdal",
        ),
    ]
    translation_dir.mkdir(parents=True, exist_ok=True)
    write_sources(mappings, translation_dir / "sources.json")
    # Create empty places/persons files so load_translations works
    (translation_dir / "places.json").write_text(
        '{"mappings": []}\n', encoding="utf-8"
    )
    (translation_dir / "persons.json").write_text(
        '{"person_mappings": [], "family_mappings": []}\n', encoding="utf-8"
    )


def main() -> int:
    """Launch the Source Translation Editor demo."""
    app = QApplication(sys.argv)

    # Create a temp project directory with sample translation files
    tmp_dir = Path(tempfile.mkdtemp(prefix="slaktbusken_demo_"))
    translation_dir = tmp_dir / "translation"
    create_sample_translations(translation_dir)

    # Set up dependencies
    project_data = create_sample_project()
    translation_service = TranslationService()

    # Create and show the editor
    editor = SourceTranslationEditor(
        translation_service=translation_service,
        project_data=project_data,
        project_path=tmp_dir,
    )
    editor.load_data()
    editor.setWindowTitle("Källöversättningsredigerare — Demo")
    editor.resize(750, 550)
    editor.show()

    print(f"Demo project directory: {tmp_dir}")
    print("Editor loaded with 3 existing mappings and 5 available sources.")
    print("Try: search, add new mappings, edit, remove, and save.")

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
