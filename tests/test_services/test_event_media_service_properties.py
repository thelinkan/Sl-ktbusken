"""Property-based tests for EventMediaService.

Feature: redigera-person-media, Property 16: Event media linking creates correct structures

Validates: Requirements 7.3, 8.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.event_media_service import EventMediaService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_EVENT_TYPES = ["death", "funeral"]
_DEATH_MEDIA_TYPES = ["dödruna", "dödsannons", "bouppteckning", "dödsbevis"]
_FUNERAL_MEDIA_TYPES = ["begravningsprogram", "minnesord"]
_ALL_EVENT_MEDIA_TYPES = _DEATH_MEDIA_TYPES + _FUNERAL_MEDIA_TYPES


@st.composite
def event_media_linking_scenario(
    draw: st.DrawFn,
) -> tuple[ProjectData, Event, MediaItem]:
    """Generate an event of type death/funeral and a valid MediaItem for linking.

    Returns (project_data, event, media_item) where:
    - event has type "death" or "funeral" with a random id and participants
    - media_item has a random id, valid media type, file path, and title
    """
    event_id = draw(st.from_regex(r"event_[1-9][0-9]{0,3}", fullmatch=True))
    event_type = draw(st.sampled_from(_EVENT_TYPES))

    # Generate at least one participant
    num_participants = draw(st.integers(min_value=1, max_value=3))
    participants = [
        Participant(
            person_id=draw(st.from_regex(r"person_[1-9][0-9]{0,3}", fullmatch=True)),
            role=draw(st.sampled_from(["deceased", "mourner", "officiant"])),
        )
        for _ in range(num_participants)
    ]

    event = Event(
        id=event_id,
        type=event_type,
        participants=participants,
        media_ids=[],
    )

    # Generate a media item with a type appropriate for the event
    media_id = draw(st.from_regex(r"media_[1-9][0-9]{0,3}", fullmatch=True))
    media_type = draw(st.sampled_from(_ALL_EVENT_MEDIA_TYPES))
    title = draw(
        st.text(
            alphabet=st.characters(categories=("L", "N", "Zs")),
            min_size=1,
            max_size=50,
        )
    )
    file_path = draw(st.from_regex(r"files/[a-z0-9_]{1,15}\.(jpg|pdf|png)", fullmatch=True))

    media_item = MediaItem(
        id=media_id,
        type=media_type,
        file=file_path,
        title=title,
        linked_entities=[],
    )

    project_data = ProjectData(
        project=ProjectMetadata(title="Property Test"),
        events=[event],
        media=[media_item],
    )

    return project_data, event, media_item


# ---------------------------------------------------------------------------
# Property 16: Event media linking creates correct structures
# ---------------------------------------------------------------------------


class TestEventMediaLinkingCreatesCorrectStructures:
    """Feature: redigera-person-media, Property 16: Event media linking creates correct structures

    For any event of type "death" or "funeral" and a valid MediaItem, after
    linking the event's media_ids SHALL contain the MediaItem's id and the
    MediaItem's linked_entities SHALL contain a LinkedEntity with entity_type
    "event" and entity_id matching the event's id.

    **Validates: Requirements 7.3, 8.3**
    """

    @given(scenario=event_media_linking_scenario())
    @settings(max_examples=100, deadline=None)
    def test_linking_adds_media_id_to_event_and_linked_entity_to_media(
        self, scenario: tuple[ProjectData, Event, MediaItem]
    ) -> None:
        """Property 16: Event media linking creates correct structures.

        Feature: redigera-person-media, Property 16: Event media linking creates correct structures
        **Validates: Requirements 7.3, 8.3**
        """
        project_data, event, media_item = scenario

        service = EventMediaService(project_data)
        service.add_media_to_event(event, media_item)

        # Assert: media_item.id is in event.media_ids
        assert media_item.id in event.media_ids, (
            f"Expected media_item.id '{media_item.id}' in event.media_ids, "
            f"but got: {event.media_ids}"
        )

        # Assert: media_item.linked_entities contains a LinkedEntity
        # with entity_type "event" and entity_id matching event.id
        event_links = [
            link
            for link in media_item.linked_entities
            if link.entity_type == "event" and link.entity_id == event.id
        ]
        assert len(event_links) == 1, (
            f"Expected exactly 1 LinkedEntity with entity_type='event' and "
            f"entity_id='{event.id}', found {len(event_links)}.\n"
            f"All linked_entities: {[(l.entity_type, l.entity_id) for l in media_item.linked_entities]}"
        )

    @given(scenario=event_media_linking_scenario())
    @settings(max_examples=100, deadline=None)
    def test_linking_is_idempotent(
        self, scenario: tuple[ProjectData, Event, MediaItem]
    ) -> None:
        """Property 16 (idempotency): Calling add_media_to_event twice does not duplicate.

        Feature: redigera-person-media, Property 16: Event media linking creates correct structures
        **Validates: Requirements 7.3, 8.3**
        """
        project_data, event, media_item = scenario

        service = EventMediaService(project_data)

        # Call twice
        service.add_media_to_event(event, media_item)
        service.add_media_to_event(event, media_item)

        # Assert: media_item.id appears exactly once in event.media_ids
        count_in_media_ids = event.media_ids.count(media_item.id)
        assert count_in_media_ids == 1, (
            f"Expected media_item.id '{media_item.id}' exactly once in "
            f"event.media_ids, found {count_in_media_ids} times.\n"
            f"event.media_ids: {event.media_ids}"
        )

        # Assert: exactly one LinkedEntity for this event in media_item
        event_links = [
            link
            for link in media_item.linked_entities
            if link.entity_type == "event" and link.entity_id == event.id
        ]
        assert len(event_links) == 1, (
            f"Expected exactly 1 LinkedEntity for event '{event.id}' after "
            f"double-linking, found {len(event_links)}.\n"
            f"All linked_entities: {[(l.entity_type, l.entity_id) for l in media_item.linked_entities]}"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 17
# ---------------------------------------------------------------------------


@st.composite
def event_media_unlinking_scenario(
    draw: st.DrawFn,
) -> tuple[ProjectData, Event, str, list[MediaItem]]:
    """Generate an event with multiple linked media items for unlinking tests.

    Returns (project_data, event, target_media_id, all_media_items) where:
    - event has type "death" or "funeral" with linked media items
    - target_media_id is the media id to unlink
    - all_media_items contains all MediaItems in project_data.media
    """
    event_id = draw(st.from_regex(r"event_[1-9][0-9]{0,3}", fullmatch=True))
    event_type = draw(st.sampled_from(_EVENT_TYPES))

    # Generate at least one participant
    num_participants = draw(st.integers(min_value=1, max_value=3))
    participants = [
        Participant(
            person_id=draw(st.from_regex(r"person_[1-9][0-9]{0,3}", fullmatch=True)),
            role=draw(st.sampled_from(["deceased", "mourner", "officiant"])),
        )
        for _ in range(num_participants)
    ]

    # Generate 1 to 4 media items with unique ids
    num_media = draw(st.integers(min_value=1, max_value=4))
    media_ids = draw(
        st.lists(
            st.from_regex(r"media_[1-9][0-9]{0,3}", fullmatch=True),
            min_size=num_media,
            max_size=num_media,
            unique=True,
        )
    )

    # Build media items, some with additional non-event linked entities
    media_items: list[MediaItem] = []
    for mid in media_ids:
        media_type = draw(st.sampled_from(_ALL_EVENT_MEDIA_TYPES))
        title = draw(
            st.text(
                alphabet=st.characters(categories=("L", "N", "Zs")),
                min_size=1,
                max_size=30,
            )
        )
        file_path = draw(
            st.from_regex(r"files/[a-z0-9_]{1,10}\.(jpg|pdf|png)", fullmatch=True)
        )

        # Generate some non-event linked entities to verify they are preserved
        num_other_links = draw(st.integers(min_value=0, max_value=2))
        other_links: list[LinkedEntity] = []
        for _ in range(num_other_links):
            other_entity_type = draw(st.sampled_from(["person", "source", "place"]))
            other_entity_id = draw(
                st.from_regex(r"[a-z]+_[1-9][0-9]{0,2}", fullmatch=True)
            )
            other_links.append(
                LinkedEntity(entity_type=other_entity_type, entity_id=other_entity_id)
            )

        media_item = MediaItem(
            id=mid,
            type=media_type,
            file=file_path,
            title=title,
            linked_entities=other_links,
        )
        media_items.append(media_item)

    event = Event(
        id=event_id,
        type=event_type,
        participants=participants,
        media_ids=[],
    )

    project_data = ProjectData(
        project=ProjectMetadata(title="Property Test Unlinking"),
        events=[event],
        media=media_items,
    )

    # Link all media items to the event using the service
    service = EventMediaService(project_data)
    for mi in media_items:
        service.add_media_to_event(event, mi)

    # Pick one media item to unlink
    target_index = draw(st.integers(min_value=0, max_value=len(media_items) - 1))
    target_media_id = media_items[target_index].id

    return project_data, event, target_media_id, media_items


# ---------------------------------------------------------------------------
# Property 17: Event media unlinking preserves MediaItem
# ---------------------------------------------------------------------------


class TestEventMediaUnlinkingPreservesMediaItem:
    """Feature: redigera-person-media, Property 17: Event media unlinking preserves MediaItem

    For any event with linked media, after unlinking a media_id, the event's
    media_ids SHALL not contain that id, the MediaItem's linked_entities SHALL
    not contain a LinkedEntity for that event, but the MediaItem record itself
    SHALL still exist in project_data.media.

    **Validates: Requirements 7.4, 8.4**
    """

    @given(scenario=event_media_unlinking_scenario())
    @settings(max_examples=100, deadline=None)
    def test_unlinked_media_id_removed_from_event(
        self, scenario: tuple[ProjectData, Event, str, list[MediaItem]]
    ) -> None:
        """Property 17: After unlinking, the media_id SHALL NOT be in event.media_ids.

        Feature: redigera-person-media, Property 17: Event media unlinking preserves MediaItem
        **Validates: Requirements 7.4, 8.4**
        """
        project_data, event, target_media_id, all_media = scenario

        service = EventMediaService(project_data)
        service.remove_media_from_event(event, target_media_id)

        assert target_media_id not in event.media_ids, (
            f"Expected media_id '{target_media_id}' to be removed from "
            f"event.media_ids, but it is still present: {event.media_ids}"
        )

    @given(scenario=event_media_unlinking_scenario())
    @settings(max_examples=100, deadline=None)
    def test_unlinked_media_has_no_event_linked_entity(
        self, scenario: tuple[ProjectData, Event, str, list[MediaItem]]
    ) -> None:
        """Property 17: After unlinking, the MediaItem's linked_entities SHALL NOT
        contain a LinkedEntity with entity_type "event" and entity_id == event.id.

        Feature: redigera-person-media, Property 17: Event media unlinking preserves MediaItem
        **Validates: Requirements 7.4, 8.4**
        """
        project_data, event, target_media_id, all_media = scenario

        service = EventMediaService(project_data)
        service.remove_media_from_event(event, target_media_id)

        # Find the target media item
        target_item = next(m for m in project_data.media if m.id == target_media_id)

        event_links = [
            link
            for link in target_item.linked_entities
            if link.entity_type == "event" and link.entity_id == event.id
        ]
        assert len(event_links) == 0, (
            f"Expected no LinkedEntity with entity_type='event' and "
            f"entity_id='{event.id}' on MediaItem '{target_media_id}', "
            f"but found: {[(l.entity_type, l.entity_id) for l in event_links]}"
        )

    @given(scenario=event_media_unlinking_scenario())
    @settings(max_examples=100, deadline=None)
    def test_unlinked_media_item_still_exists_in_project_data(
        self, scenario: tuple[ProjectData, Event, str, list[MediaItem]]
    ) -> None:
        """Property 17: After unlinking, the MediaItem record SHALL still exist
        in project_data.media.

        Feature: redigera-person-media, Property 17: Event media unlinking preserves MediaItem
        **Validates: Requirements 7.4, 8.4**
        """
        project_data, event, target_media_id, all_media = scenario

        service = EventMediaService(project_data)
        service.remove_media_from_event(event, target_media_id)

        media_ids_in_project = [m.id for m in project_data.media]
        assert target_media_id in media_ids_in_project, (
            f"Expected MediaItem '{target_media_id}' to still exist in "
            f"project_data.media after unlinking, but it was not found.\n"
            f"Remaining media ids: {media_ids_in_project}"
        )

    @given(scenario=event_media_unlinking_scenario())
    @settings(max_examples=100, deadline=None)
    def test_other_linked_media_remain_unchanged(
        self, scenario: tuple[ProjectData, Event, str, list[MediaItem]]
    ) -> None:
        """Property 17: Other linked media items on the same event SHALL remain unchanged.

        Feature: redigera-person-media, Property 17: Event media unlinking preserves MediaItem
        **Validates: Requirements 7.4, 8.4**
        """
        project_data, event, target_media_id, all_media = scenario

        # Record expected remaining media ids
        expected_remaining = [mid for mid in event.media_ids if mid != target_media_id]

        service = EventMediaService(project_data)
        service.remove_media_from_event(event, target_media_id)

        # All other media ids should still be in event.media_ids
        assert event.media_ids == expected_remaining, (
            f"Expected remaining media_ids to be {expected_remaining}, "
            f"but got: {event.media_ids}"
        )

    @given(scenario=event_media_unlinking_scenario())
    @settings(max_examples=100, deadline=None)
    def test_non_event_linked_entities_preserved_on_unlinked_media(
        self, scenario: tuple[ProjectData, Event, str, list[MediaItem]]
    ) -> None:
        """Property 17: Non-event linked entities on the removed MediaItem are preserved.

        Feature: redigera-person-media, Property 17: Event media unlinking preserves MediaItem
        **Validates: Requirements 7.4, 8.4**
        """
        project_data, event, target_media_id, all_media = scenario

        # Record non-event linked entities before unlinking
        target_item = next(m for m in project_data.media if m.id == target_media_id)
        non_event_links_before = [
            (link.entity_type, link.entity_id)
            for link in target_item.linked_entities
            if not (link.entity_type == "event" and link.entity_id == event.id)
        ]

        service = EventMediaService(project_data)
        service.remove_media_from_event(event, target_media_id)

        # Check non-event links are preserved
        non_event_links_after = [
            (link.entity_type, link.entity_id)
            for link in target_item.linked_entities
            if not (link.entity_type == "event" and link.entity_id == event.id)
        ]
        assert non_event_links_after == non_event_links_before, (
            f"Expected non-event linked entities to be preserved.\n"
            f"Before: {non_event_links_before}\n"
            f"After: {non_event_links_after}"
        )
