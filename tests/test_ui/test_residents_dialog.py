"""Unit tests for the ResidentsDialog.

Tests the place/year query UI, results display, role grouping, and place chain
column as defined by Requirements 8.1, 8.5, 8.6, 8.10.
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.model.person import Person, Name
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.ui.dialogs.residents_dialog import ResidentsDialog


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def empty_project() -> ProjectData:
    """An empty project."""
    return ProjectData(project=ProjectMetadata(title="Test"))


@pytest.fixture()
def project_with_residents() -> ProjectData:
    """A project with places, persons and residence facts for query testing."""
    places = [
        Place(id="farm_a", type="farm", name="Gården A"),
        Place(id="farm_b", type="farm", name="Gården B", parent_place_id="farm_a"),
    ]
    persons = [
        Person(
            id="p1",
            sex="M",
            names=[Name(type="birth", given="Anders", surname="Andersson")],
        ),
        Person(
            id="p2",
            sex="F",
            names=[Name(type="birth", given="Brita", surname="Eriksdotter")],
        ),
        Person(
            id="p3",
            sex="M",
            names=[Name(type="birth", given="Carl", surname="Carlsson")],
        ),
    ]
    residences = [
        ResidenceFact(
            id="res_1",
            person_id="p1",
            place_id="farm_a",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1850", latest="1850"),
            role_in_household="husbonde",
        ),
        ResidenceFact(
            id="res_2",
            person_id="p2",
            place_id="farm_a",
            start=Endpoint(earliest="1842", latest="1842"),
            end=Endpoint(earliest="1848", latest="1848"),
            role_in_household="piga",
        ),
        ResidenceFact(
            id="res_3",
            person_id="p3",
            place_id="farm_b",
            start=Endpoint(earliest="1838", latest="1838"),
            end=Endpoint(earliest="1855", latest="1855"),
            role_in_household="",
        ),
    ]
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        places=places,
        persons=persons,
        residences=residences,
    )


class TestDialogInstantiation:
    """Tests for dialog creation and basic structure."""

    def test_can_instantiate_empty(self, qapp, empty_project):
        """Dialog instantiates with an empty project."""
        dialog = ResidentsDialog(parent=None, project_data=empty_project)
        assert dialog is not None
        assert dialog.windowTitle() == "Boende på plats"

    def test_has_place_combo(self, qapp, empty_project):
        """Dialog has a place combo box."""
        dialog = ResidentsDialog(parent=None, project_data=empty_project)
        assert dialog.place_combo is not None

    def test_has_year_spin(self, qapp, empty_project):
        """Dialog has a year spin box with correct range."""
        dialog = ResidentsDialog(parent=None, project_data=empty_project)
        assert dialog.year_spin.minimum() == 1000
        assert dialog.year_spin.maximum() == 2999

    def test_has_search_button(self, qapp, empty_project):
        """Dialog has a search button."""
        dialog = ResidentsDialog(parent=None, project_data=empty_project)
        assert dialog.search_button.text() == "Sök"

    def test_has_group_button(self, qapp, empty_project):
        """Dialog has a checkable group-by-role button."""
        dialog = ResidentsDialog(parent=None, project_data=empty_project)
        assert dialog.group_button.isCheckable()

    def test_has_results_table(self, qapp, empty_project):
        """Dialog has a results table with 5 columns."""
        dialog = ResidentsDialog(parent=None, project_data=empty_project)
        table = dialog.results_table
        assert table.columnCount() == 5

    def test_table_headers(self, qapp, empty_project):
        """Table has the correct Swedish column headers."""
        dialog = ResidentsDialog(parent=None, project_data=empty_project)
        table = dialog.results_table
        headers = [
            table.horizontalHeaderItem(i).text()
            for i in range(table.columnCount())
        ]
        assert headers == ["Person", "Platskedja", "Period", "Säkerhet", "Roll"]


class TestPlaceCombo:
    """Tests for the place combo box population."""

    def test_place_combo_shows_all_places(self, qapp, project_with_residents):
        """Place combo is populated with all project places."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        # First item is the "(välj plats)" placeholder
        combo = dialog.place_combo
        assert combo.count() == 3  # placeholder + 2 places

    def test_place_combo_placeholder(self, qapp, project_with_residents):
        """First item in place combo is the placeholder."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        assert dialog.place_combo.itemText(0) == "(välj plats)"
        assert dialog.place_combo.itemData(0) == ""

    def test_place_combo_stores_place_id(self, qapp, project_with_residents):
        """Each place item stores the place id as user data."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        combo = dialog.place_combo
        place_ids = [combo.itemData(i) for i in range(1, combo.count())]
        assert "farm_a" in place_ids
        assert "farm_b" in place_ids


