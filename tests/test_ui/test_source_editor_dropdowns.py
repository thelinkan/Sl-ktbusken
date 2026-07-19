"""Unit tests for SourceEditor Leverantör/Källtyp dropdown behavior.

Tests that:
- Provider combo is populated with all Leverantörer
- Källtyp combo updates when Leverantör changes
- Save stores correct leverantor_id and kalltyp_id
- Load pre-selects correct items in both combos
- Provider combo has empty first entry
- Källtyp combo resets when provider changes

Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5
"""

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QApplication

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Kalltyp, Leverantor, Source
from slaktbusken.ui.editors.source_editor import SourceEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def project_with_three_leverantorer() -> ProjectData:
    """Create a project with 3 Leverantörer and associated Källtyper."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        leverantorer=[
            Leverantor(id="lev-1", name="Arkiv Digital"),
            Leverantor(id="lev-2", name="Rötter.se"),
            Leverantor(id="lev-3", name="SVAR"),
        ],
        kalltyper=[
            Kalltyp(id="kt-1", leverantor_id="lev-1", name="Husförhörslängd"),
            Kalltyp(id="kt-2", leverantor_id="lev-1", name="Födelse- och dopbok"),
            Kalltyp(id="kt-3", leverantor_id="lev-2", name="Sveriges Dödbok Webb",
                    root_url="https://www.rotter.se/post/"),
            Kalltyp(id="kt-4", leverantor_id="lev-3", name="Folkräkning"),
        ],
    )


@pytest.fixture()
def project_with_two_leverantorer() -> ProjectData:
    """Create a project with 2 Leverantörer having different Källtyper."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        leverantorer=[
            Leverantor(id="lev-a", name="Leverantör A"),
            Leverantor(id="lev-b", name="Leverantör B"),
        ],
        kalltyper=[
            Kalltyp(id="kt-a1", leverantor_id="lev-a", name="Typ A1"),
            Kalltyp(id="kt-a2", leverantor_id="lev-a", name="Typ A2"),
            Kalltyp(id="kt-b1", leverantor_id="lev-b", name="Typ B1"),
        ],
    )


class TestProviderComboPopulated:
    """Tests for Requirement 12.1: Provider combo populated with all Leverantörer."""

    def test_provider_combo_populated_with_all_leverantorer(
        self, qapp, project_with_three_leverantorer
    ) -> None:
        """Provider combo has empty + 3 Leverantörer = 4 items total."""
        editor = SourceEditor(
            project_data=project_with_three_leverantorer,
        )
        combo = editor._ui.provider_combo

        # 1 empty + 3 leverantörer = 4 items
        assert combo.count() == 4

        # Verify names match
        assert combo.itemText(1) == "Arkiv Digital"
        assert combo.itemText(2) == "Rötter.se"
        assert combo.itemText(3) == "SVAR"

    def test_provider_combo_has_empty_first_entry(
        self, qapp, project_with_three_leverantorer
    ) -> None:
        """First item in provider combo is empty string with None userData."""
        editor = SourceEditor(
            project_data=project_with_three_leverantorer,
        )
        combo = editor._ui.provider_combo

        assert combo.itemText(0) == ""
        assert combo.itemData(0) is None


class TestKalltypComboUpdates:
    """Tests for Requirement 12.2 and 12.3: Källtyp combo updates on provider change."""

    def test_kalltyp_combo_updates_when_provider_changes(
        self, qapp, project_with_two_leverantorer
    ) -> None:
        """Selecting a Leverantör populates Källtyp combo with its types."""
        editor = SourceEditor(
            project_data=project_with_two_leverantorer,
        )
        kalltyp_combo = editor._ui.kalltyp_combo
        provider_combo = editor._ui.provider_combo

        # Select Leverantör A (index 1)
        provider_combo.setCurrentIndex(1)

        # Källtyp combo: empty + 2 types for lev-a
        assert kalltyp_combo.count() == 3
        assert kalltyp_combo.itemText(1) == "Typ A1"
        assert kalltyp_combo.itemText(2) == "Typ A2"

        # Now select Leverantör B (index 2)
        provider_combo.setCurrentIndex(2)

        # Källtyp combo: empty + 1 type for lev-b
        assert kalltyp_combo.count() == 2
        assert kalltyp_combo.itemText(1) == "Typ B1"

    def test_kalltyp_combo_resets_when_provider_changes(
        self, qapp, project_with_two_leverantorer
    ) -> None:
        """Changing provider resets Källtyp combo to index 0 (empty)."""
        editor = SourceEditor(
            project_data=project_with_two_leverantorer,
        )
        kalltyp_combo = editor._ui.kalltyp_combo
        provider_combo = editor._ui.provider_combo

        # Select Leverantör A and pick a Källtyp
        provider_combo.setCurrentIndex(1)
        kalltyp_combo.setCurrentIndex(1)  # Select "Typ A1"
        assert kalltyp_combo.currentIndex() == 1

        # Change to Leverantör B
        provider_combo.setCurrentIndex(2)

        # Källtyp should be reset to index 0
        assert kalltyp_combo.currentIndex() == 0


class TestSaveStoresCorrectIds:
    """Tests for Requirement 12.4: Save stores correct leverantor_id and kalltyp_id."""

    def test_save_stores_correct_leverantor_and_kalltyp_ids(
        self, qapp, project_with_two_leverantorer
    ) -> None:
        """Saving after selecting provider and källtyp stores correct IDs."""
        editor = SourceEditor(
            project_data=project_with_two_leverantorer,
        )

        # Select Leverantör A (index 1, id="lev-a")
        editor._ui.provider_combo.setCurrentIndex(1)

        # Select Typ A2 (index 2, id="kt-a2")
        editor._ui.kalltyp_combo.setCurrentIndex(2)

        # Fill required fields
        editor._ui.title_input.setText("Test Source Title")

        # Trigger save
        editor._on_save()

        saved = editor.saved_source
        assert saved is not None
        assert saved.leverantor_id == "lev-a"
        assert saved.kalltyp_id == "kt-a2"


class TestLoadPreselectsCorrectItems:
    """Tests for Requirement 12.5: Load pre-selects correct items."""

    def test_load_preselects_correct_items(
        self, qapp, project_with_two_leverantorer
    ) -> None:
        """Opening editor with existing source pre-selects provider and källtyp."""
        project = project_with_two_leverantorer

        # Create a source that references lev-b and kt-b1
        source = Source(
            id="src-1",
            provider="Leverantör B",
            source_type="church_book",
            title="Existing Source",
            leverantor_id="lev-b",
            kalltyp_id="kt-b1",
        )
        project.sources.append(source)

        editor = SourceEditor(
            project_data=project,
            source=source,
        )

        provider_combo = editor._ui.provider_combo
        kalltyp_combo = editor._ui.kalltyp_combo

        # Provider should be pre-selected to "Leverantör B" (index 2)
        assert provider_combo.currentData() == "lev-b"
        assert provider_combo.currentText() == "Leverantör B"

        # Källtyp should be pre-selected to "Typ B1"
        assert kalltyp_combo.currentData() == "kt-b1"
        assert kalltyp_combo.currentText() == "Typ B1"
