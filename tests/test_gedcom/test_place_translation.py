"""Unit tests for GEDCOM place string to hierarchical Place mapping.

Validates: Requirements 4.5
"""

from __future__ import annotations

import pytest

from slaktbusken.gedcom.translation.models import GedcomPlace
from slaktbusken.gedcom.translation.place_translation import (
    find_matching_place,
    infer_place_type,
    map_place_to_hierarchy,
    parse_place_string,
)
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.place import Place
from slaktbusken.persistence.translation_io import PlaceMapping


# ---------------------------------------------------------------------------
# parse_place_string tests
# ---------------------------------------------------------------------------


class TestParsePlaceString:
    """Tests for parse_place_string function."""

    def test_three_level_place(self) -> None:
        """A standard three-level Swedish place string is parsed correctly."""
        result = parse_place_string("Ljusdal, Gävleborgs län, Sverige")
        assert result.original == "Ljusdal, Gävleborgs län, Sverige"
        assert result.levels == ["Ljusdal", "Gävleborgs län", "Sverige"]

    def test_four_level_place(self) -> None:
        """A four-level place string with church is parsed correctly."""
        result = parse_place_string(
            "Ljusdals kyrka, Ljusdal, Gävleborgs län, Sverige"
        )
        assert result.levels == [
            "Ljusdals kyrka",
            "Ljusdal",
            "Gävleborgs län",
            "Sverige",
        ]

    def test_single_level_place(self) -> None:
        """A single name with no commas produces one level."""
        result = parse_place_string("Sverige")
        assert result.levels == ["Sverige"]

    def test_two_level_place(self) -> None:
        """A two-level place is parsed correctly."""
        result = parse_place_string("Ljusdal, Sverige")
        assert result.levels == ["Ljusdal", "Sverige"]

    def test_whitespace_stripping(self) -> None:
        """Extra whitespace around components is stripped."""
        result = parse_place_string("  Ljusdal  ,  Gävleborgs län  ,  Sverige  ")
        assert result.levels == ["Ljusdal", "Gävleborgs län", "Sverige"]

    def test_empty_string(self) -> None:
        """An empty string produces no levels."""
        result = parse_place_string("")
        assert result.levels == []
        assert result.original == ""


# ---------------------------------------------------------------------------
# infer_place_type tests
# ---------------------------------------------------------------------------


class TestInferPlaceType:
    """Tests for infer_place_type function."""

    def test_sverige_is_country(self) -> None:
        """'Sverige' is always detected as country regardless of position."""
        assert infer_place_type(0, 1, "Sverige") == "country"
        assert infer_place_type(2, 3, "Sverige") == "country"

    def test_lan_suffix_is_county(self) -> None:
        """Names ending with 'län' are detected as county."""
        assert infer_place_type(1, 3, "Gävleborgs län") == "county"
        assert infer_place_type(0, 1, "Stockholms län") == "county"

    def test_kyrka_suffix_is_church(self) -> None:
        """Names ending with 'kyrka' are detected as church."""
        assert infer_place_type(0, 4, "Ljusdals kyrka") == "church"

    def test_kapell_suffix_is_church(self) -> None:
        """Names ending with 'kapell' are detected as church."""
        assert infer_place_type(0, 4, "Hammerdals kapell") == "church"

    def test_kyrkogard_suffix_is_cemetery(self) -> None:
        """Names ending with 'kyrkogård' are detected as cemetery."""
        assert infer_place_type(0, 4, "Ljusdals kyrkogård") == "cemetery"

    def test_begravningsplats_suffix_is_cemetery(self) -> None:
        """Names ending with 'begravningsplats' are detected as cemetery."""
        assert infer_place_type(0, 4, "Norra begravningsplats") == "cemetery"

    def test_single_level_default_parish(self) -> None:
        """A single level with an unrecognized name defaults to parish."""
        assert infer_place_type(0, 1, "Ljusdal") == "parish"

    def test_two_levels_positional(self) -> None:
        """Two-level positional inference: parish + country."""
        assert infer_place_type(0, 2, "Ljusdal") == "parish"
        assert infer_place_type(1, 2, "Unknown") == "country"

    def test_three_levels_positional(self) -> None:
        """Three-level positional inference: parish + county + country."""
        assert infer_place_type(0, 3, "Ljusdal") == "parish"
        assert infer_place_type(1, 3, "SomeRegion") == "county"
        assert infer_place_type(2, 3, "Unknown") == "country"

    def test_four_levels_positional(self) -> None:
        """Four-level positional: church + parish + county + country."""
        assert infer_place_type(0, 4, "SomePlace") == "church"
        assert infer_place_type(1, 4, "SomeParish") == "parish"
        assert infer_place_type(2, 4, "SomeRegion") == "county"
        assert infer_place_type(3, 4, "SomeCountry") == "country"

    def test_name_detection_overrides_position(self) -> None:
        """Name-based detection takes precedence over positional inference."""
        # "Sverige" at index 0 is still country even though position says parish
        assert infer_place_type(0, 3, "Sverige") == "country"
        # "Stockholms län" at index 0 is county
        assert infer_place_type(0, 3, "Stockholms län") == "county"

    def test_case_insensitive_country(self) -> None:
        """Country detection is case-insensitive."""
        assert infer_place_type(0, 1, "SVERIGE") == "country"
        assert infer_place_type(0, 1, "sverige") == "country"

    def test_case_insensitive_church(self) -> None:
        """Church suffix detection is case-insensitive."""
        assert infer_place_type(0, 4, "Ljusdals Kyrka") == "church"


