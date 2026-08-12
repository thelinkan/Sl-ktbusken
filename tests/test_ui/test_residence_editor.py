"""Unit tests for the ResidenceEditor widget.

Tests widget structure, field labels, observation table sizing,
role validation, and loading from a ResidenceFact.
"""

from __future__ import annotations

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication

from slaktbusken.model.event import SourceRef
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source
from slaktbusken.ui.editors.residence_editor import ResidenceEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def empty_project() -> ProjectData:
    """Create an empty project data for testing."""
    return ProjectData(project=ProjectMetadata(title="Test"))


@pytest.fixture()
def project_with_residences() -> ProjectData:
    """Project with existing residences providing role suggestions."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        residences=[
            ResidenceFact(
                id="res_1",
                person_id="p1",
                place_id="pl1",
                role_in_household="husbonde",
            ),
            ResidenceFact(
                id="res_2",
                person_id="p2",
                place_id="pl1",
                role_in_household="piga",
            ),
            ResidenceFact(
                id="res_3",
                person_id="p3",
                place_id="pl1",
                role_in_household="husbonde",  # duplicate, should appear once
            ),
        ],
    )


@pytest.fixture()
def sample_residence() -> ResidenceFact:
    """A fully populated ResidenceFact for load testing."""
    return ResidenceFact(
        id="res_test",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1840", latest="1842"),
        end=Endpoint(earliest="1870", latest="1875"),
        role_in_household="inhyses",
        observations=[
            Observation(
                source_ref=SourceRef(source_id="src_1", quality="primary"),
                observed_from="1842",
                observed_to="1847",
                page_note="sid 15",
            ),
            Observation(
                source_ref=SourceRef(source_id="src_2", quality="primary"),
                observed_from="1847",
                observed_to="1852",
                page_note="",
            ),
            Observation(
                source_ref=SourceRef(source_id="src_3", quality="primary"),
                observed_from="1840",
                observed_to="1842",
                page_note="sid 3",
            ),
        ],
    )


@pytest.fixture()
def project_with_sources() -> ProjectData:
    """Project with sources that can be resolved for observation display."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        sources=[
            Source(id="src_1", provider="AD", source_type="church_book", title="Ljusdal AI:17"),
            Source(id="src_2", provider="AD", source_type="church_book", title="Ljusdal AI:18"),
            Source(id="src_3", provider="AD", source_type="church_book", title="Ljusdal AI:16"),
        ],
    )


# ============================================================================
# Test: Widget instantiation and import
# ============================================================================


class TestResidenceEditorInstantiation:
    """Verify ResidenceEditor can be created without errors."""

    def test_can_instantiate_empty(self, qapp, empty_project):
        """ResidenceEditor can be instantiated with no residence."""
        editor = ResidenceEditor(empty_project)
        assert editor is not None

    def test_can_instantiate_with_residence(self, qapp, empty_project, sample_residence):
        """ResidenceEditor can be instantiated with an existing residence."""
        editor = ResidenceEditor(empty_project, residence=sample_residence)
        assert editor is not None


# ============================================================================
# Test: Bound fields (Requirement 16.2)
# ============================================================================


