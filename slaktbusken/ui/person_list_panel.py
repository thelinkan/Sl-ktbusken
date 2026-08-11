"""Person List Panel for Släktbusken.

Displays all persons in the project sorted alphabetically by surname then
given name, with filtering via an external FilterDialog. Supports toggle
between showing all persons and a filtered subset, single-click (set active
person) and double-click (open edit window).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from slaktbusken.app import Application

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.name_parser import parse_given_name
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.model.dna import DnaCluster, DnaCompany, DnaProfile
from slaktbusken.model.media import MediaItem
from slaktbusken.services.lineage_computer import LineageComputer
from slaktbusken.ui.icons.icon_registry import icon_registry
from slaktbusken.ui.swedish_locale import format_residence_interval

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure filtering logic (no Qt dependency)
# ---------------------------------------------------------------------------


@dataclass
class FilterCriteria:
    """Criteria for filtering the person list.

    Attributes:
        title: Case-insensitive substring match on person title.
        given: Case-insensitive substring match on given name.
        surname: Case-insensitive substring match on surname.
        event_types: Person must have at least one event of these types (if non-empty).
        birth_year_from: Birth year must be >= this (as string, compared as int).
        birth_year_to: Birth year must be <= this (as string, compared as int).
        death_year_from: Death year must be >= this (as string, compared as int).
        death_year_to: Death year must be <= this (as string, compared as int).
        marriage_year_from: Marriage year must be >= this (as string, compared as int).
        marriage_year_to: Marriage year must be <= this (as string, compared as int).
        parish: Parish name to match (includes sub-places of parish).
        cluster: DNA cluster name to match (case-insensitive substring).
    """

    title: str = ""
    given: str = ""
    surname: str = ""
    event_types: set[str] = field(default_factory=set)
    birth_year_from: str = ""
    birth_year_to: str = ""
    death_year_from: str = ""
    death_year_to: str = ""
    marriage_year_from: str = ""
    marriage_year_to: str = ""
    parish: str = ""
    cluster: str = ""
    occupation: str = ""


@dataclass
class PersonDisplayInfo:
    """Pre-computed display information for a person.

    Attributes:
        person_id: The unique identifier of the person.
        given: Given name from the first name entry (clean, asterisk removed).
        surname: Surname from the first name entry.
        title: Person title (e.g. 'Fil.Dr') or empty string.
        birth_year: Birth year as string, or empty if unavailable.
        death_year: Death year as string, or empty if unavailable.
        marriage_year: Year from first marriage event, or empty if unavailable.
        event_types: Set of event types the person participates in.
        parish_names: Set of parish names associated with this person's events.
        cluster_names: Set of DNA cluster names (lowercase) the person belongs to.
        tilltalsnamn_index: Zero-based index of the tilltalsnamn part, or None.
        sex: Sex of the person ('M', 'F', or '').
        occupation: Person's occupation or empty string if not available.
        cluster_names_display: Comma-separated sorted cluster names for display.
        dna_company_ids: Company IDs that have DNA profiles for this person.
        name_count: Number of Name records associated with this person.
        all_names: All name records as (type, given, surname) tuples.
        is_ancestor: Whether this person is an ancestor of the main person.
        is_descendant: Whether this person is a descendant of the main person.
    """

    person_id: str
    given: str
    surname: str
    title: str
    birth_year: str
    death_year: str
    marriage_year: str
    event_types: set[str]
    parish_names: set[str]
    cluster_names: set[str] = field(default_factory=set)
    tilltalsnamn_index: int | None = None
    sex: str = ""
    occupation: str = ""
    cluster_names_display: str = ""
    dna_company_ids: list[str] = field(default_factory=list)
    name_count: int = 1
    all_names: list[tuple[str, str, str]] = field(default_factory=list)
    is_ancestor: bool = False
    is_descendant: bool = False
    birth_date: str = ""
    birth_place: str = ""
    death_date: str = ""
    death_place: str = ""
    residence_intervals: str = ""


def extract_year(date_value_str: str) -> str:
    """Extract the year (first 4 characters) from an ISO date string.

    Args:
        date_value_str: An ISO 8601 date string (YYYY, YYYY-MM, or YYYY-MM-DD).

    Returns:
        The 4-digit year string, or empty string if input is too short.
    """
    if len(date_value_str) >= 4:
        return date_value_str[:4]
    return ""


def get_person_birth_death_years(
    person: Person,
    events: list[Event],
) -> tuple[str, str]:
    """Find birth and death years for a person from the event list.

    Args:
        person: The person to look up.
        events: All events in the project.

    Returns:
        Tuple of (birth_year, death_year) as strings.
        - A year string (e.g. "1845") if the event has a parseable year.
        - "?" if the event exists but has no parseable year.
        - "" if no such event exists for the person.
    """
    birth_year = ""
    death_year = ""
    has_birth_event = False
    has_death_event = False

    for event in events:
        for participant in event.participants:
            if participant.person_id == person.id:
                if event.type == "birth" and not has_birth_event:
                    has_birth_event = True
                    if event.date is not None:
                        birth_year = extract_year(event.date.value)
                    if not birth_year:
                        birth_year = "?"
                elif event.type == "death" and not has_death_event:
                    has_death_event = True
                    if event.date is not None:
                        death_year = extract_year(event.date.value)
                    if not death_year:
                        death_year = "?"
                break
        if has_birth_event and has_death_event:
            break
    return birth_year, death_year


def _get_person_birth_death_details(
    person: Person,
    events: list[Event],
    place_by_id: dict[str, Place],
) -> tuple[str, str, str, str]:
    """Extract full birth/death date and place name for a person.

    Args:
        person: The person to look up.
        events: All events in the project.
        place_by_id: Pre-built place lookup dict.

    Returns:
        Tuple of (birth_date, birth_place, death_date, death_place).
        Empty strings where data is unavailable.
    """
    birth_date = ""
    birth_place = ""
    death_date = ""
    death_place = ""
    for event in events:
        for participant in event.participants:
            if participant.person_id == person.id:
                if event.type == "birth" and not birth_date:
                    if event.date is not None:
                        birth_date = event.date.value
                    if event.place is not None:
                        place = place_by_id.get(event.place.place_id)
                        if place is not None:
                            birth_place = place.name
                elif event.type == "death" and not death_date:
                    if event.date is not None:
                        death_date = event.date.value
                    if event.place is not None:
                        place = place_by_id.get(event.place.place_id)
                        if place is not None:
                            death_place = place.name
                break
        if birth_date and death_date:
            break
    return birth_date, birth_place, death_date, death_place


def get_person_marriage_year(
    person: Person,
    events: list[Event],
    families: list[Family],
) -> str:
    """Find the first marriage year for a person.

    Looks through families the person belongs to, finds their event_ids,
    and checks for marriage events with dates.

    Args:
        person: The person to look up.
        events: All events in the project.
        families: All families in the project.

    Returns:
        The year of the first marriage event, or empty string if not found.
    """
    # Find all family event_ids for families this person is a partner in
    event_by_id = {e.id: e for e in events}
    for family in families:
        person_in_family = any(
            p.person_id == person.id for p in family.partners
        )
        if not person_in_family:
            continue
        for event_id in family.event_ids:
            event = event_by_id.get(event_id)
            if event and event.type == "marriage" and event.date:
                year = extract_year(event.date.value)
                if year:
                    return year

    # Also check events where the person is a direct participant in a marriage
    for event in events:
        if event.type == "marriage" and event.date:
            for participant in event.participants:
                if participant.person_id == person.id:
                    year = extract_year(event.date.value)
                    if year:
                        return year
    return ""


def get_person_event_types(
    person: Person,
    events: list[Event],
    families: list[Family],
) -> set[str]:
    """Get all event types a person participates in.

    Includes both direct participation and family events.

    Args:
        person: The person to look up.
        events: All events in the project.
        families: All families in the project.

    Returns:
        Set of event type strings.
    """
    event_types: set[str] = set()

    # Direct participation
    for event in events:
        for participant in event.participants:
            if participant.person_id == person.id:
                event_types.add(event.type)
                break

    # Family events (person is a partner in the family)
    event_by_id = {e.id: e for e in events}
    for family in families:
        person_in_family = any(
            p.person_id == person.id for p in family.partners
        )
        if not person_in_family:
            continue
        for event_id in family.event_ids:
            event = event_by_id.get(event_id)
            if event:
                event_types.add(event.type)

    return event_types


def get_parish_place_ids(parish_name: str, places: list[Place]) -> set[str]:
    """Get all place IDs that belong to a parish (the parish itself + sub-places).

    A sub-place belongs to a parish if its parent_place_id points to a place
    of type 'parish' with the given name.

    Args:
        parish_name: The parish name to match (case-insensitive).
        places: All places in the project.

    Returns:
        Set of place_ids that are the parish or sub-places of it.
    """
    parish_name_lower = parish_name.lower()
    # Find all parish places matching the name
    parish_ids: set[str] = set()
    for place in places:
        if place.type == "parish" and place.name.lower() == parish_name_lower:
            parish_ids.add(place.id)

    # Find sub-places (church, cemetery) whose parent is one of these parishes
    result = set(parish_ids)
    for place in places:
        if place.type in ("church", "cemetery") and place.parent_place_id in parish_ids:
            result.add(place.id)

    return result


def get_person_parish_names(
    person: Person,
    events: list[Event],
    places: list[Place],
) -> set[str]:
    """Get all parish names associated with a person's events.

    A person is associated with a parish if any of their events have a place_id
    that is either a parish directly or a sub-place (church, cemetery) whose
    parent_place_id references a parish.

    Args:
        person: The person to look up.
        events: All events in the project.
        places: All places in the project.

    Returns:
        Set of parish names (lowercase) associated with this person.
    """
    # Build place lookup
    place_by_id: dict[str, Place] = {p.id: p for p in places}

    # Find all events this person participates in
    person_place_ids: set[str] = set()
    for event in events:
        if event.place is None:
            continue
        for participant in event.participants:
            if participant.person_id == person.id:
                person_place_ids.add(event.place.place_id)
                break

    # Resolve each place to its parish
    parish_names: set[str] = set()
    for place_id in person_place_ids:
        place = place_by_id.get(place_id)
        if place is None:
            continue
        if place.type == "parish":
            parish_names.add(place.name.lower())
        elif place.type in ("church", "cemetery") and place.parent_place_id:
            parent = place_by_id.get(place.parent_place_id)
            if parent and parent.type == "parish":
                parish_names.add(parent.name.lower())

    return parish_names


def get_person_cluster_names(
    person: Person,
    dna_clusters: list[DnaCluster],
) -> set[str]:
    """Get all DNA cluster names a person belongs to.

    Args:
        person: The person to look up.
        dna_clusters: All DNA clusters in the project.

    Returns:
        Set of cluster names (lowercase) the person is a member of.
    """
    names: set[str] = set()
    for cluster in dna_clusters:
        if person.id in cluster.person_ids:
            names.add(cluster.name.lower())
    return names


def build_person_display_list(
    persons: list[Person],
    events: list[Event],
    places: list[Place],
    families: list[Family] | None = None,
    dna_clusters: list[DnaCluster] | None = None,
    dna_profiles: list[DnaProfile] | None = None,
    dna_companies: list[DnaCompany] | None = None,
    ancestor_ids: set[str] | None = None,
    descendant_ids: set[str] | None = None,
    residences: list[ResidenceFact] | None = None,
) -> list[PersonDisplayInfo]:
    """Build a sorted list of person display info from project data.

    Sorted by surname (case-insensitive) then given name (case-insensitive).

    Args:
        persons: All persons in the project.
        events: All events in the project.
        places: All places in the project.
        families: All families in the project (optional for backward compat).
        dna_clusters: All DNA clusters in the project (optional).
        dna_profiles: All DNA profiles in the project (optional).
        dna_companies: All DNA companies in the project (optional).
        ancestor_ids: Set of person IDs that are ancestors of the main person (optional).
        descendant_ids: Set of person IDs that are descendants of the main person (optional).
        residences: All residence facts in the project (optional).

    Returns:
        Sorted list of PersonDisplayInfo items.
    """
    if families is None:
        families = []
    if dna_clusters is None:
        dna_clusters = []
    if dna_profiles is None:
        dna_profiles = []
    if dna_companies is None:
        dna_companies = []
    if ancestor_ids is None:
        ancestor_ids = set()
    if descendant_ids is None:
        descendant_ids = set()
    if residences is None:
        residences = []

    # Pre-build lookup: company_id -> company name for sorting
    company_name_by_id: dict[str, str] = {c.id: c.name for c in dna_companies}

    # Pre-build lookup: person_id -> list of company_ids from profiles
    person_company_ids: dict[str, set[str]] = {}
    for profile in dna_profiles:
        person_company_ids.setdefault(profile.person_id, set()).add(profile.company_id)

    # Pre-build place lookup for birth/death place resolution
    place_by_id: dict[str, Place] = {p.id: p for p in places}

    # Pre-build lookup: person_id -> list of ResidenceFacts for residence intervals
    person_residences: dict[str, list[ResidenceFact]] = {}
    for fact in residences:
        person_residences.setdefault(fact.person_id, []).append(fact)

    display_list: list[PersonDisplayInfo] = []
    for person in persons:
        if not person.names:
            continue
        first_name = person.names[0]
        birth_year, death_year = get_person_birth_death_years(person, events)
        birth_date, birth_place, death_date, death_place = _get_person_birth_death_details(
            person, events, place_by_id
        )
        marriage_year = get_person_marriage_year(person, events, families)
        event_types = get_person_event_types(person, events, families)
        parish_names = get_person_parish_names(person, events, places)
        cluster_names = get_person_cluster_names(person, dna_clusters)

        # Parse given name to extract tilltalsnamn and clean display string
        given_display = first_name.given
        tilltalsnamn_index: int | None = None
        try:
            parsed = parse_given_name(first_name.given)
            given_display = parsed.display_string
            tilltalsnamn_index = parsed.tilltalsnamn_index
        except ValueError:
            # Multiple markers — fall back to raw given name, no tilltalsnamn
            given_display = first_name.given
            tilltalsnamn_index = None

        # Occupation
        occupation = person.occupation or ""

        # Cluster names display: original-case names sorted alphabetically
        person_cluster_names_display: list[str] = []
        for cluster in dna_clusters:
            if person.id in cluster.person_ids:
                person_cluster_names_display.append(cluster.name)
        person_cluster_names_display.sort(key=str.lower)
        cluster_names_display = ", ".join(person_cluster_names_display)

        # DNA company IDs: distinct company IDs sorted by company name, max 5
        raw_company_ids = person_company_ids.get(person.id, set())
        sorted_company_ids = sorted(
            raw_company_ids,
            key=lambda cid: company_name_by_id.get(cid, "").lower(),
        )[:5]

        # Name count and all names
        name_count = len(person.names)
        all_names = [(n.type, n.given, n.surname) for n in person.names]

        # Lineage flags
        is_ancestor = person.id in ancestor_ids
        is_descendant = person.id in descendant_ids

        # Residence intervals: render each fact's interval through the formatter
        # ordered by start.earliest, start.latest (absent first), then place name.
        facts = person_residences.get(person.id, [])
        residence_intervals = ""
        if facts:
            def _absent_first(val: str | None) -> tuple[int, str]:
                if val is None or val.strip() == "":
                    return (0, "")
                return (1, val)

            sorted_facts = sorted(
                facts,
                key=lambda f: (
                    _absent_first(f.start.earliest),
                    _absent_first(f.start.latest),
                    (place_by_id.get(f.place_id).name if place_by_id.get(f.place_id) else f.place_id),
                ),
            )
            residence_intervals = "; ".join(
                format_residence_interval(f.start, f.end) for f in sorted_facts
            )

        display_list.append(
            PersonDisplayInfo(
                person_id=person.id,
                given=given_display,
                surname=first_name.surname,
                title=person.title or "",
                birth_year=birth_year,
                death_year=death_year,
                marriage_year=marriage_year,
                event_types=event_types,
                parish_names=parish_names,
                cluster_names=cluster_names,
                tilltalsnamn_index=tilltalsnamn_index,
                sex=person.sex,
                occupation=occupation,
                cluster_names_display=cluster_names_display,
                dna_company_ids=sorted_company_ids,
                name_count=name_count,
                all_names=all_names,
                is_ancestor=is_ancestor,
                is_descendant=is_descendant,
                birth_date=birth_date,
                birth_place=birth_place,
                death_date=death_date,
                death_place=death_place,
                residence_intervals=residence_intervals,
            )
        )

    # Sort uses clean given name (asterisk marker already removed via name_parser)
    # so sort order is unaffected by the tilltalsnamn marker.
    display_list.sort(key=lambda p: (p.surname.lower(), p.given.lower()))
    return display_list


def _year_in_range(year_str: str, from_str: str, to_str: str) -> bool:
    """Check if a year string falls within an optional range.

    Args:
        year_str: The year to check (may be empty).
        from_str: Minimum year (inclusive), or empty for no lower bound.
        to_str: Maximum year (inclusive), or empty for no upper bound.

    Returns:
        True if the year matches the range constraints.
        If year_str is empty and any range bound is set, returns False.
    """
    from_stripped = from_str.strip()
    to_stripped = to_str.strip()

    if not from_stripped and not to_stripped:
        return True

    if not year_str:
        return False

    try:
        year_int = int(year_str)
    except ValueError:
        return False

    if from_stripped:
        try:
            if year_int < int(from_stripped):
                return False
        except ValueError:
            pass

    if to_stripped:
        try:
            if year_int > int(to_stripped):
                return False
        except ValueError:
            pass

    return True


def format_names_tooltip(all_names: list[tuple[str, str, str]]) -> str:
    """Format the multiple-names tooltip text.

    Each name record is shown on one line as "typ: förnamn efternamn",
    with name types translated to Swedish. Omits empty components.

    Args:
        all_names: List of (type, given, surname) tuples.

    Returns:
        Multi-line tooltip text.
    """
    _NAME_TYPE_SV: dict[str, str] = {
        "birth": "Födelsenamn",
        "married": "Giftnamn",
        "adopted": "Adoptivnamn",
        "other": "Övrigt",
    }
    lines: list[str] = []
    for name_type, given, surname in all_names:
        parts: list[str] = []
        if given:
            parts.append(given)
        if surname:
            parts.append(surname)
        name_str = " ".join(parts)
        if name_type:
            type_label = _NAME_TYPE_SV.get(name_type, name_type)
            lines.append(f"{type_label}: {name_str}")
        else:
            lines.append(name_str)
    return "\n".join(lines)


def filter_persons(
    persons: list[PersonDisplayInfo],
    criteria: FilterCriteria,
    all_persons_names: dict[str, list[Name]] | None = None,
) -> list[PersonDisplayInfo]:
    """Filter a list of persons by the given criteria using AND logic.

    - title: case-insensitive substring on person's title
    - given: case-insensitive substring on given name (asterisk-free)
    - surname: case-insensitive substring on surname
    - event_types: person must participate in at least one event of these types
    - birth_year_from/to: birth year must be within range
    - death_year_from/to: death year must be within range
    - marriage_year_from/to: marriage year must be within range
    - parish: case-insensitive match on any of the person's parish names
    - cluster: case-insensitive substring on any of the person's cluster names

    When *all_persons_names* is provided, given/surname filters match against
    ALL Name records for a person (not just the primary name stored in
    PersonDisplayInfo). Asterisk markers are stripped from Name.given before
    comparison. Combined given+surname: person is included if (any Name
    satisfies given) AND (any Name satisfies surname) — evaluated independently.

    Args:
        persons: The pre-computed person display list.
        criteria: The filter criteria to apply.
        all_persons_names: Optional mapping of person_id to all their Name
            records for multi-name filtering. When None, falls back to
            filtering against the primary name in PersonDisplayInfo.

    Returns:
        Filtered list of PersonDisplayInfo matching all active criteria.
    """
    result: list[PersonDisplayInfo] = []
    title_lower = criteria.title.strip().lower()
    given_lower = criteria.given.strip().lower()
    surname_lower = criteria.surname.strip().lower()
    parish_lower = criteria.parish.strip().lower()
    cluster_lower = criteria.cluster.strip().lower()
    occupation_lower = criteria.occupation.strip().lower()

    for person in persons:
        # Title filter: substring on person's title
        if title_lower:
            if title_lower not in person.title.lower():
                continue

        # Given name filter: substring on given name(s)
        if given_lower:
            if all_persons_names and person.person_id in all_persons_names:
                names = all_persons_names[person.person_id]
                if not any(
                    given_lower in name.given.replace("*", "").lower()
                    for name in names
                ):
                    continue
            else:
                if given_lower not in person.given.lower():
                    continue

        # Surname filter: substring on surname(s)
        if surname_lower:
            if all_persons_names and person.person_id in all_persons_names:
                names = all_persons_names[person.person_id]
                if not any(
                    surname_lower in name.surname.lower()
                    for name in names
                ):
                    continue
            else:
                if surname_lower not in person.surname.lower():
                    continue

        # Event types filter: person must have at least one of the checked types
        if criteria.event_types:
            if not criteria.event_types.intersection(person.event_types):
                continue

        # Birth year range filter
        if not _year_in_range(
            person.birth_year, criteria.birth_year_from, criteria.birth_year_to
        ):
            continue

        # Death year range filter
        if not _year_in_range(
            person.death_year, criteria.death_year_from, criteria.death_year_to
        ):
            continue

        # Marriage year range filter
        if not _year_in_range(
            person.marriage_year, criteria.marriage_year_from, criteria.marriage_year_to
        ):
            continue

        # Parish filter: case-insensitive match on person's parishes
        if parish_lower:
            if parish_lower not in person.parish_names:
                continue

        # Cluster filter: case-insensitive substring on person's cluster names
        if cluster_lower:
            if not any(cluster_lower in cn for cn in person.cluster_names):
                continue

        # Occupation filter: case-insensitive substring on person's occupation
        if occupation_lower:
            if occupation_lower not in person.occupation.lower():
                continue

        result.append(person)

    return result


# ---------------------------------------------------------------------------
# Custom delegate for colored dot indicators
# ---------------------------------------------------------------------------

# Custom data roles for lineage flags
_ROLE_IS_ANCESTOR = Qt.ItemDataRole.UserRole + 1
_ROLE_IS_DESCENDANT = Qt.ItemDataRole.UserRole + 2
_ROLE_HAS_MULTI_NAMES = Qt.ItemDataRole.UserRole + 3
_ROLE_IS_MAIN_PERSON = Qt.ItemDataRole.UserRole + 4
_ROLE_DNA_COMPANY_IDS = Qt.ItemDataRole.UserRole + 10

_ANCESTOR_DOT_COLOR = QColor("#C0392B")
_DESCENDANT_DOT_COLOR = QColor("#27AE60")
_MAIN_PERSON_DOT_COLOR = QColor("#E67E22")  # Orange, matching main person frame
_MULTI_NAMES_COLOR = QColor("#2980B9")  # Blue marker for multiple names
_DOT_DIAMETER = 8


class _DotDelegate(QStyledItemDelegate):
    """Delegate for column 0 that draws colored ancestor/descendant dots and multi-names marker.

    Shifts the text rightward to make room for indicators between the icon and name.
    Indicators (left to right): multi-names marker, ancestor dot, descendant dot.
    """

    def _indicator_width(self, index: QModelIndex) -> int:
        """Calculate total pixel width needed for indicators."""
        width = 0
        has_multi = index.data(_ROLE_HAS_MULTI_NAMES) or False
        is_main = index.data(_ROLE_IS_MAIN_PERSON) or False
        is_ancestor = index.data(_ROLE_IS_ANCESTOR) or False
        is_descendant = index.data(_ROLE_IS_DESCENDANT) or False
        if has_multi:
            width += 14  # multi-names marker width + gap
        if is_main:
            width += _DOT_DIAMETER + 3
        if is_ancestor:
            width += _DOT_DIAMETER + 3
        if is_descendant:
            width += _DOT_DIAMETER + 3
        return width

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        """Paint the item with indicators between icon and text, text shifted right."""
        is_main = index.data(_ROLE_IS_MAIN_PERSON) or False
        is_ancestor = index.data(_ROLE_IS_ANCESTOR) or False
        is_descendant = index.data(_ROLE_IS_DESCENDANT) or False
        has_multi = index.data(_ROLE_HAS_MULTI_NAMES) or False

        indicator_w = self._indicator_width(index)

        if indicator_w > 0:
            self.initStyleOption(option, index)
            from PySide6.QtWidgets import QApplication
            style = option.widget.style() if option.widget else QApplication.style()

            # Save text for manual drawing; keep icon for style to draw
            text = option.text
            option.text = ""

            # Let style draw background + icon normally (this reliably renders the icon)
            style.drawControl(style.ControlElement.CE_ItemViewItem, option, painter, option.widget)

            # Calculate where the icon ends
            rect = option.rect
            icon_size = option.decorationSize
            if icon_size.width() <= 0:
                icon_size = QSize(20, 20)

            # Position for indicators: after icon area + gap
            x_offset = rect.left() + icon_size.width() + 6

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Multi-names marker: "≡" character in blue, drawn before dots
            if has_multi:
                painter.setPen(QPen(_MULTI_NAMES_COLOR))
                font = painter.font()
                font.setPointSize(10)
                font.setBold(True)
                painter.setFont(font)
                marker_rect = QRect(x_offset, rect.top(), 14, rect.height())
                painter.drawText(marker_rect, Qt.AlignmentFlag.AlignCenter, "≡")
                x_offset += 14

            # Main person dot (orange)
            dot_y = rect.top() + (rect.height() - _DOT_DIAMETER) // 2
            if is_main:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(_MAIN_PERSON_DOT_COLOR))
                painter.drawEllipse(x_offset, dot_y, _DOT_DIAMETER, _DOT_DIAMETER)
                x_offset += _DOT_DIAMETER + 3

            # Ancestor dot
            if is_ancestor:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(_ANCESTOR_DOT_COLOR))
                painter.drawEllipse(x_offset, dot_y, _DOT_DIAMETER, _DOT_DIAMETER)
                x_offset += _DOT_DIAMETER + 3

            # Descendant dot
            if is_descendant:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(_DESCENDANT_DOT_COLOR))
                painter.drawEllipse(x_offset, dot_y, _DOT_DIAMETER, _DOT_DIAMETER)
                x_offset += _DOT_DIAMETER + 3

            painter.restore()

            # Draw text after indicators
            text_left = x_offset + 2
            text_rect = QRect(text_left, rect.top(), rect.right() - text_left, rect.height())
            painter.save()
            if option.state & style.StateFlag.State_Selected:
                painter.setPen(QPen(option.palette.highlightedText().color()))
            else:
                painter.setPen(QPen(option.palette.text().color()))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            painter.restore()
        else:
            # No indicators — use default rendering
            super().paint(painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Return size hint accounting for indicator space."""
        size = super().sizeHint(option, index)
        extra = self._indicator_width(index)
        return QSize(size.width() + extra, max(size.height(), _DOT_DIAMETER + 4))