# ---------------------------------------------------------------------------
# find_matching_place tests
# ---------------------------------------------------------------------------


class TestFindMatchingPlace:
    """Tests for find_matching_place function."""

    def test_exact_match_found(self) -> None:
        """Returns app_id when GEDCOM string matches a mapping exactly."""
        place = Place(id="place_1", type="parish", name="Ljusdal")
        mapping = PlaceMapping(
            gedcom_place="Ljusdal, Gävleborgs län, Sverige",
            app_id="place_1",
            name="Ljusdal",
        )
        gp = parse_place_string("Ljusdal, Gävleborgs län, Sverige")

        result = find_matching_place(gp, [place], [mapping])
        assert result == "place_1"

    def test_case_insensitive_match(self) -> None:
        """Matching is case-insensitive."""
        place = Place(id="place_2", type="parish", name="Ljusdal")
        mapping = PlaceMapping(
            gedcom_place="ljusdal, gävleborgs län, sverige",
            app_id="place_2",
            name="Ljusdal",
        )
        gp = parse_place_string("Ljusdal, Gävleborgs Län, Sverige")

        result = find_matching_place(gp, [place], [mapping])
        assert result == "place_2"

    def test_no_match_returns_none(self) -> None:
        """Returns None when no mapping matches."""
        place = Place(id="place_1", type="parish", name="Ljusdal")
        mapping = PlaceMapping(
            gedcom_place="Sundsvall, Västernorrlands län, Sverige",
            app_id="place_1",
            name="Sundsvall",
        )
        gp = parse_place_string("Ljusdal, Gävleborgs län, Sverige")

        result = find_matching_place(gp, [place], [mapping])
        assert result is None

    def test_mapping_points_to_deleted_place(self) -> None:
        """Returns None when the mapped place no longer exists."""
        mapping = PlaceMapping(
            gedcom_place="Ljusdal, Gävleborgs län, Sverige",
            app_id="place_99",
            name="Ljusdal",
        )
        gp = parse_place_string("Ljusdal, Gävleborgs län, Sverige")

        # No place with id "place_99" in existing_places
        result = find_matching_place(gp, [], [mapping])
        assert result is None

    def test_whitespace_normalized_match(self) -> None:
        """Extra whitespace in GEDCOM string still matches."""
        place = Place(id="place_3", type="parish", name="Ljusdal")
        mapping = PlaceMapping(
            gedcom_place="Ljusdal, Gävleborgs län, Sverige",
            app_id="place_3",
            name="Ljusdal",
        )
        gp = parse_place_string("  Ljusdal ,  Gävleborgs län ,  Sverige  ")

        result = find_matching_place(gp, [place], [mapping])
        assert result == "place_3"


# ---------------------------------------------------------------------------
# map_place_to_hierarchy tests
# ---------------------------------------------------------------------------


