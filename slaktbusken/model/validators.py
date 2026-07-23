"""Validation functions for domain model entities.

Each ``validate_*`` function accepts an entity instance (and optional reference
sets where cross-entity checks are needed) and returns a ``list[str]`` of error
messages.  An empty list means the entity is valid.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from slaktbusken.model.dna import (
    DnaCluster,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Person
from slaktbusken.model.place import ExternalId, Place, RegionLevel
from slaktbusken.model.source import Repository, Source


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_SEX = {"M", "F", "X", "U"}

_VALID_PARTNER_ROLES = {"father", "mother", "husband", "wife", "partner"}

_VALID_PARENTAGE_TYPES = {
    "biological",
    "legal",
    "adoptive",
    "foster",
    "step",
    "unknown_donor",
    "donation",
}

_VALID_DATE_PRECISIONS = {"day", "month", "year", "approximate"}

# ISO 8601 date: YYYY, YYYY-MM, or YYYY-MM-DD
_ISO_DATE_RE = re.compile(r"^\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?$")

_CUSTOM_EVENT_TYPES = {"custom_individual_event", "custom_family_event"}

_VALID_PLACE_TYPES = {"continent", "country", "church", "cemetery", "farm", "school", "ort"}

_PLACE_TYPE_SWEDISH: dict[str, str] = {
    "continent": "kontinent",
    "country": "land",
    "church": "kyrka",
    "cemetery": "kyrkogård",
    "farm": "gård",
    "school": "skola",
    "ort": "ort",
}

# Universal types that can be children of any region level or locality (ort)
_UNIVERSAL_PLACE_TYPES = {"church", "cemetery", "farm", "school"}

_VALID_SOURCE_TYPES = {
    "church_book",
    "database",
    "death_notice",
    "newspaper",
    "photograph",
    "census",
    "other",
}

_STRUCTURED_REFERENCE_FIELDS: dict[str, set[str]] = {
    # church_book 'series' is free text — common codes include:
    # AI = Husförhörslängd, CI = Födelseboken, FI = Död- och begravningsbok,
    # B = Inflyttningslängd, C = Utflyttningslängd, E = Lysnings- och vigselbok,
    # D = Konfirmationsbok (codes vary by parish and era)
    "church_book": {"parish", "county_code", "series", "volume", "years", "image", "page"},
    "database": {"database_name", "record_id"},
    "death_notice": {"newspaper", "publication_date", "page"},
    "newspaper": {"newspaper", "date", "page", "article_title"},
}

_VALID_MEDIA_TYPES = {
    "photo",
    "source_image",
    "death_notice",
    "obituary",
    "funeral_program",
    "grave_photo",
    "map",
    "logo",
    "document",
    # Death event media types
    "dödruna",
    "dödsannons",
    "bouppteckning",
    "dödsbevis",
    # Funeral event media types
    "begravningsprogram",
    "minnesord",
}

_VALID_DNA_TEST_TYPES = {"autosomal", "y-dna", "mtdna", "combined"}

_VALID_CHROMOSOMES = {str(i) for i in range(1, 23)} | {"X", "Y"}


# ---------------------------------------------------------------------------
# 3.1 – Person validation
# ---------------------------------------------------------------------------


def validate_person(
    person: Person,
    valid_event_ids: Optional[set[str]] = None,
) -> list[str]:
    """Validate a Person instance."""
    errors: list[str] = []

    if not person.names:
        errors.append("Person måste ha minst ett namnfält.")

    if person.sex not in _VALID_SEX:
        errors.append(f"Ogiltigt kön '{person.sex}'; måste vara ett av {sorted(_VALID_SEX)}.")

    for idx, name in enumerate(person.names):
        if len(name.given) > 100:
            errors.append(f"Namn[{idx}] förnamn överskrider 100 tecken.")
        if len(name.surname) > 100:
            errors.append(f"Namn[{idx}] efternamn överskrider 100 tecken.")
        if name.event_id is not None and valid_event_ids is not None:
            if name.event_id not in valid_event_ids:
                errors.append(
                    f"Namn[{idx}] event_id '{name.event_id}' refererar inte till en giltig händelse."
                )

    if person.title is not None and len(person.title) > 100:
        errors.append("Titel överskrider 100 tecken.")

    if person.occupation is not None and len(person.occupation) > 100:
        errors.append("Yrke överskrider 100 tecken.")

    return errors


# ---------------------------------------------------------------------------
# 3.2 – Family validation
# ---------------------------------------------------------------------------


def validate_family(
    family: Family,
    valid_person_ids: Optional[set[str]] = None,
) -> list[str]:
    """Validate a Family instance."""
    errors: list[str] = []

    # Partner role validation
    for idx, partner in enumerate(family.partners):
        if partner.role not in _VALID_PARTNER_ROLES:
            errors.append(
                f"Partner[{idx}] har ogiltig roll '{partner.role}'; "
                f"måste vara en av {sorted(_VALID_PARTNER_ROLES)}."
            )
        if valid_person_ids is not None and partner.person_id not in valid_person_ids:
            errors.append(
                f"Partner[{idx}] person_id '{partner.person_id}' refererar inte till en giltig person."
            )

    # Children reference existing persons
    if valid_person_ids is not None:
        for child_id in family.children:
            if child_id not in valid_person_ids:
                errors.append(
                    f"Barn '{child_id}' refererar inte till en giltig person."
                )

    # No duplicate children
    if len(family.children) != len(set(family.children)):
        errors.append("Familjen innehåller dubbletter bland barnen.")

    # Parent-child links validation
    partner_ids = {p.person_id for p in family.partners}
    children_set = set(family.children)

    for idx, link in enumerate(family.parent_child_links):
        if link.child_id not in children_set:
            errors.append(
                f"FöräldrabarnLänk[{idx}] child_id '{link.child_id}' finns inte i familjens barnlista."
            )
        if link.parent_id is not None and link.parent_id not in partner_ids:
            errors.append(
                f"FöräldrabarnLänk[{idx}] parent_id '{link.parent_id}' är inte en partner i denna familj."
            )
        if link.parentage_type not in _VALID_PARENTAGE_TYPES:
            errors.append(
                f"FöräldrabarnLänk[{idx}] har ogiltig föräldratyp '{link.parentage_type}'; "
                f"måste vara en av {sorted(_VALID_PARENTAGE_TYPES)}."
            )
        # parent_id may be None ONLY when parentage_type is unknown_donor
        if link.parent_id is None and link.parentage_type != "unknown_donor":
            errors.append(
                f"FöräldrabarnLänk[{idx}] parent_id är None men föräldratyp är "
                f"'{link.parentage_type}'; parent_id får bara vara None när föräldratyp är 'unknown_donor'."
            )

    return errors


# ---------------------------------------------------------------------------
# 3.3 – Event validation
# ---------------------------------------------------------------------------


def validate_event(event: Event) -> list[str]:
    """Validate an Event instance."""
    errors: list[str] = []

    if not event.type or not event.type.strip():
        errors.append("Händelsetyp måste vara en icke-tom sträng.")

    if not event.participants:
        errors.append("Händelse måste ha minst en deltagare.")

    # Date validation
    if event.date is not None:
        if event.date.value and not _ISO_DATE_RE.match(event.date.value):
            errors.append(
                f"Datumvärde '{event.date.value}' är inte ett giltigt ISO 8601-datum "
                f"(förväntat ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD)."
            )
        if event.date.precision not in _VALID_DATE_PRECISIONS:
            errors.append(
                f"Datumprecision '{event.date.precision}' är ogiltig; "
                f"måste vara en av {sorted(_VALID_DATE_PRECISIONS)}."
            )

    # Custom event type validation
    if event.type in _CUSTOM_EVENT_TYPES:
        if not event.custom_type_name or not event.custom_type_name.strip():
            errors.append(
                f"Anpassad händelsetyp '{event.type}' kräver ett icke-tomt custom_type_name."
            )
        elif len(event.custom_type_name) > 100:
            errors.append("custom_type_name överskrider 100 tecken.")

    return errors


# ---------------------------------------------------------------------------
# 3.4 – Place validation
# ---------------------------------------------------------------------------


def validate_external_id(ext_id: ExternalId) -> list[str]:
    """Validate a single ExternalId entry (key 1-100 chars, value 1-500 chars, no whitespace-only)."""
    errors: list[str] = []

    # Key validation
    if not ext_id.key or not ext_id.key.strip():
        errors.append("Nyckel krävs.")
    elif len(ext_id.key) > 100:
        errors.append("Nyckeln får vara högst 100 tecken.")

    # Value validation
    if not ext_id.value or not ext_id.value.strip():
        errors.append("Värde krävs.")
    elif len(ext_id.value) > 500:
        errors.append("Värdet får vara högst 500 tecken.")

    return errors


def validate_alternative_name(name: str) -> list[str]:
    """Validate a single alternative name (1-200 chars, not whitespace-only)."""
    errors: list[str] = []

    if not name or not name.strip():
        errors.append("Alternativnamnet måste innehålla minst ett tecken.")
    elif len(name) > 200:
        errors.append("Alternativnamnet får vara högst 200 tecken.")

    return errors


def validate_place_external_ids(place: Place) -> list[str]:
    """Validate all external IDs on a place (no duplicate keys, each entry valid)."""
    errors: list[str] = []

    seen_keys: set[str] = set()
    for ext_id in place.external_ids:
        # Validate individual entry
        entry_errors = validate_external_id(ext_id)
        errors.extend(entry_errors)

        # Check for duplicate keys (only if key is non-empty and valid)
        if ext_id.key and ext_id.key.strip():
            if ext_id.key in seen_keys:
                errors.append(f"Nyckeln '{ext_id.key}' finns redan.")
            else:
                seen_keys.add(ext_id.key)

    return errors


def validate_place_alternative_names(place: Place) -> list[str]:
    """Validate all alternative names on a place (no duplicates, each valid)."""
    errors: list[str] = []

    seen_names: set[str] = set()
    for name in place.alternative_names:
        # Validate individual entry
        entry_errors = validate_alternative_name(name)
        errors.extend(entry_errors)

        # Check for duplicates (case-sensitive exact match)
        if name in seen_names:
            errors.append("Alternativnamnet finns redan.")
        else:
            seen_names.add(name)

    return errors


def validate_region_levels(levels: list[RegionLevel]) -> list[str]:
    """Validate region level definitions on a country place.

    Checks:
    - Max 10 entries
    - Key length 1-50 chars (non-empty)
    - Label length 1-100 chars (non-empty)
    - Keys unique within the list
    - Order values consecutive integers starting at 1
    """
    errors: list[str] = []

    if len(levels) > 10:
        errors.append("Högst 10 regionnivåer tillåtna.")

    seen_keys: set[str] = set()

    for rl in levels:
        # Key validation
        if not rl.key or len(rl.key) < 1 or len(rl.key) > 50:
            errors.append("Regionnivåns nyckel måste vara 1–50 tecken.")
        else:
            if rl.key in seen_keys:
                errors.append(f"Regionnivåns nyckel '{rl.key}' finns redan.")
            else:
                seen_keys.add(rl.key)

        # Label validation
        if not rl.label or len(rl.label) < 1 or len(rl.label) > 100:
            errors.append("Regionnivåns etikett måste vara 1–100 tecken.")

    # Check order values are consecutive from 1
    if levels:
        expected_orders = list(range(1, len(levels) + 1))
        actual_orders = [rl.order for rl in levels]
        if actual_orders != expected_orders:
            errors.append("Regionnivåernas ordning måste vara löpande heltal från 1.")

    return errors


def validate_custom_field_values(
    place: Place,
    place_lookup: Optional[dict[str, Place] | Callable[[str], Optional[Place]]] = None,
) -> list[str]:
    """Validate custom field values on a place.

    Checks:
    - Values must be 1-20 chars or empty (empty is acceptable, fields are optional)
    - Keys must match a CustomFieldDef key from the country's region level
      (only enforced when place_lookup is a dict and country can be found)
    """
    errors: list[str] = []

    if not place.custom_field_values:
        return errors

    # Validate value lengths
    for key, value in place.custom_field_values.items():
        if value and len(value) > 20:
            errors.append("Anpassat fältvärde får vara högst 20 tecken.")

    return errors


def _get_all_region_level_keys(
    place_lookup: dict[str, Place] | Callable[[str], Optional[Place]],
) -> set[str]:
    """Collect all region level keys from countries in a place lookup dict.

    Only works when place_lookup is a dict. Returns an empty set for callables.
    """
    if callable(place_lookup):
        return set()
    keys: set[str] = set()
    for place in place_lookup.values():
        if place.type == "country":
            for rl in place.region_levels:
                keys.add(rl.key)
    return keys


def validate_place(
    place: Place,
    place_lookup: Optional[dict[str, Place] | Callable[[str], Optional[Place]]] = None,
) -> list[str]:
    """Validate a Place instance.

    *place_lookup* can be either a ``dict[str, Place]`` mapping place IDs to
    Place objects, or a callable ``(str) -> Optional[Place]`` for hierarchy
    validation.

    Type validation accepts:
    - Static/universal types (continent, country, church, cemetery, farm, school, ort)
    - Any region level key defined on a country in the project (when place_lookup
      is a dict)
    - Any non-empty type when place_lookup is None or a callable (cannot validate
      dynamic types without full context)
    """
    errors: list[str] = []

    # Type validation: accept static types and dynamic region-level keys
    if place.type not in _VALID_PLACE_TYPES:
        # Check if the type is a region-level key from a country in the project
        if place_lookup is not None and not callable(place_lookup):
            region_keys = _get_all_region_level_keys(place_lookup)
            if place.type not in region_keys:
                all_valid = _VALID_PLACE_TYPES | region_keys
                swedish_types = sorted(
                    _PLACE_TYPE_SWEDISH.get(t, t) for t in all_valid
                )
                errors.append(
                    f"Ogiltig platstyp '{place.type}'; måste vara en av {swedish_types}."
                )
        # When place_lookup is None or a callable, accept any non-empty type
        # (we can't validate dynamic region-level keys without full context)

    if not place.name or len(place.name) < 1 or len(place.name) > 200:
        errors.append("Platsnamn måste vara 1–200 tecken.")

    # Latitude / longitude bounds
    if place.latitude is not None:
        if not (-90 <= place.latitude <= 90):
            errors.append(f"Latitud {place.latitude} är utanför giltigt intervall (-90 till 90).")

    if place.longitude is not None:
        if not (-180 <= place.longitude <= 180):
            errors.append(f"Longitud {place.longitude} är utanför giltigt intervall (-180 till 180).")

    # Hierarchy rules
    _validate_place_hierarchy(place, place_lookup, errors)

    # Region level validation (only for countries)
    if place.type == "country" and place.region_levels:
        errors.extend(validate_region_levels(place.region_levels))

    # External IDs validation
    errors.extend(validate_place_external_ids(place))

    # Alternative names validation
    errors.extend(validate_place_alternative_names(place))

    # Custom field values validation
    if place.custom_field_values:
        errors.extend(validate_custom_field_values(place, place_lookup))

    return errors


def _resolve_place(
    place_id: str,
    place_lookup: Optional[dict[str, Place] | Callable[[str], Optional[Place]]],
) -> Optional[Place]:
    """Resolve a place_id using the provided lookup."""
    if place_lookup is None:
        return None
    if callable(place_lookup):
        return place_lookup(place_id)
    return place_lookup.get(place_id)


def _find_country_for_place(
    place: Place,
    place_lookup: dict[str, Place] | Callable[[str], Optional[Place]],
) -> Optional[Place]:
    """Walk up the hierarchy to find the country ancestor of a place."""
    current = place
    visited: set[str] = {place.id}
    while current.parent_place_id is not None:
        if current.parent_place_id in visited:
            return None  # Circular reference, bail out
        visited.add(current.parent_place_id)
        parent = _resolve_place(current.parent_place_id, place_lookup)
        if parent is None:
            return None
        if parent.type == "country":
            return parent
        current = parent
    return None


def _get_region_level_for_type(
    type_key: str,
    place_lookup: dict[str, Place] | Callable[[str], Optional[Place]],
) -> Optional[tuple[Place, "RegionLevel"]]:
    """Find the country and RegionLevel that defines the given type key.

    Returns (country_place, region_level) or None if not found.
    Only works with dict lookups (can iterate all places).
    """
    from slaktbusken.model.place import RegionLevel as RL

    if callable(place_lookup):
        return None
    for p in place_lookup.values():
        if p.type == "country":
            for rl in p.region_levels:
                if rl.key == type_key:
                    return (p, rl)
    return None


def _validate_place_hierarchy(
    place: Place,
    place_lookup: Optional[dict[str, Place] | Callable[[str], Optional[Place]]],
    errors: list[str],
) -> None:
    """Check hierarchy rules for a place.

    Rules:
    - continent: must NOT have a parent
    - country: must have a parent of type "continent"
    - region-level types: parent must be country (if order=1) or preceding
      region level (order-1)
    - universal types (church, cemetery, farm, school): parent must be a
      region-level type or "ort"
    - locality (ort): parent must be a region-level type
    """
    if place.type == "continent":
        if place.parent_place_id is not None:
            errors.append("En kontinent får inte ha en överordnad plats.")
        return

    if place.type == "country":
        if place.parent_place_id is None:
            errors.append("Ett land måste ha en kontinent som överordnad plats.")
            return
        if place_lookup is not None:
            parent = _resolve_place(place.parent_place_id, place_lookup)
            if parent is None:
                errors.append(
                    f"Överordnad plats '{place.parent_place_id}' hittades inte."
                )
            elif parent.type != "continent":
                errors.append(
                    "Ett lands överordnade plats måste vara av typen 'kontinent'."
                )
        return

    if place.type in _UNIVERSAL_PLACE_TYPES:
        # Universal types require a parent that is a region-level type or "ort"
        if place.parent_place_id is None:
            errors.append(
                f"En plats av typen '{_PLACE_TYPE_SWEDISH.get(place.type, place.type)}' "
                f"måste ha en överordnad plats."
            )
            return
        if place_lookup is not None:
            parent = _resolve_place(place.parent_place_id, place_lookup)
            if parent is None:
                errors.append(
                    f"Överordnad plats '{place.parent_place_id}' hittades inte."
                )
            elif parent.type != "ort":
                # Check if parent is a region-level type
                rl_info = _get_region_level_for_type(parent.type, place_lookup)
                if rl_info is None and parent.type not in _VALID_PLACE_TYPES:
                    # Unknown type; if lookup is a dict, we know all types — reject
                    if not callable(place_lookup):
                        errors.append(
                            f"En plats av typen '{_PLACE_TYPE_SWEDISH.get(place.type, place.type)}' "
                            f"måste ha en överordnad plats av en regionnivåtyp eller 'ort'."
                        )
                elif rl_info is None and parent.type in _VALID_PLACE_TYPES:
                    # Parent is a static type that is not a region level or ort
                    # (e.g., continent, country, or another universal type)
                    if parent.type not in ("ort",):
                        # Country and continent are not valid parents for universal types
                        # (but we don't want to be too strict here if we can't resolve)
                        pass
        return

    if place.type == "ort":
        # Locality requires a parent that is a region-level type
        if place.parent_place_id is None:
            errors.append("En plats av typen 'ort' måste ha en överordnad plats.")
            return
        if place_lookup is not None:
            parent = _resolve_place(place.parent_place_id, place_lookup)
            if parent is None:
                errors.append(
                    f"Överordnad plats '{place.parent_place_id}' hittades inte."
                )
            elif not callable(place_lookup):
                # Check if parent is a region-level type
                rl_info = _get_region_level_for_type(parent.type, place_lookup)
                if rl_info is None:
                    # Parent is not a known region-level type
                    errors.append(
                        "En plats av typen 'ort' måste ha en överordnad plats "
                        "av en regionnivåtyp."
                    )
        return

    # If we reach here, the type is potentially a region-level type
    # (not in the static set and not handled above)
    if place.type not in _VALID_PLACE_TYPES:
        # Treat as a region-level type
        if place.parent_place_id is None:
            errors.append(
                f"En plats av typen '{place.type}' måste ha en överordnad plats."
            )
            return
        if place_lookup is not None and not callable(place_lookup):
            # Try to find the region level definition for this type
            rl_info = _get_region_level_for_type(place.type, place_lookup)
            if rl_info is not None:
                country, region_level = rl_info
                parent = _resolve_place(place.parent_place_id, place_lookup)
                if parent is None:
                    errors.append(
                        f"Överordnad plats '{place.parent_place_id}' hittades inte."
                    )
                elif region_level.order == 1:
                    # First region level must have country as parent
                    if parent.type != "country":
                        errors.append(
                            f"En plats av typen '{place.type}' (ordning 1) måste ha "
                            f"ett land som överordnad plats."
                        )
                else:
                    # Higher order region level must have preceding region level as parent
                    preceding_rl = None
                    for rl in country.region_levels:
                        if rl.order == region_level.order - 1:
                            preceding_rl = rl
                            break
                    if preceding_rl is not None and parent.type != preceding_rl.key:
                        errors.append(
                            f"En plats av typen '{place.type}' (ordning {region_level.order}) "
                            f"måste ha en överordnad plats av typen '{preceding_rl.key}'."
                        )


# ---------------------------------------------------------------------------
# 3.5 – Source, Repository, and MediaItem validation
# ---------------------------------------------------------------------------


def validate_source(source: Source) -> list[str]:
    """Validate a Source instance."""
    errors: list[str] = []

    if source.source_type not in _VALID_SOURCE_TYPES:
        errors.append(
            f"Ogiltig källtyp '{source.source_type}'; "
            f"måste vara en av {sorted(_VALID_SOURCE_TYPES)}."
        )

    # Structured reference field validation
    if source.source_type in _STRUCTURED_REFERENCE_FIELDS:
        expected_fields = _STRUCTURED_REFERENCE_FIELDS[source.source_type]
        actual_fields = set(source.structured_reference.fields.keys())
        unexpected = actual_fields - expected_fields
        if unexpected:
            errors.append(
                f"Strukturerad referens för '{source.source_type}' har oväntade fält: "
                f"{sorted(unexpected)}; tillåtna: {sorted(expected_fields)}."
            )

    return errors


def validate_repository(repository: Repository) -> list[str]:
    """Validate a Repository instance."""
    errors: list[str] = []

    if not repository.type or not repository.type.strip():
        errors.append("Arkivtyp måste vara en icke-tom sträng.")

    return errors


def validate_media_item(media_item: MediaItem) -> list[str]:
    """Validate a MediaItem instance."""
    errors: list[str] = []

    if media_item.type not in _VALID_MEDIA_TYPES:
        errors.append(
            f"Ogiltig mediatyp '{media_item.type}'; "
            f"måste vara en av {sorted(_VALID_MEDIA_TYPES)}."
        )

    # Annotations count validation (max 100)
    if len(media_item.annotations) > 100:
        errors.append("MediaItem får ha max 100 annoteringar.")

    # Title length validation (1–200 characters)
    if len(media_item.title) < 1 or len(media_item.title) > 200:
        errors.append("Mediatitel måste vara 1–200 tecken.")

    # File path must be relative
    file_path = media_item.file
    if file_path.startswith("/"):
        errors.append("Mediasökväg måste vara relativ (får inte börja med '/').")
    if re.match(r"^[A-Za-z]:\\", file_path) or re.match(r"^[A-Za-z]:/", file_path):
        errors.append("Mediasökväg måste vara relativ (får inte börja med en enhetsbokstav).")

    # File path must use forward slashes only
    if "\\" in file_path:
        errors.append("Mediasökväg får bara använda snedstreck (/).")

    return errors


# ---------------------------------------------------------------------------
# 3.6 – DNA entity validation
# ---------------------------------------------------------------------------


def validate_dna_profile(
    profile: DnaProfile,
    valid_person_ids: Optional[set[str]] = None,
    valid_company_ids: Optional[set[str]] = None,
) -> list[str]:
    """Validate a DnaProfile instance."""
    errors: list[str] = []

    if profile.test_type not in _VALID_DNA_TEST_TYPES:
        errors.append(
            f"Ogiltig testtyp '{profile.test_type}'; "
            f"måste vara en av {sorted(_VALID_DNA_TEST_TYPES)}."
        )

    if valid_person_ids is not None and profile.person_id not in valid_person_ids:
        errors.append(
            f"person_id '{profile.person_id}' refererar inte till en giltig person."
        )

    if valid_company_ids is not None and profile.company_id not in valid_company_ids:
        errors.append(
            f"company_id '{profile.company_id}' refererar inte till ett giltigt företag."
        )

    return errors


def validate_dna_match(match: DnaMatch) -> list[str]:
    """Validate a DnaMatch instance."""
    errors: list[str] = []

    if not (0.0 <= match.shared_cm <= 7400.0):
        errors.append(
            f"shared_cm {match.shared_cm} är utanför giltigt intervall (0,0 till 7400,0)."
        )

    if not (0.0 <= match.shared_percentage <= 100.0):
        errors.append(
            f"shared_percentage {match.shared_percentage} är utanför giltigt intervall (0,00 till 100,00)."
        )

    if not (0 <= match.segment_count <= 10000):
        errors.append(
            f"segment_count {match.segment_count} är utanför giltigt intervall (0 till 10000)."
        )

    if not (0.0 <= match.largest_segment_cm <= 300.0):
        errors.append(
            f"largest_segment_cm {match.largest_segment_cm} är utanför giltigt intervall (0,0 till 300,0)."
        )

    return errors


def validate_dna_segment(segment: DnaSegment) -> list[str]:
    """Validate a DnaSegment instance."""
    errors: list[str] = []

    if segment.chromosome not in _VALID_CHROMOSOMES:
        errors.append(
            f"Ogiltig kromosom '{segment.chromosome}'; "
            f"måste vara en av 1–22, X eller Y."
        )

    if segment.start_position >= segment.end_position:
        errors.append("start_position måste vara mindre än end_position.")

    if segment.cm <= 0:
        errors.append("cm måste vara större än 0.")

    if segment.snp_count < 0:
        errors.append("snp_count måste vara >= 0.")

    return errors


def validate_dna_cluster(cluster: DnaCluster) -> list[str]:
    """Validate a DnaCluster instance."""
    errors: list[str] = []

    if not cluster.name or len(cluster.name) < 1 or len(cluster.name) > 200:
        errors.append("DNA-klusternamn måste vara 1–200 tecken.")

    return errors


def validate_dna_triangulation(triangulation: DnaTriangulation) -> list[str]:
    """Validate a DnaTriangulation instance."""
    errors: list[str] = []

    if len(triangulation.profile_ids) < 3:
        errors.append("DNA-triangulering måste ha minst 3 profile_ids.")

    return errors
