# Feature: residence-periods, Property 37: Flytt places are cited independently, checked for consistency, and linkable in one action
"""Property-based test for Flytt place citation, consistency and linking.

Feature: residence-periods, Property 37: Flytt places are cited independently,
checked for consistency, and linkable in one action

For any Flytt_Event, from_place and place carry independent source_refs; the
same-place warning is reported only when from_place.place_id == place.place_id
and both are present; flytt_link_findings reports a mismatch when a linked
endpoint's residence has a different place; and the create-flytt action in the
editor links both endpoints.

**Validates: Requirements 18.4, 18.7, 18.10, 18.12**
"""

from __future__ import annotations

import copy
import sys
from typing import Optional
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.validators import event_findings
from slaktbusken.services.residence_validation import flytt_link_findings

from tests.test_model.residence_strategies import (
    _well_formed_iso,
    PRECISION_VALUES,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MSG_FLYTT_SAME_PLACE = (
    "Flytten har samma plats som både från och till – kontrollera uppgifterna."
)

_MSG_FLYTT_LINK_MISMATCH = (
    "Flyttens platser stämmer inte med de kopplade boendena."
)

_PLACE_IDS = ("place_1", "place_2", "place_3")
_PLACE_NAMES_LOCAL = ("Norrgården", "Sörgården", "Åby")


def _noop(self) -> None:
    """No-op placeholder for action handlers not under test."""
    pass


def _create_editor(
    project: ProjectData, residence: ResidenceFact, person_id: str
) -> ResidenceEditor:
    """Create a ResidenceEditor, stubbing out unrelated action handlers."""
    with (
        patch.object(ResidenceEditor, "_on_use_as_exact_start", _noop, create=True),
        patch.object(ResidenceEditor, "_on_use_as_exact_end", _noop, create=True),
        patch.object(ResidenceEditor, "_on_split", _noop, create=True),
        patch.object(ResidenceEditor, "_on_merge", _noop, create=True),
        patch.object(ResidenceEditor, "_on_bulk_plan", _noop, create=True),
        patch.object(ResidenceEditor, "_on_bulk_execute", _noop, create=True),
    ):
        editor = ResidenceEditor(
            project_data=project,
            residence=residence,
            person_id=person_id,
        )
    return editor


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


@st.composite
def _flytt_place_scenario(draw: DrawFn):
    """Generate a complete scenario covering all four sub-properties of Property 37.

    Returns a dict with keys for each sub-property's inputs:
    - flytt_event: a Flytt event with from_place/place drawn from a small pool
    - linked_project: a project with linked residences for flytt_link_findings
    - create_project: a project with adjacent residences for create-flytt action
    """
    places = [
        Place(id=pid, type="farm", name=name)
        for pid, name in zip(_PLACE_IDS, _PLACE_NAMES_LOCAL)
    ]
    person = Person(
        id="person_1",
        sex="M",
        names=[Name(type="birth", given="Anders", surname="Ek")],
    )

    # --- Data for sub-property A & B: independent citation and same-place warning ---
    has_from = draw(st.booleans())
    has_to = draw(st.booleans())

    from_place: Optional[PlaceRef] = None
    to_place: Optional[PlaceRef] = None
    from_place_id: Optional[str] = None
    to_place_id: Optional[str] = None

    if has_from:
        from_place_id = draw(st.sampled_from(_PLACE_IDS))
        from_refs = [
            SourceRef(source_id=f"src_from_{i}", quality="primary", note="", aspects=[])
            for i in range(draw(st.integers(min_value=0, max_value=2)))
        ]
        from_place = PlaceRef(place_id=from_place_id, source_refs=from_refs)

    if has_to:
        to_place_id = draw(st.sampled_from(_PLACE_IDS))
        to_refs = [
            SourceRef(source_id=f"src_to_{i}", quality="primary", note="", aspects=[])
            for i in range(draw(st.integers(min_value=0, max_value=2)))
        ]
        to_place = PlaceRef(place_id=to_place_id, source_refs=to_refs)

    flytt_event = Event(
        id="flytt_1",
        type="flytt",
        participants=[Participant(person_id="person_1", role="subject")],
        date=None,
        place=to_place,
        from_place=from_place,
    )

    # --- Data for sub-property C: flytt_link_findings mismatch ---
    linked_from_place_id = draw(st.sampled_from(_PLACE_IDS))
    linked_to_place_id = draw(st.sampled_from(_PLACE_IDS))
    earlier_residence_place_id = draw(st.sampled_from(_PLACE_IDS))
    later_residence_place_id = draw(st.sampled_from(_PLACE_IDS))

    link_date = draw(_well_formed_iso(min_year=1830, max_year=1870))

    linked_flytt = Event(
        id="flytt_linked",
        type="flytt",
        participants=[Participant(person_id="person_1", role="subject")],
        date=DateValue(value=link_date, precision="year"),
        place=PlaceRef(place_id=linked_to_place_id),
        from_place=PlaceRef(place_id=linked_from_place_id),
    )

    earlier_fact = ResidenceFact(
        id="residence_1",
        person_id="person_1",
        place_id=earlier_residence_place_id,
        start=Endpoint(earliest="1820", latest="1820"),
        end=Endpoint(earliest=link_date, latest=link_date, event_id="flytt_linked"),
    )
    later_fact = ResidenceFact(
        id="residence_2",
        person_id="person_1",
        place_id=later_residence_place_id,
        start=Endpoint(earliest=link_date, latest=link_date, event_id="flytt_linked"),
        end=Endpoint(earliest="1890", latest="1890"),
    )

    linked_project = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[person],
        places=places,
        events=[linked_flytt],
        residences=[earlier_fact, later_fact],
    )

    # --- Data for sub-property D: create-flytt action ---
    boundary_year = draw(st.integers(min_value=1800, max_value=1890))

    create_earlier = ResidenceFact(
        id="residence_c1",
        person_id="person_1",
        place_id="place_1",
        start=Endpoint(
            earliest=f"{boundary_year - 10}", latest=f"{boundary_year - 10}"
        ),
        end=Endpoint(earliest=f"{boundary_year}", latest=f"{boundary_year}"),
    )
    create_later = ResidenceFact(
        id="residence_c2",
        person_id="person_1",
        place_id="place_2",
        start=Endpoint(earliest=f"{boundary_year}", latest=f"{boundary_year}"),
        end=Endpoint(
            earliest=f"{boundary_year + 10}", latest=f"{boundary_year + 10}"
        ),
    )

    create_project = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[person],
        places=places,
        events=[],
        residences=[create_earlier, create_later],
    )

    return {
        "flytt_event": flytt_event,
        "linked_project": linked_project,
        "earlier_fact": earlier_fact,
        "later_fact": later_fact,
        "linked_from_place_id": linked_from_place_id,
        "linked_to_place_id": linked_to_place_id,
        "earlier_residence_place_id": earlier_residence_place_id,
        "later_residence_place_id": later_residence_place_id,
        "create_project": create_project,
        "create_earlier": create_earlier,
        "create_later": create_later,
    }


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestFlyttPlaceCitationConsistencyLinking:
    """Property 37: Flytt places are cited independently, checked for
    consistency, and linkable in one action.

    **Validates: Requirements 18.4, 18.7, 18.10, 18.12**
    """

    @given(scenario=_flytt_place_scenario())
    @settings(max_examples=100, deadline=None)
    def test_flytt_place_citation_consistency_and_linking(
        self,
        scenario,
    ) -> None:
        """Flytt places carry independent citations, the same-place warning
        fires only when both are present with equal place_id, flytt_link_findings
        reports mismatches for linked residences, and create-flytt links both
        endpoints.

        **Validates: Requirements 18.4, 18.7, 18.10, 18.12**
        """
        flytt_event = scenario["flytt_event"]

        # --- Sub-property A: Independent source_refs (Requirement 18.4) ---
        if flytt_event.from_place is not None and flytt_event.place is not None:
            # Mutating from_place.source_refs does not affect place.source_refs.
            original_to_refs = list(flytt_event.place.source_refs)
            original_from_refs = list(flytt_event.from_place.source_refs)

            flytt_event.from_place.source_refs.append(
                SourceRef(source_id="extra", quality="primary", note="", aspects=[])
            )
            assert flytt_event.place.source_refs == original_to_refs

            flytt_event.from_place.source_refs.pop()
            flytt_event.place.source_refs.append(
                SourceRef(source_id="extra2", quality="primary", note="", aspects=[])
            )
            assert flytt_event.from_place.source_refs == original_from_refs
            flytt_event.place.source_refs.pop()

        # --- Sub-property B: Same-place warning (Requirement 18.7) ---
        findings = event_findings(flytt_event)
        same_place_findings = [
            f for f in findings if f.message == _MSG_FLYTT_SAME_PLACE
        ]

        both_present = (
            flytt_event.from_place is not None and flytt_event.place is not None
        )
        same_place = (
            both_present
            and flytt_event.from_place.place_id == flytt_event.place.place_id
        )

        if same_place:
            assert len(same_place_findings) == 1
        else:
            assert len(same_place_findings) == 0

        # --- Sub-property C: flytt_link_findings mismatch (Requirement 18.10) ---
        linked_project = scenario["linked_project"]
        earlier_fact = scenario["earlier_fact"]
        later_fact = scenario["later_fact"]
        linked_from_place_id = scenario["linked_from_place_id"]
        linked_to_place_id = scenario["linked_to_place_id"]
        earlier_residence_place_id = scenario["earlier_residence_place_id"]
        later_residence_place_id = scenario["later_residence_place_id"]

        link_findings = flytt_link_findings(linked_project)
        mismatch_findings = [
            f for f in link_findings if f.message == _MSG_FLYTT_LINK_MISMATCH
        ]

        # End-linked residence (earlier) mismatches when its place != from_place.
        earlier_mismatches = [
            f for f in mismatch_findings if f.residence_id == earlier_fact.id
        ]
        expect_earlier_mismatch = earlier_residence_place_id != linked_from_place_id
        if expect_earlier_mismatch:
            assert len(earlier_mismatches) == 1
        else:
            assert len(earlier_mismatches) == 0

        # Start-linked residence (later) mismatches when its place != place.
        later_mismatches = [
            f for f in mismatch_findings if f.residence_id == later_fact.id
        ]
        expect_later_mismatch = later_residence_place_id != linked_to_place_id
        if expect_later_mismatch:
            assert len(later_mismatches) == 1
        else:
            assert len(later_mismatches) == 0

        # --- Sub-property D: Create-flytt action (Requirement 18.12) ---
        create_project = scenario["create_project"]
        create_earlier = scenario["create_earlier"]

        editor = _create_editor(create_project, create_earlier, "person_1")
        editor._on_create_flytt()

        # A new flytt event should have been added.
        flytt_events = [e for e in create_project.events if e.type == "flytt"]
        assert len(flytt_events) == 1
        new_flytt = flytt_events[0]

        # Prefilled from_place from earlier (place_1) and place from later (place_2).
        assert new_flytt.from_place is not None
        assert new_flytt.from_place.place_id == "place_1"
        assert new_flytt.place is not None
        assert new_flytt.place.place_id == "place_2"

        # Both residences now linked to the flytt.
        updated_earlier = next(
            f for f in create_project.residences if f.id == create_earlier.id
        )
        updated_later = next(
            f for f in create_project.residences if f.id == "residence_c2"
        )

        assert updated_earlier.end.event_id == new_flytt.id
        assert updated_later.start.event_id == new_flytt.id

        # If the flytt has a date, both endpoints carry that date.
        if new_flytt.date is not None and new_flytt.date.value:
            assert updated_earlier.end.earliest == new_flytt.date.value
            assert updated_earlier.end.latest == new_flytt.date.value
            assert updated_later.start.earliest == new_flytt.date.value
            assert updated_later.start.latest == new_flytt.date.value
