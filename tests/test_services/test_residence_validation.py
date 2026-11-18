"""Unit tests for the warning-level residence validation service.

Covers:
- Single-fact findings: start/end window overlap (2.17), duplicate source on one
  fact (4.13), evidence outside the recorded period (16.9).
- Overlap findings: unordered pairs, strict core overlap at coarser precision,
  same-place and different-place messages, {plats A} ordering and finding order
  (6.2–6.8).
- Flytt link findings: place mismatch between Flytt_Event and linked residences
  (18.10).
"""

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.services.residence_validation import (
    ResidenceFinding,
    flytt_link_findings,
    overlap_findings,
    residence_findings,
)


def _observation(observed_from="", observed_to="", source_id="source_1"):
    return Observation(
        source_ref=SourceRef(source_id=source_id, quality="secondary"),
        observed_from=observed_from,
        observed_to=observed_to,
    )


def _fact(
    start=None,
    end=None,
    observations=None,
    residence_id="r1",
    person_id="person_1",
    place_id="place_1",
):
    return ResidenceFact(
        id=residence_id,
        person_id=person_id,
        place_id=place_id,
        start=start or Endpoint(),
        end=end or Endpoint(),
        observations=observations or [],
    )


# ===========================================================================
# Single-fact findings: residence_findings
# ===========================================================================


class TestWindowOverlap:
    """Requirement 2.17: start/end window overlap warning."""

    def test_window_overlap_when_start_latest_after_end_earliest(self):
        """start.latest.last > end.earliest.first → warning."""
        fact = _fact(
            start=Endpoint(latest="1850"),
            end=Endpoint(earliest="1845"),
        )
        findings = residence_findings(fact, ProjectData())
        msgs = [f.message for f in findings]
        assert any("start- och slutfönster överlappar" in m for m in msgs)

    def test_no_window_overlap_when_core_is_valid(self):
        """start.latest <= end.earliest → no warning."""
        fact = _fact(
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
        )
        findings = residence_findings(fact, ProjectData())
        msgs = [f.message for f in findings]
        assert not any("start- och slutfönster överlappar" in m for m in msgs)

    def test_no_window_overlap_when_bounds_are_absent(self):
        """Both absent → no warning."""
        fact = _fact()
        findings = residence_findings(fact, ProjectData())
        assert findings == []

    def test_touching_cores_produce_no_overlap_warning(self):
        """start.latest == end.earliest at same day → no warning (core is a point)."""
        fact = _fact(
            start=Endpoint(latest="1840-06-15"),
            end=Endpoint(earliest="1840-06-15"),
        )
        findings = residence_findings(fact, ProjectData())
        msgs = [f.message for f in findings]
        assert not any("start- och slutfönster överlappar" in m for m in msgs)


class TestDuplicateSource:
    """Requirement 4.13: duplicate source on one fact."""

    def test_duplicate_source_yields_one_warning(self):
        """Two observations with the same source_id → one warning."""
        fact = _fact(
            observations=[
                _observation("1866", "1870", source_id="src_a"),
                _observation("1871", "1875", source_id="src_a"),
            ]
        )
        findings = residence_findings(fact, ProjectData())
        msgs = [f.message for f in findings]
        assert msgs.count("Samma källa är kopplad till boendet mer än en gång.") == 1

    def test_no_duplicate_when_different_sources(self):
        """Different source_ids → no warning."""
        fact = _fact(
            observations=[
                _observation("1866", "1870", source_id="src_a"),
                _observation("1871", "1875", source_id="src_b"),
            ]
        )
        findings = residence_findings(fact, ProjectData())
        msgs = [f.message for f in findings]
        assert "Samma källa är kopplad till boendet mer än en gång." not in msgs

    def test_no_duplicate_when_no_observations(self):
        fact = _fact(observations=[])
        findings = residence_findings(fact, ProjectData())
        assert findings == []


