"""Place data container."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExternalId:
    """A key-value pair linking a place to an external system identifier."""

    key: str
    value: str


@dataclass
class Place:
    """A place, optionally nested within a parent place hierarchy."""

    id: str
    type: str
    name: str
    parent_place_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: str = ""
    external_ids: list[ExternalId] = field(default_factory=list)
    alternative_names: list[str] = field(default_factory=list)


def needs_red_dot(place: Place) -> bool:
    """Determine if a place should show the red dot indicator."""
    return place.type != "country" and place.parent_place_id is None


def add_alternative_name(place: Place, name: str) -> list[str]:
    """Validate, trim, and append an alternative name to a place.

    Returns a list of error messages (empty list on success).
    The name is trimmed of leading/trailing whitespace before duplicate
    checking and storage. Duplicate detection is case-sensitive exact match
    on the trimmed value.
    """
    errors: list[str] = []

    # Validate: must not be empty or whitespace-only
    if not name or not name.strip():
        errors.append("Alternativnamnet måste innehålla minst ett tecken.")
        return errors

    # Validate: must not exceed 200 characters
    if len(name) > 200:
        errors.append("Alternativnamnet får vara högst 200 tecken.")
        return errors

    trimmed = name.strip()

    # Check for duplicates (case-sensitive exact match after trimming)
    if trimmed in place.alternative_names:
        errors.append("Alternativnamnet finns redan.")
        return errors

    place.alternative_names.append(trimmed)
    return errors


def remove_alternative_name(place: Place, index: int) -> None:
    """Remove the alternative name at the given index.

    Preserves the order of all remaining entries.
    """
    del place.alternative_names[index]


# ---------------------------------------------------------------------------
# External ID helper operations
# ---------------------------------------------------------------------------


def _validate_external_id_fields(ext_id: ExternalId) -> list[str]:
    """Validate a single ExternalId entry (key 1-100 chars, value 1-500 chars, no whitespace-only).

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    if not ext_id.key or not ext_id.key.strip():
        errors.append("Nyckel krävs.")
    elif len(ext_id.key) > 100:
        errors.append("Nyckeln får vara högst 100 tecken.")

    if not ext_id.value or not ext_id.value.strip():
        errors.append("Värde krävs.")
    elif len(ext_id.value) > 500:
        errors.append("Värdet får vara högst 500 tecken.")

    return errors


def add_external_id(place: Place, ext_id: ExternalId) -> list[str]:
    """Validate and append an ExternalId to a place.

    Checks that the entry is valid (non-empty, within length limits) and that
    the key does not already exist on the place. If valid, appends the entry.

    Returns a list of error messages. An empty list means success.
    """
    errors = _validate_external_id_fields(ext_id)
    if errors:
        return errors

    # Check for duplicate key
    for existing in place.external_ids:
        if existing.key == ext_id.key:
            errors.append(f"Nyckeln '{ext_id.key}' finns redan.")
            return errors

    place.external_ids.append(ext_id)
    return []


def remove_external_id(place: Place, key: str) -> None:
    """Remove an ExternalId entry by key from a place.

    If no entry with the given key exists, the list remains unchanged.
    """
    place.external_ids = [eid for eid in place.external_ids if eid.key != key]


def edit_external_id(place: Place, old_key: str, new_ext_id: ExternalId) -> list[str]:
    """Validate and update an ExternalId entry on a place.

    Replaces the entry whose key matches *old_key* with *new_ext_id*.
    Validates that the new entry is valid and that the new key does not
    conflict with other existing keys (excluding the entry being replaced).

    Returns a list of error messages. An empty list means success.
    """
    errors = _validate_external_id_fields(new_ext_id)
    if errors:
        return errors

    # Check for duplicate key among other entries (excluding the one being replaced)
    for existing in place.external_ids:
        if existing.key == old_key:
            continue
        if existing.key == new_ext_id.key:
            errors.append(f"Nyckeln '{new_ext_id.key}' finns redan.")
            return errors

    # Find and replace the entry
    for i, existing in enumerate(place.external_ids):
        if existing.key == old_key:
            place.external_ids[i] = new_ext_id
            return []

    # old_key not found — no change
    return []
