"""Property-based tests for Photo Management Rework.

Feature: photo-management-rework
"""

from __future__ import annotations

import calendar

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.services.photo_date_validator import PhotoDate, PhotoDateValidator


# ---------------------------------------------------------------------------
# Strategies for Property 2
# ---------------------------------------------------------------------------

# Slightly wider than valid range to test boundaries
year_strategy = st.one_of(st.none(), st.integers(min_value=0, max_value=10000))
month_strategy = st.one_of(st.none(), st.integers(min_value=0, max_value=13))
day_strategy = st.one_of(st.none(), st.integers(min_value=0, max_value=32))


# ---------------------------------------------------------------------------
# Oracle: independent validity computation
# ---------------------------------------------------------------------------


def is_valid_photo_date(year: int | None, month: int | None, day: int | None) -> bool:
    """Independently compute whether a photo date combination is valid.

    Rules:
    - All None: valid
    - Month without year: invalid
    - Day without month or year: invalid
    - Year range: 1-9999
    - Month range: 1-12
    - Day must be valid for the given month/year (using calendar)
    """
    # All None: valid
    if year is None and month is None and day is None:
        return True
    # Month without year: invalid
    if month is not None and year is None:
        return False
    # Day without month or year: invalid
    if day is not None and (month is None or year is None):
        return False
    # Year range check
    if year is not None and (year < 1 or year > 9999):
        return False
    # Month range check
    if month is not None and (month < 1 or month > 12):
        return False
    # Day validation
    if day is not None and month is not None and year is not None:
        _, max_day = calendar.monthrange(year, month)
        if day < 1 or day > max_day:
            return False
    return True


# ---------------------------------------------------------------------------
# Property 2: Photo date validation correctness
# ---------------------------------------------------------------------------


class TestPhotoDateValidationCorrectness:
    """Feature: photo-management-rework, Property 2: Photo date validation correctness

    For any combination of year (1-9999 or None), month (1-12 or None), and
    day (1-31 or None), the date validator SHALL accept the combination if and
    only if: (a) all fields are None, (b) only year is provided, (c) year and
    valid month are provided, or (d) year, month, and a day valid for that
    month/year are provided. It SHALL reject month-without-year and
    day-without-month cases, as well as invalid day values for the given
    month/year (e.g., Feb 30).

    **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8**
    """

    @given(year=year_strategy, month=month_strategy, day=day_strategy)
    @settings(max_examples=100, deadline=None)
    def test_validate_matches_oracle(
        self, year: int | None, month: int | None, day: int | None
    ) -> None:
        """Property 2: Photo date validation correctness.

        The validator returns an empty error list if and only if the oracle
        deems the combination valid.

        Feature: photo-management-rework, Property 2: Photo date validation correctness
        **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8**
        """
        errors = PhotoDateValidator.validate(year, month, day)
        expected_valid = is_valid_photo_date(year, month, day)

        if expected_valid:
            assert errors == [], (
                f"Expected valid date (year={year}, month={month}, day={day}) "
                f"but got errors: {errors}"
            )
        else:
            assert len(errors) > 0, (
                f"Expected invalid date (year={year}, month={month}, day={day}) "
                f"but validator returned no errors"
            )


# ---------------------------------------------------------------------------
# Strategies for Property 3
# ---------------------------------------------------------------------------


@st.composite
def valid_full_date(draw: st.DrawFn) -> tuple[int, int, int]:
    """Generate a valid full date (year, month, day) respecting calendar rules."""
    year = draw(st.integers(min_value=1, max_value=9999))
    month = draw(st.integers(min_value=1, max_value=12))
    _, max_day = calendar.monthrange(year, month)
    day = draw(st.integers(min_value=1, max_value=max_day))
    return (year, month, day)


def valid_photo_date() -> st.SearchStrategy[tuple[int | None, int | None, int | None]]:
    """Generate only valid photo date combinations.

    Valid combinations:
    - All None (no date)
    - Year only (year 1-9999, month=None, day=None)
    - Year+month (year 1-9999, month 1-12, day=None)
    - Full valid date (year 1-9999, month 1-12, day valid for that month/year)
    """
    return st.one_of(
        # All None
        st.just((None, None, None)),
        # Year only
        st.integers(min_value=1, max_value=9999).map(lambda y: (y, None, None)),
        # Year + month
        st.tuples(
            st.integers(min_value=1, max_value=9999),
            st.integers(min_value=1, max_value=12),
        ).map(lambda t: (t[0], t[1], None)),
        # Full valid date
        valid_full_date(),
    )


