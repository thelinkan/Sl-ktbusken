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
from slaktbusken.model.event import DateValue, Event, Participant


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


# ============================================================================
# Test: Per-Endpoint Event Selectors
# ============================================================================


@pytest.fixture()
def project_with_events() -> ProjectData:
    """Project with a person who has dated and undated events."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        events=[
            Event(
                id="evt_birth",
                type="birth",
                participants=[Participant(person_id="p1", role="subject")],
                date=DateValue(value="1820-03-15", precision="day"),
            ),
            Event(
                id="evt_death",
                type="death",
                participants=[Participant(person_id="p1", role="subject")],
                date=DateValue(value="1890-11-02", precision="day"),
            ),
            Event(
                id="evt_confirm",
                type="confirmation",
                participants=[Participant(person_id="p1", role="subject")],
                date=DateValue(value="1835", precision="year"),
            ),
            Event(
                id="evt_undated",
                type="emigration",
                participants=[Participant(person_id="p1", role="subject")],
                date=None,
            ),
            Event(
                id="evt_flytt",
                type="flytt",
                participants=[Participant(person_id="p1", role="subject")],
                date=DateValue(value="1860-06", precision="month"),
            ),
            # Event for a different person — should not appear
            Event(
                id="evt_other",
                type="birth",
                participants=[Participant(person_id="p2", role="subject")],
                date=DateValue(value="1825", precision="year"),
            ),
        ],
    )


@pytest.fixture()
def residence_with_event() -> ResidenceFact:
    """A residence with start linked to an event."""
    return ResidenceFact(
        id="res_linked",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(
            earliest="1820-03-15",
            latest="1820-03-15",
            precision="day",
            event_id="evt_birth",
        ),
        end=Endpoint(earliest="1890", latest="1890-11-02"),
    )


class TestEventSelectors:
    """Tests for the per-Endpoint Event selector combo boxes."""

    def test_has_start_event_combo(self, qapp, project_with_events):
        """The editor has a start event combo box."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        assert editor._start_event_combo is not None
        assert editor._start_event_combo.count() > 0

    def test_has_end_event_combo(self, qapp, project_with_events):
        """The editor has an end event combo box."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        assert editor._end_event_combo is not None
        assert editor._end_event_combo.count() > 0

    def test_first_item_is_empty_choice(self, qapp, project_with_events):
        """Both selectors have an empty first choice (no linked event)."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        # First item text is empty, data is None
        assert editor._start_event_combo.itemText(0) == ""
        assert editor._start_event_combo.itemData(0) is None
        assert editor._end_event_combo.itemText(0) == ""
        assert editor._end_event_combo.itemData(0) is None

    def test_only_person_events_shown(self, qapp, project_with_events):
        """Only events for the person_id are listed, not other persons."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        combo = editor._start_event_combo
        event_ids = [combo.itemData(i) for i in range(combo.count()) if combo.itemData(i)]
        # p1 has 5 events; p2's event should not appear
        assert "evt_other" not in event_ids
        assert "evt_birth" in event_ids
        assert "evt_death" in event_ids

    def test_events_ordered_by_date_undated_last(self, qapp, project_with_events):
        """Dated events are ordered by date ascending; undated events come last."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        combo = editor._start_event_combo
        event_ids = [combo.itemData(i) for i in range(1, combo.count())]
        # Expected order: birth(1820-03-15), confirm(1835), flytt(1860-06),
        #                 death(1890-11-02), undated(emigration)
        assert event_ids == [
            "evt_birth", "evt_confirm", "evt_flytt", "evt_death", "evt_undated"
        ]

    def test_event_label_with_date(self, qapp, project_with_events):
        """A dated event is labelled as 'Type (date)'."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        combo = editor._start_event_combo
        # Find the birth event (index 1, first dated)
        label = combo.itemText(1)
        assert label == "Födelse (1820-03-15)"

    def test_event_label_undated(self, qapp, project_with_events):
        """An undated event is labelled with just its type label."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        combo = editor._start_event_combo
        # Find the undated event (last)
        last_idx = combo.count() - 1
        label = combo.itemText(last_idx)
        assert label == "Emigration"

    def test_no_events_shows_only_empty_choice(self, qapp, project_with_events):
        """If the person has no events, only the empty choice is shown."""
        editor = ResidenceEditor(project_with_events, person_id="p_nobody")
        assert editor._start_event_combo.count() == 1
        assert editor._end_event_combo.count() == 1

    def test_dated_selection_writes_bounds(self, qapp, project_with_events):
        """Selecting a dated event writes event_id, earliest, latest, precision."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        # Select birth event (index 1)
        editor._start_event_combo.setCurrentIndex(1)
        assert editor.start_event_id == "evt_birth"
        assert editor._start_earliest_edit.text() == "1820-03-15"
        assert editor._start_latest_edit.text() == "1820-03-15"
        assert editor.start_precision == "day"

    def test_undated_selection_writes_only_event_id(self, qapp, project_with_events):
        """Selecting an undated event writes only event_id, leaves bounds unchanged."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        # Set some initial bounds
        editor._end_earliest_edit.setText("1880")
        editor._end_latest_edit.setText("1885")
        # Select the undated emigration event (last item)
        last_idx = editor._end_event_combo.count() - 1
        editor._end_event_combo.setCurrentIndex(last_idx)
        assert editor.end_event_id == "evt_undated"
        # Bounds should be unchanged
        assert editor._end_earliest_edit.text() == "1880"
        assert editor._end_latest_edit.text() == "1885"

    def test_empty_choice_clears_only_event_id(self, qapp, project_with_events):
        """Selecting the empty choice clears event_id, keeps bounds."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        # First select a dated event
        editor._start_event_combo.setCurrentIndex(1)
        assert editor.start_event_id == "evt_birth"
        # Now clear by selecting empty
        editor._start_event_combo.setCurrentIndex(0)
        assert editor.start_event_id is None
        # Bounds should remain from the dated selection
        assert editor._start_earliest_edit.text() == "1820-03-15"
        assert editor._start_latest_edit.text() == "1820-03-15"

    def test_bounds_editable_with_event_id(self, qapp, project_with_events):
        """Bounds fields stay editable after linking an event; event_id unchanged."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        editor._start_event_combo.setCurrentIndex(1)  # birth
        assert editor.start_event_id == "evt_birth"
        # User types new values
        editor._start_earliest_edit.setText("1819")
        editor._start_latest_edit.setText("1821")
        # event_id should remain
        assert editor.start_event_id == "evt_birth"
        assert editor.get_start_earliest() == "1819"
        assert editor.get_start_latest() == "1821"

    def test_date_mismatch_message(self, qapp, project_with_events):
        """Date mismatch message shown when bounds differ from event date."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        # Select birth event then change the earliest field
        editor._start_event_combo.setCurrentIndex(1)
        editor._start_earliest_edit.setText("1819")
        # Trigger message re-evaluation
        editor._update_event_messages()
        assert not editor._start_event_label.isHidden()
        assert "Kopplad händelse har ett annat datum" in editor._start_event_label.text()

    def test_no_mismatch_when_bounds_match(self, qapp, project_with_events):
        """No mismatch message when bounds match event date."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        editor._start_event_combo.setCurrentIndex(1)  # birth: 1820-03-15
        # Bounds were set by the selection, should match
        editor._update_event_messages()
        # Should show the event label, not a warning
        assert not editor._start_event_label.isHidden()
        assert "Kopplad händelse har ett annat datum" not in editor._start_event_label.text()

    def test_missing_event_message(self, qapp, project_with_events):
        """Missing event message shown when event_id references a deleted event."""
        # Create a residence with a non-existent event_id
        residence = ResidenceFact(
            id="res_missing",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(
                earliest="1850", latest="1850", event_id="evt_gone"
            ),
            end=Endpoint(),
        )
        editor = ResidenceEditor(project_with_events, residence=residence)
        assert not editor._start_event_label.isHidden()
        assert "Händelsen saknas" in editor._start_event_label.text()

    def test_wrong_side_death_on_start(self, qapp, project_with_events):
        """Death event on start endpoint shows wrong-side warning."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        # Find death event index
        combo = editor._start_event_combo
        death_idx = None
        for i in range(combo.count()):
            if combo.itemData(i) == "evt_death":
                death_idx = i
                break
        assert death_idx is not None
        combo.setCurrentIndex(death_idx)
        assert not editor._start_event_label.isHidden()
        assert "boendets andra endpunkt" in editor._start_event_label.text()

    def test_wrong_side_birth_on_end(self, qapp, project_with_events):
        """Birth event on end endpoint shows wrong-side warning."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        combo = editor._end_event_combo
        birth_idx = None
        for i in range(combo.count()):
            if combo.itemData(i) == "evt_birth":
                birth_idx = i
                break
        assert birth_idx is not None
        combo.setCurrentIndex(birth_idx)
        assert not editor._end_event_label.isHidden()
        assert "boendets andra endpunkt" in editor._end_event_label.text()

    def test_no_wrong_side_for_flytt(self, qapp, project_with_events):
        """Flytt event on either endpoint shows no wrong-side warning."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        # Flytt on start
        combo = editor._start_event_combo
        flytt_idx = None
        for i in range(combo.count()):
            if combo.itemData(i) == "evt_flytt":
                flytt_idx = i
                break
        assert flytt_idx is not None
        combo.setCurrentIndex(flytt_idx)
        # Should not have the wrong-side message
        label_text = editor._start_event_label.text()
        assert "boendets andra endpunkt" not in label_text

        # Flytt on end
        editor2 = ResidenceEditor(project_with_events, person_id="p1")
        combo2 = editor2._end_event_combo
        flytt_idx2 = None
        for i in range(combo2.count()):
            if combo2.itemData(i) == "evt_flytt":
                flytt_idx2 = i
                break
        combo2.setCurrentIndex(flytt_idx2)
        label_text2 = editor2._end_event_label.text()
        assert "boendets andra endpunkt" not in label_text2

    def test_loads_event_link_from_residence(self, qapp, project_with_events, residence_with_event):
        """Loading a residence with an event_id selects it in the combo."""
        editor = ResidenceEditor(project_with_events, residence=residence_with_event)
        assert editor.start_event_id == "evt_birth"
        # The combo should be set to the birth event
        selected_data = editor._start_event_combo.currentData()
        assert selected_data == "evt_birth"

    def test_event_label_shown_when_linked(self, qapp, project_with_events, residence_with_event):
        """The linked event label is displayed when no warning applies."""
        editor = ResidenceEditor(project_with_events, residence=residence_with_event)
        # Start is linked to birth, and bounds match — should show the label
        assert not editor._start_event_label.isHidden()
        assert "Födelse (1820-03-15)" in editor._start_event_label.text()

    def test_flytt_event_labelled_correctly(self, qapp, project_with_events):
        """A Flytt event is labelled with 'Flytt (date)'."""
        editor = ResidenceEditor(project_with_events, person_id="p1")
        combo = editor._start_event_combo
        for i in range(combo.count()):
            if combo.itemData(i) == "evt_flytt":
                assert combo.itemText(i) == "Flytt (1860-06)"
                break
        else:
            pytest.fail("Flytt event not found in combo")
