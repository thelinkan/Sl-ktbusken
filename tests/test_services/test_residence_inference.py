"""Unit tests for slaktbusken.services.residence_inference."""

from __future__ import annotations

import pytest

from slaktbusken.model.date_span import expand_iso
from slaktbusken.model.event import DateValue, Event, Participant, SourceRef
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.services.residence_inference import (
    DerivedBound,
    InferenceResult,
    _MSG_CONTRADICTION,
    infer_bounds,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project_with(
    residences: list[ResidenceFact] | None = None,
    events: list[Event] | None = None,
    places: list | None = None,
) -> ProjectData:
    """Build a minimal ProjectData for testing."""
    from slaktbusken.model.place import Place

    data = ProjectData(project=ProjectMetadata(title="test"))
    if residences:
        data.residences = residences
    if events:
        data.events = events
    if places:
        data.places = places
    else:
        data.places = [
            Place(id="place_a", name="Gård A", type="farm"),
            Place(id="place_b", name="Gård B", type="farm"),
            Place(id="place_c", name="Gård C", type="farm"),
        ]
    return data


def _fact(
    id: str,
    person_id: str = "person_1",
    place_id: str = "place_a",
    start_earliest: str | None = None,
    start_latest: str | None = None,
    end_earliest: str | None = None,
    end_latest: str | None = None,
) -> ResidenceFact:
    """Build a ResidenceFact with given bounds."""
    return ResidenceFact(
        id=id,
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=start_earliest, latest=start_latest),
        end=Endpoint(earliest=end_earliest, latest=end_latest),
    )


# ---------------------------------------------------------------------------
# Test: all bounds present → no derivation (7.10)
# ---------------------------------------------------------------------------


class TestNoCandidateWhenBoundsPresent:
    """When all bounds are present, no candidate is formed."""

    def test_all_bounds_present_returns_empty(self):
        fact = _fact("r1", start_earliest="1840", start_latest="1841",
                     end_earliest="1850", end_latest="1851")
        data = _project_with(residences=[fact])
        result = infer_bounds(fact, data)
        assert result.derived == []
        assert result.findings == []

    def test_start_earliest_present_skips_start_candidate(self):
        """No start.earliest candidate when it's already present."""
        fact_a = _fact("r1", place_id="place_a",
                       start_earliest="1835", start_latest="1840",
                       end_earliest="1850")
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1838", end_latest="1845")
        data = _project_with(residences=[fact_a, fact_b])
        result = infer_bounds(fact_a, data)
        # start.earliest already present → no derivation for it
        assert not any(
            d.endpoint == "start" and d.bound == "earliest"
            for d in result.derived
        )

    def test_end_latest_present_skips_end_candidate(self):
        """No end.latest candidate when it's already present."""
        fact_a = _fact("r1", place_id="place_a",
                       start_latest="1840", end_earliest="1850",
                       end_latest="1855")
        fact_b = _fact("r2", place_id="place_b",
                       start_latest="1852")
        data = _project_with(residences=[fact_a, fact_b])
        result = infer_bounds(fact_a, data)
        assert not any(
            d.endpoint == "end" and d.bound == "latest"
            for d in result.derived
        )


# ---------------------------------------------------------------------------
# Test: neighbour candidate for start.earliest (7.3)
# ---------------------------------------------------------------------------