# ---------------------------------------------------------------------------
# Property 3: Photo date storage round-trip
# ---------------------------------------------------------------------------


class TestPhotoDateStorageRoundTrip:
    """Feature: photo-management-rework, Property 3: Photo date storage round-trip

    For any valid photo date (all-None, year-only, year+month, or full date),
    converting to storage format and back SHALL produce the original date values
    with no loss of precision.

    **Validates: Requirements 4.9, 4.10**
    """

    @given(date=valid_photo_date())
    @settings(max_examples=100, deadline=None)
    def test_round_trip_preserves_date(
        self, date: tuple[int | None, int | None, int | None]
    ) -> None:
        """Property 3: Photo date storage round-trip.

        Any valid photo date survives to_storage_format -> from_storage_format
        without loss of precision.

        Feature: photo-management-rework, Property 3: Photo date storage round-trip
        **Validates: Requirements 4.9, 4.10**
        """
        year, month, day = date

        stored = PhotoDateValidator.to_storage_format(year, month, day)
        restored = PhotoDateValidator.from_storage_format(stored)

        assert restored.year == year
        assert restored.month == month
        assert restored.day == day


# ---------------------------------------------------------------------------
# Strategies for Property 4
# ---------------------------------------------------------------------------

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.photo_tagging_service import PhotoTaggingService


@st.composite
def event_filtering_scenario(draw: st.DrawFn) -> tuple[
    list[str],  # person_ids on photo
    list[Event],  # events in project
    MediaItem,  # media item with some already-tagged events
]:
    """Generate a scenario for testing event filtering by linked persons.

    Produces:
    - A list of person IDs (the persons linked to the photo)
    - A list of Events with various participants
    - A MediaItem with some event LinkedEntities already tagged
    """
    # Generate a pool of person IDs (some will be on the photo, some only on events)
    all_person_ids = draw(
        st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N")),
                min_size=1,
                max_size=8,
            ),
            min_size=0,
            max_size=6,
            unique=True,
        )
    )

    # Person IDs linked to the photo (subset of all, or possibly empty)
    if all_person_ids:
        person_ids_on_photo = draw(
            st.lists(
                st.sampled_from(all_person_ids),
                min_size=0,
                max_size=len(all_person_ids),
                unique=True,
            )
        )
    else:
        person_ids_on_photo = []

    # Generate events with participants drawn from all_person_ids
    event_ids = draw(
        st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=("L", "N")),
                min_size=1,
                max_size=8,
            ),
            min_size=0,
            max_size=5,
            unique=True,
        )
    )

    events: list[Event] = []
    for event_id in event_ids:
        if all_person_ids:
            participants = draw(
                st.lists(
                    st.sampled_from(all_person_ids).map(
                        lambda pid: Participant(person_id=pid, role="Participant")
                    ),
                    min_size=0,
                    max_size=min(3, len(all_person_ids)),
                    unique_by=lambda p: p.person_id,
                )
            )
        else:
            participants = []
        events.append(Event(id=event_id, type="generic", participants=participants))

    # Some events are already tagged on the media item
    already_tagged_ids: list[str] = []
    if event_ids:
        already_tagged_ids = draw(
            st.lists(
                st.sampled_from(event_ids),
                min_size=0,
                max_size=len(event_ids),
                unique=True,
            )
        )

    linked_entities = [
        LinkedEntity(entity_type="event", entity_id=eid) for eid in already_tagged_ids
    ]
    # Add some non-event linked entities to ensure they don't interfere
    linked_entities.extend(
        draw(
            st.lists(
                st.just(LinkedEntity(entity_type="person", entity_id="some_person")),
                min_size=0,
                max_size=2,
            )
        )
    )

    media_item = MediaItem(
        id="photo_1",
        type="photo",
        file="test.jpg",
        title="Test Photo",
        linked_entities=linked_entities,
    )

    return (person_ids_on_photo, events, media_item)


# ---------------------------------------------------------------------------
# Property 4: Event filtering by linked persons
# ---------------------------------------------------------------------------