# ---------------------------------------------------------------------------
# DNA icon delegate
# ---------------------------------------------------------------------------

_DNA_ICON_SIZE = 16
_DNA_ICON_SPACING = 2


class _DnaIconDelegate(QStyledItemDelegate):
    """Delegate for column 8 that draws DNA company logo icons side-by-side."""

    def __init__(self, panel: "PersonListPanel") -> None:
        super().__init__(panel)
        self._panel = panel

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        """Paint DNA company icons horizontally, vertically centered."""
        # Let base class handle background, selection highlight, etc.
        # We call initStyleOption to get proper background painting.
        self.initStyleOption(option, index)
        option.text = ""
        from PySide6.QtWidgets import QApplication
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(style.ControlElement.CE_ItemViewItem, option, painter, option.widget)

        company_ids = index.data(_ROLE_DNA_COMPANY_IDS)
        if not company_ids:
            return

        company_by_id = getattr(self._panel, "_company_by_id", {})
        media_by_id = getattr(self._panel, "_media_by_id", {})

        painter.save()
        rect = option.rect
        x = rect.left() + 4
        y = rect.top() + (rect.height() - _DNA_ICON_SIZE) // 2

        for cid in company_ids:
            pixmap = self._panel._resolve_dna_icon_cached(
                cid, company_by_id, media_by_id
            )
            painter.drawPixmap(x, y, pixmap)
            x += _DNA_ICON_SIZE + _DNA_ICON_SPACING

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Return width based on number of icons, height from row."""
        company_ids = index.data(_ROLE_DNA_COMPANY_IDS)
        n = len(company_ids) if company_ids else 0
        if n == 0:
            width = _DNA_ICON_SIZE
        else:
            width = n * _DNA_ICON_SIZE + (n - 1) * _DNA_ICON_SPACING + 8
        height = max(super().sizeHint(option, index).height(), _DNA_ICON_SIZE + 4)
        return QSize(width, height)


# ---------------------------------------------------------------------------
# Qt Widget
# ---------------------------------------------------------------------------


class PersonListPanel(QWidget):
    """Panel showing a filterable, sorted list of all persons in the project.

    Emits signals when the user selects (single-click) or edits (double-click)
    a person. Provides a toggle button to switch between showing all persons
    and a filtered subset, plus a button to open the FilterDialog.

    Signals:
        person_selected: Emitted with person_id on single-click.
        person_edit_requested: Emitted with person_id on double-click.
    """

    _FULL_HEADERS = ["Namn", "Födelsedatum", "Födelseort", "Dödsdatum", "Dödsort", "Titel", "Yrke", "Kluster", "DNA", "Boende"]

    person_selected = Signal(str)
    person_edit_requested = Signal(str)
    context_menu_action = Signal(str, str)  # action_type, person_id
    person_count_changed = Signal(int, object)  # total, filtered_count_or_None

    def __init__(self, app: "Application", parent: Optional[QWidget] = None) -> None:
        """Initialise the PersonListPanel.

        Args:
            app: The Application instance providing project data.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._app = app
        self._display_list: list[PersonDisplayInfo] = []
        self._filtered_list: list[PersonDisplayInfo] = []
        self._current_criteria: FilterCriteria = FilterCriteria()
        self._showing_filtered = False
        self._filter_dialog: Optional[object] = None
        self._ancestor_ids: set[str] = set()
        self._descendant_ids: set[str] = set()
        self._lineage_main_person_id: str | None = None
        self._compact_mode: bool = False
        self._syncing_from_diagram: bool = False
        self._refreshing: bool = False
        self._person_list_config = None  # Will be set via apply_person_list_config

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Build the panel UI: toggle + filter button + tree widget with columns."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        title_label = QLabel("Personlista")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        # Button row: toggle + filter button
        button_row = QHBoxLayout()

        self._toggle_button = QPushButton("Visa filtrerade")
        self._toggle_button.setCheckable(True)
        button_row.addWidget(self._toggle_button)

        self._filter_button = QPushButton("Filter...")
        button_row.addWidget(self._filter_button)

        button_row.addStretch()
        layout.addLayout(button_row)

        # Person list as QTreeWidget with columns
        # Columns: 0=Namn, 1=Födelsedatum, 2=Födelseort, 3=Dödsdatum, 4=Dödsort,
        #          5=Titel, 6=Yrke, 7=Kluster, 8=DNA, 9=Boende
        self._tree_widget = QTreeWidget()
        self._tree_widget.setHeaderLabels(
            ["Namn", "Födelsedatum", "Födelseort", "Dödsdatum", "Dödsort", "Titel", "Yrke", "Kluster", "DNA", "Boende"]
        )
        self._tree_widget.setIconSize(QSize(20, 20))
        self._tree_widget.setRootIsDecorated(False)
        self._tree_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._tree_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._tree_widget.setIndentation(0)
        self._tree_widget.setUniformRowHeights(True)
        self._tree_widget.setAlternatingRowColors(True)

        # Custom delegate for colored dot indicators in column 0
        self._dot_delegate = _DotDelegate(self._tree_widget)
        self._tree_widget.setItemDelegateForColumn(0, self._dot_delegate)

        # Custom delegate for DNA company icons in column 8
        self._dna_delegate = _DnaIconDelegate(self)
        self._tree_widget.setItemDelegateForColumn(8, self._dna_delegate)

        # Configure header
        header = self._tree_widget.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(1, 90)
        header.resizeSection(2, 90)
        header.resizeSection(3, 90)
        header.resizeSection(4, 90)
        header.resizeSection(5, 60)
        header.resizeSection(6, 70)
        header.resizeSection(7, 70)
        header.resizeSection(8, 70)
        header.resizeSection(9, 120)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_column_visibility_menu)

        layout.addWidget(self._tree_widget)

        # No results message
        self._no_results_label = QLabel("Inga personer matchar filtret")
        self._no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results_label.setStyleSheet("color: gray; font-style: italic;")
        self._no_results_label.setVisible(False)
        layout.addWidget(self._no_results_label)

        # Apply saved column visibility settings on startup
        self._restore_column_visibility()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Check panel width and toggle compact column mode accordingly."""
        super().resizeEvent(event)
        compact = self.width() < 350
        self._apply_compact_mode(compact)

    def _apply_compact_mode(self, compact: bool) -> None:
        """Switch between compact and full column header/padding modes.

        Args:
            compact: True to use truncated headers and reduced padding.
        """
        if compact == self._compact_mode:
            return
        self._compact_mode = compact

        if compact:
            headers = [
                (label[:4] + "\u2026") if len(label) > 4 else label
                for label in self._FULL_HEADERS
            ]
            self._tree_widget.setHeaderLabels(headers)
            self._tree_widget.setStyleSheet(
                "QTreeWidget::item { padding-left: 2px; padding-right: 2px; }"
            )
        else:
            self._tree_widget.setHeaderLabels(self._FULL_HEADERS)
            self._tree_widget.setStyleSheet(
                "QTreeWidget::item { padding-left: 6px; padding-right: 6px; }"
            )

    def _build_column_header(self) -> QWidget:
        """Legacy method — column header is now built into the QTreeWidget.

        Returns:
            An empty placeholder widget (not used).
        """
        return QWidget()

    def _show_column_visibility_menu(self, pos: QPoint) -> None:
        """Show context menu on tree header for toggling column visibility.

        Creates a QMenu with checkable actions for each configurable column.
        Toggling a column immediately updates visibility and persists the change.

        Args:
            pos: The local position of the right-click within the header.
        """
        menu = QMenu(self)

        # Read current visibility state
        settings = self._app.app_settings_service._settings
        visibility = settings.column_visibility

        # Födelsedatum (column 1)
        action_birth_date = QAction("Födelsedatum", menu)
        action_birth_date.setCheckable(True)
        action_birth_date.setChecked(visibility.birth_date if hasattr(visibility, 'birth_date') else True)
        action_birth_date.toggled.connect(
            lambda checked: self._on_column_visibility_changed("birth_date", checked)
        )
        menu.addAction(action_birth_date)

        # Födelseort (column 2)
        action_birth_place = QAction("Födelseort", menu)
        action_birth_place.setCheckable(True)
        action_birth_place.setChecked(visibility.birth_place if hasattr(visibility, 'birth_place') else True)
        action_birth_place.toggled.connect(
            lambda checked: self._on_column_visibility_changed("birth_place", checked)
        )
        menu.addAction(action_birth_place)

        # Dödsdatum (column 3)
        action_death_date = QAction("Dödsdatum", menu)
        action_death_date.setCheckable(True)
        action_death_date.setChecked(visibility.death_date if hasattr(visibility, 'death_date') else True)
        action_death_date.toggled.connect(
            lambda checked: self._on_column_visibility_changed("death_date", checked)
        )
        menu.addAction(action_death_date)

        # Dödsort (column 4)
        action_death_place = QAction("Dödsort", menu)
        action_death_place.setCheckable(True)
        action_death_place.setChecked(visibility.death_place if hasattr(visibility, 'death_place') else True)
        action_death_place.toggled.connect(
            lambda checked: self._on_column_visibility_changed("death_place", checked)
        )
        menu.addAction(action_death_place)

        # Titel (column 5)
        action_titel = QAction("Titel", menu)
        action_titel.setCheckable(True)
        action_titel.setChecked(visibility.titel)
        action_titel.toggled.connect(
            lambda checked: self._on_column_visibility_changed("titel", checked)
        )
        menu.addAction(action_titel)

        # Yrke (column 6)
        action_yrke = QAction("Yrke", menu)
        action_yrke.setCheckable(True)
        action_yrke.setChecked(visibility.yrke)
        action_yrke.toggled.connect(
            lambda checked: self._on_column_visibility_changed("yrke", checked)
        )
        menu.addAction(action_yrke)

        # Kluster (column 7)
        action_kluster = QAction("Kluster", menu)
        action_kluster.setCheckable(True)
        action_kluster.setChecked(visibility.kluster)
        action_kluster.toggled.connect(
            lambda checked: self._on_column_visibility_changed("kluster", checked)
        )
        menu.addAction(action_kluster)

        # DNA company (column 8)
        action_dna = QAction("DNA", menu)
        action_dna.setCheckable(True)
        action_dna.setChecked(visibility.dna_company)
        action_dna.toggled.connect(
            lambda checked: self._on_column_visibility_changed("dna_company", checked)
        )
        menu.addAction(action_dna)

        # Boende (column 9)
        action_boende = QAction("Boende", menu)
        action_boende.setCheckable(True)
        action_boende.setChecked(getattr(visibility, 'boende', True))
        action_boende.toggled.connect(
            lambda checked: self._on_column_visibility_changed("boende", checked)
        )
        menu.addAction(action_boende)

        global_pos = self._tree_widget.header().mapToGlobal(pos)
        menu.exec(global_pos)

    def _on_column_visibility_changed(self, column: str, visible: bool) -> None:
        """Handle column visibility toggle and persist the change.

        Shows/hides the corresponding tree widget column and saves the
        new state to application settings.

        Args:
            column: The column identifier ('titel', 'yrke', 'kluster', 'dna_company').
            visible: Whether the column should be visible.
        """
        col_map = {
            "birth_date": 1, "birth_place": 2,
            "death_date": 3, "death_place": 4,
            "titel": 5, "yrke": 6, "kluster": 7, "dna_company": 8,
            "boende": 9,
        }
        col_index = col_map.get(column)
        if col_index is not None:
            self._tree_widget.setColumnHidden(col_index, not visible)

        # Persist the change
        settings = self._app.app_settings_service._settings
        setattr(settings.column_visibility, column, visible)
        self._app.app_settings_service.save(settings)

    def _restore_column_visibility(self) -> None:
        """Restore column visibility from persisted application settings.

        Called during startup to apply saved visibility state. Falls back
        to all-visible defaults if settings cannot be read.
        """
        settings = self._app.app_settings_service._settings
        visibility = settings.column_visibility

        self._tree_widget.setColumnHidden(1, not getattr(visibility, 'birth_date', True))
        self._tree_widget.setColumnHidden(2, not getattr(visibility, 'birth_place', True))
        self._tree_widget.setColumnHidden(3, not getattr(visibility, 'death_date', True))
        self._tree_widget.setColumnHidden(4, not getattr(visibility, 'death_place', True))
        self._tree_widget.setColumnHidden(5, not visibility.titel)
        self._tree_widget.setColumnHidden(6, not visibility.yrke)
        self._tree_widget.setColumnHidden(7, not visibility.kluster)
        self._tree_widget.setColumnHidden(8, not visibility.dna_company)
        self._tree_widget.setColumnHidden(9, not getattr(visibility, 'boende', True))

    def _connect_signals(self) -> None:
        """Connect button signals and tree selection signals."""
        self._toggle_button.toggled.connect(self._on_toggle_changed)
        self._filter_button.clicked.connect(self._on_filter_button_clicked)

        self._tree_widget.currentItemChanged.connect(self._on_item_clicked)
        self._tree_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree_widget.customContextMenuRequested.connect(
            self._on_context_menu_requested
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _compute_lineage_sets(self) -> None:
        """Recompute ancestor/descendant sets from main_person_id.

        Caches the results on the panel instance. Returns early if the
        main_person_id has not changed since the last computation. Clears
        both sets when main_person_id is None or empty.
        """
        data = self._app.project_service.data
        main_person_id = (
            data.project.main_person_id
            if hasattr(data, "project") and data.project is not None
            else None
        )

        # No main person → no dots
        if not main_person_id:
            self._ancestor_ids = set()
            self._descendant_ids = set()
            self._lineage_main_person_id = None
            return

        # Same main person → use cached sets
        if main_person_id == self._lineage_main_person_id:
            return

        # Recompute
        computer = LineageComputer(data)
        self._ancestor_ids = computer.get_ancestors(main_person_id)
        self._descendant_ids = computer.get_descendants(main_person_id)
        self._lineage_main_person_id = main_person_id

    def refresh(self) -> None:
        """Refresh the person list from the current project data.

        Call this when the project data changes (e.g., after import, edit).
        """
        self._refreshing = True
        try:
            data = self._app.project_service.data
            families = data.families if hasattr(data, "families") else []
            dna_clusters = data.dna_clusters if hasattr(data, "dna_clusters") else []
            dna_profiles = data.dna_profiles if hasattr(data, "dna_profiles") else []
            dna_companies = data.dna_companies if hasattr(data, "dna_companies") else []
            self._compute_lineage_sets()
            self._display_list = build_person_display_list(
                data.persons,
                data.events,
                data.places,
                families,
                dna_clusters,
                dna_profiles=dna_profiles,
                dna_companies=dna_companies,
                ancestor_ids=self._ancestor_ids,
                descendant_ids=self._descendant_ids,
                residences=data.residences if hasattr(data, "residences") else [],
            )
            self._apply_current_view()
        finally:
            self._refreshing = False

    def apply_filter(self, criteria: FilterCriteria) -> None:
        """Apply filter criteria from the FilterDialog.

        Automatically switches to filtered view so the user immediately
        sees the filter results.

        Args:
            criteria: The filter criteria to apply.
        """
        self._current_criteria = criteria
        self._filtered_list = filter_persons(
            self._display_list, criteria, self._get_all_persons_names()
        )
        # Automatically switch to filtered view
        if not self._showing_filtered:
            self._toggle_button.setChecked(True)
        else:
            self._update_list_widget()

    def apply_dna_match_filter(self, person_ids: set[str], select_person_id: str | None = None) -> None:
        """Filter the person list to show only persons with given IDs.

        Used for "Filtrera på DNA-träffar" — shows the right-clicked person
        and all persons who share DNA matches with them.

        Args:
            person_ids: Set of person IDs to include in the filtered view.
            select_person_id: Optional person ID to select after filtering.
        """
        self._filtered_list = [
            p for p in self._display_list if p.person_id in person_ids
        ]
        # Guard against emitting person_selected during rebuild
        self._refreshing = True
        try:
            # Automatically switch to filtered view
            if not self._showing_filtered:
                self._toggle_button.setChecked(True)
            else:
                self._update_list_widget()
        finally:
            self._refreshing = False

        # Select the specified person in the filtered list
        if select_person_id:
            for i in range(self._tree_widget.topLevelItemCount()):
                item = self._tree_widget.topLevelItem(i)
                if item and item.data(0, Qt.ItemDataRole.UserRole) == select_person_id:
                    self._tree_widget.setCurrentItem(item)
                    self._tree_widget.scrollToItem(item)
                    break

    def select_person_from_diagram(self, person_id: str) -> None:
        """Select and scroll to a person without emitting person_selected signal.

        Called when the diagram panel activates a person (e.g. via A-key shortcut).
        Uses a guard flag to prevent circular signal loops.

        Args:
            person_id: The ID of the person to select.
        """
        # Check if person_id exists in the full (unfiltered) list
        person_in_full_list = any(
            p.person_id == person_id for p in self._display_list
        )
        if not person_in_full_list:
            # Person not found at all — clear selection, don't change view
            self._tree_widget.setCurrentItem(None)
            return

        self._syncing_from_diagram = True
        try:
            # If currently showing filtered view and person not in filtered list,
            # switch to unfiltered view
            if self._showing_filtered:
                person_in_filtered = any(
                    p.person_id == person_id for p in self._filtered_list
                )
                if not person_in_filtered:
                    # Switch to unfiltered: setChecked(False) triggers
                    # _on_toggle_changed which updates text and rebuilds list
                    self._toggle_button.setChecked(False)

            # Find and select the item in the tree widget
            for i in range(self._tree_widget.topLevelItemCount()):
                item = self._tree_widget.topLevelItem(i)
                if item and item.data(0, Qt.ItemDataRole.UserRole) == person_id:
                    self._tree_widget.setCurrentItem(item)
                    self._tree_widget.scrollToItem(item)
                    break
        finally:
            self._syncing_from_diagram = False

    def get_selected_person_id(self) -> Optional[str]:
        """Return the person ID of the currently selected item, or None."""
        current = self._tree_widget.currentItem()
        if current is not None:
            return current.data(0, Qt.ItemDataRole.UserRole)
        return None

    def apply_person_list_config(self, config) -> None:
        """Apply person list configuration to show/hide columns and icons.

        Args:
            config: PersonListConfig with visibility flags.
        """
        from slaktbusken.persistence.settings_io import PersonListConfig

        if not isinstance(config, PersonListConfig):
            return

        self._person_list_config = config

        # Column mapping: header index → config field
        # Columns: 0=Namn, 1=Födelsedatum, 2=Födelseort, 3=Dödsdatum, 4=Dödsort,
        #          5=Titel, 6=Yrke, 7=Kluster, 8=DNA
        header = self._tree_widget.header()
        header.setSectionHidden(1, not config.birth_date)
        header.setSectionHidden(2, not config.birth_place)
        header.setSectionHidden(3, not config.death_date)
        header.setSectionHidden(4, not config.death_place)
        header.setSectionHidden(5, not config.title)
        header.setSectionHidden(6, not config.occupation)
        header.setSectionHidden(7, not config.clusters)
        header.setSectionHidden(8, not config.dna)

        # Refresh the list to apply icon/date visibility changes
        self._apply_current_view()

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_toggle_changed(self, checked: bool) -> None:
        """Handle toggle button state change.

        Args:
            checked: True when showing filtered, False when showing all.
        """
        self._showing_filtered = checked
        if checked:
            self._toggle_button.setText("Visa alla")
        else:
            self._toggle_button.setText("Visa filtrerade")
        self._refreshing = True
        try:
            self._apply_current_view()
        finally:
            self._refreshing = False

    def _on_filter_button_clicked(self) -> None:
        """Open the FilterDialog (non-modal)."""
        from slaktbusken.ui.dialogs.filter_dialog import FilterDialog

        if self._filter_dialog is None:
            self._filter_dialog = FilterDialog(self)
            self._filter_dialog.filter_applied.connect(self.apply_filter)
        # Update available cluster names for autocomplete
        self._update_cluster_completions()
        self._filter_dialog.show()
        self._filter_dialog.raise_()
        self._filter_dialog.activateWindow()

    def _update_cluster_completions(self) -> None:
        """Feed available cluster names to the FilterDialog autocomplete."""
        if self._filter_dialog is None:
            return
        data = self._app.project_service.data
        dna_clusters = data.dna_clusters if hasattr(data, "dna_clusters") else []
        cluster_names = sorted({c.name for c in dna_clusters if c.name})
        self._filter_dialog.set_available_clusters(cluster_names)

    def _apply_current_view(self) -> None:
        """Update the list widget based on the current toggle state."""
        if self._showing_filtered:
            self._filtered_list = filter_persons(
                self._display_list,
                self._current_criteria,
                self._get_all_persons_names(),
            )
            self._update_list_widget()
        else:
            self._filtered_list = list(self._display_list)
            self._update_list_widget()
        self._emit_person_count()

    def _emit_person_count(self) -> None:
        """Emit the person_count_changed signal with current counts."""
        total = len(self._display_list)
        if self._showing_filtered:
            filtered = len(self._filtered_list)
            self.person_count_changed.emit(total, filtered)
        else:
            self.person_count_changed.emit(total, None)

    def _get_all_persons_names(self) -> dict[str, list[Name]]:
        """Build a mapping of person_id to all their Name records.

        Used by filter_persons() for multi-name filtering.
        """
        data = self._app.project_service.data
        return {person.id: person.names for person in data.persons}

    def _update_list_widget(self) -> None:
        """Rebuild the QTreeWidget items from the filtered list.

        Uses QTreeWidgetItem for each person with text columns for Namn,
        Födelsedatum, Födelseort, Dödsdatum, Dödsort, Titel, Yrke, Kluster,
        and DNA company names. The first column includes gender icon, dot
        indicators, and multiple-names marker.
        """
        self._tree_widget.clear()

        if not self._filtered_list:
            self._no_results_label.setVisible(True)
            self._tree_widget.setVisible(False)
            return

        self._no_results_label.setVisible(False)
        self._tree_widget.setVisible(True)

        # Pre-build company name lookup for DNA column
        data = self._app.project_service.data
        main_person_id = (
            data.project.main_person_id
            if hasattr(data, "project") and data.project is not None
            else None
        )
        company_name_by_id: dict[str, str] = {
            c.id: c.name for c in data.dna_companies
        }
        # Store lookups for the DNA icon delegate
        self._company_by_id = {c.id: c for c in data.dna_companies}
        self._media_by_id = {m.id: m for m in data.media}

        # Suspend UI updates while populating
        self._tree_widget.setUpdatesEnabled(False)
        try:
            items: list[QTreeWidgetItem] = []
            for person_info in self._filtered_list:
                # Build name display text
                name_text = self._format_person_display(person_info)

                display_name = name_text

                # DNA company names (for tooltip only; icons drawn by delegate)
                dna_text = ""
                if person_info.dna_company_ids:
                    dna_names = [
                        company_name_by_id.get(cid, "?")
                        for cid in person_info.dna_company_ids[:5]
                    ]
                    dna_text = ", ".join(dna_names)

                # Create tree item with columns (column 8 text empty; delegate paints icons)
                tree_item = QTreeWidgetItem([
                    display_name,
                    person_info.birth_date,
                    person_info.birth_place,
                    person_info.death_date,
                    person_info.death_place,
                    person_info.title,
                    person_info.occupation,
                    person_info.cluster_names_display,
                    "",
                    person_info.residence_intervals,
                ])

                # Store person_id in UserRole on column 0
                tree_item.setData(0, Qt.ItemDataRole.UserRole, person_info.person_id)

                # Store DNA company IDs for the icon delegate
                if person_info.dna_company_ids:
                    tree_item.setData(8, _ROLE_DNA_COMPANY_IDS, person_info.dna_company_ids[:5])

                # Store lineage flags for the dot delegate
                if person_info.is_ancestor:
                    tree_item.setData(0, _ROLE_IS_ANCESTOR, True)
                if person_info.is_descendant:
                    tree_item.setData(0, _ROLE_IS_DESCENDANT, True)
                if person_info.name_count > 1:
                    tree_item.setData(0, _ROLE_HAS_MULTI_NAMES, True)
                if person_info.person_id == main_person_id:
                    tree_item.setData(0, _ROLE_IS_MAIN_PERSON, True)

                # Set gender icon (respects config)
                cfg = self._person_list_config
                show_sex = cfg.sex if cfg else True
                show_relation = cfg.relation if cfg else True
                show_multi_names = cfg.multiple_names if cfg else True

                if show_sex:
                    pixmap = icon_registry.get_gender_icon(person_info.sex)
                    tree_item.setIcon(0, QIcon(pixmap))

                # Only store relation/multi-names data if config enables them
                if not show_relation:
                    tree_item.setData(0, _ROLE_IS_ANCESTOR, False)
                    tree_item.setData(0, _ROLE_IS_DESCENDANT, False)
                    tree_item.setData(0, _ROLE_IS_MAIN_PERSON, False)
                if not show_multi_names:
                    tree_item.setData(0, _ROLE_HAS_MULTI_NAMES, False)

                # Tooltips
                tooltip_parts: list[str] = []
                if person_info.is_ancestor and person_info.is_descendant:
                    tooltip_parts.append("Anfader & ättling")
                elif person_info.is_ancestor:
                    tooltip_parts.append("Anfader")
                elif person_info.is_descendant:
                    tooltip_parts.append("Ättling")
                if person_info.name_count > 1:
                    tooltip_parts.append(self._format_names_tooltip(person_info.all_names))
                if person_info.title:
                    tree_item.setToolTip(5, person_info.title)
                if person_info.occupation:
                    tree_item.setToolTip(6, person_info.occupation)
                if person_info.cluster_names_display:
                    tree_item.setToolTip(7, person_info.cluster_names_display)
                if dna_text:
                    tree_item.setToolTip(8, dna_text)
                if person_info.residence_intervals:
                    tree_item.setToolTip(9, person_info.residence_intervals)
                if tooltip_parts:
                    tree_item.setToolTip(0, "\n".join(tooltip_parts))

                items.append(tree_item)

            self._tree_widget.addTopLevelItems(items)
        finally:
            self._tree_widget.setUpdatesEnabled(True)

    def _build_dot_html(self, info: PersonDisplayInfo) -> str:
        """Build HTML text for the ancestry/descendancy dot indicator.

        Args:
            info: The person display info.

        Returns:
            HTML string with colored dots, or empty string if neither flag is set.
        """
        parts: list[str] = []
        if info.is_ancestor:
            parts.append('<span style="color:#C0392B;">●</span>')
        if info.is_descendant:
            parts.append('<span style="color:#27AE60;">●</span>')
        return "".join(parts)

    def _resolve_dna_icon_cached(
        self,
        company_id: str,
        company_by_id: dict[str, DnaCompany],
        media_by_id: dict[str, "MediaItem"],
    ) -> QPixmap:
        """Resolve DNA company icon using pre-built lookups, with caching.

        Uses an instance-level cache (_dna_icon_cache) to avoid repeated disk
        reads for the same company icon.

        Args:
            company_id: The ID of the DNA company.
            company_by_id: Pre-built company lookup dict.
            media_by_id: Pre-built media lookup dict.

        Returns:
            A 16×16 QPixmap with the company logo or a gray placeholder.
        """
        # Check cache first
        if not hasattr(self, "_dna_icon_cache"):
            self._dna_icon_cache: dict[str, QPixmap] = {}
        if company_id in self._dna_icon_cache:
            return self._dna_icon_cache[company_id]

        company = company_by_id.get(company_id)
        if company is None or not company.logo_media_id:
            pixmap = self._placeholder_icon()
            self._dna_icon_cache[company_id] = pixmap
            return pixmap

        media_item = media_by_id.get(company.logo_media_id)
        if media_item is None or not media_item.file:
            pixmap = self._placeholder_icon()
            self._dna_icon_cache[company_id] = pixmap
            return pixmap

        project_path = self._app.project_service.project_path
        if project_path is not None:
            import unicodedata
            normalized_file = unicodedata.normalize("NFC", media_item.file)
            icon_path = project_path.parent / normalized_file
            if icon_path.exists():
                loaded = QPixmap(str(icon_path))
                if not loaded.isNull():
                    pixmap = loaded.scaled(
                        16, 16,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._dna_icon_cache[company_id] = pixmap
                    return pixmap
                else:
                    logger.warning("Failed to load DNA icon: %s", icon_path)
            else:
                logger.warning("DNA icon file not found: %s", icon_path)

        pixmap = self._placeholder_icon()
        self._dna_icon_cache[company_id] = pixmap
        return pixmap

    def _resolve_dna_icon(self, company_id: str) -> QPixmap:
        """Resolve DNA company icon from media or return a placeholder.

        Legacy method kept for backward compatibility. Prefer
        _resolve_dna_icon_cached for bulk operations.

        Args:
            company_id: The ID of the DNA company.

        Returns:
            A 16×16 QPixmap with the company logo or a gray placeholder.
        """
        data = self._app.project_service.data
        company_by_id = {c.id: c for c in data.dna_companies}
        media_by_id = {m.id: m for m in data.media}
        return self._resolve_dna_icon_cached(company_id, company_by_id, media_by_id)

    def _placeholder_icon(self) -> QPixmap:
        """Return a cached 16×16 gray placeholder icon.

        Returns:
            A 16×16 QPixmap filled with light gray.
        """
        if not hasattr(self, "_placeholder_pixmap"):
            from PySide6.QtGui import QColor
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(200, 200, 200))
            self._placeholder_pixmap = pixmap
        return self._placeholder_pixmap

    def _get_company_name(self, company_id: str) -> str:
        """Look up the display name of a DNA company by ID.

        Args:
            company_id: The company ID to look up.

        Returns:
            The company name, or empty string if not found.
        """
        data = self._app.project_service.data
        for c in data.dna_companies:
            if c.id == company_id:
                return c.name
        return ""

    def _format_names_tooltip(self, all_names: list[tuple[str, str, str]]) -> str:
        """Format the multiple-names tooltip text.

        Each name record is shown on one line as "type: given surname",
        omitting empty components.

        Args:
            all_names: List of (type, given, surname) tuples.

        Returns:
            Multi-line tooltip text.
        """
        return format_names_tooltip(all_names)

    def _format_person_display(self, info: PersonDisplayInfo) -> str:
        """Format a person's display text for the list.

        Shows: "Surname, Given (birth–death)" with years where available.
        Years always appear in the name column regardless of config.
        No death recorded = no "?" shown. Death without year = "?".

        Args:
            info: The person display info.

        Returns:
            Formatted display string.
        """
        name_part = f"{info.surname}, {info.given}"

        if info.birth_year or info.death_year:
            birth_display = info.birth_year if info.birth_year else "?"
            death_display = info.death_year
            if death_display:
                return f"{name_part} ({birth_display}\u2013{death_display})"
            else:
                return f"{name_part} ({birth_display}\u2013)"

        return name_part

    def _format_person_html(self, info: PersonDisplayInfo) -> str:
        """Format a person's display text as HTML with tilltalsnamn underlined.

        Shows: "Surname, Given1 <u>Given2</u> Given3 (birth–death)" where the
        tilltalsnamn part is wrapped in <u> tags. If no tilltalsnamn is marked,
        all given names are rendered without underline.

        The raw asterisk is never displayed.

        Args:
            info: The person display info.

        Returns:
            HTML string for rendering in a QLabel.
        """
        # Build the given name portion with underline on tilltalsnamn
        given_parts = info.given.split() if info.given else []
        if info.tilltalsnamn_index is not None and 0 <= info.tilltalsnamn_index < len(given_parts):
            html_given_parts: list[str] = []
            for i, part in enumerate(given_parts):
                if i == info.tilltalsnamn_index:
                    html_given_parts.append(f"<u>{part}</u>")
                else:
                    html_given_parts.append(part)
            given_html = " ".join(html_given_parts)
        else:
            given_html = info.given

        name_html = f"{info.surname}, {given_html}"

        # Add years if available
        if info.birth_year or info.death_year:
            birth = info.birth_year if info.birth_year else "?"
            death = info.death_year
            if death:
                return f"{name_html} ({birth}\u2013{death})"
            else:
                return f"{name_html} ({birth}\u2013)"
        return name_html

    def _on_item_clicked(self, current: QTreeWidgetItem, previous: QTreeWidgetItem) -> None:
        """Handle single-click: emit person_selected signal.

        Args:
            current: The newly selected item.
            previous: The previously selected item.
        """
        if self._syncing_from_diagram or self._refreshing:
            return
        if current is not None:
            person_id = current.data(0, Qt.ItemDataRole.UserRole)
            if person_id:
                self.person_selected.emit(person_id)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click: emit person_edit_requested signal.

        Args:
            item: The double-clicked item.
            column: The column that was double-clicked.
        """
        if item is not None:
            person_id = item.data(0, Qt.ItemDataRole.UserRole)
            if person_id:
                self.person_edit_requested.emit(person_id)

    def _on_context_menu_requested(self, pos) -> None:
        """Handle right-click context menu on a person list item.

        Uses ContextMenuBuilder to create and show the standard person
        context menu, then emits context_menu_action with the selected action.

        Args:
            pos: The local position of the right-click within the list widget.
        """
        from slaktbusken.ui.context_menu_builder import ContextMenuBuilder

        item = self._tree_widget.itemAt(pos)
        if item is None:
            return

        person_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not person_id:
            return

        # Determine main person id
        main_person_id: Optional[str] = None
        data = self._app.project_service.data
        if data is not None and hasattr(data, "project"):
            main_person_id = data.project.main_person_id

        builder = ContextMenuBuilder()
        menu = builder.build_person_menu(person_id, main_person_id, self)

        global_pos = self._tree_widget.mapToGlobal(pos)
        action = menu.exec(global_pos)
        if action is None:
            return

        action_data = action.data()
        if action_data and isinstance(action_data, tuple) and len(action_data) == 2:
            action_type, pid = action_data
            if action_type == "show_relationship" and pid == main_person_id:
                return
            self.context_menu_action.emit(action_type, pid)
