"""Unit tests for TranslationService.

Tests cover the translation file lifecycle: loading, saving, and updating
mappings. Validates that the service properly coordinates with the
persistence layer and handles errors with Swedish messages.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from slaktbusken.persistence.translation_io import (
    FamilyMapping,
    PersonMapping,
    PlaceMapping,
    SourceMapping,
    TranslationData,
    TranslationIOError,
    write_all,
)
from slaktbusken.services.translation_service import (
    TranslationEntry,
    TranslationService,
    TranslationServiceError,
)


@pytest.fixture
def service() -> TranslationService:
    """Create a fresh TranslationService instance."""
    return TranslationService()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a project folder with a translation subdirectory and empty files."""
    project_folder = tmp_path / "TestProjekt"
    project_folder.mkdir()
    translation_dir = project_folder / "translation"
    translation_dir.mkdir()
    # Write empty translation files.
    write_all(TranslationData(), translation_dir)
    return project_folder


@pytest.fixture
def project_file(project_dir: Path) -> Path:
    """Create a fake .json.gz file path inside the project folder."""
    data_file = project_dir / "TestProjekt.json.gz"
    data_file.write_bytes(b"")  # Create the file so is_file() returns True.
    return data_file


@pytest.fixture
def populated_translation_dir(project_dir: Path) -> Path:
    """Create translation files with sample data."""
    data = TranslationData(
        sources=[
            SourceMapping(gedcom_id="@S1@", app_id="source_001", title="Födelseboken"),
            SourceMapping(gedcom_id="@S2@", app_id="source_002", title="Dödboken"),
        ],
        places=[
            PlaceMapping(
                gedcom_place="Ljusdal, Gävleborgs län, Sverige",
                app_id="place_ljusdal",
                name="Ljusdal",
            ),
        ],
        persons=[
            PersonMapping(gedcom_id="@I1@", app_id="person_001", fingerprint="abc123"),
        ],
        families=[
            FamilyMapping(gedcom_id="@F1@", app_id="family_001"),
        ],
    )
    translation_dir = project_dir / "translation"
    write_all(data, translation_dir)
    return project_dir


# ---------------------------------------------------------------------------
# 6.1 / 6.3 – Load translation files (sources and places)
# ---------------------------------------------------------------------------


class TestLoadTranslations:
    """Tests for TranslationService.load_translations."""

    def test_load_empty_translations(
        self, service: TranslationService, project_dir: Path
    ) -> None:
        """Loading from a project with empty translation files returns empty data."""
        result = service.load_translations(project_dir)
        assert result.sources == []
        assert result.places == []
        assert result.persons == []
        assert result.families == []

    def test_load_from_folder_path(
        self, service: TranslationService, populated_translation_dir: Path
    ) -> None:
        """Loading from a folder path resolves the translation dir correctly."""
        result = service.load_translations(populated_translation_dir)
        assert len(result.sources) == 2
        assert len(result.places) == 1
        assert len(result.persons) == 1
        assert len(result.families) == 1

    def test_load_from_file_path(
        self, service: TranslationService, populated_translation_dir: Path
    ) -> None:
        """Loading from a .json.gz file path resolves the translation dir."""
        # Create a fake .json.gz file.
        data_file = populated_translation_dir / "TestProjekt.json.gz"
        data_file.write_bytes(b"")

        result = service.load_translations(data_file)
        assert len(result.sources) == 2
        assert result.sources[0].gedcom_id == "@S1@"
        assert result.sources[0].title == "Födelseboken"

    def test_load_sources_have_correct_fields(
        self, service: TranslationService, populated_translation_dir: Path
    ) -> None:
        """Loaded source mappings have gedcom_id, app_id, and title."""
        result = service.load_translations(populated_translation_dir)
        source = result.sources[0]
        assert source.gedcom_id == "@S1@"
        assert source.app_id == "source_001"
        assert source.title == "Födelseboken"

    def test_load_places_have_correct_fields(
        self, service: TranslationService, populated_translation_dir: Path
    ) -> None:
        """Loaded place mappings have gedcom_place, app_id, and name."""
        result = service.load_translations(populated_translation_dir)
        place = result.places[0]
        assert place.gedcom_place == "Ljusdal, Gävleborgs län, Sverige"
        assert place.app_id == "place_ljusdal"
        assert place.name == "Ljusdal"

    def test_load_error_raises_service_error(
        self, service: TranslationService, tmp_path: Path
    ) -> None:
        """Loading from invalid translation files raises TranslationServiceError."""
        project_folder = tmp_path / "BadProject"
        project_folder.mkdir()
        translation_dir = project_folder / "translation"
        translation_dir.mkdir()
        # Write invalid JSON to sources.json.
        (translation_dir / "sources.json").write_text(
            "not valid json", encoding="utf-8"
        )

        with pytest.raises(TranslationServiceError) as exc_info:
            service.load_translations(project_folder)
        assert "Kunde inte läsa" in str(exc_info.value)

    def test_load_missing_files_returns_empty_lists(
        self, service: TranslationService, tmp_path: Path
    ) -> None:
        """If translation files don't exist, returns empty lists (not error)."""
        project_folder = tmp_path / "EmptyProject"
        project_folder.mkdir()
        (project_folder / "translation").mkdir()

        result = service.load_translations(project_folder)
        assert result.sources == []
        assert result.places == []
        assert result.persons == []
        assert result.families == []


