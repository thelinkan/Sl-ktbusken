"""Property-based tests for Place coordinate validation.

Tests Property 9 from the place-hierarchy-levels design document.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.place import Place
from slaktbusken.model.validators import validate_place


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALL_PLACE_TYPES = ["continent", "country", "church", "cemetery", "farm", "school", "ort"]


# ---------------------------------------------------------------------------
# Property 9: Coordinates may be None for any place type
# ---------------------------------------------------------------------------


class TestNoneCoordinatesAccepted:
    """Property 9: Coordinates may be None for any place type.

    **Validates: Requirements 4.2**

    For any place of any type with latitude=None and longitude=None,
    validation SHALL NOT produce errors about coordinates.
    """

    @given(
        place_type=st.sampled_from(_ALL_PLACE_TYPES),
        name=st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=100)
    def test_none_coordinates_accepted_for_any_type(self, place_type, name):
        """None lat/lon should never produce coordinate-related errors."""
        parent = None if place_type == "continent" else "parent_1"
        place = Place(
            id="p1",
            type=place_type,
            name=name,
            parent_place_id=parent,
            latitude=None,
            longitude=None,
        )
        errors = validate_place(place, place_lookup=None)
        coord_errors = [e for e in errors if "Latitud" in e or "Longitud" in e]
        assert coord_errors == []
