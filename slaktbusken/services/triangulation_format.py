"""Pure formatting functions for triangulation list display."""

from __future__ import annotations

from slaktbusken.model.dna import DnaTriangulation
from slaktbusken.model.project import ProjectData


def _resolve_person_name(profile_id: str, project_data: ProjectData) -> str:
    """Resolve a profile_id to a person display name.

    Resolution chain: profile_id → DnaProfile → person_id → Person → names[0]
    Returns "(okänd)" if any step fails.
    """
    # Step 1: Find the DnaProfile
    profile = None
    for p in project_data.dna_profiles:
        if p.id == profile_id:
            profile = p
            break

    if profile is None:
        return "(okänd)"

    # Step 2: Find the Person via person_id
    person = None
    for per in project_data.persons:
        if per.id == profile.person_id:
            person = per
            break

    if person is None:
        return "(okänd)"

    # Step 3: Get the first name entry
    if not person.names:
        return "(okänd)"

    name = person.names[0]
    return f"{name.given} {name.surname}"


def _resolve_company_name(company_id: str, project_data: ProjectData) -> str:
    """Resolve a company_id to its display name.

    Returns "(okänt företag)" if company not found.
    """
    for company in project_data.dna_companies:
        if company.id == company_id:
            return company.name
    return "(okänt företag)"


def format_triangulation_entry(
    triangulation: DnaTriangulation,
    project_data: ProjectData,
) -> str:
    """Format a triangulation for list display.

    Format: "{company} ({x} profiler): {person1}, {person2}, ..."
    Uses "(okänd)" for unresolvable person names.
    """
    company_name = _resolve_company_name(triangulation.company_id, project_data)

    profile_count = len(triangulation.profile_ids)

    person_names = [
        _resolve_person_name(pid, project_data)
        for pid in triangulation.profile_ids
    ]

    names_str = ", ".join(person_names)

    return f"{company_name} ({profile_count} profiler): {names_str}"
