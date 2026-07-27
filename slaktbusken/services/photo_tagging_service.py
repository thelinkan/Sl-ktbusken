"""Service for managing event and place tag associations on MediaItems."""

from __future__ import annotations

from slaktbusken.model.event import Event
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData


class PhotoTaggingService:
    """Manages event and place tag associations on MediaItems."""

    def __init__(self, project_data: ProjectData) -> None:
        self._project_data = project_data

    def get_available_events(
        self, media_item: MediaItem, person_ids: list[str]
    ) -> list[Event]:
        """Return events where any person_id is a participant, excluding already linked.

        - Filter project_data.events to those where at least one person_id
          appears in event.participants
        - Exclude events already linked via media_item.linked_entities with
          entity_type="event"
        - If person_ids is empty, return empty list
        """
        if not person_ids:
            return []

        person_id_set = set(person_ids)

        already_linked_event_ids = {
            le.entity_id
            for le in media_item.linked_entities
            if le.entity_type == "event"
        }

        results: list[Event] = []
        for event in self._project_data.events:
            if event.id in already_linked_event_ids:
                continue
            for participant in event.participants:
                if participant.person_id in person_id_set:
                    results.append(event)
                    break

        return results

    def get_available_places(self, media_item: MediaItem) -> list[Place]:
        """Return all places not already linked to this media item.

        - Get all project_data.places
        - Exclude places whose id is already in media_item.linked_entities
          with entity_type="place"
        """
        already_linked_place_ids = {
            le.entity_id
            for le in media_item.linked_entities
            if le.entity_type == "place"
        }

        return [
            place
            for place in self._project_data.places
            if place.id not in already_linked_place_ids
        ]

    def add_event_tag(self, media_item: MediaItem, event_id: str) -> None:
        """Create LinkedEntity(entity_type='event', entity_id=event_id) and append to media_item.linked_entities."""
        media_item.linked_entities.append(
            LinkedEntity(entity_type="event", entity_id=event_id)
        )

    def remove_event_tag(self, media_item: MediaItem, event_id: str) -> None:
        """Remove the LinkedEntity with entity_type='event' and entity_id=event_id from media_item.linked_entities."""
        media_item.linked_entities = [
            le
            for le in media_item.linked_entities
            if not (le.entity_type == "event" and le.entity_id == event_id)
        ]

    def add_place_tag(self, media_item: MediaItem, place_id: str) -> None:
        """Create LinkedEntity(entity_type='place', entity_id=place_id) and append to media_item.linked_entities."""
        media_item.linked_entities.append(
            LinkedEntity(entity_type="place", entity_id=place_id)
        )

    def remove_place_tag(self, media_item: MediaItem, place_id: str) -> None:
        """Remove the LinkedEntity with entity_type='place' and entity_id=place_id from media_item.linked_entities."""
        media_item.linked_entities = [
            le
            for le in media_item.linked_entities
            if not (le.entity_type == "place" and le.entity_id == place_id)
        ]

    def get_event_tags(self, media_item: MediaItem) -> list[str]:
        """Return list of event_ids currently tagged (from linked_entities with entity_type='event')."""
        return [
            le.entity_id
            for le in media_item.linked_entities
            if le.entity_type == "event"
        ]

    def get_place_tags(self, media_item: MediaItem) -> list[str]:
        """Return list of place_ids currently tagged (from linked_entities with entity_type='place')."""
        return [
            le.entity_id
            for le in media_item.linked_entities
            if le.entity_type == "place"
        ]

    def get_photos_for_place(self, place_id: str) -> list[MediaItem]:
        """Return all photo MediaItems linked to the given place.

        Filter project_data.media where:
        - type == "photo"
        - has a LinkedEntity with entity_type="place" and entity_id=place_id
        """
        results: list[MediaItem] = []
        for item in self._project_data.media:
            if item.type != "photo":
                continue
            for le in item.linked_entities:
                if le.entity_type == "place" and le.entity_id == place_id:
                    results.append(item)
                    break
        return results

    def get_photos_for_event(self, event_id: str) -> list[MediaItem]:
        """Return all photo MediaItems linked to the given event.

        Filter project_data.media where:
        - type == "photo"
        - has a LinkedEntity with entity_type="event" and entity_id=event_id
        """
        results: list[MediaItem] = []
        for item in self._project_data.media:
            if item.type != "photo":
                continue
            for le in item.linked_entities:
                if le.entity_type == "event" and le.entity_id == event_id:
                    results.append(item)
                    break
        return results
