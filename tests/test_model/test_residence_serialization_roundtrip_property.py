# Feature: residence-periods, Property 28: A Residence_Fact survives a serialization round trip
"""Property-based test for serialization round trip.

Feature: residence-periods, Property 28: A Residence_Fact survives a serialization round trip

For any Residence_Fact, serializing and then deserializing yields a fact equal to
the original field by field on `id`, `person_id`, `place_id`, `start`, `end`,
`role_in_household`, `observations` and `notes`, where an absent Endpoint
`earliest`, `latest`, `precision`, `event_id` or `note` returns absent and never
an empty string, an empty string in any of those fields returns an empty string
and never absent, an empty `role_in_household` returns an empty string, and every
Observation returns with its own `source_ref`, `observed_from`, `observed_to` and
`page_note` in the same list position; for any Project, the `residences` collection
is written in its stored order.

**Validates: Requirements 13.1, 13.2**
"""

from __future__ import annotations

from hypothesis import given, settings

from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.persistence.serialization import deserialize, serialize
from tests.test_model.residence_strategies import consistent_projects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_endpoint_equal(original: Endpoint, restored: Endpoint, label: str) -> None:
    """Assert two Endpoints are field-by-field identical, respecting absent vs empty."""
    # Requirement 13.2: absent deserializes as absent (None), never as ""
    # and "" deserializes as "", never as None.
    assert restored.earliest is original.earliest or restored.earliest == original.earliest, (
        f"{label}.earliest: expected {original.earliest!r}, got {restored.earliest!r}"
    )
    # Verify the absent-vs-empty distinction
    if original.earliest is None:
        assert restored.earliest is None, (
            f"{label}.earliest: absent value deserialized as {restored.earliest!r}, expected None"
        )
    elif original.earliest == "":
        assert restored.earliest == "", (
            f"{label}.earliest: empty string deserialized as {restored.earliest!r}, expected ''"
        )
    else:
        assert restored.earliest == original.earliest, (
            f"{label}.earliest: expected {original.earliest!r}, got {restored.earliest!r}"
        )

    if original.latest is None:
        assert restored.latest is None, (
            f"{label}.latest: absent value deserialized as {restored.latest!r}, expected None"
        )
    elif original.latest == "":
        assert restored.latest == "", (
            f"{label}.latest: empty string deserialized as {restored.latest!r}, expected ''"
        )
    else:
        assert restored.latest == original.latest, (
            f"{label}.latest: expected {original.latest!r}, got {restored.latest!r}"
        )

    if original.precision is None:
        assert restored.precision is None, (
            f"{label}.precision: absent value deserialized as {restored.precision!r}, expected None"
        )
    elif original.precision == "":
        assert restored.precision == "", (
            f"{label}.precision: empty string deserialized as {restored.precision!r}, expected ''"
        )
    else:
        assert restored.precision == original.precision, (
            f"{label}.precision: expected {original.precision!r}, got {restored.precision!r}"
        )

    if original.event_id is None:
        assert restored.event_id is None, (
            f"{label}.event_id: absent value deserialized as {restored.event_id!r}, expected None"
        )
    elif original.event_id == "":
        assert restored.event_id == "", (
            f"{label}.event_id: empty string deserialized as {restored.event_id!r}, expected ''"
        )
    else:
        assert restored.event_id == original.event_id, (
            f"{label}.event_id: expected {original.event_id!r}, got {restored.event_id!r}"
        )

    if original.note is None:
        assert restored.note is None, (
            f"{label}.note: absent value deserialized as {restored.note!r}, expected None"
        )
    elif original.note == "":
        assert restored.note == "", (
            f"{label}.note: empty string deserialized as {restored.note!r}, expected ''"
        )
    else:
        assert restored.note == original.note, (
            f"{label}.note: expected {original.note!r}, got {restored.note!r}"
        )


