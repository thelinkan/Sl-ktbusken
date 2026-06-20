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

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
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
from slaktbusken.model.dna import DnaCluster, DnaCompany, DnaProfile
from slaktbusken.model.media import MediaItem
from slaktbusken.services.lineage_computer import LineageComputer
from slaktbusken.ui.icons.icon_registry import icon_registry

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
        Tuple of (birth_year, death_year) as strings. Empty string if not found.
    """
    birth_year = ""
    death_year = ""
    for event in events:
        if event.date is None:
            continue
        for participant in event.participants:
            if participant.person_id == person.id:
                if event.type == "birth" and not birth_year:
                    birth_year = extract_year(event.date.value)
                elif event.type == "death" and not death_year:
                    death_year = extract_year(event.date.value)
                break
        if birth_year and death_year:
            break
    return birth_year, death_year


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

    # Pre-build lookup: company_id -> company name for sorting
    company_name_by_id: dict[str, str] = {c.id: c.name for c in dna_companies}

    # Pre-build lookup: person_id -> list of company_ids from profiles
    person_company_ids: dict[str, set[str]] = {}
    for profile in dna_profiles:
        person_company_ids.setdefault(profile.person_id, set()).add(profile.company_id)

    display_list: list[PersonDisplayInfo] = []
    for person in persons:
        if not person.names:
            continue
        first_name = person.names[0]
        birth_year, death_year = get_person_birth_death_years(person, events)
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

    Each name record is shown on one line as "type: given surname",
    omitting empty components.

    Args:
        all_names: List of (type, given, surname) tuples.

    Returns:
        Multi-line tooltip text.
    """
    lines: list[str] = []
    for name_type, given, surname in all_names:
        parts: list[str] = []
        if given:
            parts.append(given)
        if surname:
            parts.append(surname)
        name_str = " ".join(parts)
        if name_type:
            lines.append(f"{name_type}: {name_str}")
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

        result.append(person)

    return result


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

    person_selected = Signal(str)
    person_edit_requested = Signal(str)
    context_menu_action = Signal(str, str)  # action_type, person_id

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
        # Columns: 0=Namn, 1=Titel, 2=Yrke, 3=Kluster, 4=DNA
        self._tree_widget = QTreeWidget()
        self._tree_widget.setHeaderLabels(["Namn", "Titel", "Yrke", "Kluster", "DNA"])
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

        # Configure header
        header = self._tree_widget.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(1, 60)
        header.resizeSection(2, 70)
        header.resizeSection(3, 70)
        header.resizeSection(4, 70)
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

        # Titel (column 1)
        action_titel = QAction("Titel", menu)
        action_titel.setCheckable(True)
        action_titel.setChecked(visibility.titel)
        action_titel.toggled.connect(
            lambda checked: self._on_column_visibility_changed("titel", checked)
        )
        menu.addAction(action_titel)

        # Yrke (column 2)
        action_yrke = QAction("Yrke", menu)
        action_yrke.setCheckable(True)
        action_yrke.setChecked(visibility.yrke)
        action_yrke.toggled.connect(
            lambda checked: self._on_column_visibility_changed("yrke", checked)
        )
        menu.addAction(action_yrke)

        # Kluster (column 3)
        action_kluster = QAction("Kluster", menu)
        action_kluster.setCheckable(True)
        action_kluster.setChecked(visibility.kluster)
        action_kluster.toggled.connect(
            lambda checked: self._on_column_visibility_changed("kluster", checked)
        )
        menu.addAction(action_kluster)

        # DNA company (column 4)
        action_dna = QAction("DNA", menu)
        action_dna.setCheckable(True)
        action_dna.setChecked(visibility.dna_company)
        action_dna.toggled.connect(
            lambda checked: self._on_column_visibility_changed("dna_company", checked)
        )
        menu.addAction(action_dna)

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
        col_map = {"titel": 1, "yrke": 2, "kluster": 3, "dna_company": 4}
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

        self._tree_widget.setColumnHidden(1, not visibility.titel)
        self._tree_widget.setColumnHidden(2, not visibility.yrke)
        self._tree_widget.setColumnHidden(3, not visibility.kluster)
        self._tree_widget.setColumnHidden(4, not visibility.dna_company)

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
        )
        self._apply_current_view()

    def apply_filter(self, criteria: FilterCriteria) -> None:
        """Apply filter criteria from the FilterDialog.

        Args:
            criteria: The filter criteria to apply.
        """
        self._current_criteria = criteria
        self._filtered_list = filter_persons(
            self._display_list, criteria, self._get_all_persons_names()
        )
        if self._showing_filtered:
            self._update_list_widget()

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
        self._apply_current_view()

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

    def _get_all_persons_names(self) -> dict[str, list[Name]]:
        """Build a mapping of person_id to all their Name records.

        Used by filter_persons() for multi-name filtering.
        """
        data = self._app.project_service.data
        return {person.id: person.names for person in data.persons}

    def _update_list_widget(self) -> None:
        """Rebuild the QTreeWidget items from the filtered list.

        Uses QTreeWidgetItem for each person with text columns for Namn,
        Titel, Yrke, Kluster, and DNA company names. The first column
        includes gender icon, dot indicators, and multiple-names marker.
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
        company_name_by_id: dict[str, str] = {
            c.id: c.name for c in data.dna_companies
        }

        # Suspend UI updates while populating
        self._tree_widget.setUpdatesEnabled(False)
        try:
            items: list[QTreeWidgetItem] = []
            for person_info in self._filtered_list:
                # Build name display text with dot indicators and names marker
                name_text = self._format_person_display(person_info)

                # Prepend dot indicators
                dot_prefix = ""
                if person_info.is_ancestor and person_info.is_descendant:
                    dot_prefix = "●● "
                elif person_info.is_ancestor:
                    dot_prefix = "● "
                elif person_info.is_descendant:
                    dot_prefix = "● "

                # Append multiple-names indicator
                names_suffix = ""
                if person_info.name_count > 1:
                    names_suffix = " ²"

                display_name = dot_prefix + name_text + names_suffix

                # DNA company names (comma-separated)
                dna_text = ""
                if person_info.dna_company_ids:
                    dna_names = [
                        company_name_by_id.get(cid, "?")
                        for cid in person_info.dna_company_ids[:5]
                    ]
                    dna_text = ", ".join(dna_names)

                # Create tree item with columns
                tree_item = QTreeWidgetItem([
                    display_name,
                    person_info.title,
                    person_info.occupation,
                    person_info.cluster_names_display,
                    dna_text,
                ])

                # Store person_id in UserRole on column 0
                tree_item.setData(0, Qt.ItemDataRole.UserRole, person_info.person_id)

                # Set gender icon
                pixmap = icon_registry.get_gender_icon(person_info.sex)
                from PySide6.QtGui import QIcon
                tree_item.setIcon(0, QIcon(pixmap))

                # Color the dot prefix
                if person_info.is_ancestor or person_info.is_descendant:
                    # Set foreground for the full item isn't ideal, so use tooltip
                    pass

                # Tooltips
                tooltip_parts: list[str] = []
                if person_info.name_count > 1:
                    tooltip_parts.append(self._format_names_tooltip(person_info.all_names))
                if person_info.title:
                    tree_item.setToolTip(1, person_info.title)
                if person_info.occupation:
                    tree_item.setToolTip(2, person_info.occupation)
                if person_info.cluster_names_display:
                    tree_item.setToolTip(3, person_info.cluster_names_display)
                if dna_text:
                    tree_item.setToolTip(4, dna_text)
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
            icon_path = project_path.parent / media_item.file
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

        Args:
            info: The person display info.

        Returns:
            Formatted display string.
        """
        name_part = f"{info.surname}, {info.given}"
        years_parts: list[str] = []
        if info.birth_year or info.death_year:
            birth = info.birth_year if info.birth_year else "?"
            death = info.death_year if info.death_year else "?"
            years_parts.append(f"({birth}\u2013{death})")

        if years_parts:
            return f"{name_part} {years_parts[0]}"
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
            death = info.death_year if info.death_year else "?"
            return f"{name_html} ({birth}\u2013{death})"
        return name_html

    def _on_item_clicked(self, current: QTreeWidgetItem, previous: QTreeWidgetItem) -> None:
        """Handle single-click: emit person_selected signal.

        Args:
            current: The newly selected item.
            previous: The previously selected item.
        """
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
