"""Validation functions for source management entities (Leverantör, Källtyp)."""

from __future__ import annotations

from slaktbusken.model.source import Kalltyp, Leverantor, Source


def get_kalltyper_for_leverantor(leverantor_id: str, kalltyper: list[Kalltyp]) -> list[Kalltyp]:
    """Return all Källtyper belonging to the specified Leverantör."""
    return [kt for kt in kalltyper if kt.leverantor_id == leverantor_id]


def validate_name(value: str, max_length: int = 100) -> tuple[bool, str]:
    """Validate a Leverantör or Källtyp name.

    Accept if stripped value is non-empty and <= max_length characters.
    Returns (True, "") on success, (False, error_message) on failure.
    """
    stripped = value.strip()
    if not stripped:
        return False, "Namn krävs."
    if len(stripped) > max_length:
        return False, f"Namn får vara högst {max_length} tecken."
    return True, ""


def validate_comment(value: str, max_length: int = 500) -> tuple[bool, str]:
    """Validate a comment field.

    Optional field, accepts empty. Rejects if > max_length characters.
    Returns (True, "") on success, (False, error_message) on failure.
    """
    if len(value) > max_length:
        return False, f"Kommentar får vara högst {max_length} tecken."
    return True, ""


def validate_root_url(value: str, max_length: int = 2048) -> tuple[bool, str]:
    """Validate a root_url field.

    Optional field, accepts empty. Rejects if > max_length characters.
    Returns (True, "") on success, (False, error_message) on failure.
    """
    if len(value) > max_length:
        return False, f"URL får vara högst {max_length} tecken."
    return True, ""


def is_kalltyp_name_unique(
    leverantor_id: str,
    name: str,
    kalltyper: list[Kalltyp],
    exclude_id: str = "",
) -> bool:
    """Check if a Källtyp name is unique within the given Leverantör.

    Case-sensitive comparison. Excludes the Källtyp with exclude_id from the check
    (useful when renaming an existing Källtyp).

    Returns True if the name is unique (no conflict), False if a conflict exists.
    """
    for kt in kalltyper:
        if kt.leverantor_id != leverantor_id:
            continue
        if exclude_id and kt.id == exclude_id:
            continue
        if kt.name == name:
            return False
    return True


def is_leverantor_referenced(leverantor_id: str, sources: list[Source]) -> bool:
    """Check if a Leverantör is referenced by any Source.

    Returns True if at least one Source has leverantor_id matching the given ID.
    """
    return any(s.leverantor_id == leverantor_id for s in sources)


def is_kalltyp_referenced(kalltyp_id: str, sources: list[Source]) -> bool:
    """Check if a Källtyp is referenced by any Source.

    Returns True if at least one Source has kalltyp_id matching the given ID.
    """
    return any(s.kalltyp_id == kalltyp_id for s in sources)


def delete_leverantor(
    leverantor_id: str,
    leverantorer: list[Leverantor],
    kalltyper: list[Kalltyp],
    sources: list[Source],
) -> tuple[bool, str]:
    """Attempt to delete a Leverantör and cascade-delete its Källtyper.

    Checks:
    1. The Leverantör is not referenced by any Source
    2. None of the Leverantör's Källtyper are referenced by any Source

    If both checks pass:
    - Remove the Leverantör from the leverantorer list
    - Remove all Källtyper belonging to this Leverantör from the kalltyper list
    - Return (True, "")

    If the Leverantör itself is referenced:
    - Return (False, "Kan inte ta bort — leverantören används av en eller flera källor.")

    If any of its Källtyper are referenced:
    - Return (False, "Kan inte ta bort — en eller flera källtyper används av källor.")
    """
    if is_leverantor_referenced(leverantor_id, sources):
        return False, "Kan inte ta bort — leverantören används av en eller flera källor."

    # Check if any Källtyper belonging to this Leverantör are referenced
    for kt in kalltyper:
        if kt.leverantor_id == leverantor_id:
            if is_kalltyp_referenced(kt.id, sources):
                return False, "Kan inte ta bort — en eller flera källtyper används av källor."

    # Remove the Leverantör
    leverantorer[:] = [lev for lev in leverantorer if lev.id != leverantor_id]

    # Remove all Källtyper belonging to this Leverantör
    kalltyper[:] = [kt for kt in kalltyper if kt.leverantor_id != leverantor_id]

    return True, ""


def delete_kalltyp(
    kalltyp_id: str,
    kalltyper: list[Kalltyp],
    sources: list[Source],
) -> tuple[bool, str]:
    """Attempt to delete a single Källtyp.

    Checks if the Källtyp is referenced by any Source.

    If not referenced:
    - Remove the Källtyp from the kalltyper list
    - Return (True, "")

    If referenced:
    - Return (False, "Kan inte ta bort — källtypen används av en eller flera källor.")
    """
    if is_kalltyp_referenced(kalltyp_id, sources):
        return False, "Kan inte ta bort — källtypen används av en eller flera källor."

    kalltyper[:] = [kt for kt in kalltyper if kt.id != kalltyp_id]
    return True, ""
