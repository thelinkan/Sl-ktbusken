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
from slaktbusken.model.place import Place
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.model.source import Source
from slaktbusken.services.source_stats import residence_usage_text


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


def build_residence_groups(
    source_id: str,
    residences: list[ResidenceFact],
) -> dict[str, list[ResidenceFact]]:
    """Build a mapping of person_id -> residence facts citing the source.

    A residence cites the source when at least one of its observations does.
    """
    groups: dict[str, list[ResidenceFact]] = {}
    for fact in residences:
        if any(obs.source_ref.source_id == source_id for obs in fact.observations):
            groups.setdefault(fact.person_id, []).append(fact)
    return groups


class UsageDetailDialog(QDialog):
    """Dialog som visar användningsdetaljer för en källa.

    Listar alla distinkta personer som refererar till källan (via händelser
    eller boenden), med varje persons händelser och boenden under namnet.

    Args:
        parent: Föräldrawidget.
        source: Källan vars användning visas.
        events: Alla händelser i projektet.
        persons: Alla personer i projektet.
        residences: Alla boenden i projektet (valfritt).
        places: Alla platser i projektet, för platsnamn (valfritt).
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        source: Source,
        events: list[Event],
        persons: list[Person],
        residences: Optional[list[ResidenceFact]] = None,
        places: Optional[list[Place]] = None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._events = events
        self._persons = persons
        self._residences = residences or []
        self._places = places or []

        self.setWindowTitle(f"Användning: {source.title or source.id}")
        self.setMinimumWidth(450)
        self.setMinimumHeight(300)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Bygg dialogens UI-layout."""
        layout = QVBoxLayout(self)

        header = QLabel(f"<b>Källa:</b> {self._source.title or self._source.id}")
        header.setWordWrap(True)
        layout.addWidget(header)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        person_events = build_usage_groups(self._source.id, self._events, self._persons)
        person_residences = build_residence_groups(self._source.id, self._residences)
        person_ids = set(person_events) | set(person_residences)

        if not person_ids:
            no_usage_label = QLabel(
                "Inga händelser eller boenden refererar till denna källa."
            )
            no_usage_label.setObjectName("no_usage")
            no_usage_label.setWordWrap(True)
            scroll_layout.addWidget(no_usage_label)
        else:
            place_names = {p.id: p.name for p in self._places}
            for person_id in sorted(
                person_ids,
                key=lambda pid: _get_person_display_name(pid, self._persons).lower(),
            ):
                display_name = _get_person_display_name(person_id, self._persons)

                person_label = QLabel(f"<b>{display_name}</b>")
                person_label.setObjectName("person_header")
                scroll_layout.addWidget(person_label)

                for event in person_events.get(person_id, []):
                    event_type = _translate_event_type(event)
                    date_str = event.date.value if event.date else "inget datum"
                    event_label = QLabel(f"  • {event_type} ({date_str})")
                    event_label.setObjectName("event_item")
                    scroll_layout.addWidget(event_label)

                for fact in person_residences.get(person_id, []):
                    residence_label = QLabel(
                        f"  • {residence_usage_text(fact, place_names)}"
                    )
                    residence_label.setObjectName("residence_item")
                    scroll_layout.addWidget(residence_label)

            total_events = sum(1 for e in self._events if self._event_references_source(e))
            total_residences = sum(len(v) for v in person_residences.values())
            summary = QLabel(
                "\n<i>"
                + self._summary_text(len(person_ids), total_events, total_residences)
                + "</i>"
            )
            summary.setObjectName("usage_summary")
            scroll_layout.addWidget(summary)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

    @staticmethod
    def _summary_text(persons: int, events: int, residences: int) -> str:
        """Swedish summary line; omits the zero händelse/boende parts."""
        parts = [f"{persons} person{'er' if persons != 1 else ''}"]
        if events or not residences:
            parts.append(f"{events} händelse{'r' if events != 1 else ''}")
        if residences:
            parts.append(f"{residences} boende{'n' if residences != 1 else ''}")
        return "Totalt: " + ", ".join(parts)

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
