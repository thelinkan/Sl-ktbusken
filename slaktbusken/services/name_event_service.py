"""Service for managing name-event associations.

Provides helpers to filter events where a person is a participant,
set or clear the event_id on Name records, and detect orphaned
event references.
"""

from __future__ import annotations

from typing import Optional

from slaktbusken.model.event import Event
from slaktbusken.model.person import Name
from slaktbusken.model.project import ProjectData


def get_events_for_person(project_data: ProjectData, person_id: str) -> list[Event]:
    """Return all events where person_id is listed as a participant.

    Args:
        project_data: The root project data container.
        person_id: The ID of the person to filter events for.

    Returns:
        A list of Event instances where the person participates.
    """
    return [
        event
        for event in project_data.events
        if any(p.person_id == person_id for p in event.participants)
    ]


def set_name_event_id(name: Name, event_id: Optional[str]) -> None:
    """Set or clear the event_id on a Name record.

    Args:
        name: The Name record to update.
        event_id: The event ID to associate, or None to clear.
    """
    name.event_id = event_id


def is_event_id_valid(project_data: ProjectData, event_id: str) -> bool:
    """Check whether an event_id references an existing event.

    Used to detect orphaned event references on Name records when
    the linked event has been deleted from the project.

    Args:
        project_data: The root project data container.
        event_id: The event ID to look up.

    Returns:
        True if the event exists in the project, False otherwise.
    """
    return any(event.id == event_id for event in project_data.events)
