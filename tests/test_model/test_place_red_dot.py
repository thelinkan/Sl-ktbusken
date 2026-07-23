"""Property-based tests for Red Dot indicator logic.

Tests Property 1 from the place-hierarchy-levels design document.
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from slaktbusken.model.place import Place, needs_red_dot
from tests.conftest import place_strategy


# Feature: place-hierarchy-levels, Property 1: Red dot indicator equivalence
#
# For any place, the red dot indicator SHALL be displayed if and only if the
# place's type is not "continent" AND the place has no parent_place_id assigned.
# After any change to parent_place_id and a list refresh, this rule SHALL hold.


class TestProperty1RedDotIndicator:
    """Property 1: Red dot indicator equivalence."""

    @given(place=place_strategy())
    @settings(max_examples=100)
    def test_non_continent_without_parent_shows_red_dot(self, place: Place) -> None:
        """**Validates: Requirements 5.1**

        For any non-continent place with parent_place_id=None,
        needs_red_dot returns True.
        """
        assume(place.type != "continent")
        assume(place.parent_place_id is None)

        assert needs_red_dot(place) is True

    @given(place=place_strategy())
    @settings(max_examples=100)
    def test_continent_without_parent_no_red_dot(self, place: Place) -> None:
        """**Validates: Requirements 5.2**

        For any continent place with parent_place_id=None,
        needs_red_dot returns False.
        """
        assume(place.type == "continent")
        assume(place.parent_place_id is None)

        assert needs_red_dot(place) is False

    @given(place=place_strategy())
    @settings(max_examples=100)
    def test_any_place_with_parent_no_red_dot(self, place: Place) -> None:
        """**Validates: Requirements 5.3**

        For any place (any type) with parent_place_id set,
        needs_red_dot returns False.
        """
        assume(place.parent_place_id is not None)

        assert needs_red_dot(place) is False

    @given(
        place=place_strategy(),
        new_parent_id=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    )
    @settings(max_examples=100)
    def test_assigning_parent_removes_red_dot(
        self, place: Place, new_parent_id: str
    ) -> None:
        """**Validates: Requirements 5.4**

        After changing parent_place_id from None to a value,
        needs_red_dot changes from True to False (for non-continent places).
        """
        assume(place.type != "continent")

        # Start with no parent — red dot should be shown
        place.parent_place_id = None
        assert needs_red_dot(place) is True

        # Assign a parent — red dot should disappear
        place.parent_place_id = new_parent_id
        assert needs_red_dot(place) is False

    @given(place=place_strategy())
    @settings(max_examples=100)
    def test_removing_parent_shows_red_dot(self, place: Place) -> None:
        """**Validates: Requirements 5.5**

        After changing parent_place_id from a value to None,
        needs_red_dot changes from False to True (for non-continent places).
        """
        assume(place.type != "continent")
        assume(place.parent_place_id is not None)

        # Start with a parent — red dot should not be shown
        assert needs_red_dot(place) is False

        # Remove the parent — red dot should appear
        place.parent_place_id = None
        assert needs_red_dot(place) is True
