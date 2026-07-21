"""Unit tests for the redesigned cluster tab split-panel layout.

Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidget, QPushButton, QSplitter, QTextEdit

from slaktbusken.model.dna import DnaCluster, DnaMatch, DnaProfile
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.dna_editor import DnaEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def project_data_with_clusters() -> ProjectData:
    """Create project data with persons and clusters for testing."""
    persons = [
        Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Svensson")]),
        Person(id="p2", sex="F", names=[Name(type="birth", given="Anna", surname="Johansson")]),
        Person(id="p3", sex="M", names=[Name(type="birth", given="Lars", surname="Nilsson")]),
    ]
    clusters = [
        DnaCluster(
            id="c1",
            name="Kluster Alpha",
            notes="Anteckning för alpha",
            person_ids=["p1", "p2"],
        ),
        DnaCluster(
            id="c2",
            name="Kluster Beta",
            notes="Anteckning för beta",
            person_ids=["p3"],
        ),
    ]
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        dna_clusters=clusters,
    )


@pytest.fixture()
def editor(qtbot, project_data_with_clusters) -> DnaEditor:
    """Create a DnaEditor instance with cluster data."""
    ed = DnaEditor(project_data=project_data_with_clusters, project_path=None)
    qtbot.addWidget(ed)
    return ed


class TestClusterPanelLayout:
    """Tests for the split-panel layout structure (Req 8.1)."""

    def test_splitter_exists(self, editor: DnaEditor):
        """Cluster tab SHALL contain a horizontal QSplitter."""
        assert hasattr(editor, "_cluster_splitter")
        assert isinstance(editor._cluster_splitter, QSplitter)
        assert editor._cluster_splitter.orientation() == Qt.Orientation.Horizontal

    def test_left_panel_cluster_list(self, editor: DnaEditor):
        """Left panel SHALL contain a scrollable QListWidget of clusters."""
        assert hasattr(editor, "_cluster_list_widget")
        assert isinstance(editor._cluster_list_widget, QListWidget)

    def test_right_panel_persons_list(self, editor: DnaEditor):
        """Right panel upper SHALL contain a scrollable QListWidget of persons (Req 8.2)."""
        assert hasattr(editor, "_cluster_persons_list")
        assert isinstance(editor._cluster_persons_list, QListWidget)

    def test_right_panel_notes_area(self, editor: DnaEditor):
        """Right panel lower SHALL contain a QTextEdit for notes (Req 8.3)."""
        assert hasattr(editor, "_cluster_notes_edit")
        assert isinstance(editor._cluster_notes_edit, QTextEdit)
        # Minimum height for 3 visible text lines
        assert editor._cluster_notes_edit.minimumHeight() >= 60

    def test_cluster_list_populated(self, editor: DnaEditor):
        """Cluster list SHALL show all clusters from project data."""
        assert editor._cluster_list_widget.count() == 2
        item0 = editor._cluster_list_widget.item(0)
        item1 = editor._cluster_list_widget.item(1)
        assert item0.text() == "Kluster Alpha"
        assert item1.text() == "Kluster Beta"


class TestClusterSelection:
    """Tests for cluster selection behavior (Req 8.4, 8.6)."""

    def test_no_cluster_selected_empty_state(self, editor: DnaEditor):
        """IF no cluster selected, show empty persons list and disabled notes (Req 8.6)."""
        # Initially no cluster is selected
        assert editor._cluster_persons_list.count() == 0
        assert not editor._cluster_notes_edit.isEnabled()

    def test_selecting_cluster_shows_persons(self, editor: DnaEditor):
        """WHEN cluster selected, update persons list (Req 8.4)."""
        # Select the first cluster
        editor._cluster_list_widget.setCurrentRow(0)

        # Should show 2 persons with resolved names
        assert editor._cluster_persons_list.count() == 2
        assert editor._cluster_persons_list.item(0).text() == "Erik Svensson"
        assert editor._cluster_persons_list.item(1).text() == "Anna Johansson"

    def test_selecting_cluster_shows_notes(self, editor: DnaEditor):
        """WHEN cluster selected, update notes area (Req 8.4)."""
        editor._cluster_list_widget.setCurrentRow(0)
        assert editor._cluster_notes_edit.toPlainText() == "Anteckning för alpha"
        assert editor._cluster_notes_edit.isEnabled()

    def test_selecting_different_cluster_updates(self, editor: DnaEditor):
        """WHEN different cluster selected, update persons + notes (Req 8.4)."""
        editor._cluster_list_widget.setCurrentRow(0)
        editor._cluster_list_widget.setCurrentRow(1)

        assert editor._cluster_persons_list.count() == 1
        assert editor._cluster_persons_list.item(0).text() == "Lars Nilsson"
        assert editor._cluster_notes_edit.toPlainText() == "Anteckning för beta"


class TestNotesPersistence:
    """Tests for notes auto-persistence (Req 8.5, 8.7)."""

    def test_notes_persisted_on_cluster_switch(self, editor: DnaEditor):
        """WHEN user edits notes and selects different cluster, persist notes (Req 8.7)."""
        # Select first cluster
        editor._cluster_list_widget.setCurrentRow(0)

        # Edit notes
        editor._cluster_notes_edit.setPlainText("Ändrade anteckningar")

        # Switch to second cluster
        editor._cluster_list_widget.setCurrentRow(1)

        # Verify notes were persisted to the first cluster
        cluster_alpha = None
        for c in editor._project_data.dna_clusters:
            if c.id == "c1":
                cluster_alpha = c
                break
        assert cluster_alpha is not None
        assert cluster_alpha.notes == "Ändrade anteckningar"

    def test_notes_field_in_cluster_data(self, editor: DnaEditor):
        """Notes field SHALL be persisted as part of cluster data (Req 8.5)."""
        # This is inherently tested by the model having a notes field
        cluster = editor._project_data.dna_clusters[0]
        assert hasattr(cluster, "notes")
        assert cluster.notes == "Anteckning för alpha"


class TestPersonNameResolution:
    """Tests for person name resolution in the persons list."""

    def test_person_names_resolved(self, editor: DnaEditor):
        """Person list SHALL show resolved person names (Req 8.2)."""
        editor._cluster_list_widget.setCurrentRow(0)
        # Persons are resolved as "given surname"
        assert editor._cluster_persons_list.item(0).text() == "Erik Svensson"
        assert editor._cluster_persons_list.item(1).text() == "Anna Johansson"

    def test_unknown_person_shows_id(self, editor: DnaEditor):
        """IF person_id not found, show the raw ID."""
        # Add a cluster with an unknown person_id
        editor._project_data.dna_clusters.append(
            DnaCluster(id="c3", name="Kluster Gamma", person_ids=["unknown_id"])
        )
        editor._refresh_clusters_list()
        editor._cluster_list_widget.setCurrentRow(2)
        assert editor._cluster_persons_list.item(0).text() == "unknown_id"


# --- Fixtures and tests for context menu and DNA match filter (Req 9.1-9.6) ---


@pytest.fixture()
def project_data_with_dna() -> ProjectData:
    """Create project data with persons, profiles, matches, and clusters."""
    persons = [
        Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="Svensson")]),
        Person(id="p2", sex="F", names=[Name(type="birth", given="Anna", surname="Johansson")]),
        Person(id="p3", sex="M", names=[Name(type="birth", given="Lars", surname="Nilsson")]),
        Person(id="p4", sex="F", names=[Name(type="birth", given="Karin", surname="Berg")]),
    ]
    profiles = [
        DnaProfile(id="prof1", person_id="p1", company_id="co1", test_type="autosomal"),
        DnaProfile(id="prof2", person_id="p2", company_id="co1", test_type="autosomal"),
        DnaProfile(id="prof3", person_id="p3", company_id="co1", test_type="autosomal"),
        # p4 has NO profile
    ]
    matches = [
        # p1 (prof1) matches p2 (prof2)
        DnaMatch(id="m1", profile1_id="prof1", profile2_id="prof2", shared_cm=50.0),
        # p1 (prof1) matches p3 (prof3)
        DnaMatch(id="m2", profile1_id="prof3", profile2_id="prof1", shared_cm=30.0),
    ]
    clusters = [
        DnaCluster(
            id="c1",
            name="Kluster Alpha",
            notes="",
            person_ids=["p1", "p2", "p3", "p4"],
        ),
        DnaCluster(
            id="c2",
            name="Kluster Beta",
            notes="",
            person_ids=["p2", "p3"],
        ),
    ]
    return ProjectData(
        project=ProjectMetadata(title="Test DNA"),
        persons=persons,
        dna_profiles=profiles,
        dna_matches=matches,
        dna_clusters=clusters,
    )


@pytest.fixture()
def dna_editor(qtbot, project_data_with_dna) -> DnaEditor:
    """Create a DnaEditor instance with DNA data for context menu tests."""
    ed = DnaEditor(project_data=project_data_with_dna, project_path=None)
    qtbot.addWidget(ed)
    return ed


class TestClusterContextMenu:
    """Tests for the cluster context menu (Req 9.1, 9.2)."""

    def test_context_menu_policy_set(self, dna_editor: DnaEditor):
        """Persons list SHALL have CustomContextMenu policy (Req 9.1)."""
        assert (
            dna_editor._cluster_persons_list.contextMenuPolicy()
            == Qt.ContextMenuPolicy.CustomContextMenu
        )

    def test_filter_toggle_exists(self, dna_editor: DnaEditor):
        """Cluster panel SHALL have a 'Visa filtrerade' toggle button (Req 9.5)."""
        assert hasattr(dna_editor, "_cluster_filter_toggle")
        assert isinstance(dna_editor._cluster_filter_toggle, QPushButton)
        assert dna_editor._cluster_filter_toggle.isCheckable()
        assert dna_editor._cluster_filter_toggle.text() == "Visa filtrerade"

    def test_filter_toggle_initially_unchecked(self, dna_editor: DnaEditor):
        """Toggle SHALL be unchecked by default."""
        assert not dna_editor._cluster_filter_toggle.isChecked()


class TestClusterDnaFilter:
    """Tests for cluster DNA match filter logic (Req 9.3, 9.4, 9.5, 9.6)."""

    def test_filter_on_person_with_matches(self, dna_editor: DnaEditor):
        """WHEN filter activated for p1, show only p2 and p3 (who have matches with p1) (Req 9.3)."""
        # Select the first cluster
        dna_editor._cluster_list_widget.setCurrentRow(0)
        assert dna_editor._cluster_persons_list.count() == 4

        # Apply filter for person p1
        dna_editor._apply_cluster_dna_filter("p1")

        # Should show p2 and p3 (matched via prof1↔prof2 and prof1↔prof3)
        assert dna_editor._cluster_persons_list.count() == 2
        person_ids = [
            dna_editor._cluster_persons_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(dna_editor._cluster_persons_list.count())
        ]
        assert "p2" in person_ids
        assert "p3" in person_ids
        assert "p1" not in person_ids  # The filtered person themselves excluded
        assert "p4" not in person_ids  # No match with p1

    def test_filter_sets_toggle_checked(self, dna_editor: DnaEditor):
        """WHEN filter activated, toggle SHALL be checked (Req 9.3)."""
        dna_editor._cluster_list_widget.setCurrentRow(0)
        dna_editor._apply_cluster_dna_filter("p1")
        assert dna_editor._cluster_filter_toggle.isChecked()

    def test_filter_on_person_no_matches_shows_empty(self, dna_editor: DnaEditor):
        """IF no matches found, show empty person list (Req 9.4)."""
        dna_editor._cluster_list_widget.setCurrentRow(0)
        # p4 has no profile, hence no matches
        dna_editor._apply_cluster_dna_filter("p4")
        assert dna_editor._cluster_persons_list.count() == 0

    def test_toggle_uncheck_restores_all_persons(self, dna_editor: DnaEditor):
        """WHEN toggle unchecked, exit filter and show all persons (Req 9.5)."""
        dna_editor._cluster_list_widget.setCurrentRow(0)
        dna_editor._apply_cluster_dna_filter("p1")
        assert dna_editor._cluster_persons_list.count() == 2

        # Uncheck the toggle
        dna_editor._cluster_filter_toggle.setChecked(False)
        dna_editor._on_cluster_filter_toggle()

        # All persons should be restored
        assert dna_editor._cluster_persons_list.count() == 4

    def test_cluster_change_exits_filter(self, dna_editor: DnaEditor):
        """WHEN different cluster selected while filtered, exit filter (Req 9.6)."""
        dna_editor._cluster_list_widget.setCurrentRow(0)
        dna_editor._apply_cluster_dna_filter("p1")
        assert dna_editor._cluster_filter_toggle.isChecked()

        # Switch to another cluster
        dna_editor._cluster_list_widget.setCurrentRow(1)

        # Filter should be exited, toggle unchecked
        assert not dna_editor._cluster_filter_toggle.isChecked()
        assert not dna_editor._cluster_filter_active
        # The new cluster's persons should show (p2, p3)
        assert dna_editor._cluster_persons_list.count() == 2

    def test_filter_on_person_with_single_match(self, dna_editor: DnaEditor):
        """WHEN filter activated for p2, show only p1 (the only match partner)."""
        dna_editor._cluster_list_widget.setCurrentRow(0)
        dna_editor._apply_cluster_dna_filter("p2")

        # p2 only matches p1 via match m1
        assert dna_editor._cluster_persons_list.count() == 1
        assert (
            dna_editor._cluster_persons_list.item(0).data(Qt.ItemDataRole.UserRole) == "p1"
        )