class TestNeighbourCandidateStartEarliest:
    """Derive start.earliest from a neighbour's end.earliest."""

    def test_basic_neighbour_derivation(self):
        """The latest end.earliest at a different place earlier than start.latest."""
        fact_a = _fact("r1", place_id="place_a",
                       start_latest="1840", end_earliest="1850")
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1838", end_latest="1839")
        data = _project_with(residences=[fact_a, fact_b])

        result = infer_bounds(fact_a, data)
        assert len(result.derived) == 1
        d = result.derived[0]
        assert d.endpoint == "start"
        assert d.bound == "earliest"
        assert d.value == "1838"
        assert d.origin_kind == "residence"
        assert d.origin_id == "r2"
        assert d.origin_label == "Gård B"

    def test_picks_latest_among_neighbours(self):
        """Multiple neighbours: widest-interval picks the latest first day."""
        fact_a = _fact("r1", place_id="place_a",
                       start_latest="1840", end_earliest="1850")
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1835", end_latest="1838")
        fact_c = _fact("r3", place_id="place_c",
                       end_earliest="1838", end_latest="1839")
        data = _project_with(residences=[fact_a, fact_b, fact_c])

        result = infer_bounds(fact_a, data)
        assert len(result.derived) == 1
        assert result.derived[0].value == "1838"
        assert result.derived[0].origin_id == "r3"

    def test_same_place_excluded(self):
        """A fact at the same place is not a neighbour."""
        fact_a = _fact("r1", place_id="place_a",
                       start_latest="1840", end_earliest="1850")
        fact_b = _fact("r2", place_id="place_a",
                       end_earliest="1838", end_latest="1839")
        data = _project_with(residences=[fact_a, fact_b])

        result = infer_bounds(fact_a, data)
        assert result.derived == []

    def test_neighbour_not_earlier_excluded(self):
        """A neighbour's end.earliest that isn't earlier than start.latest."""
        fact_a = _fact("r1", place_id="place_a",
                       start_latest="1840", end_earliest="1850")
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1841", end_latest="1845")
        data = _project_with(residences=[fact_a, fact_b])

        result = infer_bounds(fact_a, data)
        # 1841 is NOT strictly earlier than 1840
        assert result.derived == []

    def test_fallback_to_end_earliest_as_reference(self):
        """When start.latest is absent, use end.earliest as the reference."""
        fact_a = _fact("r1", place_id="place_a",
                       end_earliest="1850")  # no start.latest
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1845", end_latest="1848")
        data = _project_with(residences=[fact_a, fact_b])

        result = infer_bounds(fact_a, data)
        assert len(result.derived) == 1
        assert result.derived[0].value == "1845"

    def test_no_reference_no_candidate(self):
        """When both start.latest and end.earliest are absent, no neighbour candidate."""
        fact_a = _fact("r1", place_id="place_a")  # no bounds at all
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1838", end_latest="1845")
        data = _project_with(residences=[fact_a, fact_b])

        result = infer_bounds(fact_a, data)
        # No neighbour candidate (might still have birth/death candidate)
        assert not any(
            d.origin_kind == "residence" for d in result.derived
        )

    def test_different_person_excluded(self):
        """Only facts for the same person are considered."""
        fact_a = _fact("r1", person_id="person_1", place_id="place_a",
                       start_latest="1840", end_earliest="1850")
        fact_b = _fact("r2", person_id="person_2", place_id="place_b",
                       end_earliest="1838", end_latest="1839")
        data = _project_with(residences=[fact_a, fact_b])

        result = infer_bounds(fact_a, data)
        assert result.derived == []


# ---------------------------------------------------------------------------
# Test: birth candidate for start.earliest (7.4)
# ---------------------------------------------------------------------------


class TestBirthCandidate:
    """Derive start.earliest from the person's birth event."""

    def test_basic_birth_derivation(self):
        fact = _fact("r1", place_id="place_a", start_latest="1840",
                     end_earliest="1850")
        birth_event = Event(
            id="ev1", type="birth",
            participants=[Participant(person_id="person_1", role="child")],
            date=DateValue(value="1820-05-15", precision="day"),
        )
        data = _project_with(residences=[fact], events=[birth_event])

        result = infer_bounds(fact, data)
        assert len(result.derived) == 1
        d = result.derived[0]
        assert d.endpoint == "start"
        assert d.bound == "earliest"
        assert d.value == "1820-05-15"
        assert d.origin_kind == "event"
        assert d.origin_id == "ev1"
        assert d.origin_label == "Födelse"

    def test_multiple_births_takes_earliest(self):
        """When multiple birth events exist, take the earliest."""
        fact = _fact("r1", place_id="place_a", start_latest="1840",
                     end_earliest="1850")
        events = [
            Event(id="ev1", type="birth",
                  participants=[Participant(person_id="person_1", role="child")],
                  date=DateValue(value="1820", precision="year")),
            Event(id="ev2", type="birth",
                  participants=[Participant(person_id="person_1", role="child")],
                  date=DateValue(value="1819-03", precision="month")),
        ]
        data = _project_with(residences=[fact], events=events)

        result = infer_bounds(fact, data)
        assert result.derived[0].value == "1819-03"

    def test_birth_without_date_ignored(self):
        """A birth event with no date contributes nothing."""
        fact = _fact("r1", place_id="place_a", start_latest="1840",
                     end_earliest="1850")
        birth_event = Event(
            id="ev1", type="birth",
            participants=[Participant(person_id="person_1", role="child")],
            date=None,
        )
        data = _project_with(residences=[fact], events=[birth_event])
        result = infer_bounds(fact, data)
        assert result.derived == []


