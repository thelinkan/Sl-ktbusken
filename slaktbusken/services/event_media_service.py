"""Service for managing event-specific media linking.

EventMediaService encapsulates business logic for linking and unlinking
media items to/from events (death and funeral), with type-specific
allowed media type options per event type.
"""

from __future__ import annotations

from slaktbusken.model.event import Event
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData


class EventMediaService:
    """Business logic for linking media to events."""

    DEATH_MEDIA_TYPES: list[str] = [
        "dödruna",
        "dödsannons",
        "bouppteckning",
        "dödsbevis",
    ]

    FUNERAL_MEDIA_TYPES: list[str] = [
        "begravningsprogram",
        "minnesord",
    ]

    def __init__(self, project_data: ProjectData) -> None:
        self._project_data = project_data

    def get_media_types_for_event(self, event_type: str) -> list[str]:
        """Return allowed media types for the given event type.

        Returns DEATH_MEDIA_TYPES for "death" events, FUNERAL_MEDIA_TYPES
        for "funeral" events, and an empty list for all other event types.
        """
        if event_type == "death":
            return list(self.DEATH_MEDIA_TYPES)
        elif event_type == "funeral":
            return list(self.FUNERAL_MEDIA_TYPES)
        return []

    def add_media_to_event(self, event: Event, media_item: MediaItem) -> None:
        """Link media_item to event: adds to media_ids and creates LinkedEntity.

        Adds the MediaItem's id to the Event's media_ids list and adds a
        LinkedEntity with entity_type "event" and entity_id matching the
        Event's id to the MediaItem's linked_entities list.

        If the media is already linked (id already in media_ids), this is a no-op.
        """
        if media_item.id in event.media_ids:
            return

        event.media_ids.append(media_item.id)
        media_item.linked_entities.append(
            LinkedEntity(entity_type="event", entity_id=event.id)
        )

    def remove_media_from_event(self, event: Event, media_id: str) -> None:
        """Unlink media from event. Does NOT delete the MediaItem.

        Removes the media_id from the Event's media_ids list and removes
        the LinkedEntity linking the media to this event from the MediaItem's
        linked_entities list. The MediaItem record itself is preserved.
        """
        if media_id in event.media_ids:
            event.media_ids.remove(media_id)

        # Find the MediaItem in project data and remove the event link
        for media_item in self._project_data.media:
            if media_item.id == media_id:
                media_item.linked_entities = [
                    link
                    for link in media_item.linked_entities
                    if not (
                        link.entity_type == "event" and link.entity_id == event.id
                    )
                ]
                break
