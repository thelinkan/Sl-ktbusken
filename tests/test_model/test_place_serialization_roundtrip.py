"""Property-based test for Place serialization round-trip.

Feature: place-hierarchy-levels, Property 11: Serialization round-trip preserves Place data

For any valid Place object (including places of type "country" with region_levels
and custom_fields, and places with custom_field_values), serializing then
deserializing SHALL produce an equivalent object.

**Validates: Requirements 9.1, 9.2, 9.3**
"""

from __future__ import annotations

from dataclasses import asdict

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.place import CustomFieldDef, Place, RegionLevel
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.serialization import deserialize, serialize


# ---------------------------------------------------------------------------
# Strategies for Place objects with region_levels and custom_field_values
# ---------------------------------------------------------------------------


@st.composite
def _place_with_region_levels(draw: st.DrawFn) -> Place:
    """Generate a country place with region_levels for round-trip testing."""
    name = draw(st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=1,
        max_size=50,
    ))
    # Generate 1-3 region levels with consecutive orders and unique keys
    count = draw(st.integers(min_value=1, max_value=3))
    keys = draw(st.lists(
        st.text(alphabet=st.characters(categories=("L", "N")), min_size=1, max_size=20),
        min_size=count,
        max_size=count,
        unique=True,
    ))
    levels = []
    for i, key in enumerate(keys):
        label = draw(st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=50,
        ))
        custom_fields = draw(st.lists(
            st.builds(
                CustomFieldDef,
                key=st.text(
                    alphabet=st.characters(categories=("L", "N")),
                    min_size=1,
                    max_size=20,
                ),
                label=st.text(
                    alphabet=st.characters(categories=("L", "N", "Z")),
                    min_size=1,
                    max_size=50,
                ),
            ),
            min_size=0,
            max_size=2,
        ))
        levels.append(RegionLevel(key=key, label=label, order=i + 1, custom_fields=custom_fields))

    return Place(
        id=f"country_{draw(st.integers(1, 999))}",
        type="country",
        name=name,
        parent_place_id="continent_1",
        region_levels=levels,
    )


@st.composite
def _place_with_custom_field_values(draw: st.DrawFn) -> Place:
    """Generate a place with custom_field_values for round-trip testing."""
    name = draw(st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=1,
        max_size=50,
    ))
    values = draw(st.dictionaries(
        keys=st.text(
            alphabet=st.characters(categories=("L", "N")),
            min_size=1,
            max_size=20,
        ),
        values=st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=20,
        ),
        min_size=1,
        max_size=3,
    ))
    return Place(
        id=f"region_{draw(st.integers(1, 999))}",
        type="church",
        name=name,
        parent_place_id="parent_1",
        custom_field_values=values,
    )


# ---------------------------------------------------------------------------
# Property 11: Serialization round-trip preserves Place data
# ---------------------------------------------------------------------------


class TestPlaceSerializationRoundTrip:
    """Property 11: Serialization round-trip preserves Place data.

    For any valid Place object (including places of type "country" with
    region_levels and custom_fields, and places with custom_field_values),
    serializing then deserializing SHALL produce an equivalent object.

    **Validates: Requirements 9.1, 9.2, 9.3**
    """

    @given(place=_place_with_region_levels())
    @settings(max_examples=100, deadline=None)
    def test_round_trip_preserves_region_levels(self, place: Place) -> None:
        """Region levels (with custom_fields) survive serialize/deserialize.

        **Validates: Requirements 9.1, 9.2**
        """
        project = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="Test"),
            places=[place],
        )
        json_str = serialize(project)
        restored = deserialize(json_str)

        assert len(restored.places) == 1
        restored_place = restored.places[0]

        # Verify basic fields
        assert restored_place.id == place.id
        assert restored_place.type == place.type
        assert restored_place.name == place.name
        assert restored_place.parent_place_id == place.parent_place_id

        # Verify region_levels structure
        assert len(restored_place.region_levels) == len(place.region_levels), (
            f"Expected {len(place.region_levels)} region levels, "
            f"got {len(restored_place.region_levels)}"
        )
        for original, restored_rl in zip(place.region_levels, restored_place.region_levels):
            assert restored_rl.key == original.key
            assert restored_rl.label == original.label
            assert restored_rl.order == original.order
            assert len(restored_rl.custom_fields) == len(original.custom_fields)
            for orig_cf, rest_cf in zip(original.custom_fields, restored_rl.custom_fields):
                assert rest_cf.key == orig_cf.key
                assert rest_cf.label == orig_cf.label

    @given(place=_place_with_custom_field_values())
    @settings(max_examples=100, deadline=None)
    def test_round_trip_preserves_custom_field_values(self, place: Place) -> None:
        """Custom field values survive serialize/deserialize.

        **Validates: Requirements 9.2, 9.3**
        """
        project = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="Test"),
            places=[place],
        )
        json_str = serialize(project)
        restored = deserialize(json_str)

        assert len(restored.places) == 1
        restored_place = restored.places[0]

        # Verify custom_field_values dict
        assert restored_place.custom_field_values == place.custom_field_values, (
            f"Expected custom_field_values {place.custom_field_values}, "
            f"got {restored_place.custom_field_values}"
        )

    @given(place=_place_with_region_levels())
    @settings(max_examples=100, deadline=None)
    def test_round_trip_structural_equality(self, place: Place) -> None:
        """Place as dict is identical after round-trip (structural equality).

        **Validates: Requirements 9.1, 9.2, 9.3**
        """
        project = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="Test"),
            places=[place],
        )
        json_str = serialize(project)
        restored = deserialize(json_str)

        assert len(restored.places) == 1
        original_dict = asdict(place)
        restored_dict = asdict(restored.places[0])

        assert original_dict == restored_dict, (
            "Place data not preserved through serialize/deserialize round-trip"
        )
