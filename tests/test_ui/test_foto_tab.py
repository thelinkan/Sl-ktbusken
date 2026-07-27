"""Unit tests for FotoTab widget.

Verifies that:
- The photo table displays photos with Foto_Typ and Title columns.
- Photos are ordered alphabetically by title.
- The empty state message is shown when no photos are linked.
- The table is shown when photos exist.
- The refresh() method reloads the photo list.
- Button layout order and enable/disable states (Requirements 2.1, 2.2, 2.3, 2.4).
- Inline editing sections are removed (Requirements 11.1, 11.2, 11.3, 11.4, 11.5).
- Double-click opens EditPhotoDialog (Requirement 11.5).

Covers Requirements 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.5, 3.7, 11.1, 11.2, 11.3, 11.4, 11.5.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
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
def project_data_empty() -> ProjectData:
    """Return project data with no media items."""
    return ProjectData()


@pytest.fixture()
def project_data_with_photos(person: Person) -> ProjectData:
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
        MediaItem(
            id="m3",
            type="photo",
            file="photo3.jpg",
            title="[Familjefoto] Familjen Svensson",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="p1")
            ],
        ),
        # Not linked to person p1
        MediaItem(
            id="m4",
            type="photo",
            file="photo4.jpg",
            title="[Porträtt] Annan person",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="p2")
            ],
        ),
        # Not a photo type
        MediaItem(
            id="m5",
            type="document",
            file="doc.pdf",
            title="Dokument",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="p1")
            ],
        ),
    ]
    pd = ProjectData()
    pd.media = media
    return pd


@pytest.fixture()
def foto_mapp(tmp_path: Path) -> Path:
    """Return a temporary foto_mapp directory."""
    return tmp_path / "media" / "photos"


class TestEmptyState:
    """Tests for empty state display."""

    def test_empty_label_shown_when_no_photos(
        self, qapp, person: Person, project_data_empty: ProjectData, foto_mapp: Path
    ):
        """Empty state message is visible when no photos are linked."""
        service = PhotoService(project_data_empty, foto_mapp)
        tab = FotoTab(project_data_empty, person, service)

        # The stacked layout should show the empty label
        assert tab._stack_layout.currentWidget() == tab._empty_label

    def test_empty_label_text_content(
        self, qapp, person: Person, project_data_empty: ProjectData, foto_mapp: Path
    ):
        """Empty state message contains appropriate text."""
        service = PhotoService(project_data_empty, foto_mapp)
        tab = FotoTab(project_data_empty, person, service)

        text = tab._empty_label.text()
        assert "Inga foton" in text

    def test_table_row_count_zero_when_empty(
        self, qapp, person: Person, project_data_empty: ProjectData, foto_mapp: Path
    ):
        """Table has zero rows when no photos exist."""
        service = PhotoService(project_data_empty, foto_mapp)
        tab = FotoTab(project_data_empty, person, service)

        assert tab._table.rowCount() == 0


class TestPhotoDisplay:
    """Tests for photo list display."""

    def test_table_shown_when_photos_exist(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """Table widget is visible when photos are linked."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        assert tab._stack_layout.currentWidget() == tab._table

    def test_correct_row_count(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """Table has correct number of rows matching linked photos."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # Only 3 photos are linked to person p1 and are of type "photo"
        assert tab._table.rowCount() == 3

    def test_photos_ordered_alphabetically(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """Photos are displayed in alphabetical order by title."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # Alphabetical by full title:
        # "[Familjefoto] Familjen Svensson" < "[Gruppfoto] Alla syskon" < "[Porträtt] Barnfoto"
        titles = [
            tab._table.item(row, 1).text()
            for row in range(tab._table.rowCount())
        ]
        assert titles == ["Familjen Svensson", "Alla syskon", "Barnfoto"]

    def test_foto_typ_displayed_separately(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """Foto_Typ is displayed in column 0 without brackets."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        typs = [
            tab._table.item(row, 0).text()
            for row in range(tab._table.rowCount())
        ]
        assert "Familjefoto" in typs
        assert "Gruppfoto" in typs
        assert "Porträtt" in typs

    def test_title_displayed_without_prefix(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """Title is displayed without the [Foto_Typ] bracket prefix."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        for row in range(tab._table.rowCount()):
            title = tab._table.item(row, 1).text()
            assert not title.startswith("[")

    def test_media_id_stored_in_user_role(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """Media item ID is stored in UserRole data on the first column."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        ids = [
            tab._table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(tab._table.rowCount())
        ]
        # All linked photo IDs should be present
        assert set(ids) == {"m1", "m2", "m3"}


class TestRefresh:
    """Tests for the refresh() method."""

    def test_refresh_updates_table(
        self, qapp, person: Person, project_data_empty: ProjectData, foto_mapp: Path
    ):
        """Calling refresh() after adding photos updates the table."""
        service = PhotoService(project_data_empty, foto_mapp)
        tab = FotoTab(project_data_empty, person, service)

        # Initially empty
        assert tab._table.rowCount() == 0
        assert tab._stack_layout.currentWidget() == tab._empty_label

        # Add a photo to the project data
        project_data_empty.media.append(
            MediaItem(
                id="m10",
                type="photo",
                file="new_photo.jpg",
                title="[Övrigt foto] Nytt foto",
                linked_entities=[
                    LinkedEntity(entity_type="person", entity_id="p1")
                ],
            )
        )

        tab.refresh()

        assert tab._table.rowCount() == 1
        assert tab._stack_layout.currentWidget() == tab._table
        assert tab._table.item(0, 0).text() == "Övrigt foto"
        assert tab._table.item(0, 1).text() == "Nytt foto"


class TestButtonLayout:
    """Tests for button layout order (Requirement 2.1)."""

    def test_buttons_in_correct_order(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """Buttons are arranged: 'Lägg till foto', 'Redigera foto', 'Ta bort foto'."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # The buttons should be in the expected order
        assert tab._add_button.text() == "Lägg till foto"
        assert tab._edit_button.text() == "Redigera foto"
        assert tab._delete_button.text() == "Ta bort foto"

    def test_button_visual_order_left_to_right(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """Buttons are positioned left to right in the correct order."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)
        tab.show()
        tab.resize(600, 400)

        # Force geometry calculation
        QApplication.processEvents()

        # Verify left-to-right ordering via x-position
        add_x = tab._add_button.geometry().x()
        edit_x = tab._edit_button.geometry().x()
        delete_x = tab._delete_button.geometry().x()

        assert add_x < edit_x < delete_x


class TestButtonInitialState:
    """Tests for button initial state (Requirements 2.2, 2.3)."""

    def test_add_button_enabled_initially(
        self, qapp, person: Person, project_data_empty: ProjectData, foto_mapp: Path
    ):
        """'Lägg till foto' is always enabled, even with no photos."""
        service = PhotoService(project_data_empty, foto_mapp)
        tab = FotoTab(project_data_empty, person, service)

        assert tab._add_button.isEnabled() is True

    def test_edit_button_disabled_initially(
        self, qapp, person: Person, project_data_empty: ProjectData, foto_mapp: Path
    ):
        """'Redigera foto' is disabled when no photo is selected."""
        service = PhotoService(project_data_empty, foto_mapp)
        tab = FotoTab(project_data_empty, person, service)

        assert tab._edit_button.isEnabled() is False

    def test_delete_button_disabled_initially(
        self, qapp, person: Person, project_data_empty: ProjectData, foto_mapp: Path
    ):
        """'Ta bort foto' is disabled when no photo is selected."""
        service = PhotoService(project_data_empty, foto_mapp)
        tab = FotoTab(project_data_empty, person, service)

        assert tab._delete_button.isEnabled() is False

    def test_add_button_enabled_with_photos(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """'Lägg till foto' stays enabled when photos exist but none selected."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        assert tab._add_button.isEnabled() is True

    def test_edit_button_disabled_with_photos_no_selection(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """'Redigera foto' is disabled even when photos exist but none selected."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        assert tab._edit_button.isEnabled() is False


class TestButtonStateWithSelection:
    """Tests for button state when a photo is selected (Requirement 2.4)."""

    def test_edit_button_enabled_on_selection(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """'Redigera foto' becomes enabled when a photo is selected."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # Select the first row
        tab._table.selectRow(0)

        assert tab._edit_button.isEnabled() is True

    def test_delete_button_enabled_on_selection(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """'Ta bort foto' becomes enabled when a photo is selected."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # Select the first row
        tab._table.selectRow(0)

        assert tab._delete_button.isEnabled() is True

    def test_add_button_still_enabled_on_selection(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """'Lägg till foto' stays enabled when a photo is selected."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        tab._table.selectRow(0)

        assert tab._add_button.isEnabled() is True


class TestButtonStateOnDeselection:
    """Tests for button state when selection is cleared (Requirement 2.3)."""

    def test_edit_button_disabled_on_deselection(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """'Redigera foto' becomes disabled when selection is cleared."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # Select then deselect
        tab._table.selectRow(0)
        assert tab._edit_button.isEnabled() is True

        tab._table.clearSelection()

        assert tab._edit_button.isEnabled() is False

    def test_delete_button_disabled_on_deselection(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """'Ta bort foto' becomes disabled when selection is cleared."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # Select then deselect
        tab._table.selectRow(0)
        assert tab._delete_button.isEnabled() is True

        tab._table.clearSelection()

        assert tab._delete_button.isEnabled() is False


class TestNoInlineEditingSections:
    """Tests that inline editing sections are removed (Requirements 11.1, 11.2, 11.3)."""

    def test_no_edit_group_attribute(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """FotoTab does not have _edit_group attribute (inline edit section removed)."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        assert not hasattr(tab, "_edit_group")

    def test_no_person_list_group_attribute(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """FotoTab does not have _person_list_group attribute (person list section removed)."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        assert not hasattr(tab, "_person_list_group")

    def test_no_spara_andringar_button(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """No 'Spara ändringar' button exists in FotoTab."""
        from PySide6.QtWidgets import QPushButton

        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # Search all QPushButton children for the old inline save button
        buttons = tab.findChildren(QPushButton)
        button_texts = [btn.text() for btn in buttons]

        assert "Spara ändringar" not in button_texts

    def test_no_spara_personlista_button(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """No 'Spara personlista' button exists in FotoTab."""
        from PySide6.QtWidgets import QPushButton

        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # Search all QPushButton children for the old person list save button
        buttons = tab.findChildren(QPushButton)
        button_texts = [btn.text() for btn in buttons]

        assert "Spara personlista" not in button_texts

    def test_selection_does_not_show_inline_editing(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path
    ):
        """Selecting a photo does not create any inline editing sections (Req 11.4)."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # Select a photo
        tab._table.selectRow(0)

        # Verify no inline editing attributes appeared
        assert not hasattr(tab, "_edit_group")
        assert not hasattr(tab, "_person_list_group")


class TestDoubleClickOpensDialog:
    """Tests that double-click opens EditPhotoDialog (Requirement 11.5)."""

    def test_double_click_calls_handler(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Double-clicking a row triggers _on_double_click_photo."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        called_with = {}

        def mock_on_double_click(row: int, column: int) -> None:
            called_with["row"] = row
            called_with["column"] = column

        monkeypatch.setattr(tab, "_on_double_click_photo", mock_on_double_click)

        # Emit the signal directly to simulate a double-click
        tab._table.cellDoubleClicked.emit(0, 0)

        assert called_with == {"row": 0, "column": 0}

    def test_double_click_opens_edit_photo_dialog(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Double-clicking a photo row opens EditPhotoDialog."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        dialog_opened = {"called": False, "media_item": None}

        # Mock _on_edit_photo to track if it's called
        def mock_on_edit_photo() -> None:
            dialog_opened["called"] = True
            dialog_opened["media_item"] = tab._selected_media_item

        monkeypatch.setattr(tab, "_on_edit_photo", mock_on_edit_photo)

        # Call the double-click handler directly with row 0
        tab._on_double_click_photo(0, 0)

        assert dialog_opened["called"] is True
        assert dialog_opened["media_item"] is not None

    def test_double_click_sets_selected_media_item(
        self, qapp, person: Person, project_data_with_photos: ProjectData, foto_mapp: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Double-clicking sets _selected_media_item before opening dialog."""
        service = PhotoService(project_data_with_photos, foto_mapp)
        tab = FotoTab(project_data_with_photos, person, service)

        # Mock _on_edit_photo to prevent actual dialog
        monkeypatch.setattr(tab, "_on_edit_photo", lambda: None)

        # Initially no selection
        assert tab._selected_media_item is None

        # Double-click first row
        tab._on_double_click_photo(0, 0)

        # After double-click, a media item should be selected
        assert tab._selected_media_item is not None
        assert tab._selected_media_item.type == "photo"
