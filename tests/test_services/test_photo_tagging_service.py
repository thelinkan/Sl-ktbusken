"""Unit tests for PhotoTaggingService.

Tests cover event/place tagging, available events/places filtering,
tag retrieval, and photo lookup by event/place.
"""

from __future__ import annotations

import pytest

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.photo_tagging_service import PhotoTaggingService


@pytest.fixture
def project_data() -> ProjectData:
    """Create a ProjectData instance with events, places, and media."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        events=[
            Event(
                id="evt1",
                type="birth",
                participants=[
                    Participant(person_id="p1", role="child"),
                    Participant(person_id="p2", role="mother"),
                ],
            ),
            Event(
                id="evt2",
                type="marriage",
                participants=[
                    Participant(person_id="p2", role="bride"),
                    Participant(person_id="p3", role="groom"),
                ],
            ),
            Event(
                id="evt3",
                type="death",
                participants=[
                    Participant(person_id="p4", role="deceased"),
                ],
            ),
        ],
        places=[
            Place(id="pl1", type="city", name="Stockholm"),
            Place(id="pl2", type="city", name="Göteborg"),
            Place(id="pl3", type="country", name="Sverige"),
        ],
        media=[
            MediaItem(
                id="m1",
                type="photo",
                file="photo1.jpg",
                title="Photo 1",
                linked_entities=[
                    LinkedEntity(entity_type="place", entity_id="pl1"),
                    LinkedEntity(entity_type="event", entity_id="evt1"),
                ],
            ),
            MediaItem(
                id="m2",
                type="photo",
                file="photo2.jpg",
                title="Photo 2",
                linked_entities=[
                    LinkedEntity(entity_type="place", entity_id="pl1"),
                ],
            ),
            MediaItem(
                id="m3",
                type="document",
                file="doc1.pdf",
                title="Doc 1",
                linked_entities=[
                    LinkedEntity(entity_type="place", entity_id="pl1"),
                ],
            ),
        ],
    )


@pytest.fixture
def service(project_data: ProjectData) -> PhotoTaggingService:
    """Create a PhotoTaggingService instance."""
    return PhotoTaggingService(project_data)


@pytest.fixture
def empty_media_item() -> MediaItem:
    """A media item with no linked entities."""
    return MediaItem(id="m_empty", type="photo", file="empty.jpg", title="Empty")


# ---------------------------------------------------------------------------
# get_available_events
# ---------------------------------------------------------------------------


class TestGetAvailableEvents:
    """Tests for get_available_events filtering."""

    def test_returns_events_with_matching_participant(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        result = service.get_available_events(empty_media_item, ["p1"])
        assert len(result) == 1
        assert result[0].id == "evt1"

    def test_returns_multiple_events_for_participant_in_several(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        result = service.get_available_events(empty_media_item, ["p2"])
        event_ids = [e.id for e in result]
        assert "evt1" in event_ids
        assert "evt2" in event_ids

    def test_excludes_already_linked_events(
        self, service: PhotoTaggingService
    ) -> None:
        media_item = MediaItem(
            id="m_test",
            type="photo",
            file="test.jpg",
            title="Test",
            linked_entities=[
                LinkedEntity(entity_type="event", entity_id="evt1"),
            ],
        )
        result = service.get_available_events(media_item, ["p1", "p2"])
        event_ids = [e.id for e in result]
        assert "evt1" not in event_ids
        assert "evt2" in event_ids

    def test_returns_empty_when_person_ids_empty(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        result = service.get_available_events(empty_media_item, [])
        assert result == []

    def test_returns_empty_when_no_participant_matches(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        result = service.get_available_events(empty_media_item, ["nonexistent"])
        assert result == []


# ---------------------------------------------------------------------------
# get_available_places
# ---------------------------------------------------------------------------


class TestGetAvailablePlaces:
    """Tests for get_available_places filtering."""

    def test_returns_all_places_when_none_linked(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        result = service.get_available_places(empty_media_item)
        assert len(result) == 3

    def test_excludes_already_linked_places(
        self, service: PhotoTaggingService
    ) -> None:
        media_item = MediaItem(
            id="m_test",
            type="photo",
            file="test.jpg",
            title="Test",
            linked_entities=[
                LinkedEntity(entity_type="place", entity_id="pl1"),
                LinkedEntity(entity_type="place", entity_id="pl2"),
            ],
        )
        result = service.get_available_places(media_item)
        place_ids = [p.id for p in result]
        assert place_ids == ["pl3"]

    def test_non_place_entities_dont_affect_filtering(
        self, service: PhotoTaggingService
    ) -> None:
        media_item = MediaItem(
            id="m_test",
            type="photo",
            file="test.jpg",
            title="Test",
            linked_entities=[
                LinkedEntity(entity_type="event", entity_id="pl1"),
            ],
        )
        result = service.get_available_places(media_item)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# add_event_tag / remove_event_tag
# ---------------------------------------------------------------------------


class TestEventTagging:
    """Tests for add_event_tag and remove_event_tag."""

    def test_add_event_tag_appends_linked_entity(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        service.add_event_tag(empty_media_item, "evt1")
        assert len(empty_media_item.linked_entities) == 1
        le = empty_media_item.linked_entities[0]
        assert le.entity_type == "event"
        assert le.entity_id == "evt1"

    def test_remove_event_tag_removes_matching_entity(
        self, service: PhotoTaggingService
    ) -> None:
        media_item = MediaItem(
            id="m_test",
            type="photo",
            file="test.jpg",
            title="Test",
            linked_entities=[
                LinkedEntity(entity_type="event", entity_id="evt1"),
                LinkedEntity(entity_type="place", entity_id="pl1"),
            ],
        )
        service.remove_event_tag(media_item, "evt1")
        assert len(media_item.linked_entities) == 1
        assert media_item.linked_entities[0].entity_type == "place"

    def test_remove_event_tag_no_effect_if_not_present(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        service.remove_event_tag(empty_media_item, "evt_nonexistent")
        assert len(empty_media_item.linked_entities) == 0


# ---------------------------------------------------------------------------
# add_place_tag / remove_place_tag
# ---------------------------------------------------------------------------


class TestPlaceTagging:
    """Tests for add_place_tag and remove_place_tag."""

    def test_add_place_tag_appends_linked_entity(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        service.add_place_tag(empty_media_item, "pl1")
        assert len(empty_media_item.linked_entities) == 1
        le = empty_media_item.linked_entities[0]
        assert le.entity_type == "place"
        assert le.entity_id == "pl1"

    def test_remove_place_tag_removes_matching_entity(
        self, service: PhotoTaggingService
    ) -> None:
        media_item = MediaItem(
            id="m_test",
            type="photo",
            file="test.jpg",
            title="Test",
            linked_entities=[
                LinkedEntity(entity_type="place", entity_id="pl1"),
                LinkedEntity(entity_type="event", entity_id="evt1"),
            ],
        )
        service.remove_place_tag(media_item, "pl1")
        assert len(media_item.linked_entities) == 1
        assert media_item.linked_entities[0].entity_type == "event"

    def test_remove_place_tag_no_effect_if_not_present(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        service.remove_place_tag(empty_media_item, "pl_nonexistent")
        assert len(empty_media_item.linked_entities) == 0


# ---------------------------------------------------------------------------
# get_event_tags / get_place_tags
# ---------------------------------------------------------------------------


class TestGetTags:
    """Tests for get_event_tags and get_place_tags."""

    def test_get_event_tags_returns_event_ids(
        self, service: PhotoTaggingService
    ) -> None:
        media_item = MediaItem(
            id="m_test",
            type="photo",
            file="test.jpg",
            title="Test",
            linked_entities=[
                LinkedEntity(entity_type="event", entity_id="evt1"),
                LinkedEntity(entity_type="event", entity_id="evt2"),
                LinkedEntity(entity_type="place", entity_id="pl1"),
            ],
        )
        result = service.get_event_tags(media_item)
        assert result == ["evt1", "evt2"]

    def test_get_place_tags_returns_place_ids(
        self, service: PhotoTaggingService
    ) -> None:
        media_item = MediaItem(
            id="m_test",
            type="photo",
            file="test.jpg",
            title="Test",
            linked_entities=[
                LinkedEntity(entity_type="place", entity_id="pl1"),
                LinkedEntity(entity_type="place", entity_id="pl2"),
                LinkedEntity(entity_type="event", entity_id="evt1"),
            ],
        )
        result = service.get_place_tags(media_item)
        assert result == ["pl1", "pl2"]

    def test_get_event_tags_empty_when_none(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        assert service.get_event_tags(empty_media_item) == []

    def test_get_place_tags_empty_when_none(
        self, service: PhotoTaggingService, empty_media_item: MediaItem
    ) -> None:
        assert service.get_place_tags(empty_media_item) == []


# ---------------------------------------------------------------------------
# get_photos_for_place / get_photos_for_event
# ---------------------------------------------------------------------------


class TestGetPhotosFor:
    """Tests for get_photos_for_place and get_photos_for_event."""

    def test_get_photos_for_place_returns_matching_photos(
        self, service: PhotoTaggingService
    ) -> None:
        result = service.get_photos_for_place("pl1")
        ids = [m.id for m in result]
        assert "m1" in ids
        assert "m2" in ids
        # m3 is a document, not a photo
        assert "m3" not in ids

    def test_get_photos_for_place_excludes_non_photos(
        self, service: PhotoTaggingService
    ) -> None:
        result = service.get_photos_for_place("pl1")
        for item in result:
            assert item.type == "photo"

    def test_get_photos_for_place_returns_empty_when_no_match(
        self, service: PhotoTaggingService
    ) -> None:
        result = service.get_photos_for_place("pl_nonexistent")
        assert result == []

    def test_get_photos_for_event_returns_matching_photos(
        self, service: PhotoTaggingService
    ) -> None:
        result = service.get_photos_for_event("evt1")
        ids = [m.id for m in result]
        assert ids == ["m1"]

    def test_get_photos_for_event_returns_empty_when_no_match(
        self, service: PhotoTaggingService
    ) -> None:
        result = service.get_photos_for_event("evt_nonexistent")
        assert result == []
