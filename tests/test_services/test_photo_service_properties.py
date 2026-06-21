"""Property-based tests for PhotoService.

Feature: redigera-person-media, Property 8: Photo list filtering and ordering

Validates: Requirements 3.2
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.photo_service import PhotoService


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_MEDIA_TYPES = ["photo", "document", "audio", "video", "other"]
_ENTITY_TYPES = ["person", "family", "event", "source", "place"]


@st.composite
def photo_filter_scenario(draw: st.DrawFn) -> tuple[ProjectData, str, list[MediaItem]]:
    """Generate a scenario for testing photo filtering and ordering.

    Returns (project_data, target_person_id, expected_photos) where:
    - project_data contains a mix of MediaItems with varying types and linked_entities
    - target_person_id is the person to filter by
    - expected_photos is the subset that should be returned (sorted by title)
    """
    target_person_id = draw(st.from_regex(r"person_[1-9][0-9]{0,3}", fullmatch=True))

    # Generate other person IDs that differ from target
    other_person_ids = draw(
        st.lists(
            st.from_regex(r"person_[1-9][0-9]{0,3}", fullmatch=True).filter(
                lambda pid: pid != target_person_id
            ),
            min_size=0,
            max_size=3,
            unique=True,
        )
    )

    num_items = draw(st.integers(min_value=0, max_value=10))

    media_items: list[MediaItem] = []
    expected_photos: list[MediaItem] = []

    for i in range(num_items):
        item_id = f"media_{i}"
        item_type = draw(st.sampled_from(_MEDIA_TYPES))
        title = draw(st.text(
            alphabet=st.characters(categories=("L", "N", "Zs")),
            min_size=1,
            max_size=20,
        ))
        file_name = f"file_{i}.jpg"

        # Generate linked entities for this item
        num_links = draw(st.integers(min_value=0, max_value=4))
        linked_entities: list[LinkedEntity] = []

        has_target_person_link = False
        for _j in range(num_links):
            entity_type = draw(st.sampled_from(_ENTITY_TYPES))
            if entity_type == "person":
                # Sometimes link to target, sometimes to others
                if other_person_ids:
                    entity_id = draw(
                        st.sampled_from([target_person_id] + other_person_ids)
                    )
                else:
                    entity_id = draw(st.sampled_from([target_person_id, "person_other"]))
            else:
                entity_id = draw(st.from_regex(r"[a-z]+_[0-9]{1,3}", fullmatch=True))

            role = draw(st.sampled_from(["", "subject", "photographer"]))
            linked_entities.append(LinkedEntity(
                entity_type=entity_type,
                entity_id=entity_id,
                role=role,
            ))

            if entity_type == "person" and entity_id == target_person_id:
                has_target_person_link = True

        item = MediaItem(
            id=item_id,
            type=item_type,
            file=file_name,
            title=title,
            linked_entities=linked_entities,
        )
        media_items.append(item)

        # Track expected results: type=="photo" AND has link to target person
        if item_type == "photo" and has_target_person_link:
            expected_photos.append(item)

    # Sort expected by title (case-insensitive)
    expected_photos.sort(key=lambda m: m.title.lower())

    project_data = ProjectData(
        project=ProjectMetadata(title="Property Test"),
        media=media_items,
    )

    return project_data, target_person_id, expected_photos


# ---------------------------------------------------------------------------
# Property 8: Photo list filtering and ordering
# ---------------------------------------------------------------------------


class TestPhotoListFilteringAndOrdering:
    """Feature: redigera-person-media, Property 8: Photo list filtering and ordering

    For any set of MediaItems in a project and a person_id, the photo list for
    that person SHALL contain exactly those MediaItems where type is 'photo' and
    a LinkedEntity with entity_type 'person' and matching entity_id exists,
    ordered alphabetically by title.

    **Validates: Requirements 3.2**
    """

    @given(scenario=photo_filter_scenario())
    @settings(max_examples=100, deadline=None)
    def test_photo_list_contains_exact_matches_sorted_by_title(
        self, scenario: tuple[ProjectData, str, list[MediaItem]]
    ) -> None:
        """Property 8: Photo list filtering and ordering.

        Feature: redigera-person-media, Property 8: Photo list filtering and ordering
        **Validates: Requirements 3.2**
        """
        project_data, target_person_id, expected_photos = scenario

        service = PhotoService(project_data, Path("/tmp"))
        result = service.get_photos_for_person(target_person_id)

        # Assert exact set of items (correct filtering)
        assert len(result) == len(expected_photos), (
            f"Expected {len(expected_photos)} photos, got {len(result)}.\n"
            f"Expected IDs: {[m.id for m in expected_photos]}\n"
            f"Got IDs: {[m.id for m in result]}"
        )

        for actual, expected in zip(result, expected_photos):
            assert actual.id == expected.id, (
                f"Mismatch at position: expected '{expected.id}', got '{actual.id}'.\n"
                f"Expected order: {[m.id for m in expected_photos]}\n"
                f"Got order: {[m.id for m in result]}"
            )

        # Assert all items are photos
        for item in result:
            assert item.type == "photo", (
                f"Non-photo item '{item.id}' with type '{item.type}' in result"
            )

        # Assert alphabetical ordering by title (case-insensitive)
        titles = [item.title.lower() for item in result]
        assert titles == sorted(titles), (
            f"Result not sorted alphabetically by title.\n"
            f"Got titles: {[item.title for item in result]}"
        )


# ---------------------------------------------------------------------------
# Property 9: Foto_Typ title format round-trip
# ---------------------------------------------------------------------------


class TestFotoTypTitleFormatRoundTrip:
    """Feature: redigera-person-media, Property 9: Foto_Typ title format round-trip

    For any valid Foto_Typ and title string (1–200 characters), formatting as
    `[Foto_Typ] title` and then parsing SHALL recover the original Foto_Typ and
    title exactly.

    **Validates: Requirements 3.4, 3.5, 3.6, 9.2, 9.3**
    """

    @given(
        foto_typ=st.sampled_from(PhotoService.FOTO_TYPES),
        title=st.text(
            alphabet=st.characters(exclude_characters="\n\r"),
            min_size=1,
            max_size=200,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_format_then_parse_recovers_original(
        self, foto_typ: str, title: str
    ) -> None:
        """Property 9: Foto_Typ title format round-trip.

        Feature: redigera-person-media, Property 9: Foto_Typ title format round-trip
        **Validates: Requirements 3.4, 3.5, 3.6, 9.2, 9.3**
        """
        service = PhotoService(
            ProjectData(project=ProjectMetadata(title="Test")), Path("/tmp")
        )

        formatted = service.format_title(foto_typ, title)
        recovered_typ, recovered_title = service.parse_title(formatted)

        assert recovered_typ == foto_typ, (
            f"Foto_Typ mismatch: expected '{foto_typ}', got '{recovered_typ}'.\n"
            f"Formatted string was: '{formatted}'"
        )
        assert recovered_title == title, (
            f"Title mismatch: expected '{title}', got '{recovered_title}'.\n"
            f"Formatted string was: '{formatted}'"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 11
# ---------------------------------------------------------------------------

import tempfile

_FILENAME_STRATEGY = st.from_regex(r"[a-zA-Z0-9_]{1,20}\.jpg", fullmatch=True)
_SUBDIR_STRATEGY = st.from_regex(r"[a-zA-Z0-9_]{1,10}", fullmatch=True)


# ---------------------------------------------------------------------------
# Property 11: Relative path computation
# ---------------------------------------------------------------------------


class TestRelativePathComputation:
    """Feature: redigera-person-media, Property 11: Relative path computation

    For any source file path and foto_mapp path, if the source is inside
    foto_mapp then needs_copy is False and the result is the relative path
    within foto_mapp; if outside, needs_copy is True and the target is
    foto_mapp / filename.

    **Validates: Requirements 4.1, 4.2**
    """

    @given(
        filename=_FILENAME_STRATEGY,
        subdir=st.one_of(st.none(), _SUBDIR_STRATEGY),
    )
    @settings(max_examples=100, deadline=None)
    def test_file_inside_foto_mapp_needs_no_copy(
        self, filename: str, subdir: str | None
    ) -> None:
        """Case 1: Source inside foto_mapp returns relative path, needs_copy=False.

        Feature: redigera-person-media, Property 11: Relative path computation
        **Validates: Requirements 4.1, 4.2**
        """
        foto_mapp = Path(tempfile.mkdtemp())
        try:
            # Build the source path inside foto_mapp (optionally in a subdir)
            if subdir is not None:
                target_dir = foto_mapp / subdir
                target_dir.mkdir(parents=True, exist_ok=True)
                source_path = target_dir / filename
            else:
                source_path = foto_mapp / filename

            # Create the actual file on disk (required for .resolve() on Windows)
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.touch()

            project_data = ProjectData(
                project=ProjectMetadata(title="Test"),
                media=[],
            )
            service = PhotoService(project_data, foto_mapp)
            result_path, needs_copy = service.compute_target_path(source_path)

            # Assert needs_copy is False (file is already inside foto_mapp)
            assert needs_copy is False, (
                f"Expected needs_copy=False for file inside foto_mapp.\n"
                f"foto_mapp: {foto_mapp}\n"
                f"source_path: {source_path}\n"
                f"result_path: {result_path}"
            )

            # Assert the returned path is the relative path within foto_mapp
            if subdir is not None:
                expected_relative = Path(subdir) / filename
            else:
                expected_relative = Path(filename)

            assert result_path == expected_relative, (
                f"Expected relative path {expected_relative}, got {result_path}.\n"
                f"foto_mapp: {foto_mapp}\n"
                f"source_path: {source_path}"
            )
        finally:
            import shutil
            shutil.rmtree(foto_mapp, ignore_errors=True)

    @given(filename=_FILENAME_STRATEGY)
    @settings(max_examples=100, deadline=None)
    def test_file_outside_foto_mapp_needs_copy(self, filename: str) -> None:
        """Case 2: Source outside foto_mapp returns foto_mapp/filename, needs_copy=True.

        Feature: redigera-person-media, Property 11: Relative path computation
        **Validates: Requirements 4.1, 4.2**
        """
        foto_mapp = Path(tempfile.mkdtemp())
        external_dir = Path(tempfile.mkdtemp())
        try:
            # Create the source file in a directory outside foto_mapp
            source_path = external_dir / filename
            source_path.touch()

            project_data = ProjectData(
                project=ProjectMetadata(title="Test"),
                media=[],
            )
            service = PhotoService(project_data, foto_mapp)
            result_path, needs_copy = service.compute_target_path(source_path)

            # Assert needs_copy is True (file is outside foto_mapp)
            assert needs_copy is True, (
                f"Expected needs_copy=True for file outside foto_mapp.\n"
                f"foto_mapp: {foto_mapp}\n"
                f"source_path: {source_path}\n"
                f"result_path: {result_path}"
            )

            # Assert the target is foto_mapp / filename
            expected_target = foto_mapp / filename
            assert result_path == expected_target, (
                f"Expected target {expected_target}, got {result_path}.\n"
                f"foto_mapp: {foto_mapp}\n"
                f"source_path: {source_path}"
            )
        finally:
            import shutil
            shutil.rmtree(foto_mapp, ignore_errors=True)
            shutil.rmtree(external_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Strategies for Property 10
# ---------------------------------------------------------------------------

_ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"]
_DISALLOWED_EXTENSIONS = [".pdf", ".doc", ".mp4", ".xyz", ".txt", ".svg", ".raw", ".psd", ""]


def _randomize_case(ext: str, draw: st.DrawFn) -> str:
    """Randomize the case of each character in an extension."""
    return "".join(
        draw(st.sampled_from([c.lower(), c.upper()])) for c in ext
    )


@st.composite
def file_path_with_allowed_extension(draw: st.DrawFn) -> tuple[str, bool]:
    """Generate a file path with an allowed extension in random case.

    Returns (file_path, should_be_valid=True).
    """
    ext = draw(st.sampled_from(_ALLOWED_EXTENSIONS))
    # Randomize case of the extension
    ext_cased = _randomize_case(ext, draw)
    # Generate a filename (may contain dots for edge cases)
    base = draw(st.text(
        alphabet=st.characters(categories=("L", "N"), whitelist_characters="._- "),
        min_size=1,
        max_size=30,
    ))
    file_path = base + ext_cased
    return file_path, True


@st.composite
def file_path_with_disallowed_extension(draw: st.DrawFn) -> tuple[str, bool]:
    """Generate a file path with a disallowed extension.

    Returns (file_path, should_be_valid=False).
    """
    ext = draw(st.sampled_from(_DISALLOWED_EXTENSIONS))
    base = draw(st.text(
        alphabet=st.characters(categories=("L", "N"), whitelist_characters="._- "),
        min_size=1,
        max_size=30,
    ))
    if ext:
        file_path = base + ext
    else:
        # No extension case: ensure no dot suffix
        file_path = base.rstrip(".")
        if not file_path:
            file_path = "noext"
    return file_path, False


@st.composite
def file_extension_scenario(draw: st.DrawFn) -> tuple[str, bool]:
    """Generate a file path and whether it should be considered valid.

    Mixes allowed and disallowed extensions with various cases.
    """
    return draw(st.one_of(
        file_path_with_allowed_extension(),
        file_path_with_disallowed_extension(),
    ))


# ---------------------------------------------------------------------------
# Property 10: File extension validation
# ---------------------------------------------------------------------------


class TestFileExtensionValidation:
    """Feature: redigera-person-media, Property 10: File extension validation

    For any file path, the extension validator SHALL accept the path if and only
    if its lowercase extension is in the set
    {.jpg, .jpeg, .png, .tif, .tiff, .bmp, .gif, .webp}.

    **Validates: Requirements 3.8**
    """

    @given(scenario=file_extension_scenario())
    @settings(max_examples=100, deadline=None)
    def test_extension_accepted_iff_lowercase_in_allowed_set(
        self, scenario: tuple[str, bool]
    ) -> None:
        """Property 10: File extension validation.

        Feature: redigera-person-media, Property 10: File extension validation
        **Validates: Requirements 3.8**
        """
        file_path, expected_valid = scenario

        service = PhotoService(
            ProjectData(project=ProjectMetadata(title="Test"), media=[]),
            Path("/tmp"),
        )
        result = service.validate_file_extension(file_path)

        # Independently verify: the lowercase suffix should be in ALLOWED_EXTENSIONS
        from pathlib import Path as P
        actual_ext = P(file_path).suffix.lower()
        independently_valid = actual_ext in PhotoService.ALLOWED_EXTENSIONS

        assert result == independently_valid, (
            f"validate_file_extension('{file_path}') returned {result}, "
            f"but suffix '{actual_ext}' (lowercase) "
            f"{'is' if independently_valid else 'is not'} in ALLOWED_EXTENSIONS"
        )
        assert result == expected_valid, (
            f"validate_file_extension('{file_path}') returned {result}, "
            f"expected {expected_valid} based on generated scenario"
        )


# ---------------------------------------------------------------------------
# Property 12: Filename deduplication produces unique names
# ---------------------------------------------------------------------------


class TestFilenameDeduplicationProducesUniqueNames:
    """Feature: redigera-person-media, Property 12: Filename deduplication produces unique names

    For any target filename and set of existing filenames in the directory, the
    deduplication function SHALL return a filename that does not exist in the set,
    follows the pattern `name_N.ext` where N is the smallest positive integer
    producing uniqueness, and preserves the original extension.

    **Validates: Requirements 4.5**
    """

    @given(
        stem=st.from_regex(r"[a-zA-Z0-9]{1,15}", fullmatch=True),
        extension=st.sampled_from([".jpg", ".png", ".tif"]),
        num_conflicts=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_deduplication_produces_unique_names(
        self, stem: str, extension: str, num_conflicts: int
    ) -> None:
        """Property 12: Filename deduplication produces unique names.

        Feature: redigera-person-media, Property 12: Filename deduplication produces unique names
        **Validates: Requirements 4.5**
        """
        import tempfile

        work_dir = Path(tempfile.mkdtemp())

        target_path = work_dir / f"{stem}{extension}"

        # Create conflicting files on disk
        # When num_conflicts > 0, create the base file and sequential _1, _2, ... files
        if num_conflicts > 0:
            target_path.touch()
            for i in range(1, num_conflicts):
                conflict = work_dir / f"{stem}_{i}{extension}"
                conflict.touch()

        service = PhotoService(
            ProjectData(project=ProjectMetadata(title="Test")), work_dir
        )
        result = service.resolve_filename_conflict(target_path)

        if num_conflicts == 0:
            # No conflict: returns the same path
            assert result == target_path, (
                f"Expected original path '{target_path}' when no conflict, got '{result}'"
            )
        else:
            # Conflict exists: returned path must NOT exist on disk
            assert not result.exists(), (
                f"Returned path '{result}' already exists on disk"
            )

            # Must follow pattern stem_N.ext
            assert result.suffix == extension, (
                f"Extension not preserved: expected '{extension}', got '{result.suffix}'"
            )
            result_stem = result.stem
            assert result_stem.startswith(f"{stem}_"), (
                f"Result stem '{result_stem}' does not start with '{stem}_'"
            )

            # Extract the numeric suffix N
            suffix_part = result_stem[len(stem) + 1:]
            assert suffix_part.isdigit(), (
                f"Suffix part '{suffix_part}' is not a valid integer"
            )
            n = int(suffix_part)
            assert n >= 1, f"N must be >= 1, got {n}"

            # N must be the smallest positive integer producing uniqueness
            # All stem_1 through stem_(N-1) must exist on disk
            for i in range(1, n):
                expected_existing = work_dir / f"{stem}_{i}{extension}"
                assert expected_existing.exists(), (
                    f"Expected '{expected_existing}' to exist (N={n} should be smallest "
                    f"unique, but stem_{i} does not exist)"
                )

            # The result path itself must be in the parent directory
            assert result.parent == work_dir, (
                f"Result parent '{result.parent}' != work dir '{work_dir}'"
            )


# ---------------------------------------------------------------------------
# Property 13: Mentioned persons synchronization with Linked_Entity
# ---------------------------------------------------------------------------


@st.composite
def sync_linked_entities_scenario(
    draw: st.DrawFn,
) -> tuple[MediaItem, list[str]]:
    """Generate a MediaItem with mixed linked_entities and a new person_ids list.

    Returns (media_item, new_person_ids) where:
    - media_item has some person-type and some non-person-type linked_entities
    - new_person_ids is the desired final set of person links (may overlap with existing)
    """
    # Generate initial person IDs already linked
    initial_person_ids = draw(
        st.lists(
            st.from_regex(r"p[0-9]{1,4}", fullmatch=True),
            min_size=0,
            max_size=5,
            unique=True,
        )
    )

    # Generate non-person linked entities
    non_person_entity_types = ["event", "source", "family", "place"]
    num_non_person = draw(st.integers(min_value=0, max_value=4))
    non_person_links: list[LinkedEntity] = []
    for _ in range(num_non_person):
        entity_type = draw(st.sampled_from(non_person_entity_types))
        entity_id = draw(st.from_regex(r"[a-z]{2,5}_[0-9]{1,3}", fullmatch=True))
        role = draw(st.sampled_from(["", "subject", "witness", "owner"]))
        non_person_links.append(
            LinkedEntity(entity_type=entity_type, entity_id=entity_id, role=role)
        )

    # Build person-type linked entities from initial_person_ids
    person_links: list[LinkedEntity] = [
        LinkedEntity(entity_type="person", entity_id=pid)
        for pid in initial_person_ids
    ]

    # Combine into linked_entities (non-person first, then person)
    linked_entities = non_person_links + person_links

    media_item = MediaItem(
        id=draw(st.from_regex(r"media_[0-9]{1,4}", fullmatch=True)),
        type="photo",
        file="photo.jpg",
        title="Test Photo",
        linked_entities=linked_entities,
    )

    # Generate new_person_ids: may overlap partially with initial
    # Pool includes some existing and some new IDs
    extra_person_ids = draw(
        st.lists(
            st.from_regex(r"p[0-9]{1,4}", fullmatch=True),
            min_size=0,
            max_size=5,
            unique=True,
        )
    )
    all_candidates = list(set(initial_person_ids + extra_person_ids))
    new_person_ids = draw(
        st.lists(
            st.sampled_from(all_candidates) if all_candidates else st.nothing(),
            min_size=0,
            max_size=min(5, len(all_candidates)) if all_candidates else 0,
            unique=True,
        )
    )

    return media_item, new_person_ids


class TestMentionedPersonsSynchronization:
    """Feature: redigera-person-media, Property 13: Mentioned persons synchronization with Linked_Entity

    For any MediaItem and a new set of mentioned_person_ids, after synchronization
    the MediaItem's linked_entities with entity_type 'person' SHALL contain exactly
    one entry per person_id in the new set, and no entries for person_ids not in the
    new set. Other linked_entities (entity_type != 'person') SHALL be unchanged.

    **Validates: Requirements 5.2, 5.4, 5.5, 5.6, 9.4, 9.5**
    """

    @given(scenario=sync_linked_entities_scenario())
    @settings(max_examples=100, deadline=None)
    def test_sync_produces_exact_person_links_and_preserves_non_person(
        self, scenario: tuple[MediaItem, list[str]]
    ) -> None:
        """Property 13: Mentioned persons synchronization with Linked_Entity.

        Feature: redigera-person-media, Property 13
        **Validates: Requirements 5.2, 5.4, 5.5, 5.6, 9.4, 9.5**
        """
        media_item, new_person_ids = scenario

        # Record non-person linked entities before sync
        non_person_before = [
            (link.entity_type, link.entity_id, link.role)
            for link in media_item.linked_entities
            if link.entity_type != "person"
        ]

        service = PhotoService(
            ProjectData(project=ProjectMetadata(title="Test")), Path("/tmp")
        )
        service.sync_linked_entities(media_item, new_person_ids)

        # Extract person and non-person links after sync
        person_links_after = [
            link for link in media_item.linked_entities
            if link.entity_type == "person"
        ]
        non_person_after = [
            (link.entity_type, link.entity_id, link.role)
            for link in media_item.linked_entities
            if link.entity_type != "person"
        ]

        # Assert: person-type links contain exactly one entry per new_person_id
        person_ids_after = [link.entity_id for link in person_links_after]
        assert set(person_ids_after) == set(new_person_ids), (
            f"Person IDs mismatch.\n"
            f"Expected: {sorted(new_person_ids)}\n"
            f"Got: {sorted(person_ids_after)}"
        )

        # Assert: no duplicates in person links
        assert len(person_ids_after) == len(set(person_ids_after)), (
            f"Duplicate person links found: {person_ids_after}"
        )

        # Assert: no person-type entries for ids NOT in new_person_ids
        unexpected = set(person_ids_after) - set(new_person_ids)
        assert not unexpected, (
            f"Unexpected person IDs in linked_entities: {unexpected}"
        )

        # Assert: non-person linked entities are unchanged
        assert non_person_after == non_person_before, (
            f"Non-person links changed.\n"
            f"Before: {non_person_before}\n"
            f"After: {non_person_after}"
        )
