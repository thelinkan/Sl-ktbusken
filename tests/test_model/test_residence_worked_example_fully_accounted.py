"""Unit tests for the fully accounted sequence worked example (Requirement 14).

Anders is recorded at Place A until 1840 and at Place B from 1840 until his
death in 1846. His adult life has no unexplained gaps. The two facts touch at
the boundary year 1840 — this counts as touching, not overlapping.

Data setup (Requirements 14.1, 14.2):
  - Place A fact: start(latest="1837", earliest=None), end(earliest="1840", latest="1840")
  - Place B fact: start(earliest="1840", latest="1840"), end(earliest="1846", latest="1846", event_id→death)
"""

from __future__ import annotations

from datetime import date

import pytest

from slaktbusken.model import (
    Endpoint,
    Observation,
    ProjectData,
    ResidenceFact,
)
from slaktbusken.model.date_span import DaySpan, OpenSpan
from slaktbusken.model.event import DateValue, Event, Participant, SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.residence import (
    EndpointKind,
    certain_core,
    classify_endpoint,
    possible_span,
)
from slaktbusken.model.validators import validate_residence
from slaktbusken.services.residence_coverage import (
    open_endpoint_suggestions,
    timeline_gaps,
)
from slaktbusken.services.residence_query import (
    residence_timeline,
    residents_of_place,
)
from slaktbusken.services.residence_validation import overlap_findings
from slaktbusken.ui.swedish_locale import format_residence_interval


# ---------------------------------------------------------------------------
# Fixture: the "Anders" project
# ---------------------------------------------------------------------------


@pytest.fixture()
def anders_project() -> ProjectData:
    """Build the fully accounted sequence project as specified in Requirement 14."""
    person = Person(id="person_1", sex="M", names=[Name("birth", "Anders", "Andersson")])
    place_a = Place(id="place_a", type="farm", name="Gård A")
    place_b = Place(id="place_b", type="farm", name="Gård B")

    death_event = Event(
        id="event_death",
        type="death",
        participants=[Participant(person_id="person_1", role="primary")],
        date=DateValue(value="1846", precision="year"),
    )

    # Place A: start.latest=1837, no start.earliest; end: 1840/1840
    fact_a = ResidenceFact(
        id="residence_a",
        person_id="person_1",
        place_id="place_a",
        start=Endpoint(earliest=None, latest="1837"),
        end=Endpoint(earliest="1840", latest="1840"),
    )

    # Place B: start 1840/1840; end 1846/1846, linked to death event
    fact_b = ResidenceFact(
        id="residence_b",
        person_id="person_1",
        place_id="place_b",
        start=Endpoint(earliest="1840", latest="1840"),
        end=Endpoint(earliest="1846", latest="1846", event_id="event_death"),
    )

    data = ProjectData()
    data.persons.append(person)
    data.places.extend([place_a, place_b])
    data.events.append(death_event)
    data.residences.extend([fact_a, fact_b])
    return data


# ---------------------------------------------------------------------------
# 14.1 — Derivations for Place A fact
# ---------------------------------------------------------------------------


class TestPlaceADerivations:
    """Requirement 14.1: Place A fact validates clean, core 1837–1840, span unbounded–1840."""

    def test_validates_clean(self, anders_project: ProjectData) -> None:
        fact_a = anders_project.residences[0]
        errors = validate_residence(
            fact_a,
            valid_person_ids={"person_1"},
            valid_place_ids={"place_a", "place_b"},
            valid_source_ids=set(),
            valid_event_ids={"event_death"},
        )
        assert errors == []

    def test_start_is_open_latest(self, anders_project: ProjectData) -> None:
        fact_a = anders_project.residences[0]
        assert classify_endpoint(fact_a.start) == EndpointKind.OPEN_LATEST

    def test_end_is_exact(self, anders_project: ProjectData) -> None:
        fact_a = anders_project.residences[0]
        assert classify_endpoint(fact_a.end) == EndpointKind.EXACT

    def test_certain_core_is_1837_through_1840(self, anders_project: ProjectData) -> None:
        """Core: from last day of start.latest (1837-12-31) through first day of end.earliest (1840-01-01)."""
        fact_a = anders_project.residences[0]
        core = certain_core(fact_a)
        assert core is not None
        assert core == DaySpan(date(1837, 12, 31), date(1840, 1, 1))

    def test_possible_span_unbounded_through_1840(self, anders_project: ProjectData) -> None:
        """Possible_Span: start.earliest absent → first is None; end.latest 1840 → last day of 1840."""
        fact_a = anders_project.residences[0]
        span = possible_span(fact_a)
        assert span.first is None
        assert span.last == date(1840, 12, 31)


# ---------------------------------------------------------------------------
# 14.2 — Derivations for Place B fact
# ---------------------------------------------------------------------------


