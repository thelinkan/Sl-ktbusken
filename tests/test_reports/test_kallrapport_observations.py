"""Unit tests for listing residence observations in the Källrapport report.

Tests that observations appear under their source with the correct span
rendering and ordering (by observed_from, observed_to, list position).

Requirements: 11.7, 11.9
"""

from __future__ import annotations

from slaktbusken.model.event import SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.reports.kallrapport import _collect_source_usage, generate_kallrapport
from slaktbusken.reports.content import ListBlock, HeadingBlock


def _make_person(pid: str = "p1", given: str = "Erik", surname: str = "Svensson") -> Person:
    return Person(id=pid, sex="M", names=[Name(type="birth", given=given, surname=surname)])


def _make_source(sid: str = "s1", title: str = "Ljusdal AI:10") -> Source:
    return Source(
        id=sid,
        provider="",
        source_type="church_book",
        title=title,
        leverantor_id="lev1",
        kalltyp_id="kt1",
    )


def _make_observation(
    source_id: str = "s1",
    observed_from: str = "1866",
    observed_to: str = "1870",
) -> Observation:
    return Observation(
        source_ref=SourceRef(source_id=source_id, quality=""),
        observed_from=observed_from,
        observed_to=observed_to,
    )


class TestKallrapportObservationUsage:
    """_collect_source_usage includes residence observations."""

    def test_observation_appears_in_source_usage(self):
        """A residence observation is collected under its source_id."""
        person = _make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        source = _make_source()
        obs = _make_observation()
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1866", latest="1866"),
            end=Endpoint(earliest="1870", latest="1870"),
            observations=[obs],
        )
        data = ProjectData(
            persons=[person], places=[place], sources=[source], residences=[fact],
        )
        usage = _collect_source_usage(data)
        assert "s1" in usage
        entries = [e for e in usage["s1"] if e.get("is_residence_observation")]
        assert len(entries) == 1
        assert entries[0]["person_name"] == "Erik Svensson"
        assert entries[0]["event_type"] == "Boende"
        # Span rendered as "1866–1870" (using format_observation_span)
        assert entries[0]["date"] == "1866\u20131870"
        assert entries[0]["place"] == "Ekeby"

    def test_observation_span_equal_years_renders_single_year(self):
        """When observed_from == observed_to, span renders as a single year."""
        person = _make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        source = _make_source()
        obs = _make_observation(observed_from="1866", observed_to="1866")
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1866", latest="1866"),
            end=Endpoint(earliest="1866", latest="1866"),
            observations=[obs],
        )
        data = ProjectData(
            persons=[person], places=[place], sources=[source], residences=[fact],
        )
        usage = _collect_source_usage(data)
        entries = [e for e in usage["s1"] if e.get("is_residence_observation")]
        assert entries[0]["date"] == "1866"

    def test_observations_ordered_by_from_then_to_then_position(self):
        """Observations are ordered by observed_from, observed_to, list position."""
        person = _make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        source = _make_source()
        # Three observations with same source, different spans
        obs_a = _make_observation(observed_from="1871", observed_to="1875")
        obs_b = _make_observation(observed_from="1866", observed_to="1870")
        obs_c = _make_observation(observed_from="1866", observed_to="1868")
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1866", latest="1866"),
            end=Endpoint(earliest="1875", latest="1875"),
            observations=[obs_a, obs_b, obs_c],  # stored order: a, b, c
        )
        data = ProjectData(
            persons=[person], places=[place], sources=[source], residences=[fact],
        )
        usage = _collect_source_usage(data)
        entries = [e for e in usage["s1"] if e.get("is_residence_observation")]
        # Sorted: observed_from ascending, then observed_to ascending
        # obs_c: 1866-1868, obs_b: 1866-1870, obs_a: 1871-1875
        assert entries[0]["date"] == "1866\u20131868"
        assert entries[1]["date"] == "1866\u20131870"
        assert entries[2]["date"] == "1871\u20131875"

    def test_observations_same_from_to_ordered_by_position(self):
        """When observed_from and observed_to match, list position breaks the tie."""
        person = _make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        source_a = _make_source(sid="s1", title="Source A")
        source_b = _make_source(sid="s2", title="Source B")
        # Two observations with identical spans but different sources
        obs1 = _make_observation(source_id="s1", observed_from="1866", observed_to="1870")
        obs2 = _make_observation(source_id="s2", observed_from="1866", observed_to="1870")
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1866", latest="1866"),
            end=Endpoint(earliest="1870", latest="1870"),
            observations=[obs1, obs2],
        )
        data = ProjectData(
            persons=[person], places=[place],
            sources=[source_a, source_b], residences=[fact],
        )
        usage = _collect_source_usage(data)
        # Both appear for their respective sources
        s1_entries = [e for e in usage["s1"] if e.get("is_residence_observation")]
        s2_entries = [e for e in usage["s2"] if e.get("is_residence_observation")]
        assert len(s1_entries) == 1
        assert len(s2_entries) == 1

    def test_multiple_facts_observations_all_included(self):
        """Observations from multiple residence facts are all included."""
        person = _make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        source = _make_source()
        obs1 = _make_observation(observed_from="1866", observed_to="1870")
        obs2 = _make_observation(observed_from="1876", observed_to="1880")
        fact1 = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1866", latest="1866"),
            end=Endpoint(earliest="1870", latest="1870"),
            observations=[obs1],
        )
        fact2 = ResidenceFact(
            id="r2", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1876", latest="1876"),
            end=Endpoint(earliest="1880", latest="1880"),
            observations=[obs2],
        )
        data = ProjectData(
            persons=[person], places=[place], sources=[source],
            residences=[fact1, fact2],
        )
        usage = _collect_source_usage(data)
        entries = [e for e in usage["s1"] if e.get("is_residence_observation")]
        assert len(entries) == 2

    def test_observation_with_absent_span_renders_empty(self):
        """An observation with both observed_from and observed_to empty renders empty span."""
        person = _make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        source = _make_source()
        obs = _make_observation(observed_from="", observed_to="")
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            observations=[obs],
        )
        data = ProjectData(
            persons=[person], places=[place], sources=[source], residences=[fact],
        )
        usage = _collect_source_usage(data)
        entries = [e for e in usage["s1"] if e.get("is_residence_observation")]
        assert entries[0]["date"] == ""


