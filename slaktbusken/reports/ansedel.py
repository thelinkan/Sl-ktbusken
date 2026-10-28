"""Ansedel (person/family summary) report module.

Generates a structured ReportContent for a single person, including
personal details, life events, parents, partners, and children.
"""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path
from typing import Optional

from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.reports.content import (
    EmptyStateBlock,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    ParagraphBlock,
    ReportContent,
)
from slaktbusken.services.foster_sync import _PLACEMENT_END, _PLACEMENT_START
from slaktbusken.services.residence_query import swedish_sort_key
from slaktbusken.ui.swedish_locale import (
    format_residence_line,
    get_parentage_type_label,
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
        "M": "Man",
        "F": "Kvinna",
        "X": "Annat",
        "U": "Okänt",
    }
    return mapping.get(sex, sex)


def _translate_name_type(name_type: str) -> str:
    """Translate an English name type to Swedish."""
    mapping = {
        "birth": "Födelsenamn",
        "married": "Gift namn",
        "adopted": "Adoptivnamn",
        "also_known_as": "Även känd som",
        "aka": "Även känd som",
        "nickname": "Smeknamn",
        "immigrant": "Invandrarnamn",
        "maiden": "Flicknamn",
        "religious": "Religiöst namn",
    }
    return mapping.get(name_type.lower(), name_type)


def _translate_event_type(event_type: str) -> str:
    """Translate an English event type to Swedish."""
    mapping = {
        "birth": "Födelse",
        "death": "Död",
        "baptism": "Dop",
        "burial": "Begravning",
        "christening": "Dop",
        "marriage": "Vigsel",
        "divorce": "Skilsmässa",
        "engagement": "Förlovning",
        "immigration": "Invandring",
        "emigration": "Utvandring",
        "census": "Folkräkning",
        "residence": "Boende",
        "occupation": "Yrke",
        "education": "Utbildning",
        "graduation": "Examen",
        "retirement": "Pension",
        "confirmation": "Konfirmation",
        "will": "Testamente",
        "probate": "Bouppteckning",
        "naturalization": "Medborgarskap",
        "adoption": "Adoption",
        "adoption_ended": "Adoption upphörde",
        "foster_home": "Fosterhem",
        "foster_home_ended": "Fosterhem upphörde",
        "ordination": "Ordination",
        "military_service": "Militärtjänst",
        "name_change": "Namnbyte",
        "custom": "Övrigt",
    }
    return mapping.get(event_type.lower(), event_type)


def _find_event_by_type(person_id: str, event_type: str, data: ProjectData) -> Optional[object]:
    """Find the first event of a given type for a person."""
    for event in data.events:
        if event.type == event_type:
            for p in event.participants:
                if p.person_id == person_id:
                    return event
    return None


def _format_event_date(event) -> str:
    """Format an event's date value, or return empty string."""
    if event and event.date and event.date.value:
        return event.date.value
    return ""


