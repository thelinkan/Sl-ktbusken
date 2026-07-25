"""Källrapport (Source Report) module.

Generates a structured ReportContent listing all sources in the project,
organized by Leverantör → Källtyp → Title (with special handling for
Arkiv Digital where title is split into Volym and Sida/Bild).

For each source entry, shows:
- Whether an image/media is available
- All persons linked to that source and what it's a source for
  (event type, date, place, etc.)
"""

from __future__ import annotations

import logging

from slaktbusken.model.project import ProjectData
from slaktbusken.reports.content import (
    EmptyStateBlock,
    HeadingBlock,
    ListBlock,
    ParagraphBlock,
    ReportContent,
)
from slaktbusken.services.source_links import generate_direct_link

logger = logging.getLogger(__name__)

# Swedish event type labels
_EVENT_TYPE_LABELS: dict[str, str] = {
    "birth": "Födelse",
    "baptism": "Dop",
    "death": "Död",
    "burial": "Begravning",
    "marriage": "Vigsel",
    "divorce": "Skilsmässa",
    "emigration": "Utvandring",
    "immigration": "Invandring",
    "census": "Folkräkning",
    "confirmation": "Konfirmation",
    "first_communion": "Nattvardsgång",
    "graduation": "Examen",
    "retirement": "Pension",
    "will": "Testamente",
    "cremation": "Kremering",
    "adoption": "Adoption",
    "blessing": "Välsignelse",
    "engagement": "Förlovning",
    "divorce_filed": "Skilsmässoansökan",
    "name_change": "Namnbyte",
    "gender_correction": "Könskorrigering",
    "custom_individual_event": "Anpassad händelse",
    "custom_family_event": "Anpassad familjehändelse",
}


def _format_person_name(names: list, fallback: str = "Okänt namn") -> str:
    """Format a person's display name from their names list."""
    if not names:
        return fallback
    name = names[0]
    parts = []
    if name.given:
        parts.append(name.given)
    if name.surname:
        parts.append(name.surname)
    return " ".join(parts) if parts else fallback


def _get_leverantor_name(data: ProjectData, leverantor_id: str) -> str:
    """Look up leverantör name by ID."""
    for lev in data.leverantorer:
        if lev.id == leverantor_id:
            return lev.name
    return ""


def _get_kalltyp_name(data: ProjectData, kalltyp_id: str) -> str:
    """Look up källtyp name by ID."""
    for kt in data.kalltyper:
        if kt.id == kalltyp_id:
            return kt.name
    return ""


def _is_arkiv_digital(data: ProjectData, leverantor_id: str) -> bool:
    """Check if a leverantör is Arkiv Digital."""
    for lev in data.leverantorer:
        if lev.id == leverantor_id:
            return lev.name.lower() == "arkiv digital"
    return False


def _get_volume_from_source(source) -> str:
    """Extract volume info from source structured reference or title."""
    fields = source.structured_reference.fields
    # Build volume identifier from parish + series:volume
    parts = []
    parish = fields.get("parish", "")
    if parish:
        parts.append(str(parish).strip())
    series = fields.get("series", "")
    volume = fields.get("volume", "")
    if series and volume:
        parts.append(f"{series}:{volume}")
    elif series:
        parts.append(str(series).strip())

    if parts:
        return " ".join(parts)

    # Fallback: use title up to "Sida:" or "Bild:" if present
    title = source.title
    for marker in ("Sida:", "Bild:"):
        idx = title.find(marker)
        if idx > 0:
            return title[:idx].strip()
    return title


def _get_page_or_image(source) -> str:
    """Extract page or image reference from source."""
    fields = source.structured_reference.fields
    page = fields.get("page", "")
    image = fields.get("image", "")
    if page:
        return f"Sida: {page}"
    if image:
        return f"Bild: {image}"
    return ""


