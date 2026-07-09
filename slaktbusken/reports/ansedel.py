"""Ansedel (person/family summary) report module.

Generates a structured ReportContent for a single person, including
personal details, life events, parents, partners, and children.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from slaktbusken.model.project import ProjectData
from slaktbusken.reports.content import (
    EmptyStateBlock,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    ParagraphBlock,
    ReportContent,
)

logger = logging.getLogger(__name__)


def _format_person_name(names: list, fallback: str = "Okänt namn") -> str:
    """Format a person's display name from their names list.

    Uses the first name entry, combining given and surname.
    """
    if not names:
        return fallback
    name = names[0]
    parts = []
    if name.given:
        parts.append(name.given)
    if name.surname:
        parts.append(name.surname)
    return " ".join(parts) if parts else fallback


def _sex_display(sex: str) -> str:
    """Return a Swedish display string for sex."""
    mapping = {
        "male": "Man",
        "female": "Kvinna",
        "other": "Annat",
        "unknown": "Okänt",
    }
    return mapping.get(sex, sex)


def generate_ansedel(
    data: ProjectData,
    person_id: str,
    project_folder: Path | None,
) -> ReportContent:
    """Generate an Ansedel report for the given person.

    Args:
        data: The full project data containing persons, families, events, etc.
        person_id: The ID of the person to generate the report for.
        project_folder: Path to the project folder (for resolving media files).
            May be None if no folder is available.

    Returns:
        A ReportContent instance with the person's details, events, and
        family relationships.
    """
    # Look up the person.
    persons_by_id = {p.id: p for p in data.persons}
    person = persons_by_id.get(person_id)

    if person is None:
        report = ReportContent(title="Ansedel")
        report.blocks.append(
            EmptyStateBlock(text=f"Personen med id '{person_id}' hittades inte.")
        )
        return report

    person_name = _format_person_name(person.names)
    report = ReportContent(title=f"Ansedel \u2013 {person_name}")

    # --- Personal details section ---
    report.blocks.append(HeadingBlock(text="Personuppgifter", level=2))

    # Profile photo
    _add_profile_photo(report, person, data, project_folder)

    # Names
    if person.names:
        name_lines = []
        for n in person.names:
            parts = []
            if n.given:
                parts.append(n.given)
            if n.surname:
                parts.append(n.surname)
            label = n.type if n.type else "namn"
            name_lines.append(f"{label}: {' '.join(parts)}" if parts else f"{label}: -")
        report.blocks.append(ListBlock(items=name_lines))

    # Sex
    report.blocks.append(ParagraphBlock(text=f"Kön: {_sex_display(person.sex)}"))

    # Title
    if person.title:
        report.blocks.append(ParagraphBlock(text=f"Titel: {person.title}"))

    # Occupation
    if person.occupation:
        report.blocks.append(ParagraphBlock(text=f"Yrke: {person.occupation}"))

    # --- Events section ---
    report.blocks.append(HeadingBlock(text="Händelser", level=2))
    _add_events_section(report, person_id, data)

    # --- Parents section ---
    report.blocks.append(HeadingBlock(text="Föräldrar", level=2))
    _add_parents_section(report, person_id, data, persons_by_id)

    # --- Partners section ---
    report.blocks.append(HeadingBlock(text="Partner", level=2))
    _add_partners_section(report, person_id, data, persons_by_id)

    # --- Children section ---
    report.blocks.append(HeadingBlock(text="Barn", level=2))
    _add_children_section(report, person_id, data, persons_by_id)

    return report


def _add_profile_photo(
    report: ReportContent,
    person,
    data: ProjectData,
    project_folder: Path | None,
) -> None:
    """Add the person's profile photo as an ImageBlock if available."""
    if not person.profile_media_id:
        return

    # Find the media item.
    media_item = None
    for m in data.media:
        if m.id == person.profile_media_id:
            media_item = m
            break

    if media_item is None:
        logger.warning(
            "Profilbild med media-id '%s' hittades inte för person '%s'.",
            person.profile_media_id,
            person.id,
        )
        return

    if project_folder is None:
        logger.warning(
            "Ingen projektmapp angiven – kan inte visa profilbild för person '%s'.",
            person.id,
        )
        return

    photo_path = project_folder / media_item.file
    if not photo_path.exists():
        logger.warning(
            "Profilbilden '%s' saknas på disk för person '%s'.",
            photo_path,
            person.id,
        )
        return

    report.blocks.append(ImageBlock(path=photo_path, caption=None))


def _add_events_section(
    report: ReportContent,
    person_id: str,
    data: ProjectData,
) -> None:
    """Add all events linked to the person."""
    places_by_id = {p.id: p for p in data.places}

    linked_events = []
    for event in data.events:
        for participant in event.participants:
            if participant.person_id == person_id:
                linked_events.append(event)
                break

    if not linked_events:
        report.blocks.append(
            EmptyStateBlock(text="Inga händelser registrerade.")
        )
        return

    event_items = []
    for event in linked_events:
        parts = [event.type]
        if event.date:
            parts.append(event.date.value)
        if event.place:
            place = places_by_id.get(event.place.place_id)
            if place:
                parts.append(place.name)
        event_items.append(" – ".join(parts))

    report.blocks.append(ListBlock(items=event_items))


def _add_parents_section(
    report: ReportContent,
    person_id: str,
    data: ProjectData,
    persons_by_id: dict[str, object],
) -> None:
    """Add the person's parents (from families where person is a child)."""
    parent_entries: list[str] = []

    for family in data.families:
        if person_id in family.children:
            for partner in family.partners:
                parent = persons_by_id.get(partner.person_id)
                if parent:
                    name = _format_person_name(parent.names)
                    role = partner.role if partner.role else "förälder"
                    parent_entries.append(f"{name} ({role})")

    if not parent_entries:
        report.blocks.append(
            EmptyStateBlock(text="Inga uppgifter registrerade.")
        )
    else:
        report.blocks.append(ListBlock(items=parent_entries))


def _add_partners_section(
    report: ReportContent,
    person_id: str,
    data: ProjectData,
    persons_by_id: dict[str, object],
) -> None:
    """Add the person's partners (other partners in families where person is a partner)."""
    partner_entries: list[str] = []

    for family in data.families:
        person_is_partner = any(
            p.person_id == person_id for p in family.partners
        )
        if person_is_partner:
            for fp in family.partners:
                if fp.person_id != person_id:
                    partner = persons_by_id.get(fp.person_id)
                    if partner:
                        name = _format_person_name(partner.names)
                        role = fp.role if fp.role else "partner"
                        partner_entries.append(f"{name} ({role})")

    if not partner_entries:
        report.blocks.append(
            EmptyStateBlock(text="Inga uppgifter registrerade.")
        )
    else:
        report.blocks.append(ListBlock(items=partner_entries))


def _add_children_section(
    report: ReportContent,
    person_id: str,
    data: ProjectData,
    persons_by_id: dict[str, object],
) -> None:
    """Add the person's children (from families where person is a partner)."""
    children_entries: list[str] = []

    for family in data.families:
        person_is_partner = any(
            p.person_id == person_id for p in family.partners
        )
        if person_is_partner:
            for child_id in family.children:
                child = persons_by_id.get(child_id)
                if child:
                    name = _format_person_name(child.names)
                    children_entries.append(f"{name} (barn)")

    if not children_entries:
        report.blocks.append(
            EmptyStateBlock(text="Inga uppgifter registrerade.")
        )
    else:
        report.blocks.append(ListBlock(items=children_entries))
