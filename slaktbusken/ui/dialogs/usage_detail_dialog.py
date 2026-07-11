"""Användningsdetaljer för en källa.

Visar en dialog med alla distinkta personer som refererar till en källa,
med varje persons refererande händelser grupperade under personens namn.

Validates: Requirements 6.4
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.event import Event
from slaktbusken.model.person import Person
from slaktbusken.model.source import Source


# Swedish translations for known event types
_EVENT_TYPE_TRANSLATIONS: dict[str, str] = {
    "birth": "Födelse",
    "death": "Död",
    "marriage": "Vigsel",
    "baptism": "Dop",
    "burial": "Begravning",
    "census": "Folkräkning",
    "divorce": "Skilsmässa",
    "engagement": "Förlovning",
    "immigration": "Invandring",
    "emigration": "Utvandring",
    "confirmation": "Konfirmation",
    "graduation": "Examen",
    "retirement": "Pensionering",
    "occupation": "Yrke",
    "residence": "Bostad",
}


def _get_person_display_name(person_id: str, persons: list[Person]) -> str:
    """Get display name for a person by ID.

    Returns "{given} {surname}" from the first name entry,
    or the person_id if no person is found.
    """
    for person in persons:
        if person.id == person_id:
            if person.names:
                name = person.names[0]
                parts = []
                if name.given:
                    parts.append(name.given)
                if name.surname:
                    parts.append(name.surname)
                if parts:
                    return " ".join(parts)
            return person.id
    return person_id


def _translate_event_type(event: Event) -> str:
    """Translate an event type to Swedish display text."""
    if event.custom_type_name:
        return event.custom_type_name
    return _EVENT_TYPE_TRANSLATIONS.get(event.type, event.type.capitalize())


def build_usage_groups(
    source_id: str,
    events: list[Event],
    persons: list[Person],
) -> dict[str, list[Event]]:
    """Build a mapping of person_id -> list of events referencing the source.

    Groups events by person, where each person is a participant in events
    that reference the given source.

    Args:
        source_id: The source ID to check.
        events: All events in the project.
        persons: All persons in the project (unused here, for caller context).

    Returns:
        Dict mapping person_id to list of events that reference the source
        and include that person as a participant.
    """
    person_events: dict[str, list[Event]] = {}

    for event in events:
        references_source = False

        if event.date is not None:
            for ref in event.date.source_refs:
                if ref.source_id == source_id:
                    references_source = True
                    break

        if not references_source and event.place is not None:
            for ref in event.place.source_refs:
                if ref.source_id == source_id:
                    references_source = True
                    break

        if references_source:
            for participant in event.participants:
                pid = participant.person_id
                if pid not in person_events:
                    person_events[pid] = []
                person_events[pid].append(event)

    return person_events


class UsageDetailDialog(QDialog):
    """Dialog som visar användningsdetaljer för en källa.

    Listar alla distinkta personer som refererar till källan, med
    varje persons refererande händelser grupperade under personens namn.

    Args:
        parent: Föräldrawidget.
        source: Källan vars användning visas.
        events: Alla händelser i projektet.
        persons: Alla personer i projektet.
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        source: Source,
        events: list[Event],
        persons: list[Person],
    ) -> None:
        """Initiera dialogen med käll- och projektdata.

        Args:
            parent: Föräldrawidget.
            source: Källan vars användning visas.
            events: Alla händelser i projektet.
            persons: Alla personer i projektet.
        """
        super().__init__(parent)
        self._source = source
        self._events = events
        self._persons = persons

        self.setWindowTitle(f"Användning: {source.title or source.id}")
        self.setMinimumWidth(450)
        self.setMinimumHeight(300)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Bygg dialogens UI-layout."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(f"<b>Källa:</b> {self._source.title or self._source.id}")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Scrollable content area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Build grouped usage data
        person_events = build_usage_groups(
            self._source.id, self._events, self._persons
        )

        if not person_events:
            no_usage_label = QLabel("Inga händelser refererar till denna källa.")
            no_usage_label.setWordWrap(True)
            scroll_layout.addWidget(no_usage_label)
        else:
            # Sort persons by display name for consistent ordering
            sorted_persons = sorted(
                person_events.items(),
                key=lambda item: _get_person_display_name(item[0], self._persons).lower(),
            )

            for person_id, events_for_person in sorted_persons:
                display_name = _get_person_display_name(person_id, self._persons)

                # Person header
                person_label = QLabel(f"<b>{display_name}</b>")
                person_label.setObjectName("person_header")
                scroll_layout.addWidget(person_label)

                # Events for this person
                for event in events_for_person:
                    event_type = _translate_event_type(event)
                    date_str = event.date.value if event.date else "inget datum"
                    event_label = QLabel(f"  • {event_type} ({date_str})")
                    event_label.setObjectName("event_item")
                    scroll_layout.addWidget(event_label)

            # Summary at bottom
            total_persons = len(person_events)
            total_events = sum(
                1 for event in self._events
                if self._event_references_source(event)
            )
            summary = QLabel(
                f"\n<i>Totalt: {total_persons} person{'er' if total_persons != 1 else ''}, "
                f"{total_events} händelse{'r' if total_events != 1 else ''}</i>"
            )
            scroll_layout.addWidget(summary)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

    def _event_references_source(self, event: Event) -> bool:
        """Check if an event references this dialog's source."""
        if event.date is not None:
            for ref in event.date.source_refs:
                if ref.source_id == self._source.id:
                    return True

        if event.place is not None:
            for ref in event.place.source_refs:
                if ref.source_id == self._source.id:
                    return True

        return False
