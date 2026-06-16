"""Demo script to review the Place Translation Editor.

Run with:
    python demo_place_translation_editor.py

This creates a mock project with Swedish places in a hierarchy and
pre-populates some GEDCOM→App_JSON place mappings so you can see
the editor in action: search, add, edit, remove mappings, and see
the hierarchy visualization.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.translation_io import PlaceMapping, TranslationData
from slaktbusken.services.translation_service import TranslationService
from slaktbusken.ui.editors.place_translation_editor import PlaceTranslationEditor


def create_sample_project() -> ProjectData:
    """Create a sample project with a Swedish place hierarchy."""
    places = [
        Place(id="place_1", type="country", name="Sverige"),
        Place(id="place_2", type="county", name="Gävleborgs län", parent_place_id="place_1"),
        Place(id="place_3", type="parish", name="Ljusdal", parent_place_id="place_2"),
        Place(id="place_4", type="church", name="Ljusdals kyrka", parent_place_id="place_3"),
        Place(id="place_5", type="cemetery", name="Ljusdals kyrkogård", parent_place_id="place_3"),
        Place(id="place_6", type="county", name="Stockholms län", parent_place_id="place_1"),
        Place(id="place_7", type="parish", name="Stockholm", parent_place_id="place_6"),
        Place(id="place_8", type="church", name="Storkyrkan", parent_place_id="place_7"),
        Place(id="place_9", type="county", name="Västernorrlands län", parent_place_id="place_1"),
        Place(id="place_10", type="parish", name="Sundsvall", parent_place_id="place_9"),
        Place(id="place_11", type="parish", name="Ånge", parent_place_id="place_9"),
        Place(id="place_12", type="church", name="Ånge kyrka", parent_place_id="place_11"),
    ]

    return ProjectData(
        project=ProjectMetadata(title="Demo-projekt"),
        places=places,
    )


def create_sample_translations() -> TranslationData:
    """Create some pre-existing place translation mappings.

    Includes both mapped entries (with valid app_id) and unmapped entries
    (empty app_id) to demonstrate the 'create new place' workflow.
    """
    return TranslationData(
        places=[
            PlaceMapping(
                gedcom_place="Ljusdal, Gävleborgs län, Sverige",
                app_id="place_3",
                name="Ljusdal",
            ),
            PlaceMapping(
                gedcom_place="Ljusdals kyrka, Ljusdal, Gävleborgs län",
                app_id="place_4",
                name="Ljusdals kyrka",
            ),
            PlaceMapping(
                gedcom_place="Stockholm, Stockholms län, Sverige",
                app_id="place_7",
                name="Stockholm",
            ),
            PlaceMapping(
                gedcom_place="Sundsvall, Västernorrlands län, Sverige",
                app_id="place_10",
                name="Sundsvall",
            ),
            # Unmapped entries — these came from GEDCOM but have no App_JSON target yet
            PlaceMapping(
                gedcom_place="Hudiksvall, Gävleborgs län, Sverige",
                app_id="",
                name="",
            ),
            PlaceMapping(
                gedcom_place="Bollnäs, Gävleborgs län, Sverige",
                app_id="",
                name="",
            ),
            PlaceMapping(
                gedcom_place="Söderhamn, Gävleborgs län, Sverige",
                app_id="",
                name="",
            ),
            PlaceMapping(
                gedcom_place="Mora, Kopparbergs län, Sverige",
                app_id="",
                name="",
            ),
        ]
    )


def main() -> None:
    """Launch the Place Translation Editor demo."""
    app = QApplication(sys.argv)

    # Create sample data
    project_data = create_sample_project()
    sample_translations = create_sample_translations()

    # Use a temp dir as "project path"
    tmp_dir = Path(tempfile.mkdtemp(prefix="slaktbusken_demo_"))
    translation_dir = tmp_dir / "translation"
    translation_dir.mkdir(parents=True, exist_ok=True)

    # Create a translation service and patch load to return our sample data
    translation_service = TranslationService()

    # Patch load_translations to return our sample data without needing files
    original_load = translation_service.load_translations

    def mock_load(project_path: Path) -> TranslationData:
        return sample_translations

    translation_service.load_translations = mock_load  # type: ignore[method-assign]

    # Create the editor
    editor = PlaceTranslationEditor(
        translation_service=translation_service,
        project_data=project_data,
        project_path=tmp_dir,
    )

    # Load data into the editor
    editor.load_data()

    # Show the editor
    editor.setWindowTitle("Demo: Platsöversättningsredigerare")
    editor.resize(800, 600)
    editor.show()

    print("=" * 60)
    print("  DEMO: Place Translation Editor")
    print("=" * 60)
    print()
    print("  Things to try:")
    print("  1. Notice the yellow rows — those are UNMAPPED GEDCOM places")
    print("  2. Select an unmapped row (e.g. 'Hudiksvall, Gävleborgs län')")
    print("  3. Click 'Skapa ny plats...' to create a new App_JSON Place")
    print("     - Set the type (Församling, Län, etc.)")
    print("     - Pick a parent place (e.g. Gävleborgs län)")
    print("     - See the hierarchy preview update live")
    print("     - Click 'Skapa' to create it")
    print("  4. The new place appears in the combo — click 'Lägg till' to map it")
    print("  5. Try search, edit, remove as before")
    print("  6. Click 'Spara' to test save (writes to temp dir)")
    print()
    print(f"  Temp project path: {tmp_dir}")
    print("=" * 60)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
