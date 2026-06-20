"""Pure functions for DNA match display formatting and filtering."""

from __future__ import annotations

from slaktbusken.model.dna import DnaMatch
from slaktbusken.model.project import ProjectData


def resolve_person_display_name(
    profile_id: str,
    project_data: ProjectData,
) -> str:
    """Resolve a profile_id to a person display name.

    Resolution chain:
      profile_id → DnaProfile → person_id → Person → names[0] → "given surname"

    Fallbacks:
      - Profile not found → return profile_id
      - Person not found → return person_id
      - Names list empty or first entry has empty given+surname → return "(okänd)"

    Returns:
        The resolved display name string.
    """
    # Step 1: Find the DnaProfile by profile_id
    profile = None
    for p in project_data.dna_profiles:
        if p.id == profile_id:
            profile = p
            break

    if profile is None:
        return profile_id

    # Step 2: Find the Person by person_id
    person = None
    for ps in project_data.persons:
        if ps.id == profile.person_id:
            person = ps
            break

    if person is None:
        return profile.person_id

    # Step 3: Get the first name entry
    if not person.names:
        return "(okänd)"

    first_name = person.names[0]
    display = f"{first_name.given} {first_name.surname}".strip()

    if not display:
        return "(okänd)"

    return display


def matches_filter(
    matches: list[DnaMatch],
    filter_text: str,
    project_data: ProjectData,
) -> list[DnaMatch]:
    """Filter matches by person name substring (case-insensitive).

    Returns only those matches where filter_text is a substring
    of either resolved person display name (from profile1 or profile2).

    If filter_text is empty, returns all matches unchanged.
    """
    if not filter_text:
        return matches

    lower_filter = filter_text.lower()
    result = []
    for match in matches:
        name1 = resolve_person_display_name(match.profile1_id, project_data).lower()
        name2 = resolve_person_display_name(match.profile2_id, project_data).lower()
        if lower_filter in name1 or lower_filter in name2:
            result.append(match)
    return result


def format_match_entry(
    match: DnaMatch,
    project_data: ProjectData,
) -> str:
    """Format a DnaMatch into a display string.

    Format: "{Person1} \u2013 {Person2}: {shared_cm} cM ({segment_count} segment)"

    shared_cm formatting: up to 1 decimal place (e.g., "15.3", "7.0", "100.0").
    The en-dash (U+2013) is surrounded by spaces.
    """
    name1 = resolve_person_display_name(match.profile1_id, project_data)
    name2 = resolve_person_display_name(match.profile2_id, project_data)
    cm = f"{match.shared_cm:.1f}"
    return f"{name1} \u2013 {name2}: {cm} cM ({match.segment_count} segment)"
