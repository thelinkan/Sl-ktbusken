"""Person List Panel for Släktbusken.

Displays all persons in the project sorted alphabetically by surname then
given name, with filtering via an external FilterDialog. Supports toggle
between showing all persons and a filtered subset, single-click (set active
person) and double-click (open edit window).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from slaktbusken.app import Application

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.name_parser import parse_given_name
from slaktbusken.model.person import Person
from slaktbusken.model.place import Place
from slaktbusken.model.dna import DnaCluster
from slaktbusken.ui.icons.icon_registry import icon_registry


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
) -> list[PersonDisplayInfo]:
    """Build a sorted list of person display info from project data.

    Sorted by surname (case-insensitive) then given name (case-insensitive).

    Args:
        persons: All persons in the project.
        events: All events in the project.
        places: All places in the project.
        families: All families in the project (optional for backward compat).
        dna_clusters: All DNA clusters in the project (optional).

    Returns:
        Sorted list of PersonDisplayInfo items.
    """
    if families is None:
        families = []
    if dna_clusters is None:
        dna_clusters = []

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


def filter_persons(
    persons: list[PersonDisplayInfo],
    criteria: FilterCriteria,
) -> list[PersonDisplayInfo]:
    """Filter a list of persons by the given criteria using AND logic.

    - title: case-insensitive substring on person's title
    - given: case-insensitive substring on given name (asterisk-free, from name_parser)
    - surname: case-insensitive substring on surname
    - event_types: person must participate in at least one event of these types
    - birth_year_from/to: birth year must be within range
    - death_year_from/to: death year must be within range
    - marriage_year_from/to: marriage year must be within range
    - parish: case-insensitive match on any of the person's parish names
    - cluster: case-insensitive substring on any of the person's cluster names

    Note on tilltalsnamn asterisk handling:
        The ``given`` field in PersonDisplayInfo is already the clean display
        string (asterisk marker removed) produced by ``name_parser.parse_given_name``.
        This means filtering naturally ignores the asterisk marker, and a literal
        ``*`` in the search criteria is treated as a literal character — it simply
        won't match any name part since the stored given name contains no asterisks.

    Args:
        persons: The pre-computed person display list.
        criteria: The filter criteria to apply.

    Returns:
        Filtered list of PersonDisplayInfo matching all active criteria.
    """
    result: list[PersonDisplayInfo] = []
    title_lower = criteria.title.strip().lower()
    given_lower = criteria.given.strip().lower()
    surname_lower = criteria.surname.strip().lower()
    parish_lower = criteria.parish.strip().lower()

    for person in persons:
        # Title filter: substring on person's title
        if title_lower:
            if title_lower not in person.title.lower():
                continue

        # Given name filter: substring on given name
        if given_lower:
            if given_lower not in person.given.lower():
                continue

        # Surname filter: substring on surname
        if surname_lower:
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
        cluster_lower = criteria.cluster.strip().lower()
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

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Build the panel UI: toggle + filter button + person list."""
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

        # Person list
        self._list_widget = QListWidget()
        self._list_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        layout.addWidget(self._list_widget)

        # No results message
        self._no_results_label = QLabel("Inga personer matchar filtret")
        self._no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results_label.setStyleSheet("color: gray; font-style: italic;")
        self._no_results_label.setVisible(False)
        layout.addWidget(self._no_results_label)

    def _connect_signals(self) -> None:
        """Connect button signals and list selection signals."""
        self._toggle_button.toggled.connect(self._on_toggle_changed)
        self._filter_button.clicked.connect(self._on_filter_button_clicked)

        self._list_widget.currentItemChanged.connect(self._on_item_clicked)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list_widget.customContextMenuRequested.connect(
            self._on_context_menu_requested
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Refresh the person list from the current project data.

        Call this when the project data changes (e.g., after import, edit).
        """
        data = self._app.project_service.data
        families = data.families if hasattr(data, "families") else []
        dna_clusters = data.dna_clusters if hasattr(data, "dna_clusters") else []
        self._display_list = build_person_display_list(
            data.persons, data.events, data.places, families, dna_clusters
        )
        self._apply_current_view()

    def apply_filter(self, criteria: FilterCriteria) -> None:
        """Apply filter criteria from the FilterDialog.

        Args:
            criteria: The filter criteria to apply.
        """
        self._current_criteria = criteria
        self._filtered_list = filter_persons(self._display_list, criteria)
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
                self._display_list, self._current_criteria
            )
            self._update_list_widget()
        else:
            self._filtered_list = list(self._display_list)
            self._update_list_widget()

    def _update_list_widget(self) -> None:
        """Rebuild the QListWidget items from the filtered list."""
        self._list_widget.clear()

        if not self._filtered_list:
            self._no_results_label.setVisible(True)
            self._list_widget.setVisible(False)
            return

        self._no_results_label.setVisible(False)
        self._list_widget.setVisible(True)

        for person_info in self._filtered_list:
            html_text = self._format_person_html(person_info)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, person_info.person_id)
            self._list_widget.addItem(item)

            # Container widget with HBoxLayout: gender icon + name label
            container = QWidget()
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(4, 2, 4, 2)
            h_layout.setSpacing(4)

            # Gender icon (16×16 px)
            icon_label = QLabel()
            pixmap = icon_registry.get_gender_icon(person_info.sex)
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(16, 16)
            h_layout.addWidget(icon_label)

            # Person name label
            label = QLabel(html_text)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            h_layout.addWidget(label)
            h_layout.addStretch()

            item.setSizeHint(QSize(container.sizeHint().width(), container.sizeHint().height() + 4))
            self._list_widget.setItemWidget(item, container)

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

    def _on_item_clicked(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """Handle single-click: emit person_selected signal.

        Args:
            current: The newly selected item.
            previous: The previously selected item.
        """
        if current is not None:
            person_id = current.data(Qt.ItemDataRole.UserRole)
            if person_id:
                self.person_selected.emit(person_id)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click: emit person_edit_requested signal.

        Args:
            item: The double-clicked item.
        """
        if item is not None:
            person_id = item.data(Qt.ItemDataRole.UserRole)
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

        item = self._list_widget.itemAt(pos)
        if item is None:
            return

        person_id = item.data(Qt.ItemDataRole.UserRole)
        if not person_id:
            return

        # Determine main person id
        main_person_id: Optional[str] = None
        data = self._app.project_service.data
        if data is not None and hasattr(data, "project"):
            main_person_id = data.project.main_person_id

        builder = ContextMenuBuilder()
        menu = builder.build_person_menu(person_id, main_person_id, self)

        global_pos = self._list_widget.mapToGlobal(pos)
        action = menu.exec(global_pos)
        if action is None:
            return

        action_data = action.data()
        if action_data and isinstance(action_data, tuple) and len(action_data) == 2:
            action_type, pid = action_data
            if action_type == "show_relationship" and pid == main_person_id:
                return
            self.context_menu_action.emit(action_type, pid)
