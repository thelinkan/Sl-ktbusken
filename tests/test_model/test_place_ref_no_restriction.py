"""Verification tests for PlaceRef and red dot with continent/country.

Ensures that:
- PlaceRef imposes no type restriction on referenced places (Req 4.1)
- Red dot is not triggered by missing coordinates (Req 4.4)
- Continent and country places with None coords pass validation (Req 4.3)
"""

from slaktbusken.model.event import PlaceRef
from slaktbusken.model.place import Place, needs_red_dot
from slaktbusken.model.validators import validate_place


class TestPlaceRefNoTypeRestriction:
    """Verify PlaceRef allows any place type to be referenced."""

    def test_placeref_has_no_type_field(self) -> None:
        """PlaceRef only stores place_id, no type filtering."""
        ref = PlaceRef(place_id="continent_1")
        assert ref.place_id == "continent_1"
        # No type attribute — any place can be referenced
        assert not hasattr(ref, "place_type")

    def test_placeref_accepts_continent_id(self) -> None:
        """A PlaceRef can reference a continent place."""
        ref = PlaceRef(place_id="continent_1")
        assert ref.place_id == "continent_1"

    def test_placeref_accepts_country_id(self) -> None:
        """A PlaceRef can reference a country place."""
        ref = PlaceRef(place_id="country_1")
        assert ref.place_id == "country_1"


class TestRedDotNotTriggeredByMissingCoordinates:
    """Verify red dot indicator is not influenced by coordinates."""

    def test_continent_no_coords_no_red_dot(self) -> None:
        """Continent with None coords does not trigger red dot."""
        place = Place(
            id="c1", type="continent", name="Europa",
            parent_place_id=None, latitude=None, longitude=None,
        )
        assert not needs_red_dot(place)

    def test_country_no_coords_with_parent_no_red_dot(self) -> None:
        """Country with parent and None coords does not trigger red dot."""
        place = Place(
            id="s1", type="country", name="Sverige",
            parent_place_id="c1", latitude=None, longitude=None,
        )
        assert not needs_red_dot(place)

    def test_country_no_coords_no_parent_shows_red_dot(self) -> None:
        """Country without parent shows red dot (missing parent, not missing coords)."""
        place = Place(
            id="s1", type="country", name="Sverige",
            parent_place_id=None, latitude=None, longitude=None,
        )
        assert needs_red_dot(place)

    def test_continent_no_coords_passes_validation(self) -> None:
        """Continent with None coords has no coordinate validation errors."""
        place = Place(
            id="c1", type="continent", name="Europa",
            parent_place_id=None, latitude=None, longitude=None,
        )
        errors = validate_place(place)
        coord_errors = [e for e in errors if "Latitud" in e or "Longitud" in e]
        assert coord_errors == []

    def test_country_no_coords_passes_validation(self) -> None:
        """Country with None coords has no coordinate validation errors."""
        place = Place(
            id="s1", type="country", name="Sverige",
            parent_place_id="c1", latitude=None, longitude=None,
        )
        errors = validate_place(place)
        coord_errors = [e for e in errors if "Latitud" in e or "Longitud" in e]
        assert coord_errors == []