class TestSearch:
    """Tests for the search functionality."""

    def test_search_no_place_selected(self, qapp, project_with_residents):
        """Searching without a place shows a prompt message."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        dialog.place_combo.setCurrentIndex(0)  # placeholder
        dialog.search_button.click()
        assert "Välj en plats" in dialog.summary_label.text()
        assert dialog.results_table.rowCount() == 0

    def test_search_returns_matching_entries(self, qapp, project_with_residents):
        """Searching a place/year returns the correct number of entries."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        # Select "Gården A"
        combo = dialog.place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "farm_a":
                combo.setCurrentIndex(i)
                break
        dialog.year_spin.setValue(1845)
        dialog.search_button.click()

        # Should find: res_1 (p1 at farm_a), res_2 (p2 at farm_a), res_3 (p3 at farm_b descendant)
        assert dialog.results_table.rowCount() == 3

    def test_search_shows_summary(self, qapp, project_with_residents):
        """Search displays a summary with the count."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        combo = dialog.place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "farm_a":
                combo.setCurrentIndex(i)
                break
        dialog.year_spin.setValue(1845)
        dialog.search_button.click()
        assert "3 boende" in dialog.summary_label.text()

    def test_search_shows_person_name(self, qapp, project_with_residents):
        """Results display person names."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        combo = dialog.place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "farm_a":
                combo.setCurrentIndex(i)
                break
        dialog.year_spin.setValue(1845)
        dialog.search_button.click()

        table = dialog.results_table
        person_names = [
            table.item(row, 0).text() for row in range(table.rowCount())
        ]
        assert "Anders Andersson" in person_names
        assert "Brita Eriksdotter" in person_names

    def test_search_shows_label(self, qapp, project_with_residents):
        """Results display the correct certainty label."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        combo = dialog.place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "farm_a":
                combo.setCurrentIndex(i)
                break
        dialog.year_spin.setValue(1845)
        dialog.search_button.click()

        table = dialog.results_table
        labels = [
            table.item(row, 3).text() for row in range(table.rowCount())
        ]
        assert all("säker" in lbl for lbl in labels)

    def test_search_shows_role(self, qapp, project_with_residents):
        """Results display the role_in_household."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        combo = dialog.place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "farm_a":
                combo.setCurrentIndex(i)
                break
        dialog.year_spin.setValue(1845)
        dialog.search_button.click()

        table = dialog.results_table
        roles = [
            table.item(row, 4).text() for row in range(table.rowCount())
        ]
        assert "husbonde" in roles
        assert "piga" in roles


class TestPlaceChain:
    """Tests for the place chain column (Requirement 8.6)."""

    def test_descendant_place_shows_chain(self, qapp, project_with_residents):
        """A resident at a descendant place shows the place chain."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        combo = dialog.place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "farm_a":
                combo.setCurrentIndex(i)
                break
        dialog.year_spin.setValue(1845)
        dialog.search_button.click()

        table = dialog.results_table
        # Find Carl who is at farm_b (child of farm_a)
        for row in range(table.rowCount()):
            if table.item(row, 0).text() == "Carl Carlsson":
                chain_text = table.item(row, 1).text()
                # Should contain both Gården A and Gården B in the chain
                assert "Gården A" in chain_text
                assert "Gården B" in chain_text
                break
        else:
            pytest.fail("Carl Carlsson not found in results")


class TestRoleGrouping:
    """Tests for the role grouping view (Requirement 8.10)."""

    def test_group_toggle_changes_display(self, qapp, project_with_residents):
        """Toggling grouping changes the table display."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        combo = dialog.place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "farm_a":
                combo.setCurrentIndex(i)
                break
        dialog.year_spin.setValue(1845)
        dialog.search_button.click()

        flat_rows = dialog.results_table.rowCount()

        # Toggle grouping on
        dialog.group_button.setChecked(True)

        # Grouped view has more rows (group headers + entries)
        grouped_rows = dialog.results_table.rowCount()
        assert grouped_rows > flat_rows

    def test_grouped_view_has_role_headers(self, qapp, project_with_residents):
        """Grouped view contains bold group header rows."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        combo = dialog.place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "farm_a":
                combo.setCurrentIndex(i)
                break
        dialog.year_spin.setValue(1845)
        dialog.search_button.click()
        dialog.group_button.setChecked(True)

        table = dialog.results_table
        header_texts = []
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.font().bold():
                header_texts.append(item.text())

        # Should have headers for "husbonde", "piga", and "Roll saknas"
        assert "husbonde" in header_texts
        assert "piga" in header_texts
        assert "Roll saknas" in header_texts

    def test_ungroup_restores_flat_view(self, qapp, project_with_residents):
        """Untoggling grouping restores the flat view."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        combo = dialog.place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "farm_a":
                combo.setCurrentIndex(i)
                break
        dialog.year_spin.setValue(1845)
        dialog.search_button.click()
        flat_rows = dialog.results_table.rowCount()

        dialog.group_button.setChecked(True)
        dialog.group_button.setChecked(False)

        assert dialog.results_table.rowCount() == flat_rows

    def test_empty_role_group_labelled_roll_saknas(self, qapp, project_with_residents):
        """Entries with empty role are grouped under 'Roll saknas'."""
        dialog = ResidentsDialog(parent=None, project_data=project_with_residents)
        combo = dialog.place_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "farm_a":
                combo.setCurrentIndex(i)
                break
        dialog.year_spin.setValue(1845)
        dialog.search_button.click()
        dialog.group_button.setChecked(True)

        table = dialog.results_table
        # Find the "Roll saknas" header and verify Carl is under it
        found_header = False
        carl_under_header = False
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.font().bold() and item.text() == "Roll saknas":
                found_header = True
                continue
            if found_header and item and not item.font().bold():
                if "Carl" in item.text():
                    carl_under_header = True
                    break
                # If we hit another header, we've passed the group
                if item.font().bold():
                    break

        assert found_header
        assert carl_under_header