# ---------------------------------------------------------------------------
# 6.2 / 6.4 – Save translation files (persist validated mappings)
# ---------------------------------------------------------------------------


class TestSaveTranslations:
    """Tests for TranslationService.save_translations."""

    def test_save_persists_data(
        self, service: TranslationService, project_dir: Path
    ) -> None:
        """Saving translation data writes it to disk and can be reloaded."""
        data = TranslationData(
            sources=[SourceMapping(gedcom_id="@S5@", app_id="src_5", title="Källa")],
            places=[PlaceMapping(gedcom_place="Stockholm", app_id="pl_1", name="Stockholm")],
            persons=[PersonMapping(gedcom_id="@I5@", app_id="p_5")],
            families=[FamilyMapping(gedcom_id="@F5@", app_id="f_5")],
        )

        service.save_translations(data, project_dir)

        # Reload and verify.
        loaded = service.load_translations(project_dir)
        assert len(loaded.sources) == 1
        assert loaded.sources[0].gedcom_id == "@S5@"
        assert loaded.sources[0].title == "Källa"
        assert len(loaded.places) == 1
        assert loaded.places[0].gedcom_place == "Stockholm"
        assert len(loaded.persons) == 1
        assert len(loaded.families) == 1

    def test_save_from_file_path(
        self, service: TranslationService, project_file: Path
    ) -> None:
        """Saving using a .json.gz file path resolves translation dir correctly."""
        data = TranslationData(
            sources=[SourceMapping(gedcom_id="@S9@", app_id="src_9", title="Test")],
        )

        service.save_translations(data, project_file)

        # Verify by reading from the folder.
        loaded = service.load_translations(project_file)
        assert len(loaded.sources) == 1
        assert loaded.sources[0].gedcom_id == "@S9@"

    def test_save_overwrites_existing_data(
        self, service: TranslationService, populated_translation_dir: Path
    ) -> None:
        """Saving replaces existing translation file content completely."""
        # Start with populated data (2 sources), save with just 1.
        new_data = TranslationData(
            sources=[SourceMapping(gedcom_id="@S99@", app_id="src_99", title="Ny")],
        )

        service.save_translations(new_data, populated_translation_dir)
        loaded = service.load_translations(populated_translation_dir)

        assert len(loaded.sources) == 1
        assert loaded.sources[0].gedcom_id == "@S99@"
        # Old places/persons/families should be empty since we saved empty lists.
        assert loaded.places == []
        assert loaded.persons == []

    def test_save_error_raises_service_error_with_swedish_message(
        self, service: TranslationService, tmp_path: Path
    ) -> None:
        """Save failure raises TranslationServiceError with Swedish message (req 6.6)."""
        project_folder = tmp_path / "ReadOnlyProject"
        project_folder.mkdir()

        data = TranslationData(
            sources=[SourceMapping(gedcom_id="@S1@", app_id="s1", title="T")],
        )

        # Simulate write failure by patching write_all to raise TranslationIOError.
        with patch(
            "slaktbusken.services.translation_service.write_all",
            side_effect=TranslationIOError(
                "Permission denied", path=project_folder / "translation"
            ),
        ):
            with pytest.raises(TranslationServiceError) as exc_info:
                service.save_translations(data, project_folder)

            error_msg = str(exc_info.value)
            assert "Kunde inte spara" in error_msg
            assert "minnet" in error_msg  # Mentions data retained in memory.

    def test_save_error_retains_data_in_memory(
        self, service: TranslationService, tmp_path: Path
    ) -> None:
        """On save failure, the TranslationData object is not modified (req 6.6)."""
        project_folder = tmp_path / "FailProject"
        project_folder.mkdir()

        data = TranslationData(
            sources=[SourceMapping(gedcom_id="@S1@", app_id="s1", title="Källa")],
            places=[PlaceMapping(gedcom_place="Ort", app_id="pl1", name="Ort")],
        )

        with patch(
            "slaktbusken.services.translation_service.write_all",
            side_effect=TranslationIOError(
                "Disk full", path=project_folder / "translation"
            ),
        ):
            with pytest.raises(TranslationServiceError):
                service.save_translations(data, project_folder)

        # Data should be unchanged.
        assert len(data.sources) == 1
        assert data.sources[0].gedcom_id == "@S1@"
        assert len(data.places) == 1