class TestBoundFields:
    """Verify the four endpoint bound fields exist and accept ISO forms."""

    def test_has_four_bound_fields(self, qapp, empty_project):
        """Editor has four endpoint bound line edits."""
        editor = ResidenceEditor(empty_project)
        assert editor._start_earliest_edit is not None
        assert editor._start_latest_edit is not None
        assert editor._end_earliest_edit is not None
        assert editor._end_latest_edit is not None

    def test_bound_fields_accept_iso_forms(self, qapp, empty_project):
        """Bound fields accept ÅÅÅÅ, ÅÅÅÅ-MM, and ÅÅÅÅ-MM-DD."""
        editor = ResidenceEditor(empty_project)
        editor._start_earliest_edit.setText("1840")
        assert editor.get_start_earliest() == "1840"

        editor._start_latest_edit.setText("1842-06")
        assert editor.get_start_latest() == "1842-06"

        editor._end_earliest_edit.setText("1870-12-31")
        assert editor.get_end_earliest() == "1870-12-31"

        editor._end_latest_edit.setText("1875")
        assert editor.get_end_latest() == "1875"

    def test_empty_bound_fields_return_none(self, qapp, empty_project):
        """Empty bound fields return None."""
        editor = ResidenceEditor(empty_project)
        assert editor.get_start_earliest() is None
        assert editor.get_start_latest() is None
        assert editor.get_end_earliest() is None
        assert editor.get_end_latest() is None

    def test_whitespace_only_returns_none(self, qapp, empty_project):
        """Whitespace-only bound fields return None."""
        editor = ResidenceEditor(empty_project)
        editor._start_earliest_edit.setText("   ")
        assert editor.get_start_earliest() is None

    def test_loads_bounds_from_residence(self, qapp, empty_project, sample_residence):
        """Loading a residence populates the bound fields."""
        editor = ResidenceEditor(empty_project, residence=sample_residence)
        assert editor._start_earliest_edit.text() == "1840"
        assert editor._start_latest_edit.text() == "1842"
        assert editor._end_earliest_edit.text() == "1870"
        assert editor._end_latest_edit.text() == "1875"


# ============================================================================
# Test: Role in household (Requirements 10.3, 10.6)
# ============================================================================


class TestRoleInHousehold:
    """Verify the role_in_household field with suggestions and validation."""

    def test_has_role_field(self, qapp, empty_project):
        """Editor has a role_in_household line edit."""
        editor = ResidenceEditor(empty_project)
        assert editor._role_edit is not None

    def test_role_accepts_free_text(self, qapp, empty_project):
        """Role field accepts any typed text."""
        editor = ResidenceEditor(empty_project)
        editor._role_edit.setText("torpare")
        assert editor.get_role_in_household() == "torpare"

    def test_role_trims_whitespace(self, qapp, empty_project):
        """Role value is trimmed on retrieval."""
        editor = ResidenceEditor(empty_project)
        editor._role_edit.setText("  husbonde  ")
        assert editor.get_role_in_household() == "husbonde"

    def test_role_validates_within_limit(self, qapp, empty_project):
        """Role of exactly 100 chars passes validation."""
        editor = ResidenceEditor(empty_project)
        editor._role_edit.setText("x" * 100)
        assert editor.validate_role() is True

    def test_role_validates_over_limit(self, qapp, empty_project):
        """Role exceeding 100 chars fails validation and shows error."""
        editor = ResidenceEditor(empty_project)
        editor._role_edit.setText("x" * 101)
        assert editor.validate_role() is False
        # Widget not shown so isVisible() won't work; check that it's not hidden
        assert not editor._role_error_label.isHidden()
        assert "100 tecken" in editor._role_error_label.text()

    def test_role_validation_keeps_entered_text(self, qapp, empty_project):
        """Validation failure keeps the entered text unchanged."""
        editor = ResidenceEditor(empty_project)
        long_text = "å" * 105
        editor._role_edit.setText(long_text)
        editor.validate_role()
        assert editor._role_edit.text() == long_text

    def test_role_completer_with_suggestions(self, qapp, project_with_residences):
        """Editor offers existing roles as non-binding suggestions."""
        editor = ResidenceEditor(project_with_residences)
        completer = editor._role_edit.completer()
        assert completer is not None
        # Should have unique roles: "husbonde" and "piga"
        model = completer.model()
        suggestions = [model.data(model.index(i, 0)) for i in range(model.rowCount())]
        assert "husbonde" in suggestions
        assert "piga" in suggestions
        assert len(suggestions) == 2  # duplicates removed

    def test_role_completer_empty_project(self, qapp, empty_project):
        """No completer set when no existing roles exist."""
        editor = ResidenceEditor(empty_project)
        completer = editor._role_edit.completer()
        assert completer is None

    def test_loads_role_from_residence(self, qapp, empty_project, sample_residence):
        """Loading a residence populates the role field."""
        editor = ResidenceEditor(empty_project, residence=sample_residence)
        assert editor._role_edit.text() == "inhyses"


# ============================================================================
# Test: Observations table (Requirement 16.12)
# ============================================================================