def _calculate_age(birth_date: str, death_date: str) -> Optional[int]:
    """Calculate age from ISO date strings (YYYY, YYYY-MM, YYYY-MM-DD).

    Returns None if dates are insufficient for calculation.
    """
    try:
        birth_year = int(birth_date[:4])
        death_year = int(death_date[:4])
        age = death_year - birth_year

        # Adjust if we have month/day info
        if len(birth_date) >= 7 and len(death_date) >= 7:
            birth_month = int(birth_date[5:7])
            death_month = int(death_date[5:7])
            if death_month < birth_month:
                age -= 1
            elif death_month == birth_month and len(birth_date) >= 10 and len(death_date) >= 10:
                birth_day = int(birth_date[8:10])
                death_day = int(death_date[8:10])
                if death_day < birth_day:
                    age -= 1

        return age if age >= 0 else None
    except (ValueError, IndexError):
        return None


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
            label = _translate_name_type(n.type) if n.type else "Namn"
            name_lines.append(f"{label}: {' '.join(parts)}" if parts else f"{label}: -")
        report.blocks.append(ListBlock(items=name_lines))

    # Sex, birth, death, age
    sex_text = _sex_display(person.sex)
    report.blocks.append(ParagraphBlock(text=f"Kön: {sex_text}"))

    birth_event = _find_event_by_type(person_id, "birth", data)
    death_event = _find_event_by_type(person_id, "death", data)
    birth_date = _format_event_date(birth_event)
    death_date = _format_event_date(death_event)

    if birth_date:
        places_by_id = {p.id: p for p in data.places}
        birth_place = ""
        if birth_event and birth_event.place:
            place = places_by_id.get(birth_event.place.place_id)
            if place:
                birth_place = f", {place.name}"
        report.blocks.append(ParagraphBlock(text=f"Född: {birth_date}{birth_place}"))

    if death_date:
        if not hasattr(generate_ansedel, '_places_by_id_cache'):
            places_by_id = {p.id: p for p in data.places}
        death_place = ""
        if death_event and death_event.place:
            place = places_by_id.get(death_event.place.place_id)
            if place:
                death_place = f", {place.name}"
        report.blocks.append(ParagraphBlock(text=f"Död: {death_date}{death_place}"))

    if birth_date and death_date:
        age = _calculate_age(birth_date, death_date)
        if age is not None:
            report.blocks.append(ParagraphBlock(text=f"Blev {age} år"))

    # Title
    if person.title:
        report.blocks.append(ParagraphBlock(text=f"Titel: {person.title}"))

    # Occupation
    if person.occupation:
        report.blocks.append(ParagraphBlock(text=f"Yrke: {person.occupation}"))

    # --- Events section ---
    report.blocks.append(HeadingBlock(text="Händelser", level=2))
    _add_events_section(report, person_id, data)

    # --- Residences section ---
    report.blocks.append(HeadingBlock(text="Boenden", level=2))
    _add_residences_section(report, person_id, data)

    # --- Parents section ---
    report.blocks.append(HeadingBlock(text="Föräldrar", level=2))
    _add_parents_section(report, person_id, data, persons_by_id)

    # --- Partners section ---
    report.blocks.append(HeadingBlock(text="Partner", level=2))
    _add_partners_section(report, person_id, data, persons_by_id)

    # --- Children section ---
    report.blocks.append(HeadingBlock(text="Barn", level=2))
    _add_children_section(report, person_id, data, persons_by_id)

    # --- Sources section ---
    report.blocks.append(HeadingBlock(text="Källor", level=2))
    _add_sources_section(report, person_id, data)

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
    # Normalize path to NFC for correct handling of Swedish characters (å, ä, ö)
    normalized_name = unicodedata.normalize("NFC", media_item.file)
    photo_path_normalized = project_folder / normalized_name
    if not photo_path_normalized.exists():
        # Try the original non-normalized path as fallback
        if not photo_path.exists():
            logger.warning(
                "Profilbilden '%s' saknas på disk för person '%s'.",
                photo_path,
                person.id,
            )
            return
        photo_path_normalized = photo_path

    report.blocks.append(ImageBlock(path=photo_path_normalized, caption=None))


# Placement event types (start + end) that need role-aware rendering. The role
# strings themselves are imported from foster_sync (_PLACEMENT_START /
# _PLACEMENT_END) so ansedel and the sync service share a single source of
# truth for which role names mark the child vs the parents in a placement event.
_PLACEMENT_EVENT_TYPES = frozenset(_PLACEMENT_START) | frozenset(_PLACEMENT_END)


def _placement_roles_for(event_type: str) -> tuple[str, str]:
    """Return ``(child_role, parent_role)`` for a placement event type.

    Handles both START types (keys of ``_PLACEMENT_START``) and END types
    (keys of ``_PLACEMENT_END``, which resolve to their START config).
    """
    start_type = event_type if event_type in _PLACEMENT_START else _PLACEMENT_END[event_type]
    config = _PLACEMENT_START[start_type]
    return config["child_role"], config["parent_role"]