class TestPlaceBDerivations:
    """Requirement 14.2: Place B fact validates clean, core and span are both 1840–1846."""

    def test_validates_clean(self, anders_project: ProjectData) -> None:
        fact_b = anders_project.residences[1]
        errors = validate_residence(
            fact_b,
            valid_person_ids={"person_1"},
            valid_place_ids={"place_a", "place_b"},
            valid_source_ids=set(),
            valid_event_ids={"event_death"},
        )
        assert errors == []

    def test_start_is_exact(self, anders_project: ProjectData) -> None:
        fact_b = anders_project.residences[1]
        assert classify_endpoint(fact_b.start) == EndpointKind.EXACT

    def test_end_is_exact(self, anders_project: ProjectData) -> None:
        fact_b = anders_project.residences[1]
        assert classify_endpoint(fact_b.end) == EndpointKind.EXACT

    def test_certain_core_is_1840_through_1846(self, anders_project: ProjectData) -> None:
        """Core: from last day of start.latest (1840-12-31) through first day of end.earliest (1846-01-01)."""
        fact_b = anders_project.residences[1]
        core = certain_core(fact_b)
        assert core is not None
        assert core == DaySpan(date(1840, 12, 31), date(1846, 1, 1))

    def test_possible_span_is_1840_through_1846(self, anders_project: ProjectData) -> None:
        """Span: start.earliest 1840 → first day; end.latest 1846 → last day."""
        fact_b = anders_project.residences[1]
        span = possible_span(fact_b)
        assert span.first == date(1840, 1, 1)
        assert span.last == date(1846, 12, 31)


# ---------------------------------------------------------------------------
# 14.3 — Zero timeline gaps
# ---------------------------------------------------------------------------


class TestZeroTimelineGaps:
    """Requirement 14.3: The boundary year 1840 counts as touching, not a gap."""

    def test_no_timeline_gaps(self, anders_project: ProjectData) -> None:
        gaps = timeline_gaps("person_1", anders_project)
        assert gaps == []


# ---------------------------------------------------------------------------
# 14.4 — Zero overlap findings
# ---------------------------------------------------------------------------


class TestZeroOverlapFindings:
    """Requirement 14.4: Shared boundary year 1840 counts as touching, not overlapping."""

    def test_no_overlap_findings(self, anders_project: ProjectData) -> None:
        findings = overlap_findings("person_1", anders_project)
        assert findings == []


# ---------------------------------------------------------------------------
# 14.5 — Open-endpoint suggestions
# ---------------------------------------------------------------------------


class TestOpenEndpointSuggestions:
    """Requirement 14.5: Exactly one suggestion for Place A start, none for the others."""

    def test_place_a_has_one_open_start_suggestion(self, anders_project: ProjectData) -> None:
        fact_a = anders_project.residences[0]
        suggestions = open_endpoint_suggestions(fact_a)
        assert len(suggestions) == 1
        assert suggestions[0].side == "start"
        assert suggestions[0].residence_id == "residence_a"

    def test_place_a_end_has_no_suggestion(self, anders_project: ProjectData) -> None:
        """Place A end: both bounds present (exact) → no open endpoint."""
        fact_a = anders_project.residences[0]
        suggestions = open_endpoint_suggestions(fact_a)
        # Only one suggestion, for the start side
        assert all(s.side == "start" for s in suggestions)

    def test_place_b_has_no_open_endpoint_suggestions(self, anders_project: ProjectData) -> None:
        fact_b = anders_project.residences[1]
        suggestions = open_endpoint_suggestions(fact_b)
        assert suggestions == []


# ---------------------------------------------------------------------------
# 14.6 — Place A rendered interval
# ---------------------------------------------------------------------------


class TestRenderedStrings:
    """Requirements 14.6, 14.7: The formatted intervals match the spec."""

    def test_place_a_interval_is_senast_1837_dash_1840(self, anders_project: ProjectData) -> None:
        """Requirement 14.6: Place A renders as 'senast 1837–1840'."""
        fact_a = anders_project.residences[0]
        rendered = format_residence_interval(fact_a.start, fact_a.end)
        assert rendered == "senast 1837\u20131840"

    def test_place_b_interval_is_1840_dash_1846(self, anders_project: ProjectData) -> None:
        """Requirement 14.7: Place B renders as '1840–1846'."""
        fact_b = anders_project.residences[1]
        rendered = format_residence_interval(fact_b.start, fact_b.end)
        assert rendered == "1840\u20131846"


# ---------------------------------------------------------------------------
# 14.8 — Empty 1850 query
# ---------------------------------------------------------------------------


class TestEmptyQuery1850:
    """Requirement 14.8: Place B end is fixed at 1846 → no residents in 1850."""

    def test_residents_of_place_b_in_1850_is_empty(self, anders_project: ProjectData) -> None:
        entries = residents_of_place(anders_project, "place_b", 1850)
        assert entries == []


# ---------------------------------------------------------------------------
# 14.9 — Timeline order
# ---------------------------------------------------------------------------


class TestTimelineOrder:
    """Requirement 14.9: Place A first (absent start.earliest sorts earliest)."""

    def test_timeline_returns_place_a_first(self, anders_project: ProjectData) -> None:
        timeline = residence_timeline(anders_project, "person_1")
        assert len(timeline) == 2
        assert timeline[0].id == "residence_a"
        assert timeline[1].id == "residence_b"

    def test_timeline_order_is_stable(self, anders_project: ProjectData) -> None:
        """Two consecutive calls return the same order."""
        first = residence_timeline(anders_project, "person_1")
        second = residence_timeline(anders_project, "person_1")
        assert [f.id for f in first] == [f.id for f in second]