# ---------------------------------------------------------------------------
# 6.5 – Update mappings (add new GEDCOM↔App_JSON entries)
# ---------------------------------------------------------------------------


class TestUpdateMappings:
    """Tests for TranslationService.update_mappings."""

    def test_add_new_source_mapping(self, service: TranslationService) -> None:
        """Adding a new source mapping appends it to the list."""
        data = TranslationData()
        new_mappings: list[TranslationEntry] = [
            SourceMapping(gedcom_id="@S10@", app_id="source_10", title="Ny källa"),
        ]

        result = service.update_mappings(data, new_mappings)

        assert len(result.sources) == 1
        assert result.sources[0].gedcom_id == "@S10@"
        assert result.sources[0].title == "Ny källa"

    def test_add_new_place_mapping(self, service: TranslationService) -> None:
        """Adding a new place mapping appends it to the list."""
        data = TranslationData()
        new_mappings: list[TranslationEntry] = [
            PlaceMapping(gedcom_place="Gävle, Sverige", app_id="pl_gavle", name="Gävle"),
        ]

        result = service.update_mappings(data, new_mappings)

        assert len(result.places) == 1
        assert result.places[0].gedcom_place == "Gävle, Sverige"

    def test_add_new_person_mapping(self, service: TranslationService) -> None:
        """Adding a new person mapping appends it to the list."""
        data = TranslationData()
        new_mappings: list[TranslationEntry] = [
            PersonMapping(gedcom_id="@I99@", app_id="person_99", fingerprint="xyz"),
        ]

        result = service.update_mappings(data, new_mappings)

        assert len(result.persons) == 1
        assert result.persons[0].gedcom_id == "@I99@"
        assert result.persons[0].fingerprint == "xyz"

    def test_add_new_family_mapping(self, service: TranslationService) -> None:
        """Adding a new family mapping appends it to the list."""
        data = TranslationData()
        new_mappings: list[TranslationEntry] = [
            FamilyMapping(gedcom_id="@F10@", app_id="family_10"),
        ]

        result = service.update_mappings(data, new_mappings)

        assert len(result.families) == 1
        assert result.families[0].gedcom_id == "@F10@"

    def test_add_multiple_mapping_types(self, service: TranslationService) -> None:
        """Adding multiple mapping types in one call works correctly."""
        data = TranslationData()
        new_mappings: list[TranslationEntry] = [
            SourceMapping(gedcom_id="@S1@", app_id="s1", title="Källa 1"),
            PlaceMapping(gedcom_place="Ort", app_id="p1", name="Ort"),
            PersonMapping(gedcom_id="@I1@", app_id="per1"),
            FamilyMapping(gedcom_id="@F1@", app_id="fam1"),
        ]

        result = service.update_mappings(data, new_mappings)

        assert len(result.sources) == 1
        assert len(result.places) == 1
        assert len(result.persons) == 1
        assert len(result.families) == 1

    def test_upsert_existing_source_mapping(self, service: TranslationService) -> None:
        """Updating an existing source mapping replaces it (same gedcom_id)."""
        data = TranslationData(
            sources=[SourceMapping(gedcom_id="@S1@", app_id="old_id", title="Gammal")],
        )
        new_mappings: list[TranslationEntry] = [
            SourceMapping(gedcom_id="@S1@", app_id="new_id", title="Ny titel"),
        ]

        result = service.update_mappings(data, new_mappings)

        assert len(result.sources) == 1
        assert result.sources[0].app_id == "new_id"
        assert result.sources[0].title == "Ny titel"

    def test_upsert_existing_place_mapping(self, service: TranslationService) -> None:
        """Updating an existing place mapping replaces it (same gedcom_place)."""
        data = TranslationData(
            places=[PlaceMapping(gedcom_place="Ljusdal", app_id="old_pl", name="Gammal")],
        )
        new_mappings: list[TranslationEntry] = [
            PlaceMapping(gedcom_place="Ljusdal", app_id="new_pl", name="Ny"),
        ]

        result = service.update_mappings(data, new_mappings)

        assert len(result.places) == 1
        assert result.places[0].app_id == "new_pl"
        assert result.places[0].name == "Ny"

    def test_upsert_existing_person_mapping(self, service: TranslationService) -> None:
        """Updating an existing person mapping replaces it (same gedcom_id)."""
        data = TranslationData(
            persons=[PersonMapping(gedcom_id="@I1@", app_id="old_p", fingerprint="old")],
        )
        new_mappings: list[TranslationEntry] = [
            PersonMapping(gedcom_id="@I1@", app_id="new_p", fingerprint="new"),
        ]

        result = service.update_mappings(data, new_mappings)

        assert len(result.persons) == 1
        assert result.persons[0].app_id == "new_p"
        assert result.persons[0].fingerprint == "new"

    def test_upsert_existing_family_mapping(self, service: TranslationService) -> None:
        """Updating an existing family mapping replaces it (same gedcom_id)."""
        data = TranslationData(
            families=[FamilyMapping(gedcom_id="@F1@", app_id="old_f")],
        )
        new_mappings: list[TranslationEntry] = [
            FamilyMapping(gedcom_id="@F1@", app_id="new_f"),
        ]

        result = service.update_mappings(data, new_mappings)

        assert len(result.families) == 1
        assert result.families[0].app_id == "new_f"

    def test_update_returns_same_object(self, service: TranslationService) -> None:
        """update_mappings returns the same TranslationData instance (mutated)."""
        data = TranslationData()
        new_mappings: list[TranslationEntry] = [
            SourceMapping(gedcom_id="@S1@", app_id="s1", title="T"),
        ]

        result = service.update_mappings(data, new_mappings)
        assert result is data

    def test_empty_mappings_list_no_change(self, service: TranslationService) -> None:
        """Passing an empty list does not modify the data."""
        data = TranslationData(
            sources=[SourceMapping(gedcom_id="@S1@", app_id="s1", title="T")],
        )

        result = service.update_mappings(data, [])

        assert len(result.sources) == 1
        assert result.sources[0].gedcom_id == "@S1@"


