"""Unit tests for country preset region level definitions."""

from slaktbusken.data.country_presets import available_presets, get_preset
from slaktbusken.model.place import CustomFieldDef, RegionLevel


class TestCountryPresets:
    """Tests for country preset data correctness."""

    def test_available_presets_returns_seven_countries(self) -> None:
        """All 7 defined presets are available."""
        presets = available_presets()
        assert len(presets) == 7
        expected = {"Sverige", "USA", "Tyskland", "Norge", "Danmark", "Finland", "England"}
        assert set(presets) == expected

    def test_get_preset_unknown_returns_empty(self) -> None:
        """Unknown country returns empty list."""
        assert get_preset("Frankrike") == []

    def test_get_preset_returns_deep_copy(self) -> None:
        """Modifying returned preset doesn't affect original."""
        preset1 = get_preset("Sverige")
        preset1[0].key = "modified"
        preset2 = get_preset("Sverige")
        assert preset2[0].key == "lan"

    def test_sverige_preset(self) -> None:
        """Sverige has Län (order 1) and Socken (order 2)."""
        levels = get_preset("Sverige")
        assert len(levels) == 2
        assert levels[0].key == "lan"
        assert levels[0].label == "Län"
        assert levels[0].order == 1
        assert levels[1].key == "socken"
        assert levels[1].label == "Socken"
        assert levels[1].order == 2

    def test_sverige_lan_has_code_custom_field(self) -> None:
        """Sverige Län includes custom field code/Länsbokstav."""
        levels = get_preset("Sverige")
        lan_level = levels[0]
        assert len(lan_level.custom_fields) == 1
        assert lan_level.custom_fields[0].key == "code"
        assert lan_level.custom_fields[0].label == "Länsbokstav"

    def test_usa_preset(self) -> None:
        """USA has Delstat (order 1) and County (order 2)."""
        levels = get_preset("USA")
        assert len(levels) == 2
        assert levels[0].key == "delstat"
        assert levels[0].label == "Delstat"
        assert levels[0].order == 1
        assert levels[1].key == "county"
        assert levels[1].label == "County"
        assert levels[1].order == 2

    def test_tyskland_preset(self) -> None:
        """Tyskland has Förbundsland and Kreis."""
        levels = get_preset("Tyskland")
        assert len(levels) == 2
        assert levels[0].key == "forbundsland"
        assert levels[0].label == "Förbundsland"
        assert levels[1].key == "kreis"
        assert levels[1].label == "Kreis"

    def test_norge_preset(self) -> None:
        """Norge has Fylke and Kommune."""
        levels = get_preset("Norge")
        assert len(levels) == 2
        assert levels[0].key == "fylke"
        assert levels[0].label == "Fylke"
        assert levels[1].key == "kommune"
        assert levels[1].label == "Kommune"

    def test_danmark_preset(self) -> None:
        """Danmark has Region and Kommune."""
        levels = get_preset("Danmark")
        assert len(levels) == 2
        assert levels[0].key == "region"
        assert levels[0].label == "Region"
        assert levels[1].key == "kommune"
        assert levels[1].label == "Kommune"

    def test_finland_preset(self) -> None:
        """Finland has Landskap and Kommun."""
        levels = get_preset("Finland")
        assert len(levels) == 2
        assert levels[0].key == "landskap"
        assert levels[0].label == "Landskap"
        assert levels[1].key == "kommun"
        assert levels[1].label == "Kommun"

    def test_england_preset(self) -> None:
        """England has County and Parish."""
        levels = get_preset("England")
        assert len(levels) == 2
        assert levels[0].key == "county"
        assert levels[0].label == "County"
        assert levels[1].key == "parish"
        assert levels[1].label == "Parish"

    def test_all_presets_have_consecutive_order(self) -> None:
        """All presets have order values starting at 1 and increasing by 1."""
        for country in available_presets():
            levels = get_preset(country)
            orders = [rl.order for rl in levels]
            expected = list(range(1, len(levels) + 1))
            assert orders == expected, f"{country} has non-consecutive orders: {orders}"

    def test_no_preset_has_empty_custom_fields_on_non_sverige(self) -> None:
        """Only Sverige has custom fields in its presets."""
        for country in available_presets():
            levels = get_preset(country)
            for level in levels:
                if country == "Sverige" and level.key == "lan":
                    assert len(level.custom_fields) == 1
                else:
                    assert level.custom_fields == []
