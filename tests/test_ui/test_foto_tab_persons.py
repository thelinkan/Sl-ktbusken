"""Unit tests for person list management in FotoTab.

Verifies that:
- Person list section is hidden when no photo is selected.
- Person list section is shown when a photo is selected.
- Database-linked persons are displayed by name.
- Free-text persons are displayed as plain text.
- Adding a database person via dropdown updates mentioned_person_ids.
- Adding a free-text person updates mentioned_names.
- Duplicate detection prevents adding the same person twice.
- Removing a person updates the appropriate list.
- Save syncs Linked_Entity records via PhotoService.

Covers Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 9.4, 9.5, 9.6.
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
def persons() -> list[Person]:
    """Return test persons."""
    return [
        Person(
            id="p1",
            sex="male",
            names=[Name(type="birth", given="Erik", surname="Svensson")],
        ),
        Person(
            id="p2",
            sex="female",
            names=[Name(type="birth", given="Anna", surname="Karlsson")],
        ),
        Person(
            id="p3",
            sex="male",
            names=[Name(type="birth", given="Johan", surname="Andersson")],
        ),
    ]


@pytest.fixture()
def project_data(persons: list[Person]) -> ProjectData:
    """Return project data with persons and a photo linked to p1."""
    pd = ProjectData()
    pd.persons = persons
    pd.media = [
        MediaItem(
            id="m1",
            type="photo",
            file="photo1.jpg",
            title="[Porträtt] Barnfoto",
            linked_entities=[
                LinkedEntity(entity_type="person", entity_id="p1")
            ],
            mentioned_person_ids=["p2"],
            mentioned_names=["Okänd person"],
        ),
    ]
    return pd


@pytest.fixture()
def foto_mapp(tmp_path: Path) -> Path:
    """Return a temporary foto_mapp directory."""
    return tmp_path / "media" / "photos"


@pytest.fixture()
def tab(
    qapp, project_data: ProjectData, persons: list[Person], foto_mapp: Path
) -> FotoTab:
    """Create a FotoTab for person p1."""
    service = PhotoService(project_data, foto_mapp)
    return FotoTab(project_data, persons[0], service)


class TestPersonListVisibility:
    """Tests for person list section visibility."""

    def test_person_list_hidden_initially(self, tab: FotoTab):
        """Person list group is hidden when no photo is selected."""
        # Use isVisibleTo(parent) since the FotoTab itself is not shown
        assert not tab._person_list_group.isVisibleTo(tab)

    def test_person_list_shown_on_photo_selection(self, tab: FotoTab):
        """Person list group becomes visible when a photo is selected."""
        tab._table.selectRow(0)
        assert tab._person_list_group.isVisibleTo(tab)

    def test_person_list_hidden_on_deselection(self, tab: FotoTab):
        """Person list group is hidden when photo selection is cleared."""
        tab._table.selectRow(0)
        assert tab._person_list_group.isVisibleTo(tab)

        tab._table.clearSelection()
        assert not tab._person_list_group.isVisibleTo(tab)


class TestPersonListDisplay:
    """Tests for displaying persons in the selected photo."""

    def test_db_person_displayed_by_name(self, tab: FotoTab):
        """Database-linked persons display 'given surname' format."""
        tab._table.selectRow(0)

        # p2 is in mentioned_person_ids - should show "Anna Karlsson"
        list_widget = tab._person_list_widget._list_widget
        found = False
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if "Anna Karlsson" in item.text():
                found = True
                break
        assert found

    def test_free_text_person_displayed(self, tab: FotoTab):
        """Free-text persons are displayed as plain text."""
        tab._table.selectRow(0)

        list_widget = tab._person_list_widget._list_widget
        found = False
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.text() == "Okänd person":
                found = True
                break
        assert found

    def test_person_list_shows_correct_count(self, tab: FotoTab):
        """Person list shows all mentioned persons (db + free-text)."""
        tab._table.selectRow(0)

        list_widget = tab._person_list_widget._list_widget
        # 1 db person (p2) + 1 free-text
        assert list_widget.count() == 2


class TestAddPersons:
    """Tests for adding persons to the photo."""

    def test_add_db_person(self, tab: FotoTab):
        """Adding a database person updates mentioned_person_ids."""
        tab._table.selectRow(0)

        # Simulate selecting p3 (Johan Andersson) in the combo
        combo = tab._person_list_widget._person_combo
        # Find p3 in combo items
        for i in range(combo.count()):
            if combo.itemData(i) == "p3":
                combo.setCurrentIndex(i)
                break

        tab._person_list_widget._on_add_db_person()

        person_ids = tab._person_list_widget.get_person_ids()
        assert "p3" in person_ids

    def test_add_free_text_person(self, tab: FotoTab):
        """Adding a free-text person updates mentioned_names."""
        tab._table.selectRow(0)

        tab._person_list_widget._free_text_input.setText("Granne Sven")
        tab._person_list_widget._on_add_free_person()

        names = tab._person_list_widget.get_mentioned_names()
        assert "Granne Sven" in names

    def test_free_text_max_length_enforced(self, tab: FotoTab):
        """Free-text input has max length of 200 characters."""
        tab._table.selectRow(0)

        max_len = tab._person_list_widget._free_text_input.maxLength()
        assert max_len == 200


class TestDuplicateDetection:
    """Tests for duplicate person detection."""

    def test_duplicate_db_person_rejected(self, tab: FotoTab, qtbot):
        """Adding a person_id already in list shows duplicate message."""
        tab._table.selectRow(0)

        # p2 is already in mentioned_person_ids
        combo = tab._person_list_widget._person_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "p2":
                combo.setCurrentIndex(i)
                break

        # The add should show a message; person list should not grow
        initial_ids = tab._person_list_widget.get_person_ids()
        initial_count = len(initial_ids)

        # Use qtbot to handle the message box
        from unittest.mock import patch

        with patch(
            "slaktbusken.ui.widgets.person_list_widget.QMessageBox.information"
        ) as mock_msg:
            tab._person_list_widget._on_add_db_person()
            mock_msg.assert_called_once()

        assert len(tab._person_list_widget.get_person_ids()) == initial_count

    def test_duplicate_free_text_rejected(self, tab: FotoTab, qtbot):
        """Adding an identical free-text name shows duplicate message."""
        tab._table.selectRow(0)

        # "Okänd person" is already in mentioned_names
        tab._person_list_widget._free_text_input.setText("Okänd person")

        initial_names = tab._person_list_widget.get_mentioned_names()
        initial_count = len(initial_names)

        from unittest.mock import patch

        with patch(
            "slaktbusken.ui.widgets.person_list_widget.QMessageBox.information"
        ) as mock_msg:
            tab._person_list_widget._on_add_free_person()
            mock_msg.assert_called_once()

        assert len(tab._person_list_widget.get_mentioned_names()) == initial_count


class TestRemovePersons:
    """Tests for removing persons from the photo."""

    def test_remove_db_person(self, tab: FotoTab):
        """Removing a database person updates the list."""
        tab._table.selectRow(0)

        # Select the first item (db person p2)
        list_widget = tab._person_list_widget._list_widget
        list_widget.setCurrentRow(0)

        tab._person_list_widget._on_remove_person()

        person_ids = tab._person_list_widget.get_person_ids()
        assert "p2" not in person_ids

    def test_remove_free_text_person(self, tab: FotoTab):
        """Removing a free-text person updates the list."""
        tab._table.selectRow(0)

        # Select the free-text item (second in list)
        list_widget = tab._person_list_widget._list_widget
        list_widget.setCurrentRow(1)

        tab._person_list_widget._on_remove_person()

        names = tab._person_list_widget.get_mentioned_names()
        assert "Okänd person" not in names


class TestSavePersons:
    """Tests for saving person list to MediaItem."""

    def test_save_updates_media_item_person_ids(
        self, tab: FotoTab, project_data: ProjectData
    ):
        """Save updates mentioned_person_ids on the MediaItem."""
        tab._table.selectRow(0)

        # Add p3
        combo = tab._person_list_widget._person_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "p3":
                combo.setCurrentIndex(i)
                break
        tab._person_list_widget._on_add_db_person()

        # Save
        tab._on_save_persons()

        media_item = project_data.media[0]
        assert "p3" in media_item.mentioned_person_ids

    def test_save_updates_media_item_mentioned_names(
        self, tab: FotoTab, project_data: ProjectData
    ):
        """Save updates mentioned_names on the MediaItem."""
        tab._table.selectRow(0)

        tab._person_list_widget._free_text_input.setText("Ny person")
        tab._person_list_widget._on_add_free_person()

        tab._on_save_persons()

        media_item = project_data.media[0]
        assert "Ny person" in media_item.mentioned_names

    def test_save_syncs_linked_entities(
        self, tab: FotoTab, project_data: ProjectData
    ):
        """Save creates Linked_Entity records for mentioned_person_ids."""
        tab._table.selectRow(0)

        # Add p3 to person list
        combo = tab._person_list_widget._person_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "p3":
                combo.setCurrentIndex(i)
                break
        tab._person_list_widget._on_add_db_person()

        tab._on_save_persons()

        media_item = project_data.media[0]
        person_entity_ids = [
            le.entity_id
            for le in media_item.linked_entities
            if le.entity_type == "person"
        ]
        # sync_linked_entities manages all person-type entities based on mentioned_person_ids
        # mentioned_person_ids after add: ["p2", "p3"]
        assert "p2" in person_entity_ids
        assert "p3" in person_entity_ids

    def test_save_removes_stale_linked_entities(
        self, tab: FotoTab, project_data: ProjectData
    ):
        """Save removes Linked_Entity for removed persons."""
        tab._table.selectRow(0)

        # Remove p2 from person list
        list_widget = tab._person_list_widget._list_widget
        list_widget.setCurrentRow(0)  # p2 is first
        tab._person_list_widget._on_remove_person()

        tab._on_save_persons()

        media_item = project_data.media[0]
        person_entity_ids = [
            le.entity_id
            for le in media_item.linked_entities
            if le.entity_type == "person"
        ]
        assert "p2" not in person_entity_ids

    def test_save_button_disabled_initially(self, tab: FotoTab):
        """Save button is disabled when person list hasn't changed."""
        tab._table.selectRow(0)
        assert not tab._save_persons_btn.isEnabled()

    def test_save_button_enabled_after_change(self, tab: FotoTab):
        """Save button is enabled after a person is added or removed."""
        tab._table.selectRow(0)

        tab._person_list_widget._free_text_input.setText("Ny person")
        tab._person_list_widget._on_add_free_person()

        assert tab._save_persons_btn.isEnabled()

    def test_save_button_disabled_after_save(self, tab: FotoTab):
        """Save button is disabled again after saving."""
        tab._table.selectRow(0)

        tab._person_list_widget._free_text_input.setText("Ny person")
        tab._person_list_widget._on_add_free_person()
        tab._on_save_persons()

        assert not tab._save_persons_btn.isEnabled()