def _assert_observation_equal(original: Observation, restored: Observation, index: int) -> None:
    """Assert two Observations are field-by-field identical at the same list position."""
    # source_ref fields
    assert restored.source_ref.source_id == original.source_ref.source_id, (
        f"observations[{index}].source_ref.source_id: "
        f"expected {original.source_ref.source_id!r}, got {restored.source_ref.source_id!r}"
    )
    assert restored.source_ref.quality == original.source_ref.quality, (
        f"observations[{index}].source_ref.quality: "
        f"expected {original.source_ref.quality!r}, got {restored.source_ref.quality!r}"
    )
    assert restored.source_ref.note == original.source_ref.note, (
        f"observations[{index}].source_ref.note: "
        f"expected {original.source_ref.note!r}, got {restored.source_ref.note!r}"
    )
    assert restored.source_ref.aspects == original.source_ref.aspects, (
        f"observations[{index}].source_ref.aspects: "
        f"expected {original.source_ref.aspects!r}, got {restored.source_ref.aspects!r}"
    )

    # Observation's own fields
    assert restored.observed_from == original.observed_from, (
        f"observations[{index}].observed_from: "
        f"expected {original.observed_from!r}, got {restored.observed_from!r}"
    )
    assert restored.observed_to == original.observed_to, (
        f"observations[{index}].observed_to: "
        f"expected {original.observed_to!r}, got {restored.observed_to!r}"
    )
    assert restored.page_note == original.page_note, (
        f"observations[{index}].page_note: "
        f"expected {original.page_note!r}, got {restored.page_note!r}"
    )


def _assert_residence_equal(original: ResidenceFact, restored: ResidenceFact) -> None:
    """Assert two ResidenceFacts are field-by-field identical."""
    assert restored.id == original.id, (
        f"id: expected {original.id!r}, got {restored.id!r}"
    )
    assert restored.person_id == original.person_id, (
        f"person_id: expected {original.person_id!r}, got {restored.person_id!r}"
    )
    assert restored.place_id == original.place_id, (
        f"place_id: expected {original.place_id!r}, got {restored.place_id!r}"
    )

    # Endpoints
    _assert_endpoint_equal(original.start, restored.start, "start")
    _assert_endpoint_equal(original.end, restored.end, "end")

    # role_in_household: empty deserializes as "" (never absent)
    assert restored.role_in_household == original.role_in_household, (
        f"role_in_household: expected {original.role_in_household!r}, "
        f"got {restored.role_in_household!r}"
    )

    # notes
    assert restored.notes == original.notes, (
        f"notes: expected {original.notes!r}, got {restored.notes!r}"
    )

    # Observations: same count and same list position
    assert len(restored.observations) == len(original.observations), (
        f"observations count: expected {len(original.observations)}, "
        f"got {len(restored.observations)}"
    )
    for i, (orig_obs, rest_obs) in enumerate(
        zip(original.observations, restored.observations)
    ):
        _assert_observation_equal(orig_obs, rest_obs, i)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSerializationRoundTripProperty:
    """Property 28: A Residence_Fact survives a serialization round trip.

    For any consistent project with residences, serialize then deserialize
    produces identical residences (field by field, including the absent-vs-empty
    distinction and observation order).

    **Validates: Requirements 13.1, 13.2**
    """

    @given(
        project=consistent_projects(
            min_residences=1,
            max_residences=4,
            include_many_observations=False,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_residence_fact_survives_round_trip(
        self,
        project: ProjectData,
    ) -> None:
        """A Residence_Fact survives a serialization round trip field by field.

        For any consistent project with residences, serialize then deserialize
        produces identical residences — field by field, including the
        absent-vs-empty distinction and observation order.

        Feature: residence-periods, Property 28: A Residence_Fact survives a serialization round trip

        **Validates: Requirements 13.1, 13.2**
        """
        # Serialize and deserialize the project.
        json_str = serialize(project)
        restored = deserialize(json_str)

        # Requirement 13.1: residences are written in stored order.
        assert len(restored.residences) == len(project.residences), (
            f"Expected {len(project.residences)} residences, got {len(restored.residences)}"
        )

        # Requirement 13.2: every fact is equal field by field.
        for original, restored_fact in zip(project.residences, restored.residences):
            _assert_residence_equal(original, restored_fact)
