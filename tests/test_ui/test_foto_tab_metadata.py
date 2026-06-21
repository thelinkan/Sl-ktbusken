"""Unit tests for FotoTab photo metadata editing (task 8.3).

Verifies:
- Editing panel visibility on photo selection/deselection
- Title and Foto_Typ fields populated from selected photo
- Title validation (1–200 chars) before save
- Status bar messages for validation errors
- MediaItem title updated with [Foto_Typ] title format on save

Covers Requirements 9.1, 9.2, 9.3, 9.7, 9.8.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import QApplication

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.photo_service import PhotoService
from slaktbusken.ui.widgets.foto_tab import FotoTab


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def person() -> Person:
    """Return a test person."""
    return Person(
        id="p1",
        sex="male",
        names=[Name(type="birth", given="Erik", surname="Svensson")],
    )


@pytest.fixture()
def project_data(person: Person) -> ProjectData:
    """Return project data with photos linked to the test person."""
    media = [
        MediaItem(
            id="m1",
            type="photo",
            file="photo1.jpg",
            title="[Porträtt] Barnfoto",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="p1")
            ],
        ),
        MediaItem(
            id="m2",
            type="photo",
            file="photo2.jpg",
            title="[Gruppfoto] Alla syskon",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="p1")
            ],
        ),
    ]
    pd = ProjectData()
    pd.media = media
    pd.persons = [person]
    return pd


@pytest.fixture()
def foto_mapp(tmp_path: Path) -> Path:
    """Return a temporary foto_mapp directory."""
    return tmp_path / "media" / "photos"


@pytest.fixture()
def tab(qapp, project_data, person, foto_mapp) -> FotoTab:
    """Return a FotoTab with photos loaded."""
    service = PhotoService(project_data, foto_mapp)
    return FotoTab(project_data, person, service)


def _select_row(tab: FotoTab, row: int) -> None:
    """Programmatically select a row in the photo table."""
    tab._table.selectRow(row)


class TestEditPanelVisibility:
    """Tests for edit panel show/hide on selection."""

    def test_edit_panel_hidden_initially(self, tab: FotoTab):
        """Edit panel is hidden when no photo is selected."""
        assert tab._edit_group.isHidden() is True

    def test_edit_panel_shown_on_selection(self, tab: FotoTab):
        """Edit panel becomes visible when a photo is selected."""
        _select_row(tab, 0)
        assert tab._edit_group.isHidden() is False

    def test_edit_panel_hidden_on_deselection(self, tab: FotoTab):
        """Edit panel hides when selection is cleared."""
        _select_row(tab, 0)
        assert tab._edit_group.isHidden() is False

        tab._table.clearSelection()
        assert tab._edit_group.isHidden() is True


class TestFieldPopulation:
    """Tests for editing fields being populated from selected photo."""

    def test_title_populated_from_selected_photo(self, tab: FotoTab):
        """Title field is populated with the title portion (without prefix)."""
        # Photos sorted alphabetically:
        # Row 0: "[Gruppfoto] Alla syskon" -> title = "Alla syskon"
        # Row 1: "[Porträtt] Barnfoto" -> title = "Barnfoto"
        _select_row(tab, 0)
        assert tab._edit_title_input.text() == "Alla syskon"

    def test_foto_typ_populated_from_selected_photo(self, tab: FotoTab):
        """Foto_Typ dropdown is set to the current type of the selected photo."""
        # Row 0: "[Gruppfoto] Alla syskon"
        _select_row(tab, 0)
        assert tab._edit_typ_combo.currentText() == "Gruppfoto"

    def test_fields_update_on_different_selection(self, tab: FotoTab):
        """Fields update when a different photo is selected."""
        _select_row(tab, 0)
        assert tab._edit_title_input.text() == "Alla syskon"

        _select_row(tab, 1)
        assert tab._edit_title_input.text() == "Barnfoto"
        assert tab._edit_typ_combo.currentText() == "Porträtt"


class TestTitleValidation:
    """Tests for title validation on save."""

    def test_empty_title_shows_error(self, tab: FotoTab):
        """Empty title shows validation error and does not save."""
        _select_row(tab, 0)
        tab._edit_title_input.setText("")
        tab._on_save_metadata()

        assert tab._status_label.text() == "Titel måste vara 1–200 tecken."

    def test_whitespace_only_title_shows_error(self, tab: FotoTab):
        """Title with only whitespace shows validation error."""
        _select_row(tab, 0)
        tab._edit_title_input.setText("   ")
        tab._on_save_metadata()

        assert tab._status_label.text() == "Titel måste vara 1–200 tecken."

    def test_title_exceeding_200_chars_shows_error(self, tab: FotoTab):
        """Title longer than 200 characters shows validation error."""
        _select_row(tab, 0)
        # Temporarily remove max length constraint to simulate programmatic input
        tab._edit_title_input.setMaxLength(300)
        tab._edit_title_input.setText("A" * 201)
        tab._on_save_metadata()

        assert tab._status_label.text() == "Titel måste vara 1–200 tecken."
        # Restore max length
        tab._edit_title_input.setMaxLength(200)

    def test_valid_title_clears_error(self, tab: FotoTab):
        """Valid title clears any previous error message."""
        _select_row(tab, 0)
        # First trigger an error
        tab._edit_title_input.setText("")
        tab._on_save_metadata()
        assert tab._status_label.text() != ""

        # Now save with a valid title
        tab._edit_title_input.setText("Nytt namn")
        tab._on_save_metadata()
        assert tab._status_label.text() == ""


class TestSaveMetadata:
    """Tests for saving metadata changes."""

    def test_save_updates_media_item_title(
        self, tab: FotoTab, project_data: ProjectData
    ):
        """Save updates the MediaItem title with [Foto_Typ] title format."""
        _select_row(tab, 0)
        # Row 0 is "[Gruppfoto] Alla syskon" (media_id = m2 based on sort)
        tab._edit_title_input.setText("Ny titel")
        tab._edit_typ_combo.setCurrentText("Gruppfoto")
        tab._on_save_metadata()

        # Find the media item that was edited
        media = next(m for m in project_data.media if m.id == "m2")
        assert media.title == "[Gruppfoto] Ny titel"

    def test_save_changes_foto_typ(
        self, tab: FotoTab, project_data: ProjectData
    ):
        """Save with a different Foto_Typ updates the prefix."""
        _select_row(tab, 0)
        tab._edit_title_input.setText("Alla syskon")
        tab._edit_typ_combo.setCurrentText("Familjefoto")
        tab._on_save_metadata()

        media = next(m for m in project_data.media if m.id == "m2")
        assert media.title == "[Familjefoto] Alla syskon"

    def test_save_with_boundary_title_1_char(
        self, tab: FotoTab, project_data: ProjectData
    ):
        """Save succeeds with a 1-character title (minimum valid)."""
        _select_row(tab, 0)
        tab._edit_title_input.setText("X")
        tab._on_save_metadata()

        media = next(m for m in project_data.media if m.id == "m2")
        assert media.title == "[Gruppfoto] X"

    def test_save_with_boundary_title_200_chars(
        self, tab: FotoTab, project_data: ProjectData
    ):
        """Save succeeds with a 200-character title (maximum valid)."""
        _select_row(tab, 0)
        long_title = "A" * 200
        tab._edit_title_input.setText(long_title)
        tab._on_save_metadata()

        media = next(m for m in project_data.media if m.id == "m2")
        assert media.title == f"[Gruppfoto] {long_title}"

    def test_save_refreshes_table(self, tab: FotoTab):
        """After save, the table is refreshed with updated data."""
        _select_row(tab, 0)
        tab._edit_title_input.setText("Uppdaterad titel")
        tab._on_save_metadata()

        # Check the table reflects the change
        titles = [
            tab._table.item(row, 1).text()
            for row in range(tab._table.rowCount())
        ]
        assert "Uppdaterad titel" in titles

    def test_save_does_not_modify_unselected_items(
        self, tab: FotoTab, project_data: ProjectData
    ):
        """Save only modifies the selected media item, not others."""
        _select_row(tab, 1)  # Row 1: "[Porträtt] Barnfoto" -> media m1
        tab._edit_title_input.setText("Nytt barnfoto")
        tab._on_save_metadata()

        # m2 should be unchanged
        media_m2 = next(m for m in project_data.media if m.id == "m2")
        assert media_m2.title == "[Gruppfoto] Alla syskon"

        # m1 should be updated
        media_m1 = next(m for m in project_data.media if m.id == "m1")
        assert media_m1.title == "[Porträtt] Nytt barnfoto"


class TestStatusMessages:
    """Tests for status bar message display."""

    def test_status_cleared_on_selection_change(self, tab: FotoTab):
        """Status message is cleared when selection changes."""
        _select_row(tab, 0)
        tab._edit_title_input.setText("")
        tab._on_save_metadata()
        assert tab._status_label.text() != ""

        # Changing selection should clear status
        _select_row(tab, 1)
        assert tab._status_label.text() == ""

    def test_status_label_has_red_style(self, tab: FotoTab):
        """Status label has red color styling for error messages."""
        assert "red" in tab._status_label.styleSheet()