def _format_placement_event_entry(
    event,
    person_id: str,
    persons_by_id: dict[str, object],
    places_by_id: dict[str, object],
) -> str:
    """Render a foster/adoption placement event from ``person_id``'s perspective.

    The same underlying event is shown differently depending on whether this
    person is the placed child (role ``fosterbarn``/``adopterad``) or one of the
    placement parents (role ``fosterförälder``/``adoptivförälder``):

    * Child perspective – e.g. "Fosterhem (fosterföräldrar: <name>, ...)" so the
      several foster families a child lived in stay distinguishable (BUG 4).
    * Parent perspective – e.g. "Fosterhem (fosterbarn: <name>)" naming the
      placed child, since one foster family may hold several foster children and
      the parent's line must say which one it pertains to (BUG 3).

    Falls back to the plain event-type label when the person's role cannot be
    determined. The trailing " – <date> – <place>" is appended by the caller so
    the date sort key stays the raw date string.
    """
    type_label = _translate_event_type(event.type)
    child_role, parent_role = _placement_roles_for(event.type)

    # Determine this person's role in the event.
    person_role = None
    for participant in event.participants:
        if participant.person_id == person_id:
            person_role = participant.role
            break

    def _name(pid: str) -> str:
        p = persons_by_id.get(pid)
        return _format_person_name(p.names) if p else pid

    if person_role == parent_role:
        # Parent perspective: name the placed child(ren).
        child_names = [
            _name(part.person_id)
            for part in event.participants
            if part.role == child_role
        ]
        if child_names:
            noun = "adoptivbarn" if parent_role == "adoptivförälder" else "fosterbarn"
            return f"{type_label} ({noun}: {', '.join(child_names)})"
        return type_label

    if person_role == child_role:
        # Child perspective: name the other placement parents so distinct
        # families are distinguishable.
        parent_names = [
            _name(part.person_id)
            for part in event.participants
            if part.role == parent_role and part.person_id != person_id
        ]
        if parent_names:
            noun = "adoptivföräldrar" if parent_role == "adoptivförälder" else "fosterföräldrar"
            return f"{type_label} ({noun}: {', '.join(parent_names)})"
        return type_label

    return type_label


def _add_events_section(
    report: ReportContent,
    person_id: str,
    data: ProjectData,
) -> None:
    """Add all events linked to the person, including children's births/deaths, sorted by date."""
    persons_by_id = {p.id: p for p in data.persons}
    places_by_id = {p.id: p for p in data.places}

    linked_events = []
    for event in data.events:
        for participant in event.participants:
            if participant.person_id == person_id:
                linked_events.append(event)
                break

    # Find person's death date for comparison with children's deaths
    person_death_event = _find_event_by_type(person_id, "death", data)
    person_death_date = _format_event_date(person_death_event)

    # Find children whose birth/death belongs under "Barns födelse/död".
    # Only biological children count: a foster/adoptive child's birth predates
    # the placement and is not a biological "child's birth" for this person
    # (BUG 2). Include a child only when this person's link to them in that
    # family is biological.
    children_ids: set[str] = set()
    for family in data.families:
        if any(p.person_id == person_id for p in family.partners):
            for child_id in family.children:
                if _parentage_type_for(family, child_id, person_id) == "biological":
                    children_ids.add(child_id)

    # Collect all event entries as (sort_key, display_text) tuples
    # sort_key is the date string (empty dates sort first)
    all_entries: list[tuple[str, str]] = []

    # Person's own events
    for event in linked_events:
        if event.type in _PLACEMENT_EVENT_TYPES:
            # Role-aware rendering for foster/adoption placement events so the
            # parent and child lines differ and each identifies the relevant
            # child / parents (BUG 3 + BUG 4).
            lead = _format_placement_event_entry(
                event, person_id, persons_by_id, places_by_id
            )
        else:
            lead = _translate_event_type(event.type)
        parts = [lead]
        date_key = ""
        if event.date:
            date_key = event.date.value
            parts.append(event.date.value)
        if event.place:
            place = places_by_id.get(event.place.place_id)
            if place:
                parts.append(place.name)
        all_entries.append((date_key, " – ".join(parts)))

    # Children's birth and death events
    for child_id in children_ids:
        child_birth = _find_event_by_type(child_id, "birth", data)
        child_death = _find_event_by_type(child_id, "death", data)

        child = next((p for p in data.persons if p.id == child_id), None)
        child_name = _format_person_name(child.names) if child else child_id

        if child_birth and child_birth.date:
            birth_place = ""
            if child_birth.place:
                place = places_by_id.get(child_birth.place.place_id)
                if place:
                    birth_place = f", {place.name}"
            all_entries.append((
                child_birth.date.value,
                f"Barns födelse ({child_name}) – {child_birth.date.value}{birth_place}",
            ))

        # Show child's death if the child died before (or same year as) the person
        if child_death and child_death.date and person_death_date:
            child_death_date = child_death.date.value
            try:
                child_death_year = int(child_death_date[:4])
                person_death_year = int(person_death_date[:4])
                if child_death_year <= person_death_year:
                    death_place = ""
                    if child_death.place:
                        place = places_by_id.get(child_death.place.place_id)
                        if place:
                            death_place = f", {place.name}"
                    all_entries.append((
                        child_death_date,
                        f"Barns död ({child_name}) – {child_death_date}{death_place}",
                    ))
            except (ValueError, IndexError):
                pass

    if not all_entries:
        report.blocks.append(
            EmptyStateBlock(text="Inga händelser registrerade.")
        )
        return

    # Sort by date (ISO string comparison works for YYYY, YYYY-MM, YYYY-MM-DD)
    all_entries.sort(key=lambda e: e[0])

    report.blocks.append(ListBlock(items=[entry[1] for entry in all_entries]))


