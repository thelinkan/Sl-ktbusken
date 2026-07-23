"""Country preset region level definitions for common countries."""

from __future__ import annotations

import copy

from slaktbusken.model.place import CustomFieldDef, RegionLevel

_PRESETS: dict[str, list[RegionLevel]] = {
    "Sverige": [
        RegionLevel(
            key="lan",
            label="Län",
            order=1,
            custom_fields=[CustomFieldDef(key="code", label="Länsbokstav")],
        ),
        RegionLevel(key="socken", label="Socken", order=2),
    ],
    "USA": [
        RegionLevel(key="delstat", label="Delstat", order=1),
        RegionLevel(key="county", label="County", order=2),
    ],
    "Tyskland": [
        RegionLevel(key="forbundsland", label="Förbundsland", order=1),
        RegionLevel(key="kreis", label="Kreis", order=2),
    ],
    "Norge": [
        RegionLevel(key="fylke", label="Fylke", order=1),
        RegionLevel(key="kommune", label="Kommune", order=2),
    ],
    "Danmark": [
        RegionLevel(key="region", label="Region", order=1),
        RegionLevel(key="kommune", label="Kommune", order=2),
    ],
    "Finland": [
        RegionLevel(key="landskap", label="Landskap", order=1),
        RegionLevel(key="kommun", label="Kommun", order=2),
    ],
    "England": [
        RegionLevel(key="county", label="County", order=1),
        RegionLevel(key="parish", label="Parish", order=2),
    ],
}


def get_preset(country_name: str) -> list[RegionLevel]:
    """Return predefined region levels for a known country.

    Returns a new list copy each time so modifications don't affect
    the preset data. If the country_name is not found, returns an empty list.
    """
    preset = _PRESETS.get(country_name)
    if preset is None:
        return []
    return copy.deepcopy(preset)


def available_presets() -> list[str]:
    """Return list of country names with available presets."""
    return list(_PRESETS.keys())
