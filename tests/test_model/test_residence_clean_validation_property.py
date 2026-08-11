# Feature: residence-periods, Property 1: A well-formed Residence_Fact validates clean
"""Property-based test for clean validation of well-formed residence facts.

Feature: residence-periods, Property 1: A well-formed Residence_Fact validates clean

For any Residence_Fact whose person, place, sources and linked events all exist
in the Project, whose bound values are valid ISO 8601 forms, whose observation
years lie in 1500–2100, whose `notes` is at most 5000 characters, whose
`role_in_household` is at most 100 characters after trimming, and which carries
at most 100 Observations, the Residence_Validator returns an empty list of error
messages — including facts whose place is of any type, whose person/place
combination is shared with other facts, whose Endpoints are both unknown while
Observations are attached, whose Possible_Span overlaps another fact's, whose
Observations share a Source with other facts, and whose Endpoints link the same
Flytt_Event from two different facts.

**Validates: Requirements 1.3, 1.4, 1.10, 1.13, 2.2, 2.8, 4.6, 4.11, 6.1, 10.2, 16.1, 18.3, 18.8, 18.13**
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.date_span import expand_iso, is_valid_iso, strictly_earlier
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.validators import validate_residence
from tests.test_model.residence_strategies import (
    FACT_NOTES_MAX_LENGTH,
    MANY_OBSERVATIONS,
    MIN_PLAUSIBLE_YEAR,
    MAX_PLAUSIBLE_YEAR,
    NOTE_MAX_LENGTH,
    ROLE_MAX_LENGTH,
    consistent_projects,
)


def _bound_is_absent_or_valid(value: str | None) -> bool:
    """Return True when a bound value is absent (Requirement 2.1) or a valid ISO form."""
    if value is None or not value.strip():
        return True
    return is_valid_iso(value.strip())


def _endpoint_well_formed(ep: Endpoint, valid_event_ids: set[str]) -> bool:
    """Check all well-formedness constraints on one Endpoint."""
    # Bounds must be absent or valid ISO (no malformed values).
    if not _bound_is_absent_or_valid(ep.earliest):
        return False
    if not _bound_is_absent_or_valid(ep.latest):
        return False
    # Inverted bounds: latest strictly before earliest → yields error 2.9.
    if strictly_earlier(ep.latest, ep.earliest):
        return False
    # Note length: at most 1000 characters (Requirement 2.14).
    if ep.note is not None and len(ep.note) > NOTE_MAX_LENGTH:
        return False
    # Event reference must resolve if present (Requirement 2.12).
    if ep.event_id is not None and ep.event_id not in valid_event_ids:
        return False
    return True


def _observation_year_valid(value: str) -> bool:
    """A valid observation year: empty/whitespace (absent) or 4-digit in 1500–2100."""
    stripped = value.strip()
    if not stripped:
        return True
    if len(stripped) != 4 or not stripped.isdigit():
        return False
    year = int(stripped)
    return MIN_PLAUSIBLE_YEAR <= year <= MAX_PLAUSIBLE_YEAR


def _observation_well_formed(obs: Observation, valid_source_ids: set[str]) -> bool:
    """Check all well-formedness constraints on one Observation."""
    # Year values must be absent or valid 4-digit years in 1500–2100.
    if not _observation_year_valid(obs.observed_from):
        return False
    if not _observation_year_valid(obs.observed_to):
        return False
    # Inverted span: from > to (Requirement 4.4).
    from_stripped = obs.observed_from.strip()
    to_stripped = obs.observed_to.strip()
    if from_stripped and to_stripped:
        if int(from_stripped) > int(to_stripped):
            return False
    # Source reference must resolve (Requirement 4.5).
    if obs.source_ref.source_id not in valid_source_ids:
        return False
    return True


def _residence_well_formed(
    residence: ResidenceFact,
    valid_person_ids: set[str],
    valid_place_ids: set[str],
    valid_source_ids: set[str],
    valid_event_ids: set[str],
) -> bool:
    """Check all well-formedness constraints that make validate_residence return []."""
    # person_id and place_id must be non-blank and resolve (Req 1.5, 1.6, 1.7).
    if not residence.person_id.strip():
        return False
    if not residence.place_id.strip():
        return False
    if residence.person_id not in valid_person_ids:
        return False
    if residence.place_id not in valid_place_ids:
        return False
    # Text length constraints.
    if len(residence.notes) > FACT_NOTES_MAX_LENGTH:
        return False
    if len(residence.role_in_household.strip()) > ROLE_MAX_LENGTH:
        return False
    # Endpoint well-formedness.
    if not _endpoint_well_formed(residence.start, valid_event_ids):
        return False
    if not _endpoint_well_formed(residence.end, valid_event_ids):
        return False
    # Cross-endpoint: end.latest strictly before start.earliest (Req 2.10).
    if strictly_earlier(residence.end.latest, residence.start.earliest):
        return False
    # Observation count (Requirement 4.2).
    if len(residence.observations) > MANY_OBSERVATIONS:
        return False
    # Each Observation must be well-formed.
    for obs in residence.observations:
        if not _observation_well_formed(obs, valid_source_ids):
            return False
    return True


class TestCleanValidation:
    """Property 1: A well-formed Residence_Fact validates clean.

    For any Residence_Fact whose person, place, sources and linked events all
    exist in the Project, whose bound values are valid ISO 8601 forms, whose
    observation years lie in 1500–2100, whose `notes` is at most 5000
    characters, whose `role_in_household` is at most 100 characters after
    trimming, and which carries at most 100 Observations, the
    Residence_Validator returns an empty list of error messages.

    **Validates: Requirements 1.3, 1.4, 1.10, 1.13, 2.2, 2.8, 4.6, 4.11, 6.1, 10.2, 16.1, 18.3, 18.8, 18.13**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_well_formed_residence_validates_clean(self, data: st.DataObject) -> None:
        """A well-formed Residence_Fact validates with zero errors.

        Feature: residence-periods, Property 1: A well-formed Residence_Fact validates clean

        **Validates: Requirements 1.3, 1.4, 1.10, 1.13, 2.2, 2.8, 4.6, 4.11, 6.1, 10.2, 16.1, 18.3, 18.8, 18.13**
        """
        project = data.draw(
            consistent_projects(
                min_persons=1,
                max_persons=3,
                min_places=1,
                max_places=3,
                max_sources=3,
                max_events=3,
                min_residences=1,
                max_residences=4,
                include_many_observations=False,
            )
        )

        person_ids = {p.id for p in project.persons}
        place_ids = {p.id for p in project.places}
        source_ids = {s.id for s in project.sources}
        event_ids = {e.id for e in project.events}

        # Find a residence that passes all well-formedness checks. The
        # consistent_projects strategy guarantees referential integrity, but
        # facts may still have malformed ISO values, inverted bounds, or
        # over-limit text fields. We filter rather than assume on the whole
        # project so we get at least one testable fact per drawn project.
        well_formed_found = False
        for residence in project.residences:
            if not _residence_well_formed(
                residence, person_ids, place_ids, source_ids, event_ids
            ):
                continue

            well_formed_found = True
            errors = validate_residence(
                residence,
                valid_person_ids=person_ids,
                valid_place_ids=place_ids,
                valid_source_ids=source_ids,
                valid_event_ids=event_ids,
            )

            assert errors == [], (
                f"Well-formed residence {residence.id!r} produced errors: {errors}"
            )

        # If no residence in the project happened to be well-formed, skip this
        # draw rather than fail — the property is "for any well-formed fact"
        # and the strategy will find well-formed ones in other draws.
        assume(well_formed_found)
