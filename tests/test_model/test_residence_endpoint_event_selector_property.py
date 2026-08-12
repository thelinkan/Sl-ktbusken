# Feature: residence-periods, Property 9: The Endpoint Event selector lists, labels and advises correctly
"""Property-based test for the Endpoint Event selector.

Feature: residence-periods, Property 9: The Endpoint Event selector lists,
labels and advises correctly

For any person with zero or more Events, the Endpoint Event selector lists an
empty first choice followed by the person's Events ordered by date ascending
with undated last; each label is "{Swedish event type label} ({formatted date})"
for dated Events or just the Swedish event type label for undated Events; a
death Event on the start Endpoint or a birth Event on the end Endpoint shows the
wrong-side message; and a Flytt_Event on either side produces no such message.

**Validates: Requirements 3.1, 3.2, 3.7, 3.9**
"""

from __future__ import annotations

import sys
from typing import Optional

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
    _well_formed_iso,
    _EVENT_TYPES,
    _PLACE_NAMES,
    PRECISION_VALUES,
)

# Skip the entire module if PySide6 is not available (headless CI).
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from slaktbusken.ui.editors.residence_editor import (  # noqa: E402
    ResidenceEditor,
    _sort_events_for_selector,
    _build_event_label,
)
from slaktbusken.ui.swedish_locale import (  # noqa: E402
    format_date,
    get_event_type_label,
)


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


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _person_with_events(draw: DrawFn) -> tuple[ProjectData, str, list[Event]]:
    """Generate a project with one person who participates in a mix of events.

    Returns (project, person_id, person_events) where person_events includes
    dated and undated events across various event types. The events list may
    be empty (testing Requirement 3.1 zero-events case).
    """
    person_id = "person_1"
    person = Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given="Anders", surname="Ek")],
    )
    place = Place(id="place_1", type="farm", name="Norrgården")

    # Generate 0–6 events for the person (including 0 to test empty selector).
    event_count = draw(st.integers(min_value=0, max_value=6))
    events: list[Event] = []
    for i in range(event_count):
        event_type = draw(st.sampled_from(_EVENT_TYPES))
        is_dated = draw(st.booleans())
        if is_dated:
            date_value = draw(_well_formed_iso())
            date_precision = draw(
                st.sampled_from(["day", "month", "year", "approximate"])
            )
            date_obj = DateValue(value=date_value, precision=date_precision)
        else:
            date_obj = None

        place_ref = draw(st.none() | st.just(PlaceRef(place_id="place_1")))

        event = Event(
            id=f"event_{i + 1}",
            type=event_type,
            participants=[Participant(person_id=person_id, role="primary")],
            date=date_obj,
            place=place_ref,
        )
        if event_type == "flytt":
            event.from_place = draw(
                st.none() | st.just(PlaceRef(place_id="place_1"))
            )
        events.append(event)

    # Optionally add events for a different person (should not appear in selector).
    other_count = draw(st.integers(min_value=0, max_value=2))
    other_events: list[Event] = []
    for i in range(other_count):
        other_events.append(
            Event(
                id=f"other_event_{i + 1}",
                type=draw(st.sampled_from(_EVENT_TYPES)),
                participants=[Participant(person_id="person_2", role="primary")],
                date=DateValue(value="1850", precision="year"),
            )
        )

    residence = ResidenceFact(
        id="residence_1",
        person_id=person_id,
        place_id="place_1",
        start=Endpoint(),
        end=Endpoint(),
    )

    project = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[
            person,
            Person(
                id="person_2",
                sex="F",
                names=[Name(type="birth", given="Brita", surname="Persdotter")],
            ),
        ],
        places=[place],
        events=events + other_events,
        residences=[residence],
    )
    return project, person_id, events


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestEndpointEventSelector:
    """Property 9: The Endpoint Event selector lists, labels and advises correctly.

    **Validates: Requirements 3.1, 3.2, 3.7, 3.9**
    """

    @given(data=st.data(), setup=_person_with_events())
    @settings(max_examples=100, deadline=None)
    def test_endpoint_event_selector(
        self,
        data: st.DataObject,
        setup: tuple[ProjectData, str, list[Event]],
    ) -> None:
        """The selector lists, labels and advises correctly.

        Feature: residence-periods, Property 9

        **Validates: Requirements 3.1, 3.2, 3.7, 3.9**
        """
        project, person_id, person_events = setup
        residence = project.residences[0]

        editor = ResidenceEditor(
            project_data=project,
            residence=residence,
            person_id=person_id,
        )

        # Test both start and end combos.
        side = data.draw(st.sampled_from(["start", "end"]), label="side")
        combo = (
            editor._start_event_combo if side == "start" else editor._end_event_combo
        )

        # --- Sub-property A: Empty first choice (Requirement 3.1) ---
        # The first item must be the empty choice regardless of event count.
        assert combo.itemText(0) == ""
        assert combo.itemData(0) is None

        # --- Sub-property B: Only the person's events listed, in order ---
        # (Requirement 3.1)
        combo_event_ids = [
            combo.itemData(i) for i in range(1, combo.count())
        ]
        person_event_ids = [e.id for e in person_events]

        # Only person's events appear (no other_event_* ids).
        for eid in combo_event_ids:
            assert eid in person_event_ids

        # All person's events appear.
        for eid in person_event_ids:
            assert eid in combo_event_ids

        # Count: empty choice + person events.
        assert combo.count() == 1 + len(person_events)

        # Order: dated by date ascending, undated last (Requirement 3.1).
        expected_sorted = _sort_events_for_selector(person_events)
        expected_ids = [e.id for e in expected_sorted]
        assert combo_event_ids == expected_ids

        # --- Sub-property C: Labels (Requirement 3.2) ---
        for i in range(1, combo.count()):
            event_id = combo.itemData(i)
            event = next(e for e in person_events if e.id == event_id)
            expected_label = _build_event_label(event)

            # Verify the label matches the specification:
            # "{Swedish event type label} ({formatted date})" for dated,
            # just the Swedish event type label for undated.
            type_label = get_event_type_label(event.type)
            if event.date and event.date.value:
                formatted = format_date(event.date.value)
                assert expected_label == f"{type_label} ({formatted})"
            else:
                assert expected_label == type_label

            # The actual combo text must equal the expected label.
            assert combo.itemText(i) == expected_label

        # --- Sub-property D: Wrong-side advice (Requirement 3.9) ---
        # Death on start shows the wrong-side message.
        # Birth on end shows the wrong-side message.
        # Flytt on either side does NOT show the wrong-side message.
        if person_events:
            event_to_test = data.draw(
                st.sampled_from(person_events), label="advice_event"
            )

            # Find the event's index in the combo.
            test_idx = None
            for i in range(combo.count()):
                if combo.itemData(i) == event_to_test.id:
                    test_idx = i
                    break
            assume(test_idx is not None)

            combo.setCurrentIndex(test_idx)

            # Get the message label for this side.
            msg_label = (
                editor._start_event_label
                if side == "start"
                else editor._end_event_label
            )

            wrong_side_msg = (
                "Vald händelse hör normalt till boendets andra endpunkt"
                " – kontrollera kopplingen."
            )

            if event_to_test.type == "flytt":
                # Requirement 3.9: no wrong-side message for flytt.
                if not msg_label.isHidden():
                    assert wrong_side_msg not in msg_label.text()
            elif side == "start" and event_to_test.type == "death":
                # Death on start → wrong-side message.
                assert not msg_label.isHidden()
                assert wrong_side_msg in msg_label.text()
            elif side == "end" and event_to_test.type == "birth":
                # Birth on end → wrong-side message.
                assert not msg_label.isHidden()
                assert wrong_side_msg in msg_label.text()
            else:
                # Other combinations: no wrong-side message.
                if not msg_label.isHidden():
                    assert wrong_side_msg not in msg_label.text()
