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
from slaktbusken.model.place import Place
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
}

_VALID_DATE_PRECISIONS = {"day", "month", "year", "approximate"}

# ISO 8601 date: YYYY, YYYY-MM, or YYYY-MM-DD
_ISO_DATE_RE = re.compile(r"^\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?$")

_CUSTOM_EVENT_TYPES = {"custom_individual_event", "custom_family_event"}

_VALID_PLACE_TYPES = {"country", "county", "parish", "church", "cemetery"}

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
}

_VALID_DNA_TEST_TYPES = {"autosomal", "y-dna", "mtdna"}

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
        errors.append("Person must have at least one name entry.")

    if person.sex not in _VALID_SEX:
        errors.append(f"Invalid sex '{person.sex}'; must be one of {sorted(_VALID_SEX)}.")

    for idx, name in enumerate(person.names):
        if len(name.given) > 100:
            errors.append(f"Name[{idx}] given name exceeds 100 characters.")
        if len(name.surname) > 100:
            errors.append(f"Name[{idx}] surname exceeds 100 characters.")
        if name.event_id is not None and valid_event_ids is not None:
            if name.event_id not in valid_event_ids:
                errors.append(
                    f"Name[{idx}] event_id '{name.event_id}' does not reference a valid event."
                )

    if person.title is not None and len(person.title) > 100:
        errors.append("Title exceeds 100 characters.")

    if person.occupation is not None and len(person.occupation) > 100:
        errors.append("Occupation exceeds 100 characters.")

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
                f"Partner[{idx}] has invalid role '{partner.role}'; "
                f"must be one of {sorted(_VALID_PARTNER_ROLES)}."
            )
        if valid_person_ids is not None and partner.person_id not in valid_person_ids:
            errors.append(
                f"Partner[{idx}] person_id '{partner.person_id}' does not reference a valid person."
            )

    # Children reference existing persons
    if valid_person_ids is not None:
        for child_id in family.children:
            if child_id not in valid_person_ids:
                errors.append(
                    f"Child '{child_id}' does not reference a valid person."
                )

    # No duplicate children
    if len(family.children) != len(set(family.children)):
        errors.append("Family contains duplicate children.")

    # Parent-child links validation
    partner_ids = {p.person_id for p in family.partners}
    children_set = set(family.children)

    for idx, link in enumerate(family.parent_child_links):
        if link.child_id not in children_set:
            errors.append(
                f"ParentChildLink[{idx}] child_id '{link.child_id}' is not in the family's children list."
            )
        if link.parent_id is not None and link.parent_id not in partner_ids:
            errors.append(
                f"ParentChildLink[{idx}] parent_id '{link.parent_id}' is not a partner in this family."
            )
        if link.parentage_type not in _VALID_PARENTAGE_TYPES:
            errors.append(
                f"ParentChildLink[{idx}] has invalid parentage_type '{link.parentage_type}'; "
                f"must be one of {sorted(_VALID_PARENTAGE_TYPES)}."
            )
        # parent_id may be None ONLY when parentage_type is unknown_donor
        if link.parent_id is None and link.parentage_type != "unknown_donor":
            errors.append(
                f"ParentChildLink[{idx}] parent_id is None but parentage_type is "
                f"'{link.parentage_type}'; parent_id may only be None when parentage_type is 'unknown_donor'."
            )

    return errors


# ---------------------------------------------------------------------------
# 3.3 – Event validation
# ---------------------------------------------------------------------------


def validate_event(event: Event) -> list[str]:
    """Validate an Event instance."""
    errors: list[str] = []

    if not event.type or not event.type.strip():
        errors.append("Event type must be a non-empty string.")

    if not event.participants:
        errors.append("Event must have at least one participant.")

    # Date validation
    if event.date is not None:
        if event.date.value and not _ISO_DATE_RE.match(event.date.value):
            errors.append(
                f"Date value '{event.date.value}' is not a valid ISO 8601 date "
                f"(expected YYYY, YYYY-MM, or YYYY-MM-DD)."
            )
        if event.date.precision not in _VALID_DATE_PRECISIONS:
            errors.append(
                f"Date precision '{event.date.precision}' is invalid; "
                f"must be one of {sorted(_VALID_DATE_PRECISIONS)}."
            )

    # Custom event type validation
    if event.type in _CUSTOM_EVENT_TYPES:
        if not event.custom_type_name or not event.custom_type_name.strip():
            errors.append(
                f"Custom event type '{event.type}' requires a non-empty custom_type_name."
            )
        elif len(event.custom_type_name) > 100:
            errors.append("custom_type_name exceeds 100 characters.")

    return errors


