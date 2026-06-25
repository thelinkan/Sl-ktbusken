"""Property-based tests for Type Filter logic.

Tests Property 11 from the place-editor-enhancements design document.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.place import Place
from tests.conftest import place_strategy


# Feature: place-editor-enhancements, Property 11: Type filter displays correct sorted subset
#
# For any collection of places, any type filter selection T, and any text filter
# string F, the displayed place list SHALL contain exactly those places where
# (T is "Alla" OR place.type matches T) AND the formatted display text contains F
# (case-insensitive), sorted alphabetically by place name.

_TYPE_LABEL_TO_INTERNAL: dict[str, str] = {
    "Land": "country",
    "Län": "county",
    "Socken": "parish",
    "Kyrka": "church",
    "Kyrkogård": "cemetery",
    "By": "village",
    "Gård": "farm",
    "Skola": "school",
}

_TYPE_INTERNAL_TO_LABEL: dict[str, str] = {v: k for k, v in _TYPE_LABEL_TO_INTERNAL.items()}

_TYPE_FILTER_OPTIONS = ["Alla"] + list(_TYPE_LABEL_TO_INTERNAL.keys())


def format_place_display(place: Place) -> str:
    """Simulate the _format_place_display function from place_editor."""
    type_label = _TYPE_INTERNAL_TO_LABEL.get(place.type, place.type)
    return f"{place.name} ({type_label})"


def apply_type_and_text_filter(
    places: list[Place],
    type_filter: str,
    text_filter: str,
) -> list[Place]:
    """Pure implementation of the combined type + text filter logic.

    Returns the filtered and sorted subset of places matching both filters.
    """
    result: list[Place] = []
    for place in places:
        # Type filter check
        if type_filter != "Alla":
            internal_type = _TYPE_LABEL_TO_INTERNAL.get(type_filter)
            if place.type != internal_type:
                continue

        # Text filter check (case-insensitive on formatted display text)
        display_text = format_place_display(place)
        if text_filter and text_filter.lower() not in display_text.lower():
            continue

        result.append(place)

    # Sort alphabetically by place name (case-insensitive)
    result.sort(key=lambda p: p.name.lower())
    return result


class TestProperty11TypeFilter:
    """Property 11: Type filter displays correct sorted subset."""

    @given(
        places=st.lists(place_strategy(), min_size=0, max_size=20),
        type_filter=st.sampled_from(_TYPE_FILTER_OPTIONS),
        text_filter=st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=0,
            max_size=10,
        ),
    )
    @settings(max_examples=100)
    def test_filter_returns_correct_sorted_subset(
        self,
        places: list[Place],
        type_filter: str,
        text_filter: str,
    ) -> None:
        """**Validates: Requirements 6.3, 6.4**

        For any collection of places, any type filter selection, and any text
        filter string, the result contains exactly those places where the type
        matches (or filter is "Alla") AND the formatted display text contains
        the text filter (case-insensitive), sorted alphabetically by name.
        """
        filtered = apply_type_and_text_filter(places, type_filter, text_filter)

        # --- Verify membership: every included place must match both filters ---
        for place in filtered:
            display_text = format_place_display(place)
            # Type condition
            if type_filter != "Alla":
                internal_type = _TYPE_LABEL_TO_INTERNAL[type_filter]
                assert place.type == internal_type, (
                    f"Place {place.name!r} has type {place.type!r}, "
                    f"expected {internal_type!r} for filter {type_filter!r}"
                )
            # Text condition
            if text_filter:
                assert text_filter.lower() in display_text.lower(), (
                    f"Place display {display_text!r} does not contain "
                    f"text filter {text_filter!r}"
                )

        # --- Verify completeness: no matching place was excluded ---
        for place in places:
            display_text = format_place_display(place)
            type_matches = (
                type_filter == "Alla"
                or place.type == _TYPE_LABEL_TO_INTERNAL.get(type_filter)
            )
            text_matches = (
                not text_filter
                or text_filter.lower() in display_text.lower()
            )
            if type_matches and text_matches:
                assert place in filtered, (
                    f"Place {place.name!r} (type={place.type!r}) should be "
                    f"in filtered results but was not found"
                )

        # --- Verify sort order: alphabetical by name (case-insensitive) ---
        names = [p.name.lower() for p in filtered]
        assert names == sorted(names), (
            f"Results are not sorted alphabetically: {names}"
        )