class TestMapPlaceToHierarchy:
    """Tests for map_place_to_hierarchy function."""

    def test_three_level_creates_hierarchy(self) -> None:
        """Three-level place creates country > county > parish chain."""
        gp = parse_place_string("Ljusdal, Gävleborgs län, Sverige")
        id_gen = IDGenerator(set())

        new_places = map_place_to_hierarchy(gp, [], [], id_gen)

        assert len(new_places) == 3
        # Ordered from least to most specific
        assert new_places[0].name == "Sverige"
        assert new_places[0].type == "country"
        assert new_places[0].parent_place_id is None

        assert new_places[1].name == "Gävleborgs län"
        assert new_places[1].type == "county"
        assert new_places[1].parent_place_id == new_places[0].id

        assert new_places[2].name == "Ljusdal"
        assert new_places[2].type == "parish"
        assert new_places[2].parent_place_id == new_places[1].id

    def test_four_level_creates_full_hierarchy(self) -> None:
        """Four-level place creates country > county > parish > church chain."""
        gp = parse_place_string(
            "Ljusdals kyrka, Ljusdal, Gävleborgs län, Sverige"
        )
        id_gen = IDGenerator(set())

        new_places = map_place_to_hierarchy(gp, [], [], id_gen)

        assert len(new_places) == 4
        assert new_places[0].name == "Sverige"
        assert new_places[0].type == "country"

        assert new_places[1].name == "Gävleborgs län"
        assert new_places[1].type == "county"
        assert new_places[1].parent_place_id == new_places[0].id

        assert new_places[2].name == "Ljusdal"
        assert new_places[2].type == "parish"
        assert new_places[2].parent_place_id == new_places[1].id

        assert new_places[3].name == "Ljusdals kyrka"
        assert new_places[3].type == "church"
        assert new_places[3].parent_place_id == new_places[2].id

    def test_reuses_existing_country(self) -> None:
        """Existing country is reused, not duplicated."""
        existing_country = Place(
            id="place_1", type="country", name="Sverige"
        )
        gp = parse_place_string("Ljusdal, Gävleborgs län, Sverige")
        id_gen = IDGenerator({"place_1"})

        new_places = map_place_to_hierarchy(gp, [existing_country], [], id_gen)

        # Only county and parish should be new
        assert len(new_places) == 2
        assert new_places[0].name == "Gävleborgs län"
        assert new_places[0].parent_place_id == "place_1"

    def test_reuses_existing_hierarchy(self) -> None:
        """Existing country + county are reused when they match."""
        existing_country = Place(
            id="place_1", type="country", name="Sverige"
        )
        existing_county = Place(
            id="place_2",
            type="county",
            name="Gävleborgs län",
            parent_place_id="place_1",
        )
        gp = parse_place_string("Ljusdal, Gävleborgs län, Sverige")
        id_gen = IDGenerator({"place_1", "place_2"})

        new_places = map_place_to_hierarchy(
            gp, [existing_country, existing_county], [], id_gen
        )

        # Only parish should be new
        assert len(new_places) == 1
        assert new_places[0].name == "Ljusdal"
        assert new_places[0].type == "parish"
        assert new_places[0].parent_place_id == "place_2"

    def test_empty_place_string_returns_empty(self) -> None:
        """An empty place string produces no new places."""
        gp = parse_place_string("")
        result = map_place_to_hierarchy(gp, [], [])
        assert result == []

    def test_single_level_place(self) -> None:
        """A single level creates one place."""
        gp = parse_place_string("Sverige")
        id_gen = IDGenerator(set())

        new_places = map_place_to_hierarchy(gp, [], [], id_gen)

        assert len(new_places) == 1
        assert new_places[0].name == "Sverige"
        assert new_places[0].type == "country"
        assert new_places[0].parent_place_id is None

    def test_generates_unique_ids(self) -> None:
        """Each new place gets a unique ID from the generator."""
        gp = parse_place_string("Ljusdal, Gävleborgs län, Sverige")
        id_gen = IDGenerator(set())

        new_places = map_place_to_hierarchy(gp, [], [], id_gen)

        ids = [p.id for p in new_places]
        assert len(ids) == len(set(ids)), "All IDs must be unique"
        # All IDs should start with the place prefix
        for place_id in ids:
            assert place_id.startswith("place_")

    def test_no_id_generator_provided(self) -> None:
        """Works correctly when no id_generator is passed (creates one internally)."""
        existing = Place(id="place_5", type="country", name="Sverige")
        gp = parse_place_string("Ljusdal, Gävleborgs län, Sverige")

        new_places = map_place_to_hierarchy(gp, [existing], [])

        assert len(new_places) == 2
        # IDs should be generated starting after existing high-water mark
        for place in new_places:
            assert place.id.startswith("place_")