# ---------------------------------------------------------------------------
# Test: death candidate for end.latest (7.5)
# ---------------------------------------------------------------------------


class TestDeathCandidate:
    """Derive end.latest from the person's death event."""

    def test_basic_death_derivation(self):
        fact = _fact("r1", place_id="place_a", start_latest="1840",
                     end_earliest="1850")
        death_event = Event(
            id="ev1", type="death",
            participants=[Participant(person_id="person_1", role="principal")],
            date=DateValue(value="1870-12-01", precision="day"),
        )
        data = _project_with(residences=[fact], events=[death_event])

        result = infer_bounds(fact, data)
        assert len(result.derived) == 1
        d = result.derived[0]
        assert d.endpoint == "end"
        assert d.bound == "latest"
        assert d.value == "1870-12-01"
        assert d.origin_kind == "event"
        assert d.origin_id == "ev1"
        assert d.origin_label == "Död"

    def test_multiple_deaths_takes_latest(self):
        """When multiple death events exist, take the latest."""
        fact = _fact("r1", place_id="place_a", start_latest="1840",
                     end_earliest="1850")
        events = [
            Event(id="ev1", type="death",
                  participants=[Participant(person_id="person_1", role="principal")],
                  date=DateValue(value="1870", precision="year")),
            Event(id="ev2", type="death",
                  participants=[Participant(person_id="person_1", role="principal")],
                  date=DateValue(value="1871-03-20", precision="day")),
        ]
        data = _project_with(residences=[fact], events=events)

        result = infer_bounds(fact, data)
        assert result.derived[0].value == "1871-03-20"


# ---------------------------------------------------------------------------
# Test: widest-interval competition (7.6)
# ---------------------------------------------------------------------------


class TestWidestIntervalResolution:
    """Competing candidates resolved by widest-interval comparison."""

    def test_start_earliest_takes_latest_first_day(self):
        """For start.earliest, the latest candidate wins (latest first day)."""
        fact = _fact("r1", place_id="place_a", start_latest="1850",
                     end_earliest="1860")
        # Neighbour at place_b with end.earliest=1845
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1845", end_latest="1848")
        # Birth event at 1820
        birth = Event(
            id="ev1", type="birth",
            participants=[Participant(person_id="person_1", role="child")],
            date=DateValue(value="1820", precision="year"),
        )
        data = _project_with(residences=[fact, fact_b], events=[birth])

        result = infer_bounds(fact, data)
        # 1845 has first day 1845-01-01, 1820 has first day 1820-01-01
        # Latest = 1845 wins
        start_derived = [d for d in result.derived
                         if d.endpoint == "start" and d.bound == "earliest"]
        assert len(start_derived) == 1
        assert start_derived[0].value == "1845"

    def test_end_latest_takes_earliest_last_day(self):
        """For end.latest, the earliest candidate wins (earliest last day)."""
        fact = _fact("r1", place_id="place_a", start_latest="1840",
                     end_earliest="1850")
        # Neighbour at place_b with start.latest=1855
        fact_b = _fact("r2", place_id="place_b",
                       start_latest="1855", end_earliest="1860")
        # Death event at 1880
        death = Event(
            id="ev1", type="death",
            participants=[Participant(person_id="person_1", role="principal")],
            date=DateValue(value="1880", precision="year"),
        )
        data = _project_with(residences=[fact, fact_b], events=[death])

        result = infer_bounds(fact, data)
        # 1855 has last day 1855-12-31, 1880 has last day 1880-12-31
        # Earliest = 1855 wins
        end_derived = [d for d in result.derived
                       if d.endpoint == "end" and d.bound == "latest"]
        assert len(end_derived) == 1
        assert end_derived[0].value == "1855"


# ---------------------------------------------------------------------------
# Test: contradiction handling (7.12)
# ---------------------------------------------------------------------------