# ---------------------------------------------------------------------------
# 3.4 – Place validation
# ---------------------------------------------------------------------------


def validate_place(
    place: Place,
    place_lookup: Optional[dict[str, Place] | Callable[[str], Optional[Place]]] = None,
) -> list[str]:
    """Validate a Place instance.

    *place_lookup* can be either a ``dict[str, Place]`` mapping place IDs to
    Place objects, or a callable ``(str) -> Optional[Place]`` for hierarchy
    validation.
    """
    errors: list[str] = []

    if place.type not in _VALID_PLACE_TYPES:
        errors.append(
            f"Invalid place type '{place.type}'; must be one of {sorted(_VALID_PLACE_TYPES)}."
        )

    if not place.name or len(place.name) < 1 or len(place.name) > 200:
        errors.append("Place name must be 1-200 characters.")

    # Latitude / longitude bounds
    if place.latitude is not None:
        if not (-90 <= place.latitude <= 90):
            errors.append(f"Latitude {place.latitude} is out of range (-90 to 90).")

    if place.longitude is not None:
        if not (-180 <= place.longitude <= 180):
            errors.append(f"Longitude {place.longitude} is out of range (-180 to 180).")

    # Hierarchy rules
    _validate_place_hierarchy(place, place_lookup, errors)

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


def _validate_place_hierarchy(
    place: Place,
    place_lookup: Optional[dict[str, Place] | Callable[[str], Optional[Place]]],
    errors: list[str],
) -> None:
    """Check hierarchy rules for a place."""
    # Hierarchy expectations:
    # country -> no parent
    # county -> parent must be country
    # parish -> parent must be county
    # church/cemetery -> parent must be parish
    hierarchy_requirements: dict[str, Optional[str]] = {
        "country": None,  # must have NO parent
        "county": "country",
        "parish": "county",
        "church": "parish",
        "cemetery": "parish",
    }

    if place.type not in hierarchy_requirements:
        return

    expected_parent_type = hierarchy_requirements[place.type]

    if expected_parent_type is None:
        # Country must have no parent
        if place.parent_place_id is not None:
            errors.append("A country must not have a parent place.")
        return

    # All other types require a parent
    if place.parent_place_id is None:
        errors.append(
            f"A {place.type} must have a parent of type '{expected_parent_type}'."
        )
        return

    # If we have a lookup, verify the parent type
    if place_lookup is not None:
        parent = _resolve_place(place.parent_place_id, place_lookup)
        if parent is None:
            errors.append(
                f"Parent place '{place.parent_place_id}' not found."
            )
        elif parent.type != expected_parent_type:
            errors.append(
                f"A {place.type} must have a parent of type '{expected_parent_type}', "
                f"but parent '{place.parent_place_id}' is of type '{parent.type}'."
            )


# ---------------------------------------------------------------------------
# 3.5 – Source, Repository, and MediaItem validation
# ---------------------------------------------------------------------------


def validate_source(source: Source) -> list[str]:
    """Validate a Source instance."""
    errors: list[str] = []

    if source.source_type not in _VALID_SOURCE_TYPES:
        errors.append(
            f"Invalid source_type '{source.source_type}'; "
            f"must be one of {sorted(_VALID_SOURCE_TYPES)}."
        )

    # Structured reference field validation
    if source.source_type in _STRUCTURED_REFERENCE_FIELDS:
        expected_fields = _STRUCTURED_REFERENCE_FIELDS[source.source_type]
        actual_fields = set(source.structured_reference.fields.keys())
        unexpected = actual_fields - expected_fields
        if unexpected:
            errors.append(
                f"Structured reference for '{source.source_type}' has unexpected fields: "
                f"{sorted(unexpected)}; allowed: {sorted(expected_fields)}."
            )

    return errors