class TestEvidenceOutside:
    """Requirement 16.9: evidence outside the recorded period."""

    def test_observation_before_start_earliest(self):
        """observed_from earlier than start.earliest → warning."""
        fact = _fact(
            start=Endpoint(earliest="1866"),
            end=Endpoint(latest="1880"),
            observations=[_observation("1860", "1870")],
        )
        findings = residence_findings(fact, ProjectData())
        msgs = [f.message for f in findings]
        assert any("utanför den angivna perioden" in m for m in msgs)

    def test_observation_after_end_latest(self):
        """observed_to later than end.latest → warning."""
        fact = _fact(
            start=Endpoint(earliest="1866"),
            end=Endpoint(latest="1875"),
            observations=[_observation("1870", "1880")],
        )
        findings = residence_findings(fact, ProjectData())
        msgs = [f.message for f in findings]
        assert any("utanför den angivna perioden" in m for m in msgs)

    def test_no_warning_when_within_bounds(self):
        """Observation within recorded period → no warning."""
        fact = _fact(
            start=Endpoint(earliest="1860"),
            end=Endpoint(latest="1880"),
            observations=[_observation("1866", "1870")],
        )
        findings = residence_findings(fact, ProjectData())
        msgs = [f.message for f in findings]
        assert not any("utanför den angivna perioden" in m for m in msgs)

    def test_no_warning_when_outer_bounds_absent(self):
        """No start.earliest or end.latest → no evidence-outside warning."""
        fact = _fact(
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
            observations=[_observation("1830", "1860")],
        )
        findings = residence_findings(fact, ProjectData())
        msgs = [f.message for f in findings]
        assert not any("utanför den angivna perioden" in m for m in msgs)

    def test_only_one_evidence_finding_per_fact(self):
        """Multiple observations outside → still only one finding."""
        fact = _fact(
            start=Endpoint(earliest="1866"),
            end=Endpoint(latest="1875"),
            observations=[
                _observation("1860", "1870"),
                _observation("1870", "1880"),
            ],
        )
        findings = residence_findings(fact, ProjectData())
        msgs = [f.message for f in findings]
        assert msgs.count(
            "Källan styrker närvaro utanför den angivna perioden"
            " \u2013 utöka perioden om du vill."
        ) == 1


# ===========================================================================
# Overlap findings
# ===========================================================================


def _data_with_facts_and_places(facts, places=None):
    """Build a ProjectData with the given facts and places."""
    data = ProjectData()
    data.residences = list(facts)
    if places:
        data.places = list(places)
    return data


