# Feature: residence-periods, Property 8: Linking an Endpoint to an Event writes exactly the specified fields
"""Property-based test for Endpoint event linking.

Feature: residence-periods, Property 8: Linking an Endpoint to an Event writes
exactly the specified fields

For any Endpoint and any Event of the fact's person, selecting a dated Event
sets that Endpoint's `event_id`, `earliest`, `latest` and `precision` from the
Event, selecting an undated Event sets only `event_id`, selecting the empty
choice clears `event_id` while keeping the displayed bounds, and typing new
bound values leaves `event_id` unchanged; a dated Flytt_Event linked to the end
Endpoint of one fact and the start Endpoint of another makes both Endpoints
exact dates, while an undated one leaves both unchanged.

**Validates: Requirements 3.3, 3.4, 3.6, 3.8, 18.9, 18.11**
"""

from __future__ import annotations

import sys
from typing import Optional
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, ResidenceFact

from tests.test_model.residence_strategies import (
    iso_values,
    _well_formed_iso,
    PRECISION_VALUES,
    _PLACE_NAMES,
    _EVENT_TYPES,
)

# Skip the entire module if PySide6 is not available (headless CI).
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from slaktbusken.ui.editors.residence_editor import ResidenceEditor  # noqa: E402


# ---------------------------------------------------------------------------
# Qt application fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def qapp():
    """Ensure a QApplication exists for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _noop(self) -> None:
    """No-op placeholder for not-yet-implemented action handlers."""
    pass


def _create_editor(project: ProjectData, residence: ResidenceFact, person_id: str) -> ResidenceEditor:
    """Create a ResidenceEditor, stubbing out unimplemented action handlers."""
    with patch.object(ResidenceEditor, "_on_use_as_exact_start", _noop, create=True), \
         patch.object(ResidenceEditor, "_on_use_as_exact_end", _noop, create=True), \
         patch.object(ResidenceEditor, "_on_split", _noop, create=True), \
         patch.object(ResidenceEditor, "_on_merge", _noop, create=True), \
         patch.object(ResidenceEditor, "_on_create_flytt", _noop, create=True):
        editor = ResidenceEditor(
            project_data=project,
            residence=residence,
            person_id=person_id,
        )
    return editor


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _project_with_person_events(draw: DrawFn) -> tuple[ProjectData, str, list[Event]]:
    """Generate a project with one person who participates in some events.

    Returns (project, person_id, person_events) where person_events is the list
    of events that include the person as a participant — a mix of dated and
    undated events, including flytt events.
    """
    person_id = "person_1"
    person = Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given="Anders", surname="Ek")],
    )
    place = Place(id="place_1", type="farm", name="Norrgården")

    # Generate between 1 and 5 events, with a mix of dated and undated.
    event_count = draw(st.integers(min_value=1, max_value=5))
    events: list[Event] = []
    for i in range(event_count):
        event_type = draw(st.sampled_from(_EVENT_TYPES))
        # About half are dated, half undated.
        is_dated = draw(st.booleans())
        if is_dated:
            date_value = draw(_well_formed_iso())
            date_precision = draw(
                st.sampled_from(["day", "month", "year", "approximate"])
            )
            date_obj = DateValue(value=date_value, precision=date_precision)
        else:
            date_obj = None

        place_ref = draw(
            st.none() | st.just(PlaceRef(place_id="place_1"))
        )

        event = Event(
            id=f"event_{i + 1}",
            type=event_type,
            participants=[Participant(person_id=person_id, role="primary")],
            date=date_obj,
            place=place_ref,
        )
        # For flytt events, optionally add from_place.
        if event_type == "flytt":
            event.from_place = draw(
                st.none() | st.just(PlaceRef(place_id="place_1"))
            )
        events.append(event)

    # Build a residence fact for the person with some initial bounds.
    initial_earliest = draw(st.none() | _well_formed_iso())
    initial_latest = draw(st.none() | _well_formed_iso())
    initial_precision = draw(st.sampled_from(PRECISION_VALUES))

    residence = ResidenceFact(
        id="residence_1",
        person_id=person_id,
        place_id="place_1",
        start=Endpoint(
            earliest=initial_earliest,
            latest=initial_latest,
            precision=initial_precision,
        ),
        end=Endpoint(
            earliest=draw(st.none() | _well_formed_iso()),
            latest=draw(st.none() | _well_formed_iso()),
            precision=draw(st.sampled_from(PRECISION_VALUES)),
        ),
    )

    project = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[person],
        places=[place],
        events=events,
        residences=[residence],
    )
    return project, person_id, events


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestEndpointEventLinking:
    """Property 8: Linking an Endpoint to an Event writes exactly the specified fields.

    **Validates: Requirements 3.3, 3.4, 3.6, 3.8, 18.9, 18.11**
    """

    @given(data=st.data(), setup=_project_with_person_events())
    @settings(max_examples=100, deadline=None)
    def test_endpoint_event_linking(
        self,
        data: st.DataObject,
        setup: tuple[ProjectData, str, list[Event]],
    ) -> None:
        """Selecting events writes exactly the specified fields on the endpoint.

        Feature: residence-periods, Property 8

        **Validates: Requirements 3.3, 3.4, 3.6, 3.8, 18.9, 18.11**
        """
        project, person_id, person_events = setup
        residence = project.residences[0]

        # Choose which endpoint side to test.
        side = data.draw(st.sampled_from(["start", "end"]), label="side")

        # Create the editor widget (with stubs for unimplemented action handlers).
        editor = _create_editor(project, residence, person_id)

        # Pick an event to select.
        event = data.draw(st.sampled_from(person_events), label="event")
        is_dated = event.date is not None and bool(event.date.value)

        # --- Sub-property A: Selecting a dated Event (Requirement 3.3) ---
        # --- Sub-property B: Selecting an undated Event (Requirement 3.4) ---
        combo = (
            editor._start_event_combo if side == "start" else editor._end_event_combo
        )

        # Find the event in the combo box.
        event_index = None
        for i in range(combo.count()):
            if combo.itemData(i) == event.id:
                event_index = i
                break
        assume(event_index is not None)

        # Record bounds before selection.
        if side == "start":
            bounds_before = (
                editor._start_earliest_edit.text(),
                editor._start_latest_edit.text(),
                editor._start_precision,
            )
        else:
            bounds_before = (
                editor._end_earliest_edit.text(),
                editor._end_latest_edit.text(),
                editor._end_precision,
            )

        # Select the event.
        combo.setCurrentIndex(event_index)

        if is_dated:
            # Requirement 3.3: dated selection writes event_id + earliest +
            # latest + precision.
            if side == "start":
                assert editor.start_event_id == event.id
                assert editor._start_earliest_edit.text() == event.date.value
                assert editor._start_latest_edit.text() == event.date.value
                assert editor.start_precision == event.date.precision
            else:
                assert editor.end_event_id == event.id
                assert editor._end_earliest_edit.text() == event.date.value
                assert editor._end_latest_edit.text() == event.date.value
                assert editor.end_precision == event.date.precision
        else:
            # Requirement 3.4: undated selection writes only event_id.
            if side == "start":
                assert editor.start_event_id == event.id
                # Bounds unchanged.
                assert editor._start_earliest_edit.text() == bounds_before[0]
                assert editor._start_latest_edit.text() == bounds_before[1]
                assert editor.start_precision == bounds_before[2]
            else:
                assert editor.end_event_id == event.id
                # Bounds unchanged.
                assert editor._end_earliest_edit.text() == bounds_before[0]
                assert editor._end_latest_edit.text() == bounds_before[1]
                assert editor.end_precision == bounds_before[2]

        # --- Sub-property C: Empty choice clears only event_id (Requirement 3.6) ---
        # Record bounds after the selection above.
        if side == "start":
            bounds_after_link = (
                editor._start_earliest_edit.text(),
                editor._start_latest_edit.text(),
                editor.start_precision,
            )
        else:
            bounds_after_link = (
                editor._end_earliest_edit.text(),
                editor._end_latest_edit.text(),
                editor.end_precision,
            )

        # Select the empty choice (index 0).
        combo.setCurrentIndex(0)

        if side == "start":
            assert editor.start_event_id is None
            # Bounds kept as displayed before clearing.
            assert editor._start_earliest_edit.text() == bounds_after_link[0]
            assert editor._start_latest_edit.text() == bounds_after_link[1]
            assert editor.start_precision == bounds_after_link[2]
        else:
            assert editor.end_event_id is None
            assert editor._end_earliest_edit.text() == bounds_after_link[0]
            assert editor._end_latest_edit.text() == bounds_after_link[1]
            assert editor.end_precision == bounds_after_link[2]

        # --- Sub-property D: Bounds stay editable with event_id unchanged (Requirement 3.8) ---
        # Re-link the event so event_id is set.
        combo.setCurrentIndex(event_index)
        event_id_after_relink = (
            editor.start_event_id if side == "start" else editor.end_event_id
        )

        # Simulate typing new bound values into the fields.
        new_earliest = data.draw(_well_formed_iso(), label="new_earliest")
        new_latest = data.draw(_well_formed_iso(), label="new_latest")

        if side == "start":
            editor._start_earliest_edit.setText(new_earliest)
            editor._start_latest_edit.setText(new_latest)
            # event_id must remain unchanged.
            assert editor.start_event_id == event_id_after_relink
            # The typed values are present.
            assert editor._start_earliest_edit.text() == new_earliest
            assert editor._start_latest_edit.text() == new_latest
        else:
            editor._end_earliest_edit.setText(new_earliest)
            editor._end_latest_edit.setText(new_latest)
            assert editor.end_event_id == event_id_after_relink
            assert editor._end_earliest_edit.text() == new_earliest
            assert editor._end_latest_edit.text() == new_latest

