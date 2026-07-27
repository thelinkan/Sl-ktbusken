"""Integration tests for save/load cycle with place hierarchy.

Validates the full end-to-end serialization round-trip with continents,
countries with region_levels, region-level places with custom_field_values,
and universal type places.

**Validates: Requirements 9.1, 9.2, 9.3**
"""

from dataclasses import asdict

from slaktbusken.model.place import CustomFieldDef, Place, RegionLevel
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.serialization import deserialize, serialize


class TestPlaceHierarchyIntegration:
    """Integration tests for save/load with full place hierarchy."""

    def _create_test_project(self) -> ProjectData:
        """Create a realistic project with the full place hierarchy."""
        continent = Place(
            id="continent_1",
            type="continent",
            name="Europa",
            parent_place_id=None,
        )

        country = Place(
            id="country_1",
            type="country",
            name="Sverige",
            parent_place_id="continent_1",
            region_levels=[
                RegionLevel(
                    key="lan",
                    label="Län",
                    order=1,
                    custom_fields=[CustomFieldDef(key="code", label="Länsbokstav")],
                ),
                RegionLevel(
                    key="socken",
                    label="Socken",
                    order=2,
                ),
            ],
        )

        region_place = Place(
            id="lan_1",
            type="lan",
            name="Stockholms län",
            parent_place_id="country_1",
            custom_field_values={"code": "AB"},
        )

        subregion = Place(
            id="socken_1",
            type="socken",
            name="Danderyds socken",
            parent_place_id="lan_1",
        )

        church = Place(
            id="church_1",
            type="church",
            name="Danderyds kyrka",
            parent_place_id="socken_1",
        )

        locality = Place(
            id="ort_1",
            type="ort",
            name="Danderyd",
            parent_place_id="lan_1",
        )

        return ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="Testprojekt"),
            places=[continent, country, region_place, subregion, church, locality],
        )

    def test_full_hierarchy_survives_round_trip(self) -> None:
        """All places with hierarchy data survive serialize/deserialize."""
        project = self._create_test_project()

        json_str = serialize(project)
        restored = deserialize(json_str)

        assert len(restored.places) == 6

        # Compare each place structurally
        for original, restored_place in zip(project.places, restored.places):
            assert asdict(original) == asdict(restored_place), (
                f"Place '{original.name}' not preserved through round-trip"
            )

    def test_region_levels_preserved_on_country(self) -> None:
        """Country's region_levels with custom_fields survive round-trip."""
        project = self._create_test_project()

        json_str = serialize(project)
        restored = deserialize(json_str)

        # Find the country
        country = next(p for p in restored.places if p.type == "country")

        assert len(country.region_levels) == 2
        assert country.region_levels[0].key == "lan"
        assert country.region_levels[0].label == "Län"
        assert country.region_levels[0].order == 1
        assert len(country.region_levels[0].custom_fields) == 1
        assert country.region_levels[0].custom_fields[0].key == "code"
        assert country.region_levels[0].custom_fields[0].label == "Länsbokstav"
        assert country.region_levels[1].key == "socken"
        assert country.region_levels[1].order == 2

    def test_custom_field_values_preserved_on_region_place(self) -> None:
        """Region place's custom_field_values survive round-trip."""
        project = self._create_test_project()

        json_str = serialize(project)
        restored = deserialize(json_str)

        # Find the län place
        lan_place = next(p for p in restored.places if p.id == "lan_1")

        assert lan_place.custom_field_values == {"code": "AB"}

    def test_continent_has_no_parent_after_round_trip(self) -> None:
        """Continent remains root (no parent) after round-trip."""
        project = self._create_test_project()

        json_str = serialize(project)
        restored = deserialize(json_str)

        continent = next(p for p in restored.places if p.type == "continent")
        assert continent.parent_place_id is None

    def test_hierarchy_references_preserved(self) -> None:
        """Parent-child relationships preserved after round-trip."""
        project = self._create_test_project()

        json_str = serialize(project)
        restored = deserialize(json_str)

        place_map = {p.id: p for p in restored.places}

        # Country references continent
        assert place_map["country_1"].parent_place_id == "continent_1"
        # Län references country
        assert place_map["lan_1"].parent_place_id == "country_1"
        # Socken references län
        assert place_map["socken_1"].parent_place_id == "lan_1"
        # Church references socken
        assert place_map["church_1"].parent_place_id == "socken_1"
        # Ort references län
        assert place_map["ort_1"].parent_place_id == "lan_1"