def _absent_first_key(value: str | None) -> tuple[int, str]:
    """Sort key placing absent (None/empty/whitespace-only) before present."""
    if value is None or not value.strip():
        return (0, "")
    return (1, value.strip())


def _add_residences_section(
    report: ReportContent,
    person_id: str,
    data: ProjectData,
) -> None:
    """Add the person's residence facts, ordered per Requirement 11.8.

    Ordering: start.earliest ascending, start.latest ascending, with absent
    sorting earlier than any present value, then place display name in Swedish
    alphabetical order.
    """
    places_by_id = {p.id: p for p in data.places}

    facts = [fact for fact in data.residences if fact.person_id == person_id]

    def _sort_key(fact: ResidenceFact) -> tuple:
        place = places_by_id.get(fact.place_id)
        place_name = place.name if place else fact.place_id
        return (
            _absent_first_key(fact.start.earliest),
            _absent_first_key(fact.start.latest),
            swedish_sort_key(place_name),
        )

    facts.sort(key=_sort_key)

    if not facts:
        report.blocks.append(
            EmptyStateBlock(text="Inga boenden registrerade.")
        )
        return

    entries: list[str] = []
    for fact in facts:
        place = places_by_id.get(fact.place_id)
        place_name = place.name if place else fact.place_id
        line = format_residence_line(place_name, fact.start, fact.end, fact.role_in_household)
        entries.append(line)

    report.blocks.append(ListBlock(items=entries))


def _parentage_type_for(
    family: object, child_id: str, parent_id: str
) -> str:
    """Return the parentage type of a parent's link to a child in a family.

    Reads the authoritative ``parent_child_links`` on the family, finding the
    link where ``child_id`` and ``parent_id`` match. When no explicit link
    exists (e.g. older biological data), the parentage is treated as
    ``"biological"``.
    """
    for link in family.parent_child_links:
        if link.child_id == child_id and link.parent_id == parent_id:
            return link.parentage_type
    return "biological"


