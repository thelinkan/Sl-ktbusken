"""Unit tests for PersonEditor tab structure.

Verifies tab order, tab labels, and widget placement after the cluster
section was extracted into its own "Kluster" tab (Requirement 10).

Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaCluster, DnaProfile
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.person_editor import PersonEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def minimal_project_data() -> ProjectData:
    """Create a minimal project data for testing."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
    )


@pytest.fixture()
def sample_person() -> Person:
    """Create a sample person with a name for testing."""
    return Person(
        id="person_1",
        sex="M",
        names=[Name(type="birth", given="Erik", surname="Johansson")],
    )


@pytest.fixture()
def project_with_clusters(sample_person: Person) -> ProjectData:
    """Create a project with clusters for add/remove testing."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[sample_person],
        dna_profiles=[
            DnaProfile(
                id="dnaprofile_1",
                person_id="person_1",
                company_id="dnacompany_1",
                test_type="autosomal",
                kit_name="Eriks kit",
            ),
        ],
        dna_clusters=[
            DnaCluster(
                id="dnacluster_1",
                name="Kluster A",
                person_ids=["person_1", "person_3"],
            ),
            DnaCluster(
                id="dnacluster_2",
                name="Kluster B",
                person_ids=["person_2"],
            ),
        ],
    )


class TestTabOrder:
    """Tests verifying the tab order is (Namn, Händelser, Foton, DNA, Kluster)."""

    def test_tab_count_is_five(self, qapp, minimal_project_data, sample_person):
        """PersonEditor should have exactly 5 tabs."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        assert editor._ui.tab_widget.count() == 5

    def test_tab_order(self, qapp, minimal_project_data, sample_person):
        """Tabs should be in order: Namn, Händelser, Foton, DNA, Kluster."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        tw = editor._ui.tab_widget

        expected_order = ["Namn", "Händelser", "Foton", "DNA", "Kluster"]
        actual_order = [tw.tabText(i) for i in range(tw.count())]
        assert actual_order == expected_order

    def test_names_tab_is_index_0(self, qapp, minimal_project_data, sample_person):
        """Namn tab should be at index 0."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        tw = editor._ui.tab_widget
        assert tw.indexOf(editor._ui.names_tab) == 0

    def test_events_tab_is_index_1(self, qapp, minimal_project_data, sample_person):
        """Händelser tab should be at index 1."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        tw = editor._ui.tab_widget
        assert tw.indexOf(editor._ui.events_tab) == 1

    def test_photos_tab_is_index_2(self, qapp, minimal_project_data, sample_person):
        """Foton tab should be at index 2."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        tw = editor._ui.tab_widget
        assert tw.indexOf(editor._ui.photos_tab) == 2

    def test_dna_tab_is_index_3(self, qapp, minimal_project_data, sample_person):
        """DNA tab should be at index 3."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        tw = editor._ui.tab_widget
        assert tw.indexOf(editor._ui.dna_tab) == 3

    def test_cluster_tab_is_index_4(self, qapp, minimal_project_data, sample_person):
        """Kluster tab should be at index 4."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        tw = editor._ui.tab_widget
        assert tw.indexOf(editor._ui.cluster_tab) == 4


class TestTabLabels:
    """Tests verifying DNA tab text is 'DNA' and Kluster tab text is 'Kluster'."""

    def test_dna_tab_text(self, qapp, minimal_project_data, sample_person):
        """DNA tab should have text 'DNA' (not 'DNA & Kluster')."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        tw = editor._ui.tab_widget
        dna_index = tw.indexOf(editor._ui.dna_tab)
        assert tw.tabText(dna_index) == "DNA"

    def test_cluster_tab_text(self, qapp, minimal_project_data, sample_person):
        """Kluster tab should have text 'Kluster'."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        tw = editor._ui.tab_widget
        cluster_index = tw.indexOf(editor._ui.cluster_tab)
        assert tw.tabText(cluster_index) == "Kluster"


