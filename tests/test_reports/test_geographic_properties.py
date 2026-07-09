"""Property-based tests for geographic consistency report.

Feature: report-menu
Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.reports.content import HeadingBlock
from slaktbusken.reports.geographic import (
    check_geographic_consistency,
    generate_geographic_report,
)

from tests.conftest import place_strategy


_PLACE_TYPES = ["country", "county", "parish", "church", "cemetery", "village", "farm", "school"]
_SUB_PARISH_TYPES = frozenset({"church", "cemetery", "village", "farm", "school"})


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def non_empty_project_data(draw: DrawFn) -> ProjectData:
    """Generate ProjectData with at least one Place so the empty-state shortcut is not hit."""
    places = draw(st.lists(place_strategy(), min_size=1, max_size=10))
    metadata = ProjectMetadata(title=draw(st.text(min_size=1, max_size=50)))
    return ProjectData(
        project=metadata,
        places=places,
    )


@st.composite
def place_hierarchy_strategy(draw: DrawFn) -> list[Place]:
    """Generate a list of places with valid interconnected parent_place_id references.

    Each place's parent_place_id is either None or points to an already-created
    place, ensuring no dangling references (though cycles are still impossible
    by construction since parents reference earlier places).
    """
    n = draw(st.integers(min_value=1, max_value=15))
    places: list[Place] = []

    for i in range(n):
        place_id = f"place_{i}"
        place_type = draw(st.sampled_from(_PLACE_TYPES))
        name = draw(st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=30,
        ))
        # Parent is either None or one of the previously created places
        if places:
            parent_place_id = draw(
                st.none() | st.sampled_from([p.id for p in places])
            )
        else:
            parent_place_id = None

        latitude = draw(st.none() | st.floats(min_value=-90.0, max_value=90.0, allow_nan=False))
        longitude = draw(st.none() | st.floats(min_value=-180.0, max_value=180.0, allow_nan=False))

        places.append(Place(
            id=place_id,
            type=place_type,
            name=name,
            parent_place_id=parent_place_id,
            latitude=latitude,
            longitude=longitude,
        ))

    return places


# ---------------------------------------------------------------------------
# Oracle functions (independent verification)
# ---------------------------------------------------------------------------


def _oracle_has_ancestor_of_type(
    place: Place,
    ancestor_type: str,
    places_by_id: dict[str, Place],
) -> bool:
    """Independent oracle: walk parent chain to check for ancestor of given type."""
    visited: set[str] = {place.id}
    current_id = place.parent_place_id

    while current_id is not None:
        if current_id in visited:
            return False
        if current_id not in places_by_id:
            return False
        parent = places_by_id[current_id]
        if parent.type == ancestor_type:
            return True
        visited.add(current_id)
        current_id = parent.parent_place_id

    return False


def _oracle_compute_hierarchy_violations(places: list[Place]) -> set[str]:
    """Oracle: compute the set of place IDs that have hierarchy violations."""
    places_by_id = {p.id: p for p in places}
    violations: set[str] = set()

    for place in places:
        if place.type == "county":
            if not _oracle_has_ancestor_of_type(place, "country", places_by_id):
                violations.add(place.id)
        elif place.type == "parish":
            if not _oracle_has_ancestor_of_type(place, "county", places_by_id):
                violations.add(place.id)
        elif place.type in _SUB_PARISH_TYPES:
            if not _oracle_has_ancestor_of_type(place, "parish", places_by_id):
                violations.add(place.id)

    return violations


# ---------------------------------------------------------------------------
# Property 2: Geographic hierarchy violation detection
# Feature: report-menu, Property 2: Geographic hierarchy violation detection
# ---------------------------------------------------------------------------


@given(places=place_hierarchy_strategy())
@settings(max_examples=100)
def test_hierarchy_violation_detection_matches_oracle(places: list[Place]) -> None:
    """For any set of Place records, check_geographic_consistency returns hierarchy issues
    for exactly the places that lack the required ancestor type.

    Validates: Requirements 3.2, 3.3, 3.4
    """
    issues = check_geographic_consistency(places)

    # Extract hierarchy violation IDs from the actual function output
    hierarchy_check_types = {"county_no_country", "parish_no_county", "sub_no_parish"}
    actual_violation_ids = {
        issue.place_id for issue in issues if issue.check_type in hierarchy_check_types
    }

    # Compute expected violations using oracle
    expected_violation_ids = _oracle_compute_hierarchy_violations(places)

    assert actual_violation_ids == expected_violation_ids, (
        f"Mismatch: actual={actual_violation_ids}, expected={expected_violation_ids}"
    )


# ---------------------------------------------------------------------------
# Property 3: Parish missing coordinates detection
# Feature: report-menu, Property 3: Parish missing coordinates detection
# ---------------------------------------------------------------------------


@given(places=place_hierarchy_strategy())
@settings(max_examples=100)
def test_parish_missing_coordinates_detection(places: list[Place]) -> None:
    """For any set of Place records, check_geographic_consistency returns missing_coords
    issues for exactly the parishes with latitude unset, longitude unset, or both.

    Validates: Requirements 3.5
    """
    issues = check_geographic_consistency(places)

    # Extract missing_coords issue IDs from actual output
    actual_missing_coords_ids = {
        issue.place_id for issue in issues if issue.check_type == "missing_coords"
    }

    # Oracle: compute expected set of parishes missing coordinates
    expected_missing_coords_ids = {
        place.id
        for place in places
        if place.type == "parish" and (place.latitude is None or place.longitude is None)
    }

    assert actual_missing_coords_ids == expected_missing_coords_ids, (
        f"Mismatch: actual={actual_missing_coords_ids}, expected={expected_missing_coords_ids}"
    )


# ---------------------------------------------------------------------------
# Property 8: Report section structure (geographic)
# Feature: report-menu, Property 8: Report section structure
# ---------------------------------------------------------------------------


@given(data=non_empty_project_data())
@settings(max_examples=100)
def test_geographic_report_has_exactly_four_section_headings(data: ProjectData) -> None:
    """For any non-empty places list, the geographic report contains exactly 4 level-2 headings
    with the expected Swedish section names.

    Validates: Requirements 3.6
    """
    report = generate_geographic_report(data)

    headings = [b for b in report.blocks if isinstance(b, HeadingBlock) and b.level == 2]

    expected_headings = [
        "Län utan land",
        "Församlingar utan län",
        "Undertyper utan församling",
        "Församlingar utan koordinater",
    ]

    assert len(headings) == 4, (
        f"Expected exactly 4 level-2 headings, got {len(headings)}"
    )

    actual_texts = [h.text for h in headings]
    assert actual_texts == expected_headings, (
        f"Expected headings {expected_headings}, got {actual_texts}"
    )