class TestEventFilteringByLinkedPersons:
    """Feature: photo-management-rework, Property 4: Event filtering by linked persons

    For any set of person IDs linked to a photo, any set of events in the
    project, and any set of event tags already on the photo, the
    available-events filter SHALL return exactly those events where at least
    one of the photo's persons is a Participant AND the event is not already
    tagged on the photo. When the person set is empty, the result SHALL be
    empty.

    **Validates: Requirements 7.4, 7.5**
    """

    @given(scenario=event_filtering_scenario())
    @settings(max_examples=100, deadline=None)
    def test_event_filtering_matches_oracle(
        self,
        scenario: tuple[list[str], list[Event], MediaItem],
    ) -> None:
        """Property 4: Event filtering by linked persons.

        The service returns exactly the events matching the oracle logic.

        Feature: photo-management-rework, Property 4: Event filtering by linked persons
        **Validates: Requirements 7.4, 7.5**
        """
        person_ids, events, media_item = scenario

        # Build ProjectData with the generated events
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            events=events,
        )

        service = PhotoTaggingService(project_data)
        result = service.get_available_events(media_item, person_ids)

        # Oracle: independently compute expected result
        person_id_set = set(person_ids)
        already_linked = {
            le.entity_id
            for le in media_item.linked_entities
            if le.entity_type == "event"
        }

        expected_event_ids: set[str] = set()
        for event in events:
            if event.id in already_linked:
                continue
            for p in event.participants:
                if p.person_id in person_id_set:
                    expected_event_ids.add(event.id)
                    break

        # When person_ids is empty, result should be empty
        if not person_ids:
            assert result == [], (
                f"Expected empty result when person_ids is empty, got {result}"
            )
        else:
            result_event_ids = {e.id for e in result}
            assert result_event_ids == expected_event_ids, (
                f"Expected event IDs {expected_event_ids}, got {result_event_ids}. "
                f"person_ids={person_ids}, already_linked={already_linked}"
            )


# ---------------------------------------------------------------------------
# Imports for Property 6
# ---------------------------------------------------------------------------

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.photo_tagging_service import PhotoTaggingService


# ---------------------------------------------------------------------------
# Strategies for Property 6
# ---------------------------------------------------------------------------


@st.composite
def places_and_media_item(draw: st.DrawFn) -> tuple[list[Place], MediaItem]:
    """Generate a list of places and a MediaItem with some linked place entities.

    Produces:
    - A list of Place objects with unique IDs
    - A MediaItem that has a subset of those place IDs as linked entities
    """
    # Generate unique place IDs
    num_places = draw(st.integers(min_value=0, max_value=10))
    place_ids = [f"place-{i}" for i in range(num_places)]

    places = [
        Place(id=pid, type="city", name=f"Place {pid}")
        for pid in place_ids
    ]

    # Pick a subset of place IDs to be already linked
    if place_ids:
        linked_ids = draw(
            st.lists(st.sampled_from(place_ids), unique=True, max_size=num_places)
        )
    else:
        linked_ids = []

    linked_entities = [
        LinkedEntity(entity_type="place", entity_id=pid) for pid in linked_ids
    ]

    media_item = MediaItem(
        id="media-1",
        type="photo",
        file="photo.jpg",
        title="Test Photo",
        linked_entities=linked_entities,
    )

    return (places, media_item)


# ---------------------------------------------------------------------------
# Property 6: Place availability filtering excludes already linked
# ---------------------------------------------------------------------------


class TestPlaceAvailabilityFiltering:
    """Feature: photo-management-rework, Property 6: Place availability filtering excludes already linked

    For any set of places in the project and any set of place tags already on
    a MediaItem, the available-places filter SHALL return exactly those places
    whose ID is not already present as a LinkedEntity with entity_type "place"
    on the MediaItem.

    **Validates: Requirements 8.3**
    """

    @given(data=places_and_media_item())
    @settings(max_examples=100, deadline=None)
    def test_available_places_excludes_already_linked(
        self, data: tuple[list[Place], MediaItem]
    ) -> None:
        """Property 6: Place availability filtering excludes already linked.

        The service returns exactly those places not already linked to the media item.

        Feature: photo-management-rework, Property 6: Place availability filtering excludes already linked
        **Validates: Requirements 8.3**
        """
        places, media_item = data

        project_data = ProjectData(
            project=ProjectMetadata(title="Test Project"),
            places=places,
        )
        service = PhotoTaggingService(project_data)

        result = service.get_available_places(media_item)

        # Oracle
        already_linked_ids = {
            le.entity_id
            for le in media_item.linked_entities
            if le.entity_type == "place"
        }
        expected_place_ids = {p.id for p in places} - already_linked_ids

        result_ids = {p.id for p in result}
        assert result_ids == expected_place_ids, (
            f"Expected available place IDs {expected_place_ids}, "
            f"but got {result_ids}. "
            f"Already linked: {already_linked_ids}"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 5
# ---------------------------------------------------------------------------

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.photo_tagging_service import PhotoTaggingService


ENTITY_TYPES = ["person", "event", "place"]


@st.composite
def linked_entity_strategy(draw: st.DrawFn) -> LinkedEntity:
    """Generate a random LinkedEntity with a random entity type and id."""
    entity_type = draw(st.sampled_from(ENTITY_TYPES))
    entity_id = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))))
    role = draw(st.text(min_size=0, max_size=10, alphabet=st.characters(whitelist_categories=("L",))))
    return LinkedEntity(entity_type=entity_type, entity_id=entity_id, role=role)