class TestKallrapportFullReport:
    """The full Källrapport includes residence observation entries."""

    def test_observation_appears_in_full_report(self):
        """Residence observations appear in the generated report under the source."""
        from slaktbusken.model.source import Leverantor, Kalltyp

        person = _make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        lev = Leverantor(id="lev1", name="Riksarkivet")
        kt = Kalltyp(id="kt1", name="Husförhörslängd", leverantor_id="lev1")
        source = Source(
            id="s1",
            provider="",
            source_type="church_book",
            title="Ljusdal AI:10 1866–1870",
            leverantor_id="lev1",
            kalltyp_id="kt1",
        )
        obs = _make_observation(observed_from="1866", observed_to="1870")
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1866", latest="1866"),
            end=Endpoint(earliest="1870", latest="1870"),
            observations=[obs],
        )
        data = ProjectData(
            persons=[person], places=[place], sources=[source],
            residences=[fact], leverantorer=[lev], kalltyper=[kt],
        )
        report = generate_kallrapport(data)

        # Find the list block entries that contain the person name
        all_list_items = []
        for block in report.blocks:
            if isinstance(block, ListBlock):
                all_list_items.extend(block.items)

        # The person's observation should appear somewhere
        residence_entries = [item for item in all_list_items if "Boende" in item]
        assert len(residence_entries) >= 1
        assert "Erik Svensson" in residence_entries[0]
        # The span should be present
        assert "1866\u20131870" in residence_entries[0]
