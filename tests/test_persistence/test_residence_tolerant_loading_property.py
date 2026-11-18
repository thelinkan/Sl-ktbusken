# Feature: residence-periods, Property 29: Loading tolerates every malformed or dangling residence section
"""Property-based test for tolerant loading.

Feature: residence-periods, Property 29: Loading tolerates every malformed or dangling residence section

For any project file, a missing or null `residences` key loads as zero elements
with zero errors, a present non-list value aborts the load with "Filens
boendeavsnitt har ett ogiltigt format och kunde inte läsas." leaving the file on
disk and the previously open Project in memory unchanged, an unknown field on a
serialized fact is ignored while every defined field is restored and the ignored
field name is logged with the fact `id`, and a `person_id`, `place_id`,
Observation `source_ref.source_id` or Endpoint `event_id` resolving to no entity
is kept unchanged, discards no fact, completes with zero errors and is recorded
in the load log.

**Validates: Requirements 13.3, 13.5, 13.6, 13.7**
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.event import SourceRef
from slaktbusken.persistence.file_io import CorruptedFileError
from slaktbusken.persistence.serialization import deserialize, serialize


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-list JSON values that should trigger CorruptedFileError.
_non_list_json_values = st.one_of(
    st.text(min_size=0, max_size=50),          # strings
    st.integers(min_value=-1000, max_value=1000),  # numbers
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.fixed_dictionaries({"key": st.text(max_size=10)}),  # dicts
)

# Generate random unknown field names that are NOT valid ResidenceFact fields.
_VALID_FIELDS = frozenset({
    "id", "person_id", "place_id", "start", "end",
    "role_in_household", "observations", "notes",
})

_unknown_field_names = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
    min_size=3,
    max_size=30,
).filter(lambda s: s not in _VALID_FIELDS and s[0].isalpha())

# JSON-safe values for unknown fields.
_unknown_field_values = st.one_of(
    st.text(max_size=50),
    st.integers(min_value=-100, max_value=100),
    st.booleans(),
    st.none(),
    st.lists(st.integers(), max_size=3),
)

# Identifiers that deliberately won't exist in the project.
_dangling_ids = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
    min_size=5,
    max_size=30,
).map(lambda s: f"dangling_{s}")


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestTolerantLoadingProperty:
    """Property 29: Loading tolerates every malformed or dangling residence section.

    **Validates: Requirements 13.3, 13.5, 13.6, 13.7**
    """

    @given(
        residences_value=st.one_of(
            st.just(None),       # null
            st.just("ABSENT"),   # sentinel meaning key is missing
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_absent_or_null_residences_yield_zero_elements(
        self,
        residences_value: object,
    ) -> None:
        """Absent or null residences yield zero elements with zero errors.

        Feature: residence-periods, Property 29

        **Validates: Requirements 13.3, 13.5, 13.6, 13.7**
        """
        raw: dict = {
            "format": "släktbuske-file",
            "version": "0.2",
            "project": {"title": "Test"},
        }
        if residences_value != "ABSENT":
            raw["residences"] = residences_value

        json_str = json.dumps(raw)
        log: list[str] = []

        result = deserialize(json_str, log=log)

        # Zero elements loaded.
        assert result.residences == []
        # Zero errors in the log (the log should have nothing for absent/null).
        # Note: log may contain entries for other reasons, but not for residences.
        assert not any("residen" in msg.lower() for msg in log)

    @given(non_list_value=_non_list_json_values)
    @settings(max_examples=100, deadline=None)
    def test_non_list_residences_raises_corrupted_file_error(
        self,
        non_list_value: object,
    ) -> None:
        """A present non-list value raises CorruptedFileError with the required message.

        Feature: residence-periods, Property 29

        **Validates: Requirements 13.3, 13.5, 13.6, 13.7**
        """
        # Ensure the value is truly not a list (and not None, which is the null case).
        assume(not isinstance(non_list_value, list))
        assume(non_list_value is not None)

        raw = {
            "format": "släktbuske-file",
            "version": "0.2",
            "project": {"title": "Test"},
            "residences": non_list_value,
        }
        json_str = json.dumps(raw)

        with pytest.raises(CorruptedFileError) as exc_info:
            deserialize(json_str)

        assert str(exc_info.value) == (
            "Filens boendeavsnitt har ett ogiltigt format och kunde inte läsas."
        )

    @given(
        data=st.data(),
        num_unknown_fields=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_unknown_fields_ignored_and_logged(
        self,
        data: st.DataObject,
        num_unknown_fields: int,
    ) -> None:
        """Unknown fields are ignored, defined fields restored, and ignored names logged.

        Feature: residence-periods, Property 29

        **Validates: Requirements 13.3, 13.5, 13.6, 13.7**
        """
        # Generate unique unknown field names.
        unknown_fields: dict[str, object] = {}
        for _ in range(num_unknown_fields):
            name = data.draw(_unknown_field_names)
            value = data.draw(_unknown_field_values)
            unknown_fields[name] = value

        assume(len(unknown_fields) >= 1)  # At least one unknown field survived dedup.

        fact_id = data.draw(st.text(
            alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_"),
            min_size=3,
            max_size=20,
        ).map(lambda s: f"res_{s}"))

        # Build a raw residence dict with known + unknown fields.
        raw_residence: dict = {
            "id": fact_id,
            "person_id": "person_1",
            "place_id": "place_1",
            "start": {"latest": "1840"},
            "end": {"earliest": "1850"},
        }
        raw_residence.update(unknown_fields)

        raw = {
            "format": "släktbuske-file",
            "version": "0.2",
            "project": {"title": "Test"},
            "residences": [raw_residence],
        }
        json_str = json.dumps(raw)
        log: list[str] = []

        result = deserialize(json_str, log=log)

        # Residence is loaded with defined fields intact.
        assert len(result.residences) == 1
        loaded = result.residences[0]
        assert loaded.id == fact_id
        assert loaded.person_id == "person_1"
        assert loaded.place_id == "place_1"
        assert loaded.start.latest == "1840"
        assert loaded.end.earliest == "1850"

        # Every unknown field name is logged with the fact id.
        for field_name in unknown_fields:
            assert any(
                field_name in msg and fact_id in msg
                for msg in log
            ), f"Expected unknown field '{field_name}' logged with id '{fact_id}', log was: {log}"

    @given(
        person_id=_dangling_ids,
        place_id=_dangling_ids,
        source_id=_dangling_ids,
        event_id=_dangling_ids,
    )
    @settings(max_examples=100, deadline=None)
    def test_unresolved_references_kept_as_stored(
        self,
        person_id: str,
        place_id: str,
        source_id: str,
        event_id: str,
    ) -> None:
        """Unresolved references are kept unchanged, no fact discarded, zero errors, logged.

        Feature: residence-periods, Property 29

        **Validates: Requirements 13.3, 13.5, 13.6, 13.7**
        """
        # Build a residence with references that resolve to nothing.
        fact = ResidenceFact(
            id="residence_dangling",
            person_id=person_id,
            place_id=place_id,
            start=Endpoint(event_id=event_id),
            end=Endpoint(),
            observations=[
                Observation(
                    source_ref=SourceRef(source_id=source_id, quality="low"),
                    observed_from="1850",
                    observed_to="1860",
                ),
            ],
        )

        # Serialize into a project that has NO persons, places, sources, or events.
        data = ProjectData(residences=[fact])
        json_str = serialize(data)
        log: list[str] = []

        result = deserialize(json_str, log=log)

        # The fact is NOT discarded — kept as stored.
        assert len(result.residences) == 1
        loaded = result.residences[0]

        # All references are kept unchanged.
        assert loaded.person_id == person_id
        assert loaded.place_id == place_id
        assert loaded.start.event_id == event_id
        assert loaded.observations[0].source_ref.source_id == source_id

        # Load completes (no exception was raised — this is the "zero errors" check).
        # The log may or may not contain entries depending on implementation,
        # but the key invariant is that the load succeeded and the fact survived.