class TestObservationsTable:
    """Verify the Observation table structure and behaviour."""

    def test_has_observations_table(self, qapp, empty_project):
        """Editor has an Observation table widget."""
        editor = ResidenceEditor(empty_project)
        assert editor._observations_table is not None

    def test_table_has_three_columns(self, qapp, empty_project):
        """Table has columns for source title, span, and page_note."""
        editor = ResidenceEditor(empty_project)
        assert editor._observations_table.columnCount() == 3

    def test_table_headers(self, qapp, empty_project):
        """Table has correct Swedish column headers."""
        editor = ResidenceEditor(empty_project)
        headers = [
            editor._observations_table.horizontalHeaderItem(i).text()
            for i in range(3)
        ]
        assert headers == ["Källa", "Period", "Sidanteckning"]

    def test_table_minimum_height_for_15_rows(self, qapp, empty_project):
        """Table is sized for at least 15 untruncated rows."""
        editor = ResidenceEditor(empty_project)
        table = editor._observations_table
        row_height = table.verticalHeader().defaultSectionSize()
        # The minimum height should accommodate at least 15 rows
        assert table.minimumHeight() >= row_height * 15

    def test_observations_ordered_by_from_then_to(
        self, qapp, project_with_sources, sample_residence
    ):
        """Observations are displayed ordered by observed_from then observed_to."""
        editor = ResidenceEditor(project_with_sources, residence=sample_residence)
        table = editor._observations_table
        # sample_residence has observations: (1842,1847), (1847,1852), (1840,1842)
        # sorted: (1840,1842), (1842,1847), (1847,1852)
        assert table.rowCount() == 3
        assert table.item(0, 1).text() == "1840–1842"
        assert table.item(1, 1).text() == "1842–1847"
        assert table.item(2, 1).text() == "1847–1852"

    def test_observations_show_source_title(self, qapp, project_with_sources, sample_residence):
        """Observation rows resolve and display the source title."""
        editor = ResidenceEditor(project_with_sources, residence=sample_residence)
        table = editor._observations_table
        # After sorting by from/to: src_3 (1840), src_1 (1842), src_2 (1847)
        assert table.item(0, 0).text() == "Ljusdal AI:16"
        assert table.item(1, 0).text() == "Ljusdal AI:17"
        assert table.item(2, 0).text() == "Ljusdal AI:18"

    def test_observations_show_page_note(self, qapp, project_with_sources, sample_residence):
        """Observation rows display the page_note."""
        editor = ResidenceEditor(project_with_sources, residence=sample_residence)
        table = editor._observations_table
        # After sorting: src_3 (sid 3), src_1 (sid 15), src_2 ("")
        assert table.item(0, 2).text() == "sid 3"
        assert table.item(1, 2).text() == "sid 15"
        assert table.item(2, 2).text() == ""

    def test_unresolved_source_shows_id(self, qapp, empty_project):
        """If source cannot be resolved, the source_id is shown as fallback."""
        residence = ResidenceFact(
            id="res_x",
            person_id="p1",
            place_id="pl1",
            observations=[
                Observation(
                    source_ref=SourceRef(source_id="unknown_src", quality="primary"),
                    observed_from="1850",
                    observed_to="1855",
                ),
            ],
        )
        editor = ResidenceEditor(empty_project, residence=residence)
        table = editor._observations_table
        assert table.item(0, 0).text() == "unknown_src"

    def test_set_observations_updates_table(self, qapp, project_with_sources):
        """set_observations() repopulates the table correctly."""
        editor = ResidenceEditor(project_with_sources)
        observations = [
            Observation(
                source_ref=SourceRef(source_id="src_1", quality="primary"),
                observed_from="1866",
                observed_to="1870",
                page_note="uppslag 4",
            ),
        ]
        editor.set_observations(observations)
        table = editor._observations_table
        assert table.rowCount() == 1
        assert table.item(0, 0).text() == "Ljusdal AI:17"
        assert table.item(0, 1).text() == "1866–1870"
        assert table.item(0, 2).text() == "uppslag 4"

    def test_table_is_read_only(self, qapp, empty_project):
        """The Observation table does not allow direct editing."""
        editor = ResidenceEditor(empty_project)
        triggers = editor._observations_table.editTriggers()
        assert triggers == QAbstractItemView.EditTrigger.NoEditTriggers
