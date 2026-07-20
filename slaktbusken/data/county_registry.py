"""County reference data registry.

Loads county definitions from JSON files (e.g., sweden_counties.json) and
provides lookup functions for identifying and normalizing county names.
This handles alternate spellings like "Stockholm" → "Stockholms län".

Usage:
    from slaktbusken.data.county_registry import is_county, normalize_county

    is_county("Stockholm")        # True
    normalize_county("Stockholm") # "Stockholms län"
    normalize_county("Falun")     # "Falun" (unchanged, not a county)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Internal state (loaded lazily on first access)
# ---------------------------------------------------------------------------

_loaded: bool = False

# Maps lowercase alternate/canonical name → canonical county name
_lookup: dict[str, str] = {}

# Maps lowercase county name (canonical or alternate) → country name
_county_country: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_county(name: str) -> bool:
    """Check if a name (or alternate spelling) is a known county.

    Case-insensitive matching.

    Args:
        name: The place name to check.

    Returns:
        True if the name matches a known county or alternate spelling.
    """
    _ensure_loaded()
    return name.strip().lower() in _lookup


def normalize_county(name: str) -> str:
    """Return the canonical county name for a known alternate spelling.

    If the name is not a recognized county, returns it unchanged.
    Case-insensitive matching; the returned name uses the canonical casing.

    Args:
        name: The place name to normalize.

    Returns:
        The canonical county name, or the original name if not recognized.
    """
    _ensure_loaded()
    canonical = _lookup.get(name.strip().lower())
    return canonical if canonical is not None else name


def get_canonical_counties() -> list[str]:
    """Return all canonical county names.

    Returns:
        A list of canonical county name strings.
    """
    _ensure_loaded()
    return list(set(_lookup.values()))


def get_country_for_county(name: str) -> Optional[str]:
    """Return the country associated with a county name.

    Looks up both canonical names and alternate spellings.

    Args:
        name: The county name (canonical or alternate).

    Returns:
        The country name (e.g., "Sverige"), or None if not recognized.
    """
    _ensure_loaded()
    return _county_country.get(name.strip().lower())


# ---------------------------------------------------------------------------
# Loading logic
# ---------------------------------------------------------------------------


def _ensure_loaded() -> None:
    """Load county data from JSON files if not already loaded."""
    global _loaded
    if _loaded:
        return
    _loaded = True

    data_dir = Path(__file__).parent

    # Load all *_counties.json files in the data directory
    for json_file in sorted(data_dir.glob("*_counties.json")):
        _load_county_file(json_file)


def _load_county_file(path: Path) -> None:
    """Load a single county JSON file and populate the lookup dict.

    Args:
        path: Path to the JSON file (e.g., sweden_counties.json).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return

    country = data.get("country", "")
    counties = data.get("counties", [])
    for entry in counties:
        canonical = entry.get("name", "")
        if not canonical:
            continue

        # Register the canonical name itself
        _lookup[canonical.lower()] = canonical
        if country:
            _county_country[canonical.lower()] = country

        # Register all alternates
        for alt in entry.get("alternates", []):
            if alt:
                _lookup[alt.strip().lower()] = canonical
                if country:
                    _county_country[alt.strip().lower()] = country


def _reset() -> None:
    """Reset loaded state (for testing purposes)."""
    global _loaded
    _loaded = False
    _lookup.clear()
    _county_country.clear()