class TestContradiction:
    """Contradicting candidates are dropped with a finding."""

    def test_start_earliest_later_than_start_latest_contradicts(self):
        """A start.earliest candidate later than the stored start.latest."""
        fact = _fact("r1", place_id="place_a",
                     start_latest="1835", end_earliest="1850")
        # Neighbour has end.earliest=1838 which is later than start.latest 1835
        # But wait — 1838 must be strictly_earlier than 1835 for the neighbour
        # to be a candidate. Actually 1838 is NOT earlier than 1835, so it won't
        # even be a candidate. Let's use birth for the contradiction case.
        birth = Event(
            id="ev1", type="birth",
            participants=[Participant(person_id="person_1", role="child")],
            date=DateValue(value="1836", precision="year"),
        )
        data = _project_with(residences=[fact], events=[birth])

        result = infer_bounds(fact, data)
        # 1836 as start.earliest: is it later than start.latest (1835)?
        # strictly_earlier("1835", "1836") → 1835-12-31 < 1836-01-01 → True
        # So 1836 IS later than 1835 → contradiction
        assert len(result.findings) == 1
        assert result.findings[0].message == _MSG_CONTRADICTION
        assert result.derived == []

    def test_end_latest_earlier_than_end_earliest_contradicts(self):
        """An end.latest candidate earlier than the stored end.earliest."""
        fact = _fact("r1", place_id="place_a",
                     start_latest="1840", end_earliest="1870")
        # Death at 1865, earlier than end.earliest 1870
        death = Event(
            id="ev1", type="death",
            participants=[Participant(person_id="person_1", role="principal")],
            date=DateValue(value="1865", precision="year"),
        )
        data = _project_with(residences=[fact], events=[death])

        result = infer_bounds(fact, data)
        # 1865 as end.latest: is it earlier than end.earliest 1870?
        # strictly_earlier("1865", "1870") → 1865-12-31 < 1870-01-01 → True
        # Contradiction!
        assert len(result.findings) == 1
        assert result.findings[0].message == _MSG_CONTRADICTION
        assert result.derived == []

    def test_start_earliest_later_than_end_latest_contradicts(self):
        """A start.earliest candidate later than the stored end.latest."""
        fact = _fact("r1", place_id="place_a",
                     start_latest="1860", end_earliest="1850",
                     end_latest="1855")
        # Birth at 1856 is later than end.latest 1855
        birth = Event(
            id="ev1", type="birth",
            participants=[Participant(person_id="person_1", role="child")],
            date=DateValue(value="1856", precision="year"),
        )
        data = _project_with(residences=[fact], events=[birth])

        result = infer_bounds(fact, data)
        # 1856 as start.earliest: is it later than end.latest 1855?
        # strictly_earlier("1855", "1856") → True → contradiction
        assert len(result.findings) == 1
        assert result.findings[0].message == _MSG_CONTRADICTION

    def test_non_contradicting_passes(self):
        """A valid candidate that doesn't contradict is accepted."""
        fact = _fact("r1", place_id="place_a",
                     start_latest="1840", end_earliest="1850")
        birth = Event(
            id="ev1", type="birth",
            participants=[Participant(person_id="person_1", role="child")],
            date=DateValue(value="1820", precision="year"),
        )
        data = _project_with(residences=[fact], events=[birth])

        result = infer_bounds(fact, data)
        assert result.findings == []
        assert len(result.derived) == 1
        assert result.derived[0].value == "1820"


# ---------------------------------------------------------------------------
# Test: idempotence / no-op after confirmed write (7.10)
# ---------------------------------------------------------------------------


class TestIdempotence:
    """A second invocation after a confirmed write is a no-op."""

    def test_second_invocation_noop(self):
        """After writing the derived value, no new candidate is formed."""
        # Simulate: first call derived start.earliest=1838
        # After confirmed write: start.earliest is now 1838
        fact_after_write = _fact("r1", place_id="place_a",
                                 start_earliest="1838", start_latest="1840",
                                 end_earliest="1850")
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1838", end_latest="1839")
        data = _project_with(residences=[fact_after_write, fact_b])

        result = infer_bounds(fact_after_write, data)
        # start.earliest is already present → no candidate formed
        assert not any(
            d.endpoint == "start" and d.bound == "earliest"
            for d in result.derived
        )


# ---------------------------------------------------------------------------
# Test: no mutation (7.2)
# ---------------------------------------------------------------------------


class TestNoMutation:
    """The function leaves everything unchanged."""

    def test_fact_unchanged_after_inference(self):
        import copy
        fact = _fact("r1", place_id="place_a",
                     start_latest="1840", end_earliest="1850")
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1838", end_latest="1839")
        data = _project_with(residences=[fact, fact_b])

        original_fact = copy.deepcopy(fact)
        original_data = copy.deepcopy(data)

        infer_bounds(fact, data)

        assert fact.start.earliest == original_fact.start.earliest
        assert fact.start.latest == original_fact.start.latest
        assert fact.end.earliest == original_fact.end.earliest
        assert fact.end.latest == original_fact.end.latest
        assert len(data.residences) == len(original_data.residences)