def _add_parents_section(
    report: ReportContent,
    person_id: str,
    data: ProjectData,
    persons_by_id: dict[str, object],
) -> None:
    """Add the person's parents (from families where person is a child).

    Each parent is listed by name. For non-biological parents, the Swedish
    parentage label (e.g. "Foster", "Adoptiv") is appended so foster and
    adoptive parents are annotated distinctly from each other and from
    biological parents. Biological parents (and links with no explicit
    parentage type) are listed unannotated.
    """
    parent_entries: list[str] = []

    for family in data.families:
        if person_id in family.children:
            for partner in family.partners:
                parent = persons_by_id.get(partner.person_id)
                if parent:
                    name = _format_person_name(parent.names)
                    parentage_type = _parentage_type_for(
                        family, person_id, partner.person_id
                    )
                    if parentage_type and parentage_type != "biological":
                        label = get_parentage_type_label(parentage_type)
                        parent_entries.append(f"{name} ({label})")
                    else:
                        parent_entries.append(name)

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
    """Add the person's partners with birth and death dates.

    A co-partner is listed once even when they share more than one family with
    this person (e.g. a biological family and a derived foster family), while
    genuinely distinct partners are all kept. De-duplication is by
    ``person_id`` preserving first-seen order.
    """
    partner_entries: list[str] = []
    seen_partner_ids: set[str] = set()

    for family in data.families:
        person_is_partner = any(
            p.person_id == person_id for p in family.partners
        )
        if person_is_partner:
            for fp in family.partners:
                if fp.person_id != person_id and fp.person_id not in seen_partner_ids:
                    partner = persons_by_id.get(fp.person_id)
                    if partner:
                        seen_partner_ids.add(fp.person_id)
                        name = _format_person_name(partner.names)
                        dates = _get_birth_death_str(fp.person_id, data)
                        entry = f"{name}{dates}" if dates else name
                        partner_entries.append(entry)

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
    """Add the person's children with birth and death dates."""
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
                    dates = _get_birth_death_str(child_id, data)
                    entry = f"{name}{dates}" if dates else name
                    children_entries.append(entry)

    if not children_entries:
        report.blocks.append(
            EmptyStateBlock(text="Inga uppgifter registrerade.")
        )
    else:
        report.blocks.append(ListBlock(items=children_entries))


def _get_birth_death_str(person_id: str, data: ProjectData) -> str:
    """Get a formatted birth/death string for a person like ' (f. 1820, d. 1890)'."""
    birth_event = _find_event_by_type(person_id, "birth", data)
    death_event = _find_event_by_type(person_id, "death", data)
    birth_date = _format_event_date(birth_event)
    death_date = _format_event_date(death_event)

    parts = []
    if birth_date:
        parts.append(f"f. {birth_date}")
    if death_date:
        parts.append(f"d. {death_date}")

    if parts:
        return f" ({', '.join(parts)})"
    return ""


def _add_sources_section(
    report: ReportContent,
    person_id: str,
    data: ProjectData,
) -> None:
    """Add a section listing all sources referenced in the person's events."""
    sources_by_id = {s.id: s for s in data.sources}

    # Collect all unique source IDs from the person's events
    source_ids: set[str] = set()
    for event in data.events:
        person_in_event = any(p.person_id == person_id for p in event.participants)
        if not person_in_event:
            continue

        # Sources from event date
        if event.date:
            for sr in event.date.source_refs:
                source_ids.add(sr.source_id)

        # Sources from event place
        if event.place:
            for sr in event.place.source_refs:
                source_ids.add(sr.source_id)

    if not source_ids:
        report.blocks.append(
            EmptyStateBlock(text="Inga källor registrerade.")
        )
        return

    source_entries = []
    for source_id in sorted(source_ids):
        source = sources_by_id.get(source_id)
        if source:
            # Build display: title + provider
            parts = []
            if hasattr(source, 'title') and source.title:
                parts.append(source.title)
            if hasattr(source, 'provider') and source.provider:
                parts.append(f"({source.provider})")
            entry = " ".join(parts) if parts else source_id
            source_entries.append(entry)
        else:
            source_entries.append(f"[Okänd källa: {source_id}]")

    report.blocks.append(ListBlock(items=source_entries))