def _collect_source_usage(data: ProjectData) -> dict[str, list[dict]]:
    """Collect all usages of each source across events.

    Returns a dict mapping source_id -> list of usage info dicts:
        {person_id, person_name, event_type, date, place, aspect}
    """
    persons_by_id = {p.id: p for p in data.persons}
    places_by_id = {p.id: p for p in data.places}

    usage: dict[str, list[dict]] = {}

    for event in data.events:
        event_type_label = _EVENT_TYPE_LABELS.get(event.type, event.type)
        if event.type in ("custom_individual_event", "custom_family_event") and event.custom_type_name:
            event_type_label = event.custom_type_name

        date_str = event.date.value if event.date else ""
        place_str = ""
        if event.place:
            place = places_by_id.get(event.place.place_id)
            if place:
                place_str = place.name

        # Get person names for this event
        participant_names = []
        for p in event.participants:
            person = persons_by_id.get(p.person_id)
            name = _format_person_name(person.names) if person else p.person_id
            # Extract individual name parts for sorting
            given = ""
            surname = ""
            if person and person.names:
                given = person.names[0].given or ""
                surname = person.names[0].surname or ""
            participant_names.append((p.person_id, name, given, surname))

        # Collect source refs from date
        if event.date:
            for sr in event.date.source_refs:
                if sr.source_id not in usage:
                    usage[sr.source_id] = []
                for person_id, person_name, given, surname in participant_names:
                    entry: dict = {
                        "person_id": person_id,
                        "person_name": person_name,
                        "person_given": given,
                        "person_surname": surname,
                        "event_type": event_type_label,
                        "date": date_str,
                        "place": place_str,
                    }
                    if sr.aspects:
                        entry["aspects"] = sr.aspects
                    usage[sr.source_id].append(entry)

        # Collect source refs from place
        if event.place:
            for sr in event.place.source_refs:
                if sr.source_id not in usage:
                    usage[sr.source_id] = []
                for person_id, person_name, given, surname in participant_names:
                    entry = {
                        "person_id": person_id,
                        "person_name": person_name,
                        "person_given": given,
                        "person_surname": surname,
                        "event_type": event_type_label,
                        "date": date_str,
                        "place": place_str,
                    }
                    if sr.aspects:
                        entry["aspects"] = sr.aspects
                    # Avoid duplicates if same source is on both date and place
                    if entry not in usage[sr.source_id]:
                        usage[sr.source_id].append(entry)

    return usage


def generate_kallrapport(data: ProjectData) -> ReportContent:
    """Generate a Källrapport (Source Report) for the entire project.

    Sources are organized hierarchically:
    - Level 1: Leverantör (provider)
    - Level 2: Källtyp (source type)
    - Level 3: Title (or Volym + Sida/Bild for Arkiv Digital)

    For each source entry, shows image availability and linked persons
    with event details.

    Args:
        data: The full project data.

    Returns:
        A ReportContent instance with the source report.
    """
    report = ReportContent(title="Källrapport")

    if not data.sources:
        report.blocks.append(EmptyStateBlock(text="Inga källor registrerade i projektet."))
        return report

    # Collect source usage info
    source_usage = _collect_source_usage(data)

    # Group sources: leverantor_id -> kalltyp_id -> list of sources
    grouped: dict[str, dict[str, list]] = {}
    for source in data.sources:
        lev_id = source.leverantor_id or "__no_leverantor__"
        kt_id = source.kalltyp_id or "__no_kalltyp__"
        grouped.setdefault(lev_id, {}).setdefault(kt_id, []).append(source)

    # Sort leverantörer by name
    lev_order = []
    for lev_id in grouped:
        if lev_id == "__no_leverantor__":
            lev_name = "Okänd leverantör"
        else:
            lev_name = _get_leverantor_name(data, lev_id)
            if not lev_name:
                lev_name = "Okänd leverantör"
        lev_order.append((lev_name, lev_id))
    lev_order.sort(key=lambda x: x[0].lower())

    for lev_name, lev_id in lev_order:
        report.blocks.append(HeadingBlock(text=lev_name, level=2))
        is_ad = _is_arkiv_digital(data, lev_id)

        # Sort källtyper by name
        kt_groups = grouped[lev_id]
        kt_order = []
        for kt_id in kt_groups:
            if kt_id == "__no_kalltyp__":
                kt_name = "Okänd källtyp"
            else:
                kt_name = _get_kalltyp_name(data, kt_id)
                if not kt_name:
                    kt_name = "Okänd källtyp"
            kt_order.append((kt_name, kt_id))
        kt_order.sort(key=lambda x: x[0].lower())

        for kt_name, kt_id in kt_order:
            report.blocks.append(HeadingBlock(text=kt_name, level=3))
            sources = kt_groups[kt_id]

            if is_ad:
                # For Arkiv Digital: group by volume, then sort by page/image
                _add_arkiv_digital_sources(report, sources, source_usage, data)
            elif _is_flat_web_source(data, kt_id):
                # For web sources like Sveriges Dödbok Webb: flat person list, no sub-titles
                _add_flat_web_sources(report, sources, source_usage, data)
            else:
                # For others: sort by title
                _add_standard_sources(report, sources, source_usage, data)

    return report


def _is_flat_web_source(data: ProjectData, kalltyp_id: str) -> bool:
    """Check if a källtyp is a flat web source (has root_url, like Sveriges Dödbok Webb)."""
    for kt in data.kalltyper:
        if kt.id == kalltyp_id:
            return bool(kt.root_url)
    return False


