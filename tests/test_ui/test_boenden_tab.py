"""Unit tests for the BoendenTab widget (task 17.12).

Verifies that:
- The Boenden tab appears in the PersonEditor tab widget
- The residence list shows the person's residence facts
- The empty state is displayed when no residences exist
- The create button emits the create_requested signal
- The residents dialog button emits the residents_dialog_requested signal
- The edit button is enabled only when a residence is selected
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.ui.editors.person_editor import PersonEditor
from slaktbusken.ui.widgets.boenden_tab import BoendenTab


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def person() -> Person:
    """A sample person."""
    return Person(
        id="p1",
        sex="M",
        names=[Name(type="birth", given="Anders", surname="Andersson")],
    )


@pytest.fixture()
def place() -> Place:
    """A sample place."""
    return Place(id="place1", name="Ekeby")


@pytest.fixture()
def project_no_residences(person: Person, place: Place) -> ProjectData:
    """Project with person but no residences."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[person],
        places=[place],
    )


@pytest.fixture()
def project_with_residences(person: Person, place: Place) -> ProjectData:
    """Project with person and two residence facts."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[person],
        places=[place],
        residences=[
            ResidenceFact(
                id="res1",
                person_id="p1",
                place_id="place1",
                start=Endpoint(latest="1840"),
                end=Endpoint(earliest="1850"),
                role_in_household="husbonde",
            ),
            ResidenceFact(
                id="res2",
                person_id="p1",
                place_id="place1",
                start=Endpoint(latest="1855"),
                end=Endpoint(earliest="1860"),
            ),
        ],
    )


class TestBoendenTabInPersonEditor:
    """Tests that the Boenden tab is inserted into the PersonEditor."""

    def test_boenden_tab_exists(self, qapp, project_with_residences, person):
        """The Boenden tab is present in the PersonEditor tab widget."""
        editor = PersonEditor(project_with_residences, person)
        tab_texts = [
            editor._ui.tab_widget.tabText(i)
            for i in range(editor._ui.tab_widget.count())
        ]
        assert "Boenden" in tab_texts

    def test_boenden_tab_after_foton(self, qapp, project_with_residences, person):
        """The Boenden tab comes immediately after the Foton tab."""
        editor = PersonEditor(project_with_residences, person)
        tab_texts = [
            editor._ui.tab_widget.tabText(i)
            for i in range(editor._ui.tab_widget.count())
        ]
        foton_idx = tab_texts.index("Foton")
        assert tab_texts[foton_idx + 1] == "Boenden"

    def test_boenden_tab_not_created_for_new_person(self, qapp, project_no_residences):
        """No Boenden tab when creating a new person (person is None)."""
        editor = PersonEditor(project_no_residences, person=None)
        tab_texts = [
            editor._ui.tab_widget.tabText(i)
            for i in range(editor._ui.tab_widget.count())
        ]
        assert "Boenden" not in tab_texts


class TestBoendenTabWidget:
    """Tests for the standalone BoendenTab widget."""

    def test_empty_state(self, qapp, project_no_residences, person):
        """Empty state label shown when person has no residences."""
        tab = BoendenTab(project_no_residences, person)
        assert tab.stack_layout.currentWidget() == tab.empty_label

    def test_list_populated(self, qapp, project_with_residences, person):
        """List is populated when person has residences."""
        tab = BoendenTab(project_with_residences, person)
        assert tab.stack_layout.currentWidget() == tab.residence_list
        assert tab.residence_list.count() == 2

    def test_list_item_contains_place_and_interval(
        self, qapp, project_with_residences, person
    ):
        """Each list item contains the place name and interval text."""
        tab = BoendenTab(project_with_residences, person)
        text = tab.residence_list.item(0).text()
        assert "Ekeby" in text

    def test_list_item_stores_residence_id(
        self, qapp, project_with_residences, person
    ):
        """Each list item stores the residence id in UserRole."""
        tab = BoendenTab(project_with_residences, person)
        item_id = tab.residence_list.item(0).data(Qt.ItemDataRole.UserRole)
        assert item_id in ("res1", "res2")

    def test_add_button_always_enabled(self, qapp, project_no_residences, person):
        """The 'Nytt boende' button is always enabled."""
        tab = BoendenTab(project_no_residences, person)
        assert tab.add_button.isEnabled() is True

    def test_edit_button_disabled_without_selection(
        self, qapp, project_with_residences, person
    ):
        """The edit button is disabled when nothing is selected."""
        tab = BoendenTab(project_with_residences, person)
        assert tab.edit_button.isEnabled() is False

    def test_edit_button_enabled_with_selection(
        self, qapp, project_with_residences, person
    ):
        """The edit button is enabled when a residence is selected."""
        tab = BoendenTab(project_with_residences, person)
        tab.residence_list.setCurrentRow(0)
        assert tab.edit_button.isEnabled() is True

    def test_create_signal_emitted(self, qapp, project_no_residences, person):
        """Clicking 'Nytt boende' emits create_requested."""
        tab = BoendenTab(project_no_residences, person)
        signals = []
        tab.create_requested.connect(lambda: signals.append(True))
        tab.add_button.click()
        assert len(signals) == 1

    def test_edit_signal_emitted(self, qapp, project_with_residences, person):
        """Clicking 'Redigera boende' with selection emits edit_requested."""
        tab = BoendenTab(project_with_residences, person)
        signals = []
        tab.edit_requested.connect(lambda rid: signals.append(rid))
        tab.residence_list.setCurrentRow(0)
        tab.edit_button.click()
        assert len(signals) == 1
        assert signals[0] in ("res1", "res2")

    def test_residents_dialog_signal_emitted(
        self, qapp, project_no_residences, person
    ):
        """Clicking 'Boende på plats' emits residents_dialog_requested."""
        tab = BoendenTab(project_no_residences, person)
        signals = []
        tab.residents_dialog_requested.connect(lambda: signals.append(True))
        tab.residents_button.click()
        assert len(signals) == 1

    def test_refresh_updates_list(self, qapp, person, place):
        """Calling refresh after adding residences updates the list."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[person],
            places=[place],
        )
        tab = BoendenTab(project, person)
        assert tab.residence_list.count() == 0

        # Add a residence
        project.residences.append(
            ResidenceFact(
                id="res_new",
                person_id="p1",
                place_id="place1",
                start=Endpoint(latest="1870"),
                end=Endpoint(earliest="1880"),
            )
        )
        tab.refresh()
        assert tab.residence_list.count() == 1

    def test_role_shown_in_list(self, qapp, project_with_residences, person):
        """The role_in_household is shown in the list when non-empty."""
        tab = BoendenTab(project_with_residences, person)
        # First residence has role "husbonde"
        text = tab.residence_list.item(0).text()
        assert "husbonde" in text
