"""GEDCOM place string to hierarchical App_JSON Place mapping.

This module provides logic for translating GEDCOM place strings (comma-separated,
most-specific to least-specific) into App_JSON hierarchical Place entities. It
handles Swedish place naming conventions, infers place types from hierarchy
position, and manages creation of new Place records when no existing match is
found.

GEDCOM place strings follow the pattern:
    "Ljusdals kyrka, Ljusdal, Gävleborgs län, Sverige"
     (most specific → least specific)

The App_JSON Place model uses a parent_place_id chain:
    country > county > parish > church/cemetery

Swedish conventions handled:
    - "Sverige" is always type "country"
    - Names ending with "län" are counties (e.g., "Gävleborgs län")
    - Common church suffixes: "kyrka", "kapell"
    - Common cemetery suffixes: "kyrkogård", "begravningsplats"

Validates: Requirements 4.5
"""

from __future__ import annotations

import re
from typing import Optional

from slaktbusken.gedcom.translation.models import GedcomPlace
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.place import Place
from slaktbusken.persistence.translation_io import PlaceMapping


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHURCH_SUFFIXES = ("kyrka", "kapell")
_CEMETERY_SUFFIXES = ("kyrkogård", "begravningsplats")
_COUNTRY_NAMES = {"sverige", "norway", "norge", "finland", "danmark", "denmark"}
_LAN_PATTERN = re.compile(r".+\s+län$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def parse_place_string(place_string: str) -> GedcomPlace:
    """Parse a GEDCOM place string into a structured GedcomPlace.

    GEDCOM encodes places as comma-separated strings ordered from most
    specific to least specific (e.g., "Ljusdal, Gävleborgs län, Sverige").
    This function splits the string into hierarchy levels, stripping
    whitespace from each component.

    Args:
        place_string: The verbatim place string from a GEDCOM PLAC tag.

    Returns:
        A GedcomPlace instance with the original string preserved and
        levels populated from the comma-separated components.

    Examples:
        >>> place = parse_place_string("Ljusdal, Gävleborgs län, Sverige")
        >>> place.levels
        ['Ljusdal', 'Gävleborgs län', 'Sverige']
        >>> place.original
        'Ljusdal, Gävleborgs län, Sverige'
    """
    return GedcomPlace(original=place_string)


def infer_place_type(level_index: int, total_levels: int, name: str) -> str:
    """Determine the place type from its position in the hierarchy and name.

    Uses Swedish naming conventions and positional heuristics to infer the
    type of place at a given hierarchy level. Name-based detection takes
    precedence over position-based inference.

    The inference rules (in priority order):
        1. If name matches a known country name (e.g., "Sverige") → "country"
        2. If name ends with "län" → "county"
        3. If name ends with a church suffix ("kyrka", "kapell") → "church"
        4. If name ends with a cemetery suffix ("kyrkogård",
           "begravningsplats") → "cemetery"
        5. Positional inference based on total_levels:
           - 1 level: "parish" (unless name-based detection matched)
           - 2 levels: index 0 = "parish", index 1 = "country"
           - 3 levels: index 0 = "parish", index 1 = "county",
             index 2 = "country"
           - 4+ levels: index 0 = "church" or "cemetery" (from name),
             otherwise "parish"; index 1 = "parish"; second-to-last = "county";
             last = "country"

    Args:
        level_index: Zero-based index within the levels list (0 = most
            specific, higher = less specific).
        total_levels: Total number of levels in the place hierarchy.
        name: The place name at this level.

    Returns:
        A place type string: one of "country", "county", "parish",
        "church", or "cemetery".

    Examples:
        >>> infer_place_type(2, 3, "Sverige")
        'country'
        >>> infer_place_type(1, 3, "Gävleborgs län")
        'county'
        >>> infer_place_type(0, 3, "Ljusdal")
        'parish'
        >>> infer_place_type(0, 4, "Ljusdals kyrka")
        'church'
    """
    # Name-based detection (highest priority)
    name_lower = name.strip().lower()

    if name_lower in _COUNTRY_NAMES:
        return "country"

    if _LAN_PATTERN.match(name):
        return "county"

    if any(name_lower.endswith(suffix) for suffix in _CHURCH_SUFFIXES):
        return "church"

    if any(name_lower.endswith(suffix) for suffix in _CEMETERY_SUFFIXES):
        return "cemetery"

    # Positional inference when name doesn't match known patterns
    if total_levels == 1:
        return "parish"

    if total_levels == 2:
        if level_index == 0:
            return "parish"
        return "country"

    if total_levels == 3:
        if level_index == 0:
            return "parish"
        if level_index == 1:
            return "county"
        return "country"

    # 4+ levels
    if level_index == total_levels - 1:
        return "country"
    if level_index == total_levels - 2:
        return "county"
    if level_index == 0:
        # Most specific level in a 4+ hierarchy without name match
        # defaults to church (most common in Swedish genealogy for 4-level)
        return "church"
    return "parish"


def find_matching_place(
    gedcom_place: GedcomPlace,
    existing_places: list[Place],
    place_mappings: list[PlaceMapping],
) -> Optional[str]:
    """Find an existing App_JSON place ID matching the GEDCOM place string.

    Searches the place translation mappings for an exact match on the
    original GEDCOM place string. If found, returns the corresponding
    App_JSON place ID.

    This function performs case-insensitive, whitespace-normalized
    comparison of the full GEDCOM place string against known mappings.

    Args:
        gedcom_place: The parsed GEDCOM place to look up.
        existing_places: All Place records currently in the project.
            Used for validation that the mapped ID still exists.
        place_mappings: The current place translation mappings from
            the translation file.

    Returns:
        The App_JSON place ID if a match is found and the target place
        still exists in the project, or None if no match is found.

    Examples:
        >>> mapping = PlaceMapping(
        ...     gedcom_place="Ljusdal, Gävleborgs län, Sverige",
        ...     app_id="place_1",
        ...     name="Ljusdal",
        ... )
        >>> place = Place(id="place_1", type="parish", name="Ljusdal")
        >>> gp = parse_place_string("Ljusdal, Gävleborgs län, Sverige")
        >>> find_matching_place(gp, [place], [mapping])
        'place_1'
    """
    normalized_original = _normalize_place_string(gedcom_place.original)
    existing_ids = {p.id for p in existing_places}

    for mapping in place_mappings:
        if _normalize_place_string(mapping.gedcom_place) == normalized_original:
            # Verify the target place still exists
            if mapping.app_id in existing_ids:
                return mapping.app_id
    return None


def map_place_to_hierarchy(
    gedcom_place: GedcomPlace,
    existing_places: list[Place],
    place_mappings: list[PlaceMapping],
    id_generator: Optional[IDGenerator] = None,
) -> list[Place]:
    """Map a GEDCOM place to App_JSON Place hierarchy, creating records as needed.

    Processes the GEDCOM place levels from least specific (country) to most
    specific, building a parent_place_id chain. For each level, the function
    first attempts to find an existing Place with the same name and type
    among existing_places. If no match is found, a new Place record is
    created with an auto-generated ID.

    The returned list contains only *newly created* Place records. Existing
    places that were matched are not included in the output since they don't
    need to be added to the project.

    Args:
        gedcom_place: The parsed GEDCOM place with hierarchy levels.
        existing_places: All Place records currently in the project.
        place_mappings: The current place translation mappings.
        id_generator: Optional IDGenerator for creating new place IDs.
            If None, a new generator is constructed from existing place IDs.

    Returns:
        A list of newly created Place records forming the hierarchy chain.
        Empty list if all levels already exist. The list is ordered from
        least specific (country) to most specific (church/parish).

    Examples:
        >>> gp = parse_place_string("Ljusdal, Gävleborgs län, Sverige")
        >>> new_places = map_place_to_hierarchy(gp, [], [])
        >>> [p.name for p in new_places]
        ['Sverige', 'Gävleborgs län', 'Ljusdal']
        >>> new_places[0].type
        'country'
        >>> new_places[1].parent_place_id == new_places[0].id
        True
    """
    if not gedcom_place.levels:
        return []

    if id_generator is None:
        existing_ids = {p.id for p in existing_places}
        id_generator = IDGenerator(existing_ids)

    total_levels = len(gedcom_place.levels)
    new_places: list[Place] = []
    parent_id: Optional[str] = None

    # Process from least specific (last in list) to most specific (first)
    for i in range(total_levels - 1, -1, -1):
        name = gedcom_place.levels[i].strip()
        if not name:
            continue

        place_type = infer_place_type(i, total_levels, name)

        # Try to find an existing place with matching name and type
        existing = _find_existing_by_name_and_type(
            name, place_type, parent_id, existing_places
        )

        if existing is not None:
            parent_id = existing.id
        else:
            # Create a new place record
            new_id = id_generator.generate("place")
            new_place = Place(
                id=new_id,
                type=place_type,
                name=name,
                parent_place_id=parent_id,
            )
            new_places.append(new_place)
            parent_id = new_id

    return new_places


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _normalize_place_string(place_string: str) -> str:
    """Normalize a place string for comparison.

    Strips outer whitespace, normalizes internal whitespace around commas,
    and lowercases the result for case-insensitive comparison.

    Args:
        place_string: Raw place string to normalize.

    Returns:
        Normalized, lowercased place string.
    """
    # Strip, collapse whitespace around commas, lowercase
    parts = [part.strip() for part in place_string.split(",")]
    return ", ".join(parts).lower()


def _find_existing_by_name_and_type(
    name: str,
    place_type: str,
    parent_id: Optional[str],
    existing_places: list[Place],
) -> Optional[Place]:
    """Find an existing place matching name, type, and optionally parent.

    Performs case-insensitive name comparison. When parent_id is provided,
    prefers a match with the same parent, but falls back to a match with
    just name and type if no parent-specific match is found.

    Args:
        name: The place name to search for.
        place_type: The expected place type.
        parent_id: The expected parent_place_id (may be None for top-level).
        existing_places: The list of all existing places.

    Returns:
        The matching Place if found, or None.
    """
    name_lower = name.lower()
    match_with_parent: Optional[Place] = None
    match_without_parent: Optional[Place] = None

    for place in existing_places:
        if place.name.lower() == name_lower and place.type == place_type:
            if place.parent_place_id == parent_id:
                match_with_parent = place
                break
            if match_without_parent is None:
                match_without_parent = place

    # Prefer exact parent match, fall back to name+type match
    return match_with_parent if match_with_parent is not None else match_without_parent