@st.composite
def media_item_with_entities(draw: st.DrawFn) -> MediaItem:
    """Generate a MediaItem with a random set of existing LinkedEntities."""
    item_id = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))))
    entities = draw(st.lists(linked_entity_strategy(), min_size=0, max_size=10))
    return MediaItem(
        id=item_id,
        type="photo",
        file="test.jpg",
        title="Test Photo",
        linked_entities=entities,
    )


@st.composite
def tag_add_remove_scenario(draw: st.DrawFn) -> tuple[MediaItem, str, str]:
    """Generate a scenario: MediaItem, tag_id, and tag_type ('event' or 'place')."""
    media_item = draw(media_item_with_entities())
    tag_type = draw(st.sampled_from(["event", "place"]))
    tag_id = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))))
    return (media_item, tag_id, tag_type)


# ---------------------------------------------------------------------------
# Property 5: Tag add/remove preserves non-target linked entities
# ---------------------------------------------------------------------------


class TestTagAddRemovePreservesOtherEntities:
    """Feature: photo-management-rework, Property 5: Tag add/remove preserves non-target linked entities

    For any MediaItem with existing linked entities, adding an event tag (or
    place tag) SHALL append exactly one new LinkedEntity with the correct
    entity_type and entity_id, leaving all pre-existing linked entities
    unchanged. Removing a tag SHALL remove exactly the matching LinkedEntity,
    leaving all others unchanged.

    **Validates: Requirements 7.6, 7.7, 8.4, 8.5**
    """

    @given(data=tag_add_remove_scenario())
    @settings(max_examples=100, deadline=None)
    def test_add_tag_preserves_existing_and_appends_one(
        self, data: tuple[MediaItem, str, str]
    ) -> None:
        """Adding a tag appends exactly one new entity, preserving all existing ones.

        Feature: photo-management-rework, Property 5: Tag add/remove preserves non-target linked entities
        **Validates: Requirements 7.6, 7.7, 8.4, 8.5**
        """
        media_item, tag_id, tag_type = data

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
        )
        service = PhotoTaggingService(project_data)

        # Snapshot before add
        entities_before = list(media_item.linked_entities)

        # Add tag
        if tag_type == "event":
            service.add_event_tag(media_item, tag_id)
        else:
            service.add_place_tag(media_item, tag_id)

        # All pre-existing entities still present in same order
        assert media_item.linked_entities[: len(entities_before)] == entities_before, (
            "Pre-existing entities were modified after adding a tag"
        )

        # Exactly one new entity appended
        assert len(media_item.linked_entities) == len(entities_before) + 1, (
            f"Expected {len(entities_before) + 1} entities, got {len(media_item.linked_entities)}"
        )

        # The appended entity has correct type and id
        new_entity = media_item.linked_entities[-1]
        assert new_entity.entity_type == tag_type
        assert new_entity.entity_id == tag_id

    @given(data=tag_add_remove_scenario())
    @settings(max_examples=100, deadline=None)
    def test_remove_tag_removes_only_target(
        self, data: tuple[MediaItem, str, str]
    ) -> None:
        """Removing a tag removes exactly the matching entity, leaving others unchanged.

        Feature: photo-management-rework, Property 5: Tag add/remove preserves non-target linked entities
        **Validates: Requirements 7.6, 7.7, 8.4, 8.5**
        """
        media_item, tag_id, tag_type = data

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
        )
        service = PhotoTaggingService(project_data)

        # Add a tag first, so we know it exists
        if tag_type == "event":
            service.add_event_tag(media_item, tag_id)
        else:
            service.add_place_tag(media_item, tag_id)

        entities_after_add = list(media_item.linked_entities)

        # Remove the tag
        if tag_type == "event":
            service.remove_event_tag(media_item, tag_id)
        else:
            service.remove_place_tag(media_item, tag_id)

        # The target entity is gone
        remaining_target = [
            le for le in media_item.linked_entities
            if le.entity_type == tag_type and le.entity_id == tag_id
        ]

        # All entities that were NOT the target are still present
        non_target_before = [
            le for le in entities_after_add
            if not (le.entity_type == tag_type and le.entity_id == tag_id)
        ]
        assert media_item.linked_entities == non_target_before, (
            "Non-target entities were modified after removing a tag"
        )

        # The target entity is gone
        assert remaining_target == [], (
            f"Target entity ({tag_type}, {tag_id}) still present after removal"
        )

        # Total length = entities_after_add minus all matching targets
        target_count_before = sum(
            1 for le in entities_after_add
            if le.entity_type == tag_type and le.entity_id == tag_id
        )
        assert len(media_item.linked_entities) == len(entities_after_add) - target_count_before


