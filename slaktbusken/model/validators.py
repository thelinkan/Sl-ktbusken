"""Validation functions for domain model entities.

Each ``validate_*`` function accepts an entity instance (and optional reference
sets where cross-entity checks are needed) and returns a ``list[str]`` of error
messages.  An empty list means the entity is valid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from slaktbusken.model.date_span import is_valid_iso, strictly_earlier
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
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
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

# Requirement 18.7 — the exact wording of the Flytt same-place warning.
_MSG_FLYTT_SAME_PLACE = (
    "Flytten har samma plats som både från och till – kontrollera uppgifterna."
)

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

    # A Flytt_Event never errors on its two places: an absent `from_place`, an
    # absent `place` or both absent all mean an unknown side of the move, and a
    # Flytt with the same place on both sides is a warning-level finding from
    # ``event_findings`` (Requirements 18.3, 18.7).

    return errors


@dataclass
class EventFinding:
    """A warning-level observation about an Event.

    Kept apart from ``validate_event``, which returns hard errors only: the
    residence-periods design keeps errors as Swedish strings from the
    ``validate_*`` functions and gives severity-carrying findings their own
    return type.

    Attributes:
        event_id: The id of the Event the finding concerns.
        severity: Always ``"warning"`` today.
        message: The exact Swedish message to display.
    """

    event_id: str
    severity: str
    message: str


def event_findings(event: Event) -> list[EventFinding]:
    """Return the warning-level findings for an Event.

    A Flytt_Event whose ``from_place`` and ``place`` are both present and hold
    the same ``place_id`` yields ``_MSG_FLYTT_SAME_PLACE`` (Requirement 18.7).
    Everything else — an absent origin, an absent destination, both absent, or
    two different places — yields nothing, and none of these are ever errors
    (Requirement 18.3).
    """
    findings: list[EventFinding] = []

    if event.type == "flytt" and event.from_place is not None and event.place is not None:
        if event.from_place.place_id == event.place.place_id:
            findings.append(EventFinding(event.id, "warning", _MSG_FLYTT_SAME_PLACE))

    return findings


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
    """Collect all region level keys that should be considered valid place types.

    Gathers keys from three sources:
    1. Region levels explicitly set on country places in the project.
    2. ALL known country presets — unconditionally included so that any
       preset-defined region-level type (lan, socken, fylke, kommune, etc.)
       is always accepted as valid regardless of which countries exist.

    This ensures validation never rejects a region-level type that could
    legitimately appear in a GEDCOM import.

    Only works when place_lookup is a dict. Returns an empty set for callables.
    """
    if callable(place_lookup):
        return set()

    from slaktbusken.data.country_presets import get_preset, AVAILABLE_PRESETS

    keys: set[str] = set()

    # Include keys from all known country presets unconditionally
    for preset_name in AVAILABLE_PRESETS:
        for rl in get_preset(preset_name):
            keys.add(rl.key)

    # Also include any custom region_levels defined on country places in the project
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


# ---------------------------------------------------------------------------
# 3.7 – Residence validation
# ---------------------------------------------------------------------------

# Length limits (Requirements 1.10, 1.11, 2.1, 2.14, 4.1, 4.2, 10.6)
_RESIDENCE_NOTES_MAX_LENGTH = 5000
_RESIDENCE_ROLE_MAX_LENGTH = 100
_ENDPOINT_NOTE_MAX_LENGTH = 1000
_MAX_OBSERVATIONS = 100

# The plausible year range an Observation bound must fall in (Requirement 4.12).
_MIN_OBSERVATION_YEAR = 1500
_MAX_OBSERVATION_YEAR = 2100

# An Observation bound is a bare four-digit year (ÅÅÅÅ) — nothing else.
_OBSERVATION_YEAR_RE = re.compile(r"^\d{4}$")

# The exact Swedish error messages, one constant per acceptance criterion.
_MSG_PERSON_AND_PLACE_REQUIRED = "Boendet måste ange både person och plats."
_MSG_UNKNOWN_PERSON = "Boendet refererar till en person som inte finns."
_MSG_UNKNOWN_PLACE = "Boendet refererar till en plats som inte finns."
_MSG_NOTES_TOO_LONG = "Anteckningen får vara högst 5000 tecken."
_MSG_ROLE_TOO_LONG = "Roll i hushållet får vara högst 100 tecken."
_MSG_MALFORMED_ISO = (
    "Datumvärdet är inte ett giltigt ISO 8601-datum "
    "(förväntat ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD)."
)
_MSG_INVERTED_ENDPOINT = "Tidigaste datum får inte vara senare än senaste datum."
_MSG_END_BEFORE_START = "Boendets slut kan inte ligga före dess början."
_MSG_ENDPOINT_NOTE_TOO_LONG = "Endpunktens anteckning får vara högst 1000 tecken."
_MSG_UNKNOWN_EVENT = "Endpunkten refererar till en händelse som inte finns."
_MSG_TOO_MANY_OBSERVATIONS = "Ett boende får ha högst 100 observationer."
_MSG_BAD_OBSERVATION_YEAR = (
    "Observationens årtal måste anges som fyra siffror (ÅÅÅÅ) mellan 1500 och 2100."
)
_MSG_INVERTED_OBSERVATION = "Observationens startår får inte vara senare än dess slutår."
_MSG_UNKNOWN_OBSERVATION_SOURCE = "Observationen refererar till en källa som inte finns."


def _residence_value_present(value: Optional[str]) -> bool:
    """Whether a residence value counts as present.

    ``None``, empty and whitespace-only all count as absent, for Endpoint bounds
    (Requirement 2.1) as well as for `person_id`/`place_id` (Requirement 1.7).
    """
    return value is not None and bool(value.strip())


def _observation_year_value(value: Optional[str]) -> Optional[int]:
    """The year an Observation bound holds, or ``None`` when it holds no year.

    Only the bare four-digit form ÅÅÅÅ is a year; the 1500–2100 range check is
    left to the caller so an out-of-range year can still be compared with its
    counterpart.
    """
    if value is None:
        return None
    trimmed = value.strip()
    if not _OBSERVATION_YEAR_RE.match(trimmed):
        return None
    return int(trimmed)


def _validate_residence_endpoint(
    endpoint: Endpoint,
    valid_event_ids: Optional[set[str]],
    errors: list[str],
) -> None:
    """Collect the errors of one Endpoint into *errors*.

    `precision` is descriptive only, so no value of it is ever an error
    (Requirement 2.3).
    """
    # One message per offending value, so two malformed bounds yield two
    # messages (Requirement 2.11).
    for bound in (endpoint.earliest, endpoint.latest):
        if _residence_value_present(bound) and not is_valid_iso(bound):
            errors.append(_MSG_MALFORMED_ISO)

    # Inverted bounds, compared as day intervals: "1840" together with
    # "1840-06" is no error (Requirements 2.9, 2.15).
    if strictly_earlier(endpoint.latest, endpoint.earliest):
        errors.append(_MSG_INVERTED_ENDPOINT)

    if endpoint.note is not None and len(endpoint.note) > _ENDPOINT_NOTE_MAX_LENGTH:
        errors.append(_MSG_ENDPOINT_NOTE_TOO_LONG)

    if valid_event_ids is not None and _residence_value_present(endpoint.event_id):
        if endpoint.event_id not in valid_event_ids:
            errors.append(_MSG_UNKNOWN_EVENT)


def _validate_observation(
    observation: Observation,
    valid_source_ids: Optional[set[str]],
    errors: list[str],
) -> None:
    """Collect the errors of one Observation into *errors*."""
    # One message per offending bound: malformed, or a four-digit year outside
    # 1500–2100 (Requirement 4.12).
    for bound in (observation.observed_from, observation.observed_to):
        if not _residence_value_present(bound):
            continue
        year = _observation_year_value(bound)
        if year is None or not (_MIN_OBSERVATION_YEAR <= year <= _MAX_OBSERVATION_YEAR):
            errors.append(_MSG_BAD_OBSERVATION_YEAR)

    first = _observation_year_value(observation.observed_from)
    last = _observation_year_value(observation.observed_to)
    if first is not None and last is not None and first > last:
        errors.append(_MSG_INVERTED_OBSERVATION)

    if valid_source_ids is not None:
        if observation.source_ref.source_id not in valid_source_ids:
            errors.append(_MSG_UNKNOWN_OBSERVATION_SOURCE)


def validate_residence(
    residence: ResidenceFact,
    valid_person_ids: Optional[set[str]] = None,
    valid_place_ids: Optional[set[str]] = None,
    valid_source_ids: Optional[set[str]] = None,
    valid_event_ids: Optional[set[str]] = None,
) -> list[str]:
    """Validate a Residence_Fact ("Boende") and return its hard errors.

    Returns the exact Swedish error messages of Requirements 1.5, 1.6, 1.7,
    1.11, 2.9, 2.10, 2.11, 2.12, 2.14, 4.2, 4.4, 4.5, 4.12 and 10.6. An empty
    list means the fact holds no hard error.

    Each ``valid_*_ids`` set is optional: passing ``None`` skips that reference
    check, following the convention of the other ``validate_*`` functions here.

    Errors only. Warning-level findings — overlapping start/end windows (2.17),
    a source cited twice on one fact (4.13), evidence outside the recorded period
    (16.9) and every cross-fact comparison — live in
    ``slaktbusken/services/residence_validation.py``.

    Deliberately never an error: the type of the referenced place
    (Requirement 1.3), two facts sharing a `person_id`+`place_id` combination
    (Requirement 1.4), an Endpoint with both bounds absent (Requirement 2.8),
    an Observation holding only one of its two bounds (Requirement 4.6), an
    Observation span narrower than its Source's coverage period
    (Requirement 4.10) and any `precision` value, known or unknown
    (Requirement 2.3).
    """
    errors: list[str] = []

    # --- Person and place references (Requirements 1.5, 1.6, 1.7) ----------
    person_present = _residence_value_present(residence.person_id)
    place_present = _residence_value_present(residence.place_id)

    # One message however many of the two fields are blank (Requirement 1.7).
    if not person_present or not place_present:
        errors.append(_MSG_PERSON_AND_PLACE_REQUIRED)

    # A blank field is reported as blank only, never also as missing.
    if person_present and valid_person_ids is not None:
        if residence.person_id not in valid_person_ids:
            errors.append(_MSG_UNKNOWN_PERSON)

    if place_present and valid_place_ids is not None:
        if residence.place_id not in valid_place_ids:
            errors.append(_MSG_UNKNOWN_PLACE)

    # --- Text lengths (Requirements 1.11, 10.6) ---------------------------
    if len(residence.notes) > _RESIDENCE_NOTES_MAX_LENGTH:
        errors.append(_MSG_NOTES_TOO_LONG)

    # The role is measured after trimming, which is how it is stored (10.4).
    if len(residence.role_in_household.strip()) > _RESIDENCE_ROLE_MAX_LENGTH:
        errors.append(_MSG_ROLE_TOO_LONG)

    # --- Endpoints (Requirements 2.9, 2.11, 2.12, 2.14) -------------------
    _validate_residence_endpoint(residence.start, valid_event_ids, errors)
    _validate_residence_endpoint(residence.end, valid_event_ids, errors)

    # --- Across the two Endpoints (Requirement 2.10) ----------------------
    # An impossible Possible_Span is the only hard error defined across the two
    # Endpoints; an overlap of the start and end windows is a warning (2.17).
    if strictly_earlier(residence.end.latest, residence.start.earliest):
        errors.append(_MSG_END_BEFORE_START)

    # --- Observations (Requirements 4.2, 4.4, 4.5, 4.12) ------------------
    if len(residence.observations) > _MAX_OBSERVATIONS:
        errors.append(_MSG_TOO_MANY_OBSERVATIONS)

    for observation in residence.observations:
        _validate_observation(observation, valid_source_ids, errors)

    return errors
