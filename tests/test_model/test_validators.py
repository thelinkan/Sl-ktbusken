"""Property-based tests for entity validation functions.

Tests Property 6 (invalid data rejected) and Property 7 (valid data accepted)
from the design document.
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.dna import (
    DnaCluster,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.source import Repository, Source, StructuredReference
from slaktbusken.model.validators import (
    validate_dna_cluster,
    validate_dna_match,
    validate_dna_profile,
    validate_dna_segment,
    validate_dna_triangulation,
    validate_event,
    validate_family,
    validate_media_item,
    validate_person,
    validate_place,
    validate_repository,
    validate_source,
)
from tests.conftest import (
    dna_cluster_strategy,
    dna_match_strategy,
    dna_profile_strategy,
    dna_segment_strategy,
    dna_triangulation_strategy,
    event_strategy,
    family_strategy,
    media_item_strategy,
    person_strategy,
    place_strategy,
    repository_strategy,
    source_strategy,
)


# ===========================================================================
# Property 7: Entity Validation Accepts Valid Data
# **Validates: Requirements 7.5, 8.5, 9.4, 13.4, 14.1**
#
# For any entity with all fields set to values within their specified valid
# ranges and all references pointing to existing entities, the validator
# SHALL accept the entity without errors.
# ===========================================================================


class TestProperty7ValidDataAccepted:
    """Property 7: valid entities pass validation without errors."""

    @given(person=person_strategy())
    @settings(max_examples=100)
    def test_valid_person_passes_validation(self, person: Person) -> None:
        """**Validates: Requirements 7.5**"""
        # Pass None for valid_event_ids to skip reference checks
        errors = validate_person(person, valid_event_ids=None)
        assert errors == [], f"Valid person rejected: {errors}"

    @given(family=family_strategy())
    @settings(max_examples=100)
    def test_valid_family_passes_validation(self, family: Family) -> None:
        """**Validates: Requirements 8.5**"""
        # Pass None for valid_person_ids to skip reference checks
        errors = validate_family(family, valid_person_ids=None)
        assert errors == [], f"Valid family rejected: {errors}"

    @given(event=event_strategy())
    @settings(max_examples=100)
    def test_valid_event_passes_validation(self, event: Event) -> None:
        """**Validates: Requirements 9.4**"""
        errors = validate_event(event)
        assert errors == [], f"Valid event rejected: {errors}"

    @given(place=place_strategy())
    @settings(max_examples=100)
    def test_valid_place_passes_validation(self, place: Place) -> None:
        """**Validates: Requirements 13.4**"""
        # The place_strategy generates random types and parent_place_id.
        # The hierarchy validator requires non-country types to have a parent,
        # and countries to have no parent. Filter to valid hierarchy combos.
        hierarchy_requires_parent = {"county", "parish", "church", "cemetery", "village", "farm", "school"}
        if place.type == "country":
            assume(place.parent_place_id is None)
        elif place.type in hierarchy_requires_parent:
            assume(place.parent_place_id is not None)
        # Pass None for place_lookup to skip parent type verification
        errors = validate_place(place, place_lookup=None)
        assert errors == [], f"Valid place rejected: {errors}"

    @given(source=source_strategy())
    @settings(max_examples=100)
    def test_valid_source_passes_validation(self, source: Source) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_source(source)
        # The strategy may generate arbitrary field names that don't match
        # the expected structured_reference fields for the source_type.
        # We only test sources whose structured_reference fields are valid.
        # Filter: if source_type has defined fields, ensure generated fields are subset.
        from slaktbusken.model.validators import _STRUCTURED_REFERENCE_FIELDS
        if source.source_type in _STRUCTURED_REFERENCE_FIELDS:
            allowed = _STRUCTURED_REFERENCE_FIELDS[source.source_type]
            actual = set(source.structured_reference.fields.keys())
            assume(actual <= allowed)
        assert errors == [], f"Valid source rejected: {errors}"

    @given(repository=repository_strategy())
    @settings(max_examples=100)
    def test_valid_repository_passes_validation(self, repository: Repository) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_repository(repository)
        assert errors == [], f"Valid repository rejected: {errors}"

    @given(media_item=media_item_strategy())
    @settings(max_examples=100)
    def test_valid_media_item_passes_validation(self, media_item: MediaItem) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_media_item(media_item)
        assert errors == [], f"Valid media item rejected: {errors}"

    @given(profile=dna_profile_strategy())
    @settings(max_examples=100)
    def test_valid_dna_profile_passes_validation(self, profile: DnaProfile) -> None:
        """**Validates: Requirements 14.1**"""
        # Pass None for reference sets to skip reference checks
        errors = validate_dna_profile(profile, valid_person_ids=None, valid_company_ids=None)
        assert errors == [], f"Valid DnaProfile rejected: {errors}"

    @given(match=dna_match_strategy())
    @settings(max_examples=100)
    def test_valid_dna_match_passes_validation(self, match: DnaMatch) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_match(match)
        assert errors == [], f"Valid DnaMatch rejected: {errors}"

    @given(segment=dna_segment_strategy())
    @settings(max_examples=100)
    def test_valid_dna_segment_passes_validation(self, segment: DnaSegment) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_segment(segment)
        assert errors == [], f"Valid DnaSegment rejected: {errors}"

    @given(cluster=dna_cluster_strategy())
    @settings(max_examples=100)
    def test_valid_dna_cluster_passes_validation(self, cluster: DnaCluster) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_cluster(cluster)
        assert errors == [], f"Valid DnaCluster rejected: {errors}"

    @given(triangulation=dna_triangulation_strategy())
    @settings(max_examples=100)
    def test_valid_dna_triangulation_passes_validation(
        self, triangulation: DnaTriangulation
    ) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_triangulation(triangulation)
        assert errors == [], f"Valid DnaTriangulation rejected: {errors}"


# ===========================================================================
# Property 6: Entity Validation Rejects Invalid Data
# **Validates: Requirements 7.5, 7.6, 8.5, 8.6, 9.4, 9.7, 10.1, 10.3, 13.4, 13.6, 14.1, 14.4, 14.6**
#
# For any entity with invalid field values, the validator SHALL reject the
# entity and report the specific validation error.
# ===========================================================================


# --- Helpers: invalid entity strategies ---

@st.composite
def _person_no_names(draw: DrawFn) -> Person:
    """Generate a Person with empty names list (invalid)."""
    person = draw(person_strategy())
    return Person(
        id=person.id,
        sex=person.sex,
        names=[],
        profile_media_id=person.profile_media_id,
        notes=person.notes,
        title=person.title,
        occupation=person.occupation,
    )


@st.composite
def _person_invalid_sex(draw: DrawFn) -> Person:
    """Generate a Person with invalid sex value."""
    person = draw(person_strategy())
    invalid_sex = draw(st.text(min_size=1, max_size=5).filter(
        lambda s: s not in {"M", "F", "X", "U"}
    ))
    return Person(
        id=person.id,
        sex=invalid_sex,
        names=person.names,
        profile_media_id=person.profile_media_id,
        notes=person.notes,
        title=person.title,
        occupation=person.occupation,
    )


@st.composite
def _person_long_given_name(draw: DrawFn) -> Person:
    """Generate a Person with a given name exceeding 100 characters."""
    person = draw(person_strategy())
    long_given = draw(st.text(
        alphabet=st.characters(categories=("L",)),
        min_size=101,
        max_size=150,
    ))
    name = Name(type="birth", given=long_given, surname="Test")
    return Person(
        id=person.id,
        sex=person.sex,
        names=[name],
        profile_media_id=person.profile_media_id,
        notes=person.notes,
        title=person.title,
        occupation=person.occupation,
    )


@st.composite
def _person_long_title(draw: DrawFn) -> Person:
    """Generate a Person with a title exceeding 100 characters."""
    person = draw(person_strategy())
    long_title = draw(st.text(
        alphabet=st.characters(categories=("L",)),
        min_size=101,
        max_size=150,
    ))
    return Person(
        id=person.id,
        sex=person.sex,
        names=person.names,
        profile_media_id=person.profile_media_id,
        notes=person.notes,
        title=long_title,
        occupation=person.occupation,
    )


@st.composite
def _family_duplicate_children(draw: DrawFn) -> Family:
    """Generate a Family with duplicate children IDs."""
    family = draw(family_strategy())
    child_id = "person_999"
    return Family(
        id=family.id,
        partners=family.partners,
        children=[child_id, child_id],
        parent_child_links=[],
        event_ids=family.event_ids,
    )


@st.composite
def _family_invalid_partner_role(draw: DrawFn) -> Family:
    """Generate a Family with an invalid partner role."""
    invalid_role = draw(st.text(min_size=1, max_size=20).filter(
        lambda r: r not in {"father", "mother", "husband", "wife", "partner"}
    ))
    partner = FamilyPartner(person_id="person_1", role=invalid_role)
    return Family(
        id="family_1",
        partners=[partner],
        children=[],
        parent_child_links=[],
        event_ids=[],
    )


@st.composite
def _family_invalid_parentage_type(draw: DrawFn) -> Family:
    """Generate a Family with a parent-child link with invalid parentage_type."""
    valid_parentage_types = {"biological", "legal", "adoptive", "foster", "step", "unknown_donor"}
    invalid_type = draw(st.text(min_size=1, max_size=20).filter(
        lambda t: t not in valid_parentage_types
    ))
    partner = FamilyPartner(person_id="person_1", role="father")
    link = ParentChildLink(child_id="person_2", parent_id="person_1", parentage_type=invalid_type)
    return Family(
        id="family_1",
        partners=[partner],
        children=["person_2"],
        parent_child_links=[link],
        event_ids=[],
    )


@st.composite
def _family_null_parent_non_unknown_donor(draw: DrawFn) -> Family:
    """Generate a Family where parent_id is None but parentage_type is not unknown_donor."""
    non_donor_type = draw(st.sampled_from(["biological", "legal", "adoptive", "foster", "step"]))
    partner = FamilyPartner(person_id="person_1", role="father")
    link = ParentChildLink(child_id="person_2", parent_id=None, parentage_type=non_donor_type)
    return Family(
        id="family_1",
        partners=[partner],
        children=["person_2"],
        parent_child_links=[link],
        event_ids=[],
    )


@st.composite
def _event_no_participants(draw: DrawFn) -> Event:
    """Generate an Event with empty participants list."""
    event = draw(event_strategy())
    return Event(
        id=event.id,
        type=event.type,
        participants=[],
        date=event.date,
        place=event.place,
        media_ids=event.media_ids,
        custom_type_name=event.custom_type_name,
        cause_of_death=event.cause_of_death,
    )


@st.composite
def _event_empty_type(draw: DrawFn) -> Event:
    """Generate an Event with empty type."""
    event = draw(event_strategy())
    return Event(
        id=event.id,
        type="",
        participants=event.participants,
        date=event.date,
        place=event.place,
        media_ids=event.media_ids,
        custom_type_name=event.custom_type_name,
        cause_of_death=event.cause_of_death,
    )


@st.composite
def _event_invalid_date(draw: DrawFn) -> Event:
    """Generate an Event with an invalid ISO 8601 date value."""
    invalid_date_value = draw(st.sampled_from([
        "not-a-date", "2024/01/15", "15-01-2024", "2024-13-01", "2024-00-15",
    ]))
    date = DateValue(value=invalid_date_value, precision="day", source_refs=[])
    participant = Participant(person_id="person_1", role="principal")
    return Event(
        id="event_1",
        type="birth",
        participants=[participant],
        date=date,
        place=None,
        media_ids=[],
        custom_type_name=None,
        cause_of_death=None,
    )


@st.composite
def _event_invalid_precision(draw: DrawFn) -> Event:
    """Generate an Event with invalid date precision."""
    valid_precisions = {"day", "month", "year", "approximate"}
    invalid_precision = draw(st.text(min_size=1, max_size=20).filter(
        lambda p: p not in valid_precisions
    ))
    date = DateValue(value="2024-01-15", precision=invalid_precision, source_refs=[])
    participant = Participant(person_id="person_1", role="principal")
    return Event(
        id="event_1",
        type="birth",
        participants=[participant],
        date=date,
        place=None,
        media_ids=[],
        custom_type_name=None,
        cause_of_death=None,
    )


@st.composite
def _place_invalid_type(draw: DrawFn) -> Place:
    """Generate a Place with an invalid type."""
    valid_types = {"country", "county", "parish", "church", "cemetery"}
    invalid_type = draw(st.text(min_size=1, max_size=20).filter(
        lambda t: t not in valid_types
    ))
    return Place(
        id="place_1",
        type=invalid_type,
        name="Test Place",
        parent_place_id=None,
        latitude=None,
        longitude=None,
        notes="",
    )


@st.composite
def _place_invalid_latitude(draw: DrawFn) -> Place:
    """Generate a Place with latitude out of range."""
    bad_lat = draw(st.one_of(
        st.floats(min_value=90.01, max_value=1000.0, allow_nan=False),
        st.floats(min_value=-1000.0, max_value=-90.01, allow_nan=False),
    ))
    return Place(
        id="place_1",
        type="country",
        name="Test Country",
        parent_place_id=None,
        latitude=bad_lat,
        longitude=None,
        notes="",
    )


@st.composite
def _place_invalid_longitude(draw: DrawFn) -> Place:
    """Generate a Place with longitude out of range."""
    bad_lon = draw(st.one_of(
        st.floats(min_value=180.01, max_value=1000.0, allow_nan=False),
        st.floats(min_value=-1000.0, max_value=-180.01, allow_nan=False),
    ))
    return Place(
        id="place_1",
        type="country",
        name="Test Country",
        parent_place_id=None,
        latitude=None,
        longitude=bad_lon,
        notes="",
    )


@st.composite
def _place_empty_name(draw: DrawFn) -> Place:
    """Generate a Place with an empty name."""
    return Place(
        id="place_1",
        type="country",
        name="",
        parent_place_id=None,
        latitude=None,
        longitude=None,
        notes="",
    )


@st.composite
def _source_invalid_type(draw: DrawFn) -> Source:
    """Generate a Source with an invalid source_type."""
    valid_types = {"church_book", "database", "death_notice", "newspaper", "photograph", "census", "other"}
    invalid_type = draw(st.text(min_size=1, max_size=20).filter(
        lambda t: t not in valid_types
    ))
    return Source(
        id="source_1",
        provider="Test",
        source_type=invalid_type,
        title="Test Source",
        structured_reference=StructuredReference(fields={}),
    )


@st.composite
def _repository_empty_type(draw: DrawFn) -> Repository:
    """Generate a Repository with empty type."""
    empty_type = draw(st.sampled_from(["", "   ", "\t"]))
    return Repository(
        id="repo_1",
        name="Test Repository",
        type=empty_type,
    )


@st.composite
def _media_item_invalid_type(draw: DrawFn) -> MediaItem:
    """Generate a MediaItem with an invalid type."""
    valid_types = {
        "photo", "source_image", "death_notice", "obituary", "funeral_program",
        "grave_photo", "map", "logo", "document",
    }
    invalid_type = draw(st.text(min_size=1, max_size=20).filter(
        lambda t: t not in valid_types
    ))
    return MediaItem(
        id="media_1",
        type=invalid_type,
        file="photos/test.jpg",
        title="Test",
    )


@st.composite
def _media_item_backslash_path(draw: DrawFn) -> MediaItem:
    """Generate a MediaItem with backslashes in the file path."""
    return MediaItem(
        id="media_1",
        type="photo",
        file="photos\\subfolder\\test.jpg",
        title="Test",
    )


@st.composite
def _media_item_absolute_path(draw: DrawFn) -> MediaItem:
    """Generate a MediaItem with an absolute file path."""
    abs_path = draw(st.sampled_from([
        "/absolute/path/file.jpg",
        "C:\\Users\\test\\file.jpg",
        "D:/photos/file.png",
    ]))
    return MediaItem(
        id="media_1",
        type="photo",
        file=abs_path,
        title="Test",
    )


@st.composite
def _dna_profile_invalid_test_type(draw: DrawFn) -> DnaProfile:
    """Generate a DnaProfile with an invalid test_type."""
    valid_types = {"autosomal", "y-dna", "mtdna"}
    invalid_type = draw(st.text(min_size=1, max_size=20).filter(
        lambda t: t not in valid_types
    ))
    return DnaProfile(
        id="dnaprofile_1",
        person_id="person_1",
        company_id="dnacompany_1",
        test_type=invalid_type,
    )


@st.composite
def _dna_match_shared_cm_out_of_range(draw: DrawFn) -> DnaMatch:
    """Generate a DnaMatch with shared_cm outside 0-7400."""
    bad_cm = draw(st.one_of(
        st.floats(min_value=7400.01, max_value=20000.0, allow_nan=False),
        st.floats(min_value=-1000.0, max_value=-0.01, allow_nan=False),
    ))
    return DnaMatch(
        id="dnamatch_1",
        profile1_id="dnaprofile_1",
        profile2_id="dnaprofile_2",
        shared_cm=bad_cm,
        shared_percentage=50.0,
        segment_count=10,
        largest_segment_cm=50.0,
    )


@st.composite
def _dna_match_shared_percentage_out_of_range(draw: DrawFn) -> DnaMatch:
    """Generate a DnaMatch with shared_percentage outside 0-100."""
    bad_pct = draw(st.one_of(
        st.floats(min_value=100.01, max_value=500.0, allow_nan=False),
        st.floats(min_value=-100.0, max_value=-0.01, allow_nan=False),
    ))
    return DnaMatch(
        id="dnamatch_1",
        profile1_id="dnaprofile_1",
        profile2_id="dnaprofile_2",
        shared_cm=100.0,
        shared_percentage=bad_pct,
        segment_count=10,
        largest_segment_cm=50.0,
    )


@st.composite
def _dna_segment_start_gte_end(draw: DrawFn) -> DnaSegment:
    """Generate a DnaSegment where start_position >= end_position."""
    end_pos = draw(st.integers(min_value=1, max_value=250_000_000))
    start_pos = draw(st.integers(min_value=end_pos, max_value=250_000_001))
    return DnaSegment(
        id="dnasegment_1",
        match_id="dnamatch_1",
        chromosome="1",
        start_position=start_pos,
        end_position=end_pos,
        cm=5.0,
        snp_count=100,
    )


@st.composite
def _dna_segment_invalid_chromosome(draw: DrawFn) -> DnaSegment:
    """Generate a DnaSegment with an invalid chromosome."""
    valid_chroms = {str(i) for i in range(1, 23)} | {"X", "Y"}
    invalid_chrom = draw(st.text(min_size=1, max_size=5).filter(
        lambda c: c not in valid_chroms
    ))
    return DnaSegment(
        id="dnasegment_1",
        match_id="dnamatch_1",
        chromosome=invalid_chrom,
        start_position=100,
        end_position=200,
        cm=5.0,
        snp_count=100,
    )


@st.composite
def _dna_segment_cm_zero_or_negative(draw: DrawFn) -> DnaSegment:
    """Generate a DnaSegment with cm <= 0."""
    bad_cm = draw(st.floats(min_value=-100.0, max_value=0.0, allow_nan=False))
    return DnaSegment(
        id="dnasegment_1",
        match_id="dnamatch_1",
        chromosome="1",
        start_position=100,
        end_position=200,
        cm=bad_cm,
        snp_count=100,
    )


@st.composite
def _dna_cluster_invalid_name(draw: DrawFn) -> DnaCluster:
    """Generate a DnaCluster with empty name or name > 200 chars."""
    bad_name = draw(st.one_of(
        st.just(""),
        st.text(
            alphabet=st.characters(categories=("L",)),
            min_size=201,
            max_size=300,
        ),
    ))
    return DnaCluster(
        id="dnacluster_1",
        name=bad_name,
    )


@st.composite
def _dna_triangulation_too_few_profiles(draw: DrawFn) -> DnaTriangulation:
    """Generate a DnaTriangulation with fewer than 3 profile_ids."""
    profile_count = draw(st.integers(min_value=0, max_value=2))
    profile_ids = [f"dnaprofile_{i}" for i in range(profile_count)]
    return DnaTriangulation(
        id="dnatri_1",
        company_id="dnacompany_1",
        profile_ids=profile_ids,
        shared_cm=45.5,
        segment_count=3,
        largest_segment_cm=22.1,
    )


class TestProperty6InvalidDataRejected:
    """Property 6: invalid entities are rejected with specific errors."""

    # --- Person validation ---

    @given(person=_person_no_names())
    @settings(max_examples=50)
    def test_person_no_names_rejected(self, person: Person) -> None:
        """**Validates: Requirements 7.5, 7.6**"""
        errors = validate_person(person)
        assert len(errors) > 0
        assert any("minst ett namnfält" in e for e in errors)

    @given(person=_person_invalid_sex())
    @settings(max_examples=50)
    def test_person_invalid_sex_rejected(self, person: Person) -> None:
        """**Validates: Requirements 7.5, 7.6**"""
        errors = validate_person(person)
        assert len(errors) > 0
        assert any("Ogiltigt kön" in e for e in errors)

    @given(person=_person_long_given_name())
    @settings(max_examples=50)
    def test_person_long_given_name_rejected(self, person: Person) -> None:
        """**Validates: Requirements 7.5, 7.6**"""
        errors = validate_person(person)
        assert len(errors) > 0
        assert any("förnamn överskrider 100" in e for e in errors)

    @given(person=_person_long_title())
    @settings(max_examples=50)
    def test_person_long_title_rejected(self, person: Person) -> None:
        """**Validates: Requirements 7.5, 7.6**"""
        errors = validate_person(person)
        assert len(errors) > 0
        assert any("Titel överskrider 100" in e for e in errors)

    # --- Family validation ---

    @given(family=_family_duplicate_children())
    @settings(max_examples=50)
    def test_family_duplicate_children_rejected(self, family: Family) -> None:
        """**Validates: Requirements 8.5, 8.6**"""
        errors = validate_family(family)
        assert len(errors) > 0
        assert any("dubbletter" in e for e in errors)

    @given(family=_family_invalid_partner_role())
    @settings(max_examples=50)
    def test_family_invalid_partner_role_rejected(self, family: Family) -> None:
        """**Validates: Requirements 8.5, 8.6**"""
        errors = validate_family(family)
        assert len(errors) > 0
        assert any("ogiltig roll" in e for e in errors)

    @given(family=_family_invalid_parentage_type())
    @settings(max_examples=50)
    def test_family_invalid_parentage_type_rejected(self, family: Family) -> None:
        """**Validates: Requirements 8.5, 8.6**"""
        errors = validate_family(family)
        assert len(errors) > 0
        assert any("ogiltig föräldratyp" in e for e in errors)

    @given(family=_family_null_parent_non_unknown_donor())
    @settings(max_examples=50)
    def test_family_null_parent_non_unknown_donor_rejected(self, family: Family) -> None:
        """**Validates: Requirements 8.5, 8.6**"""
        errors = validate_family(family)
        assert len(errors) > 0
        assert any("parent_id är None" in e for e in errors)

    # --- Event validation ---

    @given(event=_event_no_participants())
    @settings(max_examples=50)
    def test_event_no_participants_rejected(self, event: Event) -> None:
        """**Validates: Requirements 9.4**"""
        errors = validate_event(event)
        assert len(errors) > 0
        assert any("minst en deltagare" in e for e in errors)

    @given(event=_event_empty_type())
    @settings(max_examples=50)
    def test_event_empty_type_rejected(self, event: Event) -> None:
        """**Validates: Requirements 9.4**"""
        errors = validate_event(event)
        assert len(errors) > 0
        assert any("icke-tom sträng" in e for e in errors)

    @given(event=_event_invalid_date())
    @settings(max_examples=50)
    def test_event_invalid_date_rejected(self, event: Event) -> None:
        """**Validates: Requirements 9.4**"""
        errors = validate_event(event)
        assert len(errors) > 0
        assert any("giltigt ISO 8601" in e for e in errors)

    @given(event=_event_invalid_precision())
    @settings(max_examples=50)
    def test_event_invalid_precision_rejected(self, event: Event) -> None:
        """**Validates: Requirements 9.4**"""
        errors = validate_event(event)
        assert len(errors) > 0
        assert any("precision" in e.lower() for e in errors)

    # --- Place validation ---

    @given(place=_place_invalid_type())
    @settings(max_examples=50)
    def test_place_invalid_type_rejected(self, place: Place) -> None:
        """**Validates: Requirements 13.4**"""
        errors = validate_place(place)
        assert len(errors) > 0
        assert any("Ogiltig platstyp" in e for e in errors)

    @given(place=_place_invalid_latitude())
    @settings(max_examples=50)
    def test_place_invalid_latitude_rejected(self, place: Place) -> None:
        """**Validates: Requirements 13.4**"""
        errors = validate_place(place)
        assert len(errors) > 0
        assert any("Latitud" in e for e in errors)

    @given(place=_place_invalid_longitude())
    @settings(max_examples=50)
    def test_place_invalid_longitude_rejected(self, place: Place) -> None:
        """**Validates: Requirements 13.4**"""
        errors = validate_place(place)
        assert len(errors) > 0
        assert any("Longitud" in e for e in errors)

    @given(place=_place_empty_name())
    @settings(max_examples=50)
    def test_place_empty_name_rejected(self, place: Place) -> None:
        """**Validates: Requirements 13.4**"""
        errors = validate_place(place)
        assert len(errors) > 0
        assert any("1–200 tecken" in e for e in errors)

    # --- Source, Repository, MediaItem validation ---

    @given(source=_source_invalid_type())
    @settings(max_examples=50)
    def test_source_invalid_type_rejected(self, source: Source) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_source(source)
        assert len(errors) > 0
        assert any("Ogiltig källtyp" in e for e in errors)

    @given(repository=_repository_empty_type())
    @settings(max_examples=50)
    def test_repository_empty_type_rejected(self, repository: Repository) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_repository(repository)
        assert len(errors) > 0
        assert any("icke-tom sträng" in e for e in errors)

    @given(media_item=_media_item_invalid_type())
    @settings(max_examples=50)
    def test_media_item_invalid_type_rejected(self, media_item: MediaItem) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_media_item(media_item)
        assert len(errors) > 0
        assert any("Ogiltig mediatyp" in e for e in errors)

    @given(media_item=_media_item_backslash_path())
    @settings(max_examples=50)
    def test_media_item_backslash_path_rejected(self, media_item: MediaItem) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_media_item(media_item)
        assert len(errors) > 0
        assert any("snedstreck" in e for e in errors)

    @given(media_item=_media_item_absolute_path())
    @settings(max_examples=50)
    def test_media_item_absolute_path_rejected(self, media_item: MediaItem) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_media_item(media_item)
        assert len(errors) > 0
        assert any("relativ" in e.lower() for e in errors)

    # --- DNA entity validation ---

    @given(profile=_dna_profile_invalid_test_type())
    @settings(max_examples=50)
    def test_dna_profile_invalid_test_type_rejected(self, profile: DnaProfile) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_profile(profile)
        assert len(errors) > 0
        assert any("Ogiltig testtyp" in e for e in errors)

    @given(match=_dna_match_shared_cm_out_of_range())
    @settings(max_examples=50)
    def test_dna_match_shared_cm_out_of_range_rejected(self, match: DnaMatch) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_match(match)
        assert len(errors) > 0
        assert any("shared_cm" in e for e in errors)

    @given(match=_dna_match_shared_percentage_out_of_range())
    @settings(max_examples=50)
    def test_dna_match_shared_percentage_out_of_range_rejected(self, match: DnaMatch) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_match(match)
        assert len(errors) > 0
        assert any("shared_percentage" in e for e in errors)

    @given(segment=_dna_segment_start_gte_end())
    @settings(max_examples=50)
    def test_dna_segment_start_gte_end_rejected(self, segment: DnaSegment) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_segment(segment)
        assert len(errors) > 0
        assert any("start_position" in e for e in errors)

    @given(segment=_dna_segment_invalid_chromosome())
    @settings(max_examples=50)
    def test_dna_segment_invalid_chromosome_rejected(self, segment: DnaSegment) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_segment(segment)
        assert len(errors) > 0
        assert any("Ogiltig kromosom" in e for e in errors)

    @given(segment=_dna_segment_cm_zero_or_negative())
    @settings(max_examples=50)
    def test_dna_segment_cm_zero_or_negative_rejected(self, segment: DnaSegment) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_segment(segment)
        assert len(errors) > 0
        assert any("cm måste vara större än 0" in e for e in errors)

    @given(cluster=_dna_cluster_invalid_name())
    @settings(max_examples=50)
    def test_dna_cluster_invalid_name_rejected(self, cluster: DnaCluster) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_cluster(cluster)
        assert len(errors) > 0
        assert any("1–200 tecken" in e for e in errors)

    @given(triangulation=_dna_triangulation_too_few_profiles())
    @settings(max_examples=50)
    def test_dna_triangulation_too_few_profiles_rejected(
        self, triangulation: DnaTriangulation
    ) -> None:
        """**Validates: Requirements 14.1**"""
        errors = validate_dna_triangulation(triangulation)
        assert len(errors) > 0
        assert any("minst 3 profile_ids" in e for e in errors)
