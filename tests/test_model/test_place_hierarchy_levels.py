"""Property-based tests for Place hierarchy level validation.

Tests Properties 2, 3, 5, and 8 from the place-hierarchy-levels design document.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.place import Place, RegionLevel
from slaktbusken.model.validators import validate_place, _UNIVERSAL_PLACE_TYPES
from tests.conftest import region_level_strategy


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_safe_name = st.text(
    alphabet=st.characters(categories=("L", "N", "Z")),
    min_size=1,
    max_size=50,
)

# Region level keys used in generated hierarchies
_REGION_LEVEL_KEYS = ["lan", "socken", "harad", "kommun", "distrikt"]

# Non-continent types for generating wrong-parent places in Property 3
_NON_CONTINENT_TYPES = ["country", "church", "cemetery", "farm", "school", "ort"]

_PLACE_ID = st.integers(min_value=1, max_value=9999).map(lambda n: f"place_{n}")


@st.composite
def _region_level_key_strategy(draw: DrawFn) -> str:
    """Draw a valid region level key from predefined options."""
    return draw(st.sampled_from(_REGION_LEVEL_KEYS))


@st.composite
def _hierarchy_with_universal_child(draw: DrawFn) -> tuple[dict[str, Place], Place]:
    """Build a valid hierarchy and a universal-type place as child of a region-level place.

    Returns (place_lookup, universal_place) where universal_place should
    produce no hierarchy errors when validated against the lookup.
    """
    # Pick a region level key for the country
    rl_key = draw(_region_level_key_strategy())

    # Create continent
    continent_name = draw(_safe_name)
    continent = Place(
        id="continent_1",
        type="continent",
        name=continent_name,
        parent_place_id=None,
    )

    # Create country with one region level
    country_name = draw(_safe_name)
    country = Place(
        id="country_1",
        type="country",
        name=country_name,
        parent_place_id="continent_1",
        region_levels=[RegionLevel(key=rl_key, label=rl_key.capitalize(), order=1)],
    )

    # Create a region-level place (child of country)
    region_name = draw(_safe_name)
    region_place = Place(
        id="region_1",
        type=rl_key,
        name=region_name,
        parent_place_id="country_1",
    )

    # Pick a universal type to test
    universal_type = draw(st.sampled_from(sorted(_UNIVERSAL_PLACE_TYPES)))

    # Create the universal-type place as child of the region-level place
    place_name = draw(_safe_name)
    universal_place = Place(
        id="universal_1",
        type=universal_type,
        name=place_name,
        parent_place_id="region_1",
    )

    lookup = {
        "continent_1": continent,
        "country_1": country,
        "region_1": region_place,
        "universal_1": universal_place,
    }

    return lookup, universal_place


@st.composite
def _hierarchy_with_universal_child_of_ort(draw: DrawFn) -> tuple[dict[str, Place], Place]:
    """Build a valid hierarchy with a universal-type place as child of 'ort'.

    Returns (place_lookup, universal_place) where universal_place should
    produce no hierarchy errors.
    """
    rl_key = draw(_region_level_key_strategy())

    continent = Place(
        id="continent_1",
        type="continent",
        name=draw(_safe_name),
        parent_place_id=None,
    )

    country = Place(
        id="country_1",
        type="country",
        name=draw(_safe_name),
        parent_place_id="continent_1",
        region_levels=[RegionLevel(key=rl_key, label=rl_key.capitalize(), order=1)],
    )

    region_place = Place(
        id="region_1",
        type=rl_key,
        name=draw(_safe_name),
        parent_place_id="country_1",
    )

    # Create a locality (ort) as child of the region-level place
    ort_place = Place(
        id="ort_1",
        type="ort",
        name=draw(_safe_name),
        parent_place_id="region_1",
    )

    # Pick a universal type
    universal_type = draw(st.sampled_from(sorted(_UNIVERSAL_PLACE_TYPES)))

    # Create the universal-type place as child of the ort
    universal_place = Place(
        id="universal_1",
        type=universal_type,
        name=draw(_safe_name),
        parent_place_id="ort_1",
    )

    lookup = {
        "continent_1": continent,
        "country_1": country,
        "region_1": region_place,
        "ort_1": ort_place,
        "universal_1": universal_place,
    }

    return lookup, universal_place


@st.composite
def _hierarchy_with_locality_child(draw: DrawFn) -> tuple[dict[str, Place], Place]:
    """Build a valid hierarchy with a locality (ort) as child of a region-level place.

    Returns (place_lookup, ort_place) where ort_place should produce no
    hierarchy errors.
    """
    rl_key = draw(_region_level_key_strategy())

    continent = Place(
        id="continent_1",
        type="continent",
        name=draw(_safe_name),
        parent_place_id=None,
    )

    country = Place(
        id="country_1",
        type="country",
        name=draw(_safe_name),
        parent_place_id="continent_1",
        region_levels=[RegionLevel(key=rl_key, label=rl_key.capitalize(), order=1)],
    )

    region_place = Place(
        id="region_1",
        type=rl_key,
        name=draw(_safe_name),
        parent_place_id="country_1",
    )

    # Create a locality (ort) as child of the region-level place
    ort_place = Place(
        id="ort_1",
        type="ort",
        name=draw(_safe_name),
        parent_place_id="region_1",
    )

    lookup = {
        "continent_1": continent,
        "country_1": country,
        "region_1": region_place,
        "ort_1": ort_place,
    }

    return lookup, ort_place


# ---------------------------------------------------------------------------
# Feature: place-hierarchy-levels, Property 2: Continent hierarchy enforcement
#
# For any place with type "continent", validation SHALL reject the place if
# and only if parent_place_id is not None. Conversely, a continent with
# parent_place_id = None SHALL pass hierarchy validation.
# ---------------------------------------------------------------------------


class TestProperty2ContinentHierarchyEnforcement:
    """Property 2: Continent hierarchy enforcement.

    **Validates: Requirements 1.2, 1.3**
    """

    @given(
        name=_safe_name,
        place_id=_PLACE_ID,
    )
    @settings(max_examples=100)
    def test_continent_with_no_parent_accepted(self, name: str, place_id: str) -> None:
        """**Validates: Requirements 1.2**

        A continent with parent_place_id = None produces NO hierarchy errors.
        """
        continent = Place(
            id=place_id,
            type="continent",
            name=name,
            parent_place_id=None,
        )

        errors = validate_place(continent)

        # No hierarchy error about continents should appear
        assert "En kontinent får inte ha en överordnad plats." not in errors

    @given(
        name=_safe_name,
        place_id=_PLACE_ID,
        parent_id=_PLACE_ID,
    )
    @settings(max_examples=100)
    def test_continent_with_parent_rejected(self, name: str, place_id: str, parent_id: str) -> None:
        """**Validates: Requirements 1.3**

        A continent with parent_place_id set to any non-None value produces
        the error: "En kontinent får inte ha en överordnad plats."
        """
        continent = Place(
            id=place_id,
            type="continent",
            name=name,
            parent_place_id=parent_id,
        )

        errors = validate_place(continent)

        assert "En kontinent får inte ha en överordnad plats." in errors

    @given(
        name=_safe_name,
        place_id=_PLACE_ID,
        parent_id=st.none() | _PLACE_ID,
    )
    @settings(max_examples=100)
    def test_continent_rejected_iff_parent_not_none(
        self, name: str, place_id: str, parent_id: str | None
    ) -> None:
        """**Validates: Requirements 1.2, 1.3**

        Biconditional: a continent is rejected iff parent_place_id is not None.
        """
        continent = Place(
            id=place_id,
            type="continent",
            name=name,
            parent_place_id=parent_id,
        )

        errors = validate_place(continent)
        has_hierarchy_error = "En kontinent får inte ha en överordnad plats." in errors

        if parent_id is not None:
            assert has_hierarchy_error, (
                f"Continent with parent_place_id={parent_id!r} should be rejected"
            )
        else:
            assert not has_hierarchy_error, (
                "Continent with parent_place_id=None should be accepted"
            )


# ---------------------------------------------------------------------------
# Feature: place-hierarchy-levels, Property 3: Country parent must be continent
#
# For any place with type "country", validation SHALL reject the place if
# parent_place_id is None or if it references a place whose type is not
# "continent". Validation SHALL accept the place when its parent is of type
# "continent".
# ---------------------------------------------------------------------------


class TestProperty3CountryParentMustBeContinent:
    """Property 3: Country parent must be continent.

    **Validates: Requirements 1.4, 1.5, 1.6**
    """

    @given(
        name=_safe_name,
        place_id=_PLACE_ID,
    )
    @settings(max_examples=100)
    def test_country_without_parent_rejected(self, name: str, place_id: str) -> None:
        """**Validates: Requirements 1.4**

        A country with parent_place_id = None produces the error:
        "Ett land måste ha en kontinent som överordnad plats."
        """
        country = Place(
            id=place_id,
            type="country",
            name=name,
            parent_place_id=None,
        )

        errors = validate_place(country)

        assert "Ett land måste ha en kontinent som överordnad plats." in errors

    @given(
        country_name=_safe_name,
        wrong_parent_type=st.sampled_from(_NON_CONTINENT_TYPES),
        wrong_parent_name=_safe_name,
    )
    @settings(max_examples=100)
    def test_country_with_non_continent_parent_rejected(
        self, country_name: str, wrong_parent_type: str, wrong_parent_name: str
    ) -> None:
        """**Validates: Requirements 1.5**

        A country with parent_place_id pointing to a non-continent place
        produces the error:
        "Ett lands överordnade plats måste vara av typen 'kontinent'."
        """
        # Create country referencing the wrong parent
        country_place = Place(
            id="country_1",
            type="country",
            name=country_name,
            parent_place_id="wrong_parent_1",
        )

        # Create the non-continent parent
        wrong_parent = Place(
            id="wrong_parent_1",
            type=wrong_parent_type,
            name=wrong_parent_name,
            parent_place_id=None,
        )

        # Build a place_lookup dict so validate_place can check the parent type
        place_lookup = {
            "wrong_parent_1": wrong_parent,
            "country_1": country_place,
        }

        errors = validate_place(country_place, place_lookup=place_lookup)

        assert "Ett lands överordnade plats måste vara av typen 'kontinent'." in errors

    @given(
        country_name=_safe_name,
        continent_name=_safe_name,
    )
    @settings(max_examples=100)
    def test_country_with_continent_parent_accepted(
        self, country_name: str, continent_name: str
    ) -> None:
        """**Validates: Requirements 1.6**

        A country with parent_place_id pointing to a continent place
        produces NO hierarchy-related errors.
        """
        # Create continent
        continent = Place(
            id="continent_1",
            type="continent",
            name=continent_name,
            parent_place_id=None,
        )

        # Create country referencing the continent
        country_place = Place(
            id="country_1",
            type="country",
            name=country_name,
            parent_place_id="continent_1",
        )

        # Build a place_lookup dict so validate_place can verify parent type
        place_lookup = {
            "continent_1": continent,
            "country_1": country_place,
        }

        errors = validate_place(country_place, place_lookup=place_lookup)

        # No hierarchy errors should be present
        hierarchy_errors = [
            "Ett land måste ha en kontinent som överordnad plats.",
            "Ett lands överordnade plats måste vara av typen 'kontinent'.",
        ]
        for err in hierarchy_errors:
            assert err not in errors


# ---------------------------------------------------------------------------
# Feature: place-hierarchy-levels, Property 8: Universal types and locality
# valid as children of any region level
#
# For any place of a universal type (church, cemetery, farm, school) or
# locality (ort), and for any valid region level type as its parent,
# hierarchy validation SHALL accept the assignment.
# ---------------------------------------------------------------------------


class TestProperty8UniversalTypesAndLocality:
    """Property 8: Universal types and locality valid as children of any region level."""

    @given(data=_hierarchy_with_universal_child())
    @settings(max_examples=100)
    def test_universal_type_accepted_as_child_of_region_level(
        self, data: tuple[dict[str, Place], Place]
    ) -> None:
        """**Validates: Requirements 3.6**

        For any universal type (church, cemetery, farm, school) with a parent
        that is a region-level place, validation SHALL produce no hierarchy errors.
        """
        lookup, universal_place = data

        errors = validate_place(universal_place, place_lookup=lookup)

        # Filter to only hierarchy-related errors (not name/coord issues)
        hierarchy_errors = [
            e for e in errors
            if "överordnad" in e or "regionnivå" in e or "platstyp" in e.lower()
        ]
        assert hierarchy_errors == [], (
            f"Universal type '{universal_place.type}' rejected as child of "
            f"region-level place: {hierarchy_errors}"
        )

    @given(data=_hierarchy_with_universal_child_of_ort())
    @settings(max_examples=100)
    def test_universal_type_accepted_as_child_of_ort(
        self, data: tuple[dict[str, Place], Place]
    ) -> None:
        """**Validates: Requirements 3.6**

        For any universal type (church, cemetery, farm, school) with a parent
        that is a locality (ort), validation SHALL produce no hierarchy errors.
        """
        lookup, universal_place = data

        errors = validate_place(universal_place, place_lookup=lookup)

        hierarchy_errors = [
            e for e in errors
            if "överordnad" in e or "regionnivå" in e or "platstyp" in e.lower()
        ]
        assert hierarchy_errors == [], (
            f"Universal type '{universal_place.type}' rejected as child of "
            f"'ort': {hierarchy_errors}"
        )

    @given(data=_hierarchy_with_locality_child())
    @settings(max_examples=100)
    def test_locality_accepted_as_child_of_region_level(
        self, data: tuple[dict[str, Place], Place]
    ) -> None:
        """**Validates: Requirements 3.7**

        For a locality (ort) with a parent that is a region-level place,
        validation SHALL produce no hierarchy errors.
        """
        lookup, ort_place = data

        errors = validate_place(ort_place, place_lookup=lookup)

        hierarchy_errors = [
            e for e in errors
            if "överordnad" in e or "regionnivå" in e or "platstyp" in e.lower()
        ]
        assert hierarchy_errors == [], (
            f"Locality 'ort' rejected as child of region-level place: {hierarchy_errors}"
        )


# ---------------------------------------------------------------------------
# Feature: place-hierarchy-levels, Property 5: Region levels ignored on
# non-country places
#
# For any place whose type is not "country", the region_levels field SHALL
# not produce validation errors regardless of its content (treated as
# empty/ignored).
# ---------------------------------------------------------------------------


class TestProperty5RegionLevelsIgnoredOnNonCountry:
    """Property 5: Region levels ignored on non-country places.

    **Validates: Requirements 2.5**
    """

    @given(
        place_type=st.sampled_from(["continent", "church", "cemetery", "farm", "school", "ort"]),
        name=_safe_name,
        invalid_levels=st.lists(region_level_strategy(), min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    def test_region_levels_ignored_on_non_country(
        self, place_type: str, name: str, invalid_levels: list[RegionLevel]
    ) -> None:
        """**Validates: Requirements 2.5**

        For any non-country place, region_levels does not produce validation
        errors mentioning "Regionnivå" regardless of region_levels content.
        """
        # Set parent correctly per type to avoid hierarchy errors
        parent = None if place_type == "continent" else "some_parent"
        place = Place(
            id="test_1",
            type=place_type,
            name=name,
            parent_place_id=parent,
            region_levels=invalid_levels,
        )

        errors = validate_place(place, place_lookup=None)

        region_errors = [e for e in errors if "Regionnivå" in e or "regionnivå" in e]
        assert region_errors == [], (
            f"Non-country place of type '{place_type}' should not produce "
            f"region level errors, but got: {region_errors}"
        )
