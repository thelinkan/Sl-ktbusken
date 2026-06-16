"""Person List Panel for Släktbusken.

Displays all persons in the project sorted alphabetically by surname then
given name, with filtering by text, birth year, death year, and parish.
Supports single-click (set active person) and double-click (open edit window).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from slaktbusken.app import Application

from slaktbusken.model.event import Event
from slaktbusken.model.person import Person
from slaktbusken.model.place import Place


# ---------------------------------------------------------------------------
# Pure filtering logic (no Qt dependency)
# ---------------------------------------------------------------------------


@dataclass
class FilterCriteria:
    """Criteria for filtering the person list.

    Attributes:
        text: Case-insensitive substring match on given + surname.
        birth_year: Exact match on the person's birth year (as string).
        death_year: Exact match on the person's death year (as string).
        parish: Parish name to match (includes sub-places of parish).
    """

    text: str = ""
    birth_year: str = ""
    death_year: str = ""
    parish: str = ""


@dataclass
class PersonDisplayInfo:
    """Pre-computed display information for a person.

    Attributes:
        person_id: The unique identifier of the person.
        given: Given name from the first name entry.
        surname: Surname from the first name entry.
        birth_year: Birth year as string, or empty if unavailable.
        death_year: Death year as string, or empty if unavailable.
        parish_names: Set of parish names associated with this person's events.
    """

    person_id: str
    given: str
    surname: str
    birth_year: str
    death_year: str
    parish_names: set[str]


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


def build_person_display_list(
    persons: list[Person],
    events: list[Event],
    places: list[Place],
) -> list[PersonDisplayInfo]:
    """Build a sorted list of person display info from project data.

    Sorted by surname (case-insensitive) then given name (case-insensitive).

    Args:
        persons: All persons in the project.
        events: All events in the project.
        places: All places in the project.

    Returns:
        Sorted list of PersonDisplayInfo items.
    """
    display_list: list[PersonDisplayInfo] = []
    for person in persons:
        if not person.names:
            continue
        first_name = person.names[0]
        birth_year, death_year = get_person_birth_death_years(person, events)
        parish_names = get_person_parish_names(person, events, places)
        display_list.append(
            PersonDisplayInfo(
                person_id=person.id,
                given=first_name.given,
                surname=first_name.surname,
                birth_year=birth_year,
                death_year=death_year,
                parish_names=parish_names,
            )
        )

    display_list.sort(key=lambda p: (p.surname.lower(), p.given.lower()))
    return display_list


def filter_persons(
    persons: list[PersonDisplayInfo],
    criteria: FilterCriteria,
) -> list[PersonDisplayInfo]:
    """Filter a list of persons by the given criteria using AND logic.

    - text: case-insensitive substring match on given + surname
    - birth_year: exact match (string)
    - death_year: exact match (string)
    - parish: case-insensitive match on any of the person's parish names

    Args:
        persons: The pre-computed person display list.
        criteria: The filter criteria to apply.

    Returns:
        Filtered list of PersonDisplayInfo matching all active criteria.
    """
    result: list[PersonDisplayInfo] = []
    text_lower = criteria.text.strip().lower()
    parish_lower = criteria.parish.strip().lower()

    for person in persons:
        # Text filter: substring on full name (given + surname)
        if text_lower:
            full_name = f"{person.given} {person.surname}".lower()
            if text_lower not in full_name:
                continue

        # Birth year filter: exact match
        if criteria.birth_year.strip():
            if person.birth_year != criteria.birth_year.strip():
                continue

        # Death year filter: exact match
        if criteria.death_year.strip():
            if person.death_year != criteria.death_year.strip():
                continue

        # Parish filter: case-insensitive match on person's parishes
        if parish_lower:
            if parish_lower not in person.parish_names:
                continue

        result.append(person)

    return result


# ---------------------------------------------------------------------------
# Qt Widget
# ---------------------------------------------------------------------------


class PersonListPanel(QWidget):
    """Panel showing a filterable, sorted list of all persons in the project.

    Emits signals when the user selects (single-click) or edits (double-click)
    a person.

    Signals:
        person_selected: Emitted with person_id on single-click.
        person_edit_requested: Emitted with person_id on double-click.
    """

    person_selected = Signal(str)
    person_edit_requested = Signal(str)

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

        self._setup_ui()
        self._setup_timer()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Build the panel UI: filter fields + person list."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title
        title_label = QLabel("Personlista")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        # Text filter
        self._text_filter = QLineEdit()
        self._text_filter.setPlaceholderText("Sök namn...")
        layout.addWidget(self._text_filter)

        # Year filters row
        year_row = QHBoxLayout()
        self._birth_year_filter = QLineEdit()
        self._birth_year_filter.setPlaceholderText("Födelseår")
        self._birth_year_filter.setMaximumWidth(80)
        year_row.addWidget(self._birth_year_filter)

        self._death_year_filter = QLineEdit()
        self._death_year_filter.setPlaceholderText("Dödsår")
        self._death_year_filter.setMaximumWidth(80)
        year_row.addWidget(self._death_year_filter)
        year_row.addStretch()
        layout.addLayout(year_row)

        # Parish filter
        self._parish_filter = QLineEdit()
        self._parish_filter.setPlaceholderText("Församling...")
        layout.addWidget(self._parish_filter)

        # Person list
        self._list_widget = QListWidget()
        layout.addWidget(self._list_widget)

        # No results message
        self._no_results_label = QLabel("Inga personer matchar filtret")
        self._no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_results_label.setStyleSheet("color: gray; font-style: italic;")
        self._no_results_label.setVisible(False)
        layout.addWidget(self._no_results_label)

    def _setup_timer(self) -> None:
        """Set up the debounce timer for filtering (200ms single-shot)."""
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self._apply_filter)

    def _connect_signals(self) -> None:
        """Connect filter field signals and list selection signals."""
        self._text_filter.textChanged.connect(self._on_filter_changed)
        self._birth_year_filter.textChanged.connect(self._on_filter_changed)
        self._death_year_filter.textChanged.connect(self._on_filter_changed)
        self._parish_filter.textChanged.connect(self._on_filter_changed)

        self._list_widget.currentItemChanged.connect(self._on_item_clicked)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Refresh the person list from the current project data.

        Call this when the project data changes (e.g., after import, edit).
        """
        data = self._app.project_service.data
        self._display_list = build_person_display_list(
            data.persons, data.events, data.places
        )
        self._apply_filter()

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_filter_changed(self) -> None:
        """Restart the debounce timer when any filter field changes."""
        self._filter_timer.start()

    def _apply_filter(self) -> None:
        """Apply current filter criteria and update the list widget."""
        criteria = FilterCriteria(
            text=self._text_filter.text(),
            birth_year=self._birth_year_filter.text(),
            death_year=self._death_year_filter.text(),
            parish=self._parish_filter.text(),
        )
        self._filtered_list = filter_persons(self._display_list, criteria)
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
            display_text = self._format_person_display(person_info)
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, person_info.person_id)
            self._list_widget.addItem(item)

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
            years_parts.append(f"({birth}–{death})")

        if years_parts:
            return f"{name_part} {years_parts[0]}"
        return name_part

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
