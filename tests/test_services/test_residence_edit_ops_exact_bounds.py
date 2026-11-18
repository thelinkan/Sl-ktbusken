"""Unit tests for use_as_exact_start and use_as_exact_end.

These are the only routes by which an Observation value reaches an outer bound
of a Residence_Fact. They are never invoked automatically — only through
explicit user action ("Använd som exakt början" / "Använd som exakt slut").

Requirements: 16.10, 16.11.
"""

from __future__ import annotations

import copy

from slaktbusken.model.event import SourceRef
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.services.residence_edit_ops import (
    use_as_exact_end,
    use_as_exact_start,
)


def _make_source_ref(source_id: str = "src_1") -> SourceRef:
    return SourceRef(source_id=source_id, quality="3")


def _make_observation(
    observed_from: str = "1866",
    observed_to: str = "1870",
) -> Observation:
    return Observation(
        source_ref=_make_source_ref(),
        observed_from=observed_from,
        observed_to=observed_to,
        page_note="",
    )


def _make_fact(
    start_earliest: str | None = "1860",
    start_latest: str | None = "1865",
    end_earliest: str | None = "1875",
    end_latest: str | None = "1880",
) -> ResidenceFact:
    return ResidenceFact(
        id="res_1",
        person_id="person_1",
        place_id="place_1",
        start=Endpoint(
            earliest=start_earliest,
            latest=start_latest,
            precision="year",
            event_id="evt_1",
            note="start note",
        ),
        end=Endpoint(
            earliest=end_earliest,
            latest=end_latest,
            precision="month",
            event_id="evt_2",
            note="end note",
        ),
        role_in_household="husbonde",
        observations=[_make_observation()],
        notes="Some notes",
    )


class TestUseAsExactStart:
    """use_as_exact_start sets both start bounds to obs.observed_from."""

    def test_sets_start_earliest_to_observed_from(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868", observed_to="1870")
        result = use_as_exact_start(fact, obs)
        assert result.start.earliest == "1868"

    def test_sets_start_latest_to_observed_from(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868", observed_to="1870")
        result = use_as_exact_start(fact, obs)
        assert result.start.latest == "1868"

    def test_end_earliest_unchanged(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868", observed_to="1870")
        result = use_as_exact_start(fact, obs)
        assert result.end.earliest == fact.end.earliest

    def test_end_latest_unchanged(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868", observed_to="1870")
        result = use_as_exact_start(fact, obs)
        assert result.end.latest == fact.end.latest

    def test_start_precision_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868")
        result = use_as_exact_start(fact, obs)
        assert result.start.precision == "year"

    def test_start_event_id_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868")
        result = use_as_exact_start(fact, obs)
        assert result.start.event_id == "evt_1"

    def test_start_note_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868")
        result = use_as_exact_start(fact, obs)
        assert result.start.note == "start note"

    def test_end_precision_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868")
        result = use_as_exact_start(fact, obs)
        assert result.end.precision == "month"

    def test_end_event_id_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868")
        result = use_as_exact_start(fact, obs)
        assert result.end.event_id == "evt_2"

    def test_end_note_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868")
        result = use_as_exact_start(fact, obs)
        assert result.end.note == "end note"

    def test_observations_list_unchanged(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868")
        result = use_as_exact_start(fact, obs)
        assert len(result.observations) == len(fact.observations)
        assert result.observations[0].observed_from == "1866"
        assert result.observations[0].observed_to == "1870"

    def test_other_fields_unchanged(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868")
        result = use_as_exact_start(fact, obs)
        assert result.id == "res_1"
        assert result.person_id == "person_1"
        assert result.place_id == "place_1"
        assert result.role_in_household == "husbonde"
        assert result.notes == "Some notes"

    def test_does_not_mutate_original_fact(self) -> None:
        fact = _make_fact()
        original = copy.deepcopy(fact)
        obs = _make_observation(observed_from="1868")
        use_as_exact_start(fact, obs)
        assert fact.start.earliest == original.start.earliest
        assert fact.start.latest == original.start.latest

    def test_does_not_mutate_observation(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1868", observed_to="1870")
        original_from = obs.observed_from
        original_to = obs.observed_to
        use_as_exact_start(fact, obs)
        assert obs.observed_from == original_from
        assert obs.observed_to == original_to

    def test_with_empty_observed_from(self) -> None:
        """An empty observed_from is still set as both start bounds."""
        fact = _make_fact()
        obs = _make_observation(observed_from="", observed_to="1870")
        result = use_as_exact_start(fact, obs)
        assert result.start.earliest == ""
        assert result.start.latest == ""

    def test_with_absent_start_bounds(self) -> None:
        """Works when the original start bounds are None."""
        fact = _make_fact(start_earliest=None, start_latest=None)
        obs = _make_observation(observed_from="1866")
        result = use_as_exact_start(fact, obs)
        assert result.start.earliest == "1866"
        assert result.start.latest == "1866"


class TestUseAsExactEnd:
    """use_as_exact_end sets both end bounds to obs.observed_to."""

    def test_sets_end_earliest_to_observed_to(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1866", observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.end.earliest == "1872"

    def test_sets_end_latest_to_observed_to(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1866", observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.end.latest == "1872"

    def test_start_earliest_unchanged(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1866", observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.start.earliest == fact.start.earliest

    def test_start_latest_unchanged(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1866", observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.start.latest == fact.start.latest

    def test_end_precision_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.end.precision == "month"

    def test_end_event_id_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.end.event_id == "evt_2"

    def test_end_note_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.end.note == "end note"

    def test_start_precision_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.start.precision == "year"

    def test_start_event_id_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.start.event_id == "evt_1"

    def test_start_note_preserved(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.start.note == "start note"

    def test_observations_list_unchanged(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert len(result.observations) == len(fact.observations)
        assert result.observations[0].observed_from == "1866"
        assert result.observations[0].observed_to == "1870"

    def test_other_fields_unchanged(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_to="1872")
        result = use_as_exact_end(fact, obs)
        assert result.id == "res_1"
        assert result.person_id == "person_1"
        assert result.place_id == "place_1"
        assert result.role_in_household == "husbonde"
        assert result.notes == "Some notes"

    def test_does_not_mutate_original_fact(self) -> None:
        fact = _make_fact()
        original = copy.deepcopy(fact)
        obs = _make_observation(observed_to="1872")
        use_as_exact_end(fact, obs)
        assert fact.end.earliest == original.end.earliest
        assert fact.end.latest == original.end.latest

    def test_does_not_mutate_observation(self) -> None:
        fact = _make_fact()
        obs = _make_observation(observed_from="1866", observed_to="1872")
        original_from = obs.observed_from
        original_to = obs.observed_to
        use_as_exact_end(fact, obs)
        assert obs.observed_from == original_from
        assert obs.observed_to == original_to

    def test_with_empty_observed_to(self) -> None:
        """An empty observed_to is still set as both end bounds."""
        fact = _make_fact()
        obs = _make_observation(observed_from="1866", observed_to="")
        result = use_as_exact_end(fact, obs)
        assert result.end.earliest == ""
        assert result.end.latest == ""

    def test_with_absent_end_bounds(self) -> None:
        """Works when the original end bounds are None."""
        fact = _make_fact(end_earliest=None, end_latest=None)
        obs = _make_observation(observed_to="1870")
        result = use_as_exact_end(fact, obs)
        assert result.end.earliest == "1870"
        assert result.end.latest == "1870"