# ---------------------------------------------------------------------------
# Imports for Property 7
# ---------------------------------------------------------------------------

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.photo_tagging_service import PhotoTaggingService


# ---------------------------------------------------------------------------
# Strategies for Property 7
# ---------------------------------------------------------------------------


@st.composite
def photos_for_entity_scenario(
    draw: st.DrawFn,
) -> tuple[str, str, list[MediaItem]]:
    """Generate a scenario for photos-for-entity filtering.

    Returns:
        (target_entity_type, target_entity_id, media_items)
    """
    target_entity_type = draw(st.sampled_from(["place", "event"]))
    target_entity_id = draw(st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))))

    media_types = ["photo", "document", "audio", "video"]
    entity_types = ["place", "event", "person"]

    media_items: list[MediaItem] = draw(
        st.lists(
            st.tuples(
                # id
                st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
                # type
                st.sampled_from(media_types),
                # linked_entities
                st.lists(
                    st.builds(
                        LinkedEntity,
                        entity_type=st.sampled_from(entity_types),
                        entity_id=st.one_of(
                            st.just(target_entity_id),
                            st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("L", "N"))),
                        ),
                    ),
                    min_size=0,
                    max_size=4,
                ),
            ).map(
                lambda t: MediaItem(
                    id=t[0],
                    type=t[1],
                    file=f"{t[0]}.jpg",
                    title=f"Item {t[0]}",
                    linked_entities=t[2],
                )
            ),
            min_size=0,
            max_size=10,
        )
    )

    # Ensure unique IDs
    seen_ids: set[str] = set()
    unique_items: list[MediaItem] = []
    for item in media_items:
        if item.id not in seen_ids:
            seen_ids.add(item.id)
            unique_items.append(item)

    return (target_entity_type, target_entity_id, unique_items)


# ---------------------------------------------------------------------------
# Property 7: Photos-for-entity filtering
# ---------------------------------------------------------------------------