class TestClusterWidgetPlacement:
    """Tests verifying cluster widgets are in Kluster tab and not in DNA tab."""

    def test_cluster_list_is_in_cluster_tab(self, qapp, minimal_project_data, sample_person):
        """The dna_clusters_list widget should be a child of cluster_tab."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        # The cluster list's parent chain should include cluster_tab
        assert editor._ui.dna_clusters_list.parent() == editor._ui.cluster_tab

    def test_cluster_label_is_in_cluster_tab(self, qapp, minimal_project_data, sample_person):
        """The dna_clusters_label widget should be a child of cluster_tab."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        assert editor._ui.dna_clusters_label.parent() == editor._ui.cluster_tab

    def test_add_cluster_button_in_cluster_tab(self, qapp, minimal_project_data, sample_person):
        """The add cluster button should be parented to cluster_tab."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        assert editor._add_cluster_button.parent() == editor._ui.cluster_tab

    def test_remove_cluster_button_in_cluster_tab(self, qapp, minimal_project_data, sample_person):
        """The remove cluster button should be parented to cluster_tab."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        assert editor._remove_cluster_button.parent() == editor._ui.cluster_tab

    def test_dna_tab_does_not_contain_cluster_list(self, qapp, minimal_project_data, sample_person):
        """The DNA tab should not have the clusters list as a child."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        # Walk the dna_tab's children — cluster list should NOT be among them
        dna_tab_children = editor._ui.dna_tab.findChildren(type(editor._ui.dna_clusters_list))
        assert editor._ui.dna_clusters_list not in dna_tab_children

    def test_dna_tab_does_not_contain_cluster_label(self, qapp, minimal_project_data, sample_person):
        """The DNA tab should not have the clusters label as a direct child."""
        editor = PersonEditor(minimal_project_data, person=sample_person)
        # The cluster label's parent should NOT be the dna_tab
        assert editor._ui.dna_clusters_label.parent() != editor._ui.dna_tab


class TestClusterFunctionalityInNewTab:
    """Tests verifying add/remove cluster functionality works in the new Kluster tab."""

    def test_cluster_list_populated_in_cluster_tab(
        self, qapp, project_with_clusters, sample_person
    ):
        """Clusters should be displayed in the Kluster tab list."""
        editor = PersonEditor(project_with_clusters, person=sample_person)
        assert editor._ui.dna_clusters_list.count() == 1  # person_1 is in Kluster A

    def test_remove_cluster_works_in_new_tab(
        self, qapp, project_with_clusters, sample_person
    ):
        """Removing a cluster from the Kluster tab should remove person from cluster."""
        editor = PersonEditor(project_with_clusters, person=sample_person)
        # Verify initial state
        assert editor._ui.dna_clusters_list.count() == 1

        # Select the first item and remove
        editor._ui.dna_clusters_list.setCurrentRow(0)
        editor._on_remove_cluster()

        # Person should be removed from the cluster
        assert editor._ui.dna_clusters_list.count() == 0

    def test_remove_cluster_without_selection_shows_error(
        self, qapp, project_with_clusters, sample_person
    ):
        """Removing without selection should show Swedish error message."""
        editor = PersonEditor(project_with_clusters, person=sample_person)
        editor._ui.dna_clusters_list.clearSelection()
        editor._ui.dna_clusters_list.setCurrentItem(None)
        editor._on_remove_cluster()

        assert editor._ui.status_label.text() == "Välj ett kluster att ta bort."

    def test_no_clusters_message_shown_in_cluster_tab(self, qapp, sample_person):
        """When no clusters exist in project, info message shown in Kluster tab."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[
                DnaProfile(
                    id="dnaprofile_1",
                    person_id="person_1",
                    company_id="dnacompany_1",
                    test_type="autosomal",
                    kit_name="Eriks kit",
                ),
            ],
            dna_clusters=[],
        )
        editor = PersonEditor(project, person=sample_person)
        assert editor._ui.dna_clusters_list.count() == 1
        item_text = editor._ui.dna_clusters_list.item(0).text()
        assert "Inga kluster finns i projektet" in item_text