# ---------------------------------------------------------------------------
# Integration: load → update → save round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Integration tests for the full load → update → save lifecycle."""

    def test_load_update_save_round_trip(
        self, service: TranslationService, project_dir: Path
    ) -> None:
        """Full round-trip: load, update, save, reload verifies persistence."""
        # Load empty.
        data = service.load_translations(project_dir)
        assert data.sources == []

        # Update with new mappings.
        new_mappings: list[TranslationEntry] = [
            SourceMapping(gedcom_id="@S1@", app_id="source_1", title="Dödboken"),
            PlaceMapping(gedcom_place="Uppsala, Sverige", app_id="pl_ups", name="Uppsala"),
        ]
        service.update_mappings(data, new_mappings)

        # Save.
        service.save_translations(data, project_dir)

        # Reload and verify.
        reloaded = service.load_translations(project_dir)
        assert len(reloaded.sources) == 1
        assert reloaded.sources[0].title == "Dödboken"
        assert len(reloaded.places) == 1
        assert reloaded.places[0].name == "Uppsala"

    def test_update_existing_then_save(
        self, service: TranslationService, populated_translation_dir: Path
    ) -> None:
        """Updating an existing mapping and saving persists the change."""
        data = service.load_translations(populated_translation_dir)
        assert data.sources[0].title == "Födelseboken"

        # Update the title.
        new_mappings: list[TranslationEntry] = [
            SourceMapping(gedcom_id="@S1@", app_id="source_001", title="Uppdaterad"),
        ]
        service.update_mappings(data, new_mappings)
        service.save_translations(data, populated_translation_dir)

        # Reload and verify.
        reloaded = service.load_translations(populated_translation_dir)
        assert reloaded.sources[0].title == "Uppdaterad"
        # Other source should still exist.
        assert len(reloaded.sources) == 2