def validate_repository(repository: Repository) -> list[str]:
    """Validate a Repository instance."""
    errors: list[str] = []

    if not repository.type or not repository.type.strip():
        errors.append("Repository type must be a non-empty string.")

    return errors


def validate_media_item(media_item: MediaItem) -> list[str]:
    """Validate a MediaItem instance."""
    errors: list[str] = []

    if media_item.type not in _VALID_MEDIA_TYPES:
        errors.append(
            f"Invalid media type '{media_item.type}'; "
            f"must be one of {sorted(_VALID_MEDIA_TYPES)}."
        )

    # File path must be relative
    file_path = media_item.file
    if file_path.startswith("/"):
        errors.append("Media file path must be relative (must not start with '/').")
    if re.match(r"^[A-Za-z]:\\", file_path) or re.match(r"^[A-Za-z]:/", file_path):
        errors.append("Media file path must be relative (must not start with a drive letter).")

    # File path must use forward slashes only
    if "\\" in file_path:
        errors.append("Media file path must use forward slashes only.")

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
            f"Invalid test_type '{profile.test_type}'; "
            f"must be one of {sorted(_VALID_DNA_TEST_TYPES)}."
        )

    if valid_person_ids is not None and profile.person_id not in valid_person_ids:
        errors.append(
            f"person_id '{profile.person_id}' does not reference a valid person."
        )

    if valid_company_ids is not None and profile.company_id not in valid_company_ids:
        errors.append(
            f"company_id '{profile.company_id}' does not reference a valid company."
        )

    return errors


def validate_dna_match(match: DnaMatch) -> list[str]:
    """Validate a DnaMatch instance."""
    errors: list[str] = []

    if not (0.0 <= match.shared_cm <= 7400.0):
        errors.append(
            f"shared_cm {match.shared_cm} is out of range (0.0 to 7400.0)."
        )

    if not (0.0 <= match.shared_percentage <= 100.0):
        errors.append(
            f"shared_percentage {match.shared_percentage} is out of range (0.00 to 100.00)."
        )

    if not (0 <= match.segment_count <= 10000):
        errors.append(
            f"segment_count {match.segment_count} is out of range (0 to 10000)."
        )

    if not (0.0 <= match.largest_segment_cm <= 300.0):
        errors.append(
            f"largest_segment_cm {match.largest_segment_cm} is out of range (0.0 to 300.0)."
        )

    return errors


def validate_dna_segment(segment: DnaSegment) -> list[str]:
    """Validate a DnaSegment instance."""
    errors: list[str] = []

    if segment.chromosome not in _VALID_CHROMOSOMES:
        errors.append(
            f"Invalid chromosome '{segment.chromosome}'; "
            f"must be one of 1-22, X, or Y."
        )

    if segment.start_position >= segment.end_position:
        errors.append("start_position must be less than end_position.")

    if segment.cm <= 0:
        errors.append("cm must be greater than 0.")

    if segment.snp_count < 0:
        errors.append("snp_count must be >= 0.")

    return errors


def validate_dna_cluster(cluster: DnaCluster) -> list[str]:
    """Validate a DnaCluster instance."""
    errors: list[str] = []

    if not cluster.name or len(cluster.name) < 1 or len(cluster.name) > 200:
        errors.append("DnaCluster name must be 1-200 characters.")

    return errors


def validate_dna_triangulation(triangulation: DnaTriangulation) -> list[str]:
    """Validate a DnaTriangulation instance."""
    errors: list[str] = []

    if len(triangulation.segment_ids) < 2:
        errors.append("DnaTriangulation must have at least 2 segment_ids.")

    if len(triangulation.profile_ids) < 3:
        errors.append("DnaTriangulation must have at least 3 profile_ids.")

    return errors