class TestOverlapFindings:
    """Requirements 6.2–6.8: overlap findings for same-person facts."""

    def test_overlapping_cores_same_place_yields_merge_suggestion(self):
        """Same place + overlapping cores → merge suggestion (6.5)."""
        fact_a = _fact(
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1850"),
            residence_id="r1",
            place_id="place_1",
        )
        fact_b = _fact(
            start=Endpoint(latest="1845"),
            end=Endpoint(earliest="1855"),
            residence_id="r2",
            place_id="place_1",
        )
        data = _data_with_facts_and_places(
            [fact_a, fact_b],
            [Place(id="place_1", type="farm", name="Ekeby")],
        )
        findings = overlap_findings("person_1", data)
        assert len(findings) == 1
        assert "Två boenden på samma plats överlappar" in findings[0].message
        assert "överväg att slå samman dem" in findings[0].message

    def test_overlapping_cores_different_place_yields_overlap_message(self):
        """Different places + overlapping cores → overlap message (6.4)."""
        fact_a = _fact(
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1850"),
            residence_id="r1",
            place_id="place_1",
        )
        fact_b = _fact(
            start=Endpoint(latest="1845"),
            end=Endpoint(earliest="1855"),
            residence_id="r2",
            place_id="place_2",
        )
        data = _data_with_facts_and_places(
            [fact_a, fact_b],
            [
                Place(id="place_1", type="farm", name="Ekeby"),
                Place(id="place_2", type="farm", name="Forsby"),
            ],
        )
        findings = overlap_findings("person_1", data)
        assert len(findings) == 1
        assert "Överlappande boenden:" in findings[0].message
        assert "Ekeby" in findings[0].message
        assert "Forsby" in findings[0].message

    def test_touching_cores_produce_no_overlap(self):
        """Cores sharing exactly one boundary year → touching, not overlapping (6.2)."""
        fact_a = _fact(
            start=Endpoint(latest="1835"),
            end=Endpoint(earliest="1840"),
            residence_id="r1",
        )
        fact_b = _fact(
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1850"),
            residence_id="r2",
        )
        data = _data_with_facts_and_places([fact_a, fact_b])
        findings = overlap_findings("person_1", data)
        assert findings == []

    def test_empty_core_yields_no_overlap(self):
        """A fact with no core (absent bound) never overlaps (6.6)."""
        fact_a = _fact(
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1850"),
            residence_id="r1",
        )
        fact_b = _fact(
            start=Endpoint(),  # unknown → empty core
            end=Endpoint(earliest="1855"),
            residence_id="r2",
        )
        data = _data_with_facts_and_places([fact_a, fact_b])
        findings = overlap_findings("person_1", data)
        assert findings == []

    def test_no_overlap_for_different_persons(self):
        """Only same-person pairs are evaluated (6.3)."""
        fact_a = _fact(
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1850"),
            residence_id="r1",
            person_id="person_1",
        )
        fact_b = _fact(
            start=Endpoint(latest="1845"),
            end=Endpoint(earliest="1855"),
            residence_id="r2",
            person_id="person_2",
        )
        data = _data_with_facts_and_places([fact_a, fact_b])
        findings = overlap_findings("person_1", data)
        assert findings == []

    def test_plats_a_is_earlier_starting_core(self):
        """Requirement 6.7: {plats A} is the earlier-starting core."""
        fact_a = _fact(
            start=Endpoint(latest="1845"),
            end=Endpoint(earliest="1860"),
            residence_id="r1",
            place_id="place_2",
        )
        fact_b = _fact(
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1855"),
            residence_id="r2",
            place_id="place_1",
        )
        data = _data_with_facts_and_places(
            [fact_a, fact_b],
            [
                Place(id="place_1", type="farm", name="Åkeby"),
                Place(id="place_2", type="farm", name="Berga"),
            ],
        )
        findings = overlap_findings("person_1", data)
        # fact_b starts earlier (1840 vs 1845), so {plats A} = place_1 (Åkeby)
        assert "Åkeby" in findings[0].message
        # The message puts plats_A first
        assert findings[0].message.index("Åkeby") < findings[0].message.index("Berga")

    def test_three_facts_yield_one_finding_per_pair(self):
        """Requirement 6.8: one finding per unordered pair."""
        fact_a = _fact(
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1860"),
            residence_id="r1",
            place_id="p1",
        )
        fact_b = _fact(
            start=Endpoint(latest="1845"),
            end=Endpoint(earliest="1855"),
            residence_id="r2",
            place_id="p2",
        )
        fact_c = _fact(
            start=Endpoint(latest="1850"),
            end=Endpoint(earliest="1870"),
            residence_id="r3",
            place_id="p3",
        )
        data = _data_with_facts_and_places(
            [fact_a, fact_b, fact_c],
            [
                Place(id="p1", type="farm", name="A"),
                Place(id="p2", type="farm", name="B"),
                Place(id="p3", type="farm", name="C"),
            ],
        )
        findings = overlap_findings("person_1", data)
        # a+b overlap, a+c overlap, b+c overlap → 3 findings
        assert len(findings) == 3

    def test_overlap_finding_carries_correct_fields(self):
        """ResidenceFinding carries the right ids and severity."""
        fact_a = _fact(
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1850"),
            residence_id="r1",
            place_id="place_1",
        )
        fact_b = _fact(
            start=Endpoint(latest="1845"),
            end=Endpoint(earliest="1855"),
            residence_id="r2",
            place_id="place_2",
        )
        data = _data_with_facts_and_places(
            [fact_a, fact_b],
            [
                Place(id="place_1", type="farm", name="Ekeby"),
                Place(id="place_2", type="farm", name="Forsby"),
            ],
        )
        findings = overlap_findings("person_1", data)
        assert findings[0].severity == "warning"
        assert findings[0].person_id == "person_1"
        assert findings[0].residence_id == "r1"  # r1 starts earlier
        assert findings[0].other_residence_id == "r2"