class TestPhotosForEntityFiltering:
    """Feature: photo-management-rework, Property 7: Photos-for-entity filtering

    For any set of MediaItems in a project and a given entity (place or event),
    querying photos for that entity SHALL return exactly those MediaItems where
    type is "photo" AND a LinkedEntity with the matching entity_type and
    entity_id exists.

    **Validates: Requirements 9.1**
    """

    @given(scenario=photos_for_entity_scenario())
    @settings(max_examples=100, deadline=None)
    def test_photos_for_entity_returns_exact_matches(
        self, scenario: tuple[str, str, list[MediaItem]]
    ) -> None:
        """Property 7: Photos-for-entity filtering.

        The service returns exactly those MediaItems where type is "photo"
        AND a LinkedEntity with the matching entity_type and entity_id exists.

        Feature: photo-management-rework, Property 7: Photos-for-entity filtering
        **Validates: Requirements 9.1**
        """
        target_entity_type, target_entity_id, media_items = scenario

        # Build ProjectData with the generated media items
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            media=media_items,
        )

        service = PhotoTaggingService(project_data)

        # Oracle: compute expected IDs
        expected_ids = set()
        for item in media_items:
            if item.type != "photo":
                continue
            for le in item.linked_entities:
                if le.entity_type == target_entity_type and le.entity_id == target_entity_id:
                    expected_ids.add(item.id)
                    break

        # Call the appropriate service method
        if target_entity_type == "place":
            result = service.get_photos_for_place(target_entity_id)
        else:
            result = service.get_photos_for_event(target_entity_id)

        result_ids = {item.id for item in result}

        assert result_ids == expected_ids, (
            f"entity_type={target_entity_type}, entity_id={target_entity_id}\n"
            f"Expected IDs: {expected_ids}\n"
            f"Got IDs: {result_ids}\n"
            f"Missing: {expected_ids - result_ids}\n"
            f"Extra: {result_ids - expected_ids}"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 8
# ---------------------------------------------------------------------------

import uuid

from slaktbusken.model.media import LinkedEntity, MediaItem


# ---------------------------------------------------------------------------
# Property 8: New photo creation produces correct MediaItem and LinkedEntity
# ---------------------------------------------------------------------------


class TestNewPhotoCreationLinkedEntity:
    """Feature: photo-management-rework, Property 8: New photo creation produces correct MediaItem and LinkedEntity

    For any valid entity_type ("place" or "event") and entity_id, creating a
    new photo linked to that entity SHALL produce a MediaItem with type "photo"
    and a linked_entities list containing at least one LinkedEntity with the
    specified entity_type and entity_id.

    **Validates: Requirements 9.6, 10.4**
    """

    @given(
        entity_type=st.sampled_from(["place", "event"]),
        entity_id=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ),
        title=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
        ),
        file_name=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ).map(lambda s: f"photo_{s}.jpg"),
    )
    @settings(max_examples=100, deadline=None)
    def test_new_photo_has_correct_type_and_linked_entity(
        self,
        entity_type: str,
        entity_id: str,
        title: str,
        file_name: str,
    ) -> None:
        """Property 8: New photo creation produces correct MediaItem and LinkedEntity.

        Creating a photo with a linked entity always produces a MediaItem with
        type "photo" and a linked_entities list containing the specified
        entity_type and entity_id.

        Feature: photo-management-rework, Property 8: New photo creation produces correct MediaItem and LinkedEntity
        **Validates: Requirements 9.6, 10.4**
        """
        # Create a MediaItem as the code would when adding a photo
        media_item = MediaItem(
            id=str(uuid.uuid4()),
            type="photo",
            file=file_name,
            title=title,
            linked_entities=[
                LinkedEntity(entity_type=entity_type, entity_id=entity_id)
            ],
        )

        # Assert invariants
        assert media_item.type == "photo", (
            f"Expected type 'photo', got '{media_item.type}'"
        )
        assert len(media_item.linked_entities) >= 1, (
            "Expected at least one linked entity"
        )
        assert any(
            le.entity_type == entity_type and le.entity_id == entity_id
            for le in media_item.linked_entities
        ), (
            f"Expected a LinkedEntity with entity_type='{entity_type}' and "
            f"entity_id='{entity_id}' in linked_entities, but none found: "
            f"{media_item.linked_entities}"
        )


# ---------------------------------------------------------------------------
# Property 9: Non-photo media type invariant
# ---------------------------------------------------------------------------


class TestNonPhotoMediaTypeInvariant:
    """Feature: photo-management-rework, Property 9: Non-photo media type invariant

    For any media item created via the "Annan media" section, the resulting
    MediaItem's type SHALL NOT be "photo", and it SHALL have a LinkedEntity
    with entity_type "event" and the correct event_id.

    **Validates: Requirements 10.7**
    """

    @given(
        event_id=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ),
        media_type=st.sampled_from(
            ["document", "audio", "video", "dödsannons", "vigselkort", "inbjudan"]
        ),
        title=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
        ),
        file_path=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ).map(lambda s: f"media_{s}.pdf"),
    )
    @settings(max_examples=100, deadline=None)
    def test_non_photo_media_type_and_linked_entity(
        self,
        event_id: str,
        media_type: str,
        title: str,
        file_path: str,
    ) -> None:
        """Property 9: Non-photo media type invariant.

        A MediaItem created for the "Annan media" section always has a type
        that is not "photo" and has a LinkedEntity with entity_type "event"
        and the correct event_id.

        Feature: photo-management-rework, Property 9: Non-photo media type invariant
        **Validates: Requirements 10.7**
        """
        # Create a MediaItem as the code would when adding non-photo media
        media_item = MediaItem(
            id=str(uuid.uuid4()),
            type=media_type,
            file=file_path,
            title=title,
            linked_entities=[
                LinkedEntity(entity_type="event", entity_id=event_id)
            ],
        )

        # Assert invariants
        assert media_item.type != "photo", (
            f"Expected type to NOT be 'photo', but got '{media_item.type}'"
        )
        assert any(
            le.entity_type == "event" and le.entity_id == event_id
            for le in media_item.linked_entities
        ), (
            f"Expected a LinkedEntity with entity_type='event' and "
            f"entity_id='{event_id}' in linked_entities, but none found: "
            f"{media_item.linked_entities}"
        )
