"""Unit tests for FotoTab widget.

Verifies that:
- The photo table displays photos with Foto_Typ and Title columns.
- Photos are ordered alphabetically by title.
- The empty state message is shown when no photos are linked.
- The table is shown when photos exist.
- The refresh() method reloads the photo list.

Covers Requirements 3.1, 3.2, 3.5, 3.7.
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