# ---------------------------------------------------------------------------
# Test: stored ISO form preservation (7.6)
# ---------------------------------------------------------------------------


class TestStoredIsoFormPreserved:
    """The winner is returned in its stored ISO form."""

    def test_month_precision_preserved(self):
        """A candidate with month precision keeps its ÅÅÅÅ-MM form."""
        fact = _fact("r1", place_id="place_a",
                     start_latest="1840", end_earliest="1850")
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1838-06", end_latest="1839")
        data = _project_with(residences=[fact, fact_b])

        result = infer_bounds(fact, data)
        assert result.derived[0].value == "1838-06"

    def test_day_precision_preserved(self):
        """A candidate with day precision keeps its ÅÅÅÅ-MM-DD form."""
        fact = _fact("r1", place_id="place_a",
                     start_latest="1840", end_earliest="1850")
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1838-06-15", end_latest="1839")
        data = _project_with(residences=[fact, fact_b])

        result = infer_bounds(fact, data)
        assert result.derived[0].value == "1838-06-15"


# ---------------------------------------------------------------------------
# Test: combined start and end derivation
# ---------------------------------------------------------------------------


class TestCombinedDerivation:
    """Both start.earliest and end.latest can be derived in one pass."""

    def test_both_bounds_derived(self):
        """A fact missing both outer bounds derives from neighbours."""
        fact = _fact("r1", place_id="place_a",
                     start_latest="1840", end_earliest="1850")
        # Neighbour earlier → start.earliest candidate
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1838", end_latest="1839")
        # Neighbour later → end.latest candidate
        fact_c = _fact("r3", place_id="place_c",
                       start_latest="1855", end_earliest="1860")
        data = _project_with(residences=[fact, fact_b, fact_c])

        result = infer_bounds(fact, data)
        assert len(result.derived) == 2
        endpoints = {(d.endpoint, d.bound) for d in result.derived}
        assert ("start", "earliest") in endpoints
        assert ("end", "latest") in endpoints

    def test_birth_and_death_combined(self):
        """Birth + death events derive both outer bounds."""
        fact = _fact("r1", place_id="place_a",
                     start_latest="1840", end_earliest="1850")
        birth = Event(
            id="ev1", type="birth",
            participants=[Participant(person_id="person_1", role="child")],
            date=DateValue(value="1820", precision="year"),
        )
        death = Event(
            id="ev2", type="death",
            participants=[Participant(person_id="person_1", role="principal")],
            date=DateValue(value="1880", precision="year"),
        )
        data = _project_with(residences=[fact], events=[birth, death])

        result = infer_bounds(fact, data)
        assert len(result.derived) == 2
        start_d = next(d for d in result.derived if d.endpoint == "start")
        end_d = next(d for d in result.derived if d.endpoint == "end")
        assert start_d.value == "1820"
        assert end_d.value == "1880"


# ---------------------------------------------------------------------------
# Test: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Various edge cases."""

    def test_empty_project_no_crash(self):
        fact = _fact("r1", place_id="place_a", start_latest="1840",
                     end_earliest="1850")
        data = _project_with(residences=[fact])
        result = infer_bounds(fact, data)
        assert result.derived == []
        assert result.findings == []

    def test_whitespace_only_bound_treated_as_absent(self):
        """Whitespace-only values count as absent."""
        fact = ResidenceFact(
            id="r1", person_id="person_1", place_id="place_a",
            start=Endpoint(earliest="  ", latest="1840"),
            end=Endpoint(earliest="1850", latest="   "),
        )
        fact_b = _fact("r2", place_id="place_b",
                       end_earliest="1838", end_latest="1839")
        data = _project_with(residences=[fact, fact_b])

        result = infer_bounds(fact, data)
        # Whitespace earliest is absent → candidate should be formed
        assert any(d.endpoint == "start" and d.bound == "earliest"
                   for d in result.derived)

    def test_neighbour_absent_end_earliest_skipped(self):
        """A neighbour whose end.earliest is absent provides no candidate."""
        fact = _fact("r1", place_id="place_a", start_latest="1840",
                     end_earliest="1850")
        fact_b = _fact("r2", place_id="place_b",
                       end_latest="1839")  # end.earliest absent
        data = _project_with(residences=[fact, fact_b])

        result = infer_bounds(fact, data)
        assert result.derived == []