def _add_flat_web_sources(
    report: ReportContent,
    sources: list,
    source_usage: dict[str, list[dict]],
    data: ProjectData,
) -> None:
    """Add web sources (like Sveriges Dödbok Webb) as a flat person list.

    No per-source sub-titles. All persons across all sources in this group
    are listed directly, sorted by surname then given name, each with their link.
    """
    # Collect all person entries across all sources in this group
    all_entries: list[tuple[str, str, str]] = []  # (surname, given, display)

    for source in sources:
        direct_link = generate_direct_link(source, data.kalltyper)
        usages = source_usage.get(source.id, [])
        has_media = bool(source.media_ids)
        media_marker = "📷 " if has_media else ""

        seen: set[tuple] = set()
        for u in usages:
            key = (u["person_name"], u["event_type"], u["date"], u["place"])
            if key in seen:
                continue
            seen.add(key)
            parts = [f"{media_marker}{u['person_name']}"]
            detail_parts = []
            if u["event_type"]:
                detail_parts.append(u["event_type"])
            if u["date"]:
                detail_parts.append(u["date"])
            if u["place"]:
                detail_parts.append(u["place"])
            if detail_parts:
                parts.append(f"({', '.join(detail_parts)})")
            if direct_link:
                parts.append(f"(länk: {direct_link})")
            display = " ".join(parts)

            surname = u.get("person_surname", "")
            given = u.get("person_given", "")
            all_entries.append((surname.lower(), given.lower(), display))

    # Sort by surname, then given name
    all_entries.sort(key=lambda x: (x[0], x[1]))

    if all_entries:
        report.blocks.append(ListBlock(items=[entry[2] for entry in all_entries]))
    else:
        report.blocks.append(EmptyStateBlock(text="Inga personer kopplade."))


def _add_arkiv_digital_sources(
    report: ReportContent,
    sources: list,
    source_usage: dict[str, list[dict]],
    data: ProjectData,
) -> None:
    """Add Arkiv Digital sources grouped by Volym, then by Sida/Bild."""
    # Group by volume
    by_volume: dict[str, list] = {}
    for source in sources:
        vol = _get_volume_from_source(source)
        by_volume.setdefault(vol, []).append(source)

    # Sort volumes
    for vol_name in sorted(by_volume.keys(), key=str.lower):
        report.blocks.append(ParagraphBlock(text=f"Volym: {vol_name}"))

        # Sort sources within volume by page/image
        vol_sources = by_volume[vol_name]
        vol_sources.sort(key=lambda s: _get_page_or_image(s))

        for source in vol_sources:
            page_ref = _get_page_or_image(source)
            _add_source_entry(report, source, source_usage, data, label=page_ref)


def _add_standard_sources(
    report: ReportContent,
    sources: list,
    source_usage: dict[str, list[dict]],
    data: ProjectData,
) -> None:
    """Add non-Arkiv Digital sources sorted by title."""
    sources_sorted = sorted(sources, key=lambda s: s.title.lower())
    for source in sources_sorted:
        _add_source_entry(report, source, source_usage, data, label=source.title)


def _add_source_entry(
    report: ReportContent,
    source,
    source_usage: dict[str, list[dict]],
    data: ProjectData,
    label: str,
) -> None:
    """Add a single source entry with image marker and person list."""
    # Image/media availability marker
    has_media = bool(source.media_ids)
    media_marker = "📷" if has_media else "  "

    # Build entry header
    header = f"{media_marker} {label}" if label else f"{media_marker} {source.title}"
    report.blocks.append(ParagraphBlock(text=header))

    # Check for direct link (e.g. Sveriges Dödbok Webb)
    direct_link = generate_direct_link(source, data.kalltyper)

    # Person usage details — sorted by surname, then given name
    usages = source_usage.get(source.id, [])
    if usages:
        # Deduplicate
        person_entries: list[tuple[str, str, str]] = []  # (surname, given, display)
        seen: set[tuple] = set()
        for u in usages:
            key = (u["person_name"], u["event_type"], u["date"], u["place"])
            if key in seen:
                continue
            seen.add(key)
            parts = [u["person_name"]]
            detail_parts = []
            if u["event_type"]:
                detail_parts.append(u["event_type"])
            if u["date"]:
                detail_parts.append(u["date"])
            if u["place"]:
                detail_parts.append(u["place"])
            if detail_parts:
                parts.append(f"({', '.join(detail_parts)})")
            # Append link on the person entry (one ID per person for SDB)
            if direct_link:
                parts.append(f"(länk: {direct_link})")
            display = " ".join(parts)

            # Extract surname and given for sorting
            surname = u.get("person_surname", "")
            given = u.get("person_given", "")
            person_entries.append((surname.lower(), given.lower(), display))

        # Sort by surname, then given name
        person_entries.sort(key=lambda x: (x[0], x[1]))

        report.blocks.append(ListBlock(items=[entry[2] for entry in person_entries]))