# ===========================================================================
# Flytt link findings
# ===========================================================================


def _flytt_event(
    event_id="ev1",
    person_id="person_1",
    from_place_id=None,
    to_place_id=None,
):
    return Event(
        id=event_id,
        type="flytt",
        participants=[Participant(person_id=person_id, role="principal")],
        from_place=PlaceRef(place_id=from_place_id) if from_place_id else None,
        place=PlaceRef(place_id=to_place_id) if to_place_id else None,
    )


class TestFlyttLinkFindings:
    """Requirement 18.10: flytt link place mismatch."""

    def test_from_place_mismatch_yields_finding(self):
        """Flytt from_place differs from end-linked residence's place → warning."""
        event = _flytt_event(from_place_id="place_B", to_place_id="place_2")
        fact = _fact(
            residence_id="r1",
            place_id="place_A",
            end=Endpoint(event_id="ev1"),
        )
        data = ProjectData()
        data.events = [event]
        data.residences = [fact]

        findings = flytt_link_findings(data)
        assert len(findings) == 1
        assert "Flyttens platser stämmer inte" in findings[0].message
        assert findings[0].residence_id == "r1"

    def test_to_place_mismatch_yields_finding(self):
        """Flytt place differs from start-linked residence's place → warning."""
        event = _flytt_event(from_place_id="place_1", to_place_id="place_B")
        fact = _fact(
            residence_id="r1",
            place_id="place_A",
            start=Endpoint(event_id="ev1"),
        )
        data = ProjectData()
        data.events = [event]
        data.residences = [fact]

        findings = flytt_link_findings(data)
        assert len(findings) == 1
        assert "Flyttens platser stämmer inte" in findings[0].message

    def test_matching_places_yield_no_finding(self):
        """from_place matches end-linked and place matches start-linked → no finding."""
        event = _flytt_event(from_place_id="place_A", to_place_id="place_B")
        fact_end = _fact(
            residence_id="r1",
            place_id="place_A",
            end=Endpoint(event_id="ev1"),
        )
        fact_start = _fact(
            residence_id="r2",
            place_id="place_B",
            start=Endpoint(event_id="ev1"),
        )
        data = ProjectData()
        data.events = [event]
        data.residences = [fact_end, fact_start]

        findings = flytt_link_findings(data)
        assert findings == []

    def test_absent_from_place_yields_no_finding_for_end_linked(self):
        """Flytt with no from_place → no finding for end-linked residence."""
        event = _flytt_event(from_place_id=None, to_place_id="place_B")
        fact = _fact(
            residence_id="r1",
            place_id="place_A",
            end=Endpoint(event_id="ev1"),
        )
        data = ProjectData()
        data.events = [event]
        data.residences = [fact]

        findings = flytt_link_findings(data)
        assert findings == []

    def test_absent_place_yields_no_finding_for_start_linked(self):
        """Flytt with no place → no finding for start-linked residence."""
        event = _flytt_event(from_place_id="place_A", to_place_id=None)
        fact = _fact(
            residence_id="r1",
            place_id="place_B",
            start=Endpoint(event_id="ev1"),
        )
        data = ProjectData()
        data.events = [event]
        data.residences = [fact]

        findings = flytt_link_findings(data)
        assert findings == []

    def test_non_flytt_events_are_ignored(self):
        """Non-flytt events linked to endpoints → no finding."""
        event = Event(
            id="ev1",
            type="death",
            participants=[Participant(person_id="person_1", role="principal")],
        )
        fact = _fact(
            residence_id="r1",
            place_id="place_A",
            end=Endpoint(event_id="ev1"),
        )
        data = ProjectData()
        data.events = [event]
        data.residences = [fact]

        findings = flytt_link_findings(data)
        assert findings == []
