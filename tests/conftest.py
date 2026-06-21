"""Shared test fixtures and Hypothesis strategies for Släktbusken tests.

This module provides Hypothesis strategies for generating valid instances
of all domain dataclasses (Person, Family, Event, Place, Source, MediaItem,
Repository, DNA entities, ResearchNote, ProjectData) to be used across
property-based tests.
"""

from __future__ import annotations

from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.dna import (
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.media import Annotation, LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.model.source import Repository, RepositoryRef, Source, StructuredReference


# ---------------------------------------------------------------------------
# Shared helper strategies
# ---------------------------------------------------------------------------

# Safe text without null bytes
_safe_text = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=50,
)

_safe_text_or_empty = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=0,
    max_size=50,
)

_short_text = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=100,
)


def _id_strategy(prefix: str) -> st.SearchStrategy[str]:
    """Generate IDs with the given prefix, e.g. 'person_1', 'family_42'."""
    return st.integers(min_value=1, max_value=9999).map(lambda n: f"{prefix}_{n}")


# ---------------------------------------------------------------------------
# 3.1 – Person strategies
# ---------------------------------------------------------------------------

_NAME_TYPES = ["birth", "married", "adopted", "other"]
_SEX_VALUES = ["M", "F", "X", "U"]


@st.composite
def name_strategy(draw: DrawFn) -> Name:
    """Generate a valid Name instance."""
    name_type = draw(st.sampled_from(_NAME_TYPES))
    given = draw(st.text(
        alphabet=st.characters(categories=("L", "Z")),
        min_size=1,
        max_size=100,
    ))
    surname = draw(st.text(
        alphabet=st.characters(categories=("L", "Z")),
        min_size=1,
        max_size=100,
    ))
    event_id = draw(st.none() | _id_strategy("event"))
    return Name(type=name_type, given=given, surname=surname, event_id=event_id)


@st.composite
def person_strategy(draw: DrawFn) -> Person:
    """Generate a valid Person instance with at least one name."""
    person_id = draw(_id_strategy("person"))
    sex = draw(st.sampled_from(_SEX_VALUES))
    names = draw(st.lists(name_strategy(), min_size=1, max_size=3))
    profile_media_id = draw(st.none() | _id_strategy("media"))
    notes = draw(_safe_text_or_empty)
    title = draw(st.none() | _short_text)
    occupation = draw(st.none() | _short_text)
    return Person(
        id=person_id,
        sex=sex,
        names=names,
        profile_media_id=profile_media_id,
        notes=notes,
        title=title,
        occupation=occupation,
    )


# ---------------------------------------------------------------------------
# 3.2 – Family strategies
# ---------------------------------------------------------------------------

_PARTNER_ROLES = ["father", "mother", "husband", "wife", "partner"]
_PARENTAGE_TYPES = [
    "biological", "legal", "adoptive", "foster", "step", "unknown_donor",
]


@st.composite
def family_partner_strategy(draw: DrawFn) -> FamilyPartner:
    """Generate a valid FamilyPartner instance."""
    person_id = draw(_id_strategy("person"))
    role = draw(st.sampled_from(_PARTNER_ROLES))
    return FamilyPartner(person_id=person_id, role=role)


@st.composite
def parent_child_link_strategy(
    draw: DrawFn,
    child_ids: list[str] | None = None,
    partner_ids: list[str] | None = None,
) -> ParentChildLink:
    """Generate a valid ParentChildLink instance.

    If child_ids/partner_ids are provided, picks from those lists for
    referential consistency.
    """
    if child_ids:
        child_id = draw(st.sampled_from(child_ids))
    else:
        child_id = draw(_id_strategy("person"))

    parentage_type = draw(st.sampled_from(_PARENTAGE_TYPES))

    if parentage_type == "unknown_donor":
        # parent_id may be None for unknown_donor
        if partner_ids:
            parent_id = draw(st.none() | st.sampled_from(partner_ids))
        else:
            parent_id = draw(st.none() | _id_strategy("person"))
    else:
        # parent_id must not be None
        if partner_ids:
            parent_id = draw(st.sampled_from(partner_ids))
        else:
            parent_id = draw(_id_strategy("person"))

    return ParentChildLink(
        child_id=child_id,
        parent_id=parent_id,
        parentage_type=parentage_type,
    )


@st.composite
def family_strategy(draw: DrawFn) -> Family:
    """Generate a valid Family instance with consistent internal references."""
    family_id = draw(_id_strategy("family"))
    partners = draw(st.lists(family_partner_strategy(), min_size=1, max_size=3))
    children = draw(
        st.lists(_id_strategy("person"), min_size=0, max_size=3, unique=True)
    )
    event_ids = draw(st.lists(_id_strategy("event"), min_size=0, max_size=2))

    # Generate consistent parent-child links
    partner_ids = [p.person_id for p in partners]
    if children:
        links = draw(st.lists(
            parent_child_link_strategy(child_ids=children, partner_ids=partner_ids),
            min_size=0,
            max_size=len(children),
        ))
    else:
        links = []

    return Family(
        id=family_id,
        partners=partners,
        children=children,
        parent_child_links=links,
        event_ids=event_ids,
    )


# ---------------------------------------------------------------------------
# 3.3 – Event strategies
# ---------------------------------------------------------------------------

_SOURCE_QUALITY = ["primary", "secondary", "questionable"]
_DATE_PRECISIONS = ["day", "month", "year", "approximate"]

_INDIVIDUAL_EVENT_TYPES = [
    "adoption", "baptism", "birth", "blessing", "burial", "census",
    "confirmation", "cremation", "death", "emigration", "first_communion",
    "gender_correction", "graduation", "immigration", "name_change",
    "retirement", "will", "custom_individual_event",
]
_FAMILY_EVENT_TYPES = [
    "divorce", "divorce_filed", "engagement", "marriage", "custom_family_event",
]
_ALL_EVENT_TYPES = _INDIVIDUAL_EVENT_TYPES + _FAMILY_EVENT_TYPES
_CUSTOM_EVENT_TYPES = {"custom_individual_event", "custom_family_event"}


@st.composite
def source_ref_strategy(draw: DrawFn) -> SourceRef:
    """Generate a valid SourceRef instance."""
    source_id = draw(_id_strategy("source"))
    quality = draw(st.sampled_from(_SOURCE_QUALITY))
    note = draw(_safe_text_or_empty)
    return SourceRef(source_id=source_id, quality=quality, note=note)


@st.composite
def date_value_strategy(draw: DrawFn) -> DateValue:
    """Generate a valid DateValue with ISO 8601 date string."""
    precision = draw(st.sampled_from(_DATE_PRECISIONS))

    # Generate valid ISO 8601 date values
    year = draw(st.integers(min_value=1000, max_value=2100))
    month = draw(st.integers(min_value=1, max_value=12))
    day = draw(st.integers(min_value=1, max_value=28))  # 28 to avoid invalid dates

    if precision == "year" or draw(st.booleans()):
        # YYYY format
        value = f"{year:04d}"
    elif precision == "month" or draw(st.booleans()):
        # YYYY-MM format
        value = f"{year:04d}-{month:02d}"
    else:
        # YYYY-MM-DD format
        value = f"{year:04d}-{month:02d}-{day:02d}"

    source_refs = draw(st.lists(source_ref_strategy(), min_size=0, max_size=2))
    return DateValue(value=value, precision=precision, source_refs=source_refs)


@st.composite
def place_ref_strategy(draw: DrawFn) -> PlaceRef:
    """Generate a valid PlaceRef instance."""
    place_id = draw(_id_strategy("place"))
    source_refs = draw(st.lists(source_ref_strategy(), min_size=0, max_size=2))
    return PlaceRef(place_id=place_id, source_refs=source_refs)


@st.composite
def participant_strategy(draw: DrawFn) -> Participant:
    """Generate a valid Participant instance."""
    person_id = draw(_id_strategy("person"))
    role = draw(_safe_text)
    return Participant(person_id=person_id, role=role)


@st.composite
def event_strategy(draw: DrawFn) -> Event:
    """Generate a valid Event instance."""
    event_id = draw(_id_strategy("event"))
    event_type = draw(st.sampled_from(_ALL_EVENT_TYPES))
    participants = draw(st.lists(participant_strategy(), min_size=1, max_size=3))
    date = draw(st.none() | date_value_strategy())
    place = draw(st.none() | place_ref_strategy())
    media_ids = draw(st.lists(_id_strategy("media"), min_size=0, max_size=2))

    # custom_type_name required only for custom event types
    if event_type in _CUSTOM_EVENT_TYPES:
        custom_type_name = draw(st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=100,
        ))
    else:
        custom_type_name = None

    cause_of_death = draw(st.none() | _safe_text)

    return Event(
        id=event_id,
        type=event_type,
        participants=participants,
        date=date,
        place=place,
        media_ids=media_ids,
        custom_type_name=custom_type_name,
        cause_of_death=cause_of_death,
    )


# ---------------------------------------------------------------------------
# 3.4 – Place strategies
# ---------------------------------------------------------------------------

_PLACE_TYPES = ["country", "county", "parish", "church", "cemetery", "village", "farm", "school"]


@st.composite
def place_strategy(draw: DrawFn) -> Place:
    """Generate a valid Place instance (standalone, without hierarchy checks)."""
    place_id = draw(_id_strategy("place"))
    place_type = draw(st.sampled_from(_PLACE_TYPES))
    name = draw(st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=1,
        max_size=200,
    ))
    parent_place_id = draw(st.none() | _id_strategy("place"))
    latitude = draw(st.none() | st.floats(min_value=-90.0, max_value=90.0, allow_nan=False))
    longitude = draw(st.none() | st.floats(min_value=-180.0, max_value=180.0, allow_nan=False))
    notes = draw(_safe_text_or_empty)

    return Place(
        id=place_id,
        type=place_type,
        name=name,
        parent_place_id=parent_place_id,
        latitude=latitude,
        longitude=longitude,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 3.5 – Source, Repository strategies
# ---------------------------------------------------------------------------

_SOURCE_TYPES = [
    "church_book", "database", "death_notice", "newspaper",
    "photograph", "census", "other",
]
_REPOSITORY_TYPES = [
    "archive", "digital_archive", "library", "museum", "church", "other",
]


@st.composite
def structured_reference_strategy(draw: DrawFn) -> StructuredReference:
    """Generate a valid StructuredReference with string or int field values."""
    fields = draw(st.dictionaries(
        keys=st.text(
            alphabet=st.characters(categories=("L", "N")),
            min_size=1,
            max_size=20,
        ),
        values=st.one_of(
            st.none(),
            _safe_text,
            st.integers(min_value=0, max_value=9999),
        ),
        min_size=0,
        max_size=4,
    ))
    return StructuredReference(fields=fields)


@st.composite
def repository_ref_strategy(draw: DrawFn) -> RepositoryRef:
    """Generate a valid RepositoryRef instance."""
    repository_id = draw(_id_strategy("repo"))
    call_number = draw(_safe_text_or_empty)
    source_type = draw(_safe_text_or_empty)
    image_number = draw(st.none() | st.integers(min_value=1, max_value=9999))
    page_number = draw(st.none() | st.integers(min_value=1, max_value=9999))
    media_type = draw(_safe_text_or_empty)
    media_name = draw(_safe_text_or_empty)
    notes = draw(_safe_text_or_empty)
    return RepositoryRef(
        repository_id=repository_id,
        call_number=call_number,
        source_type=source_type,
        image_number=image_number,
        page_number=page_number,
        media_type=media_type,
        media_name=media_name,
        notes=notes,
    )


@st.composite
def source_strategy(draw: DrawFn) -> Source:
    """Generate a valid Source instance."""
    source_id = draw(_id_strategy("source"))
    provider = draw(_safe_text)
    source_type = draw(st.sampled_from(_SOURCE_TYPES))
    title = draw(_safe_text)
    reference_text = draw(_safe_text_or_empty)
    provider_ref = draw(_safe_text_or_empty)
    short_note = draw(_safe_text_or_empty)
    free_note = draw(_safe_text_or_empty)
    structured_reference = draw(structured_reference_strategy())
    media_ids = draw(st.lists(_id_strategy("media"), min_size=0, max_size=2))
    repository_refs = draw(st.lists(repository_ref_strategy(), min_size=0, max_size=2))
    return Source(
        id=source_id,
        provider=provider,
        source_type=source_type,
        title=title,
        reference_text=reference_text,
        provider_ref=provider_ref,
        short_note=short_note,
        free_note=free_note,
        structured_reference=structured_reference,
        media_ids=media_ids,
        repository_refs=repository_refs,
    )


@st.composite
def repository_strategy(draw: DrawFn) -> Repository:
    """Generate a valid Repository instance."""
    repo_id = draw(_id_strategy("repo"))
    name = draw(_safe_text)
    repo_type = draw(st.sampled_from(_REPOSITORY_TYPES))
    address = draw(st.none() | _safe_text)
    phone = draw(st.lists(_safe_text, min_size=0, max_size=2))
    email = draw(st.lists(_safe_text, min_size=0, max_size=2))
    web = draw(st.lists(_safe_text, min_size=0, max_size=2))
    notes = draw(_safe_text_or_empty)
    external_ids = draw(st.lists(_safe_text, min_size=0, max_size=2))
    return Repository(
        id=repo_id,
        name=name,
        type=repo_type,
        address=address,
        phone=phone,
        email=email,
        web=web,
        notes=notes,
        external_ids=external_ids,
    )


# ---------------------------------------------------------------------------
# 3.5 – Media strategies
# ---------------------------------------------------------------------------

_MEDIA_TYPES = [
    "photo", "source_image", "death_notice", "obituary", "funeral_program",
    "grave_photo", "map", "logo", "document",
]
_LINKED_ENTITY_TYPES = ["person", "event", "source", "place"]

# File path segments using only safe characters and forward slashes
_PATH_SEGMENT = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=1,
    max_size=15,
)


@st.composite
def _relative_file_path(draw: DrawFn) -> str:
    """Generate a relative file path with forward slashes only."""
    segments = draw(st.lists(_PATH_SEGMENT, min_size=1, max_size=3))
    extension = draw(st.sampled_from([".jpg", ".png", ".pdf", ".tiff"]))
    return "/".join(segments) + extension


@st.composite
def linked_entity_strategy(draw: DrawFn) -> LinkedEntity:
    """Generate a valid LinkedEntity instance."""
    entity_type = draw(st.sampled_from(_LINKED_ENTITY_TYPES))

    # Pick matching ID prefix
    prefix_map = {
        "person": "person",
        "event": "event",
        "source": "source",
        "place": "place",
    }
    entity_id = draw(_id_strategy(prefix_map[entity_type]))
    role = draw(_safe_text_or_empty)
    return LinkedEntity(entity_type=entity_type, entity_id=entity_id, role=role)


@st.composite
def annotation_strategy(draw: DrawFn) -> Annotation:
    """Generate a valid Annotation instance with normalized coordinates."""
    x = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    y = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    width = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    height = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    entity_type = draw(st.sampled_from(_LINKED_ENTITY_TYPES))
    prefix_map = {
        "person": "person",
        "event": "event",
        "source": "source",
        "place": "place",
    }
    entity_id = draw(_id_strategy(prefix_map[entity_type]))
    return Annotation(
        x=x,
        y=y,
        width=width,
        height=height,
        entity_type=entity_type,
        entity_id=entity_id,
    )


@st.composite
def media_item_strategy(draw: DrawFn) -> MediaItem:
    """Generate a valid MediaItem instance with relative forward-slash paths."""
    media_id = draw(_id_strategy("media"))
    media_type = draw(st.sampled_from(_MEDIA_TYPES))
    file = draw(_relative_file_path())
    title = draw(_safe_text)
    linked_entities = draw(st.lists(linked_entity_strategy(), min_size=0, max_size=3))
    publication = draw(st.none())  # Keep simple — dict generation is complex
    transcription = draw(st.none() | _safe_text)
    mentioned_person_ids = draw(st.lists(_id_strategy("person"), min_size=0, max_size=3))
    mentioned_names = draw(st.lists(_safe_text, min_size=0, max_size=3))
    annotations = draw(st.lists(annotation_strategy(), min_size=0, max_size=5))
    return MediaItem(
        id=media_id,
        type=media_type,
        file=file,
        title=title,
        linked_entities=linked_entities,
        publication=publication,
        transcription=transcription,
        mentioned_person_ids=mentioned_person_ids,
        mentioned_names=mentioned_names,
        annotations=annotations,
    )


# ---------------------------------------------------------------------------
# 3.6 – DNA strategies
# ---------------------------------------------------------------------------

_DNA_TEST_TYPES = ["autosomal", "y-dna", "mtdna"]
_DNA_MATCH_SOURCES = ["internal", "external"]
_CHROMOSOMES = [str(i) for i in range(1, 23)] + ["X", "Y"]


@st.composite
def dna_company_strategy(draw: DrawFn) -> DnaCompany:
    """Generate a valid DnaCompany instance."""
    company_id = draw(_id_strategy("dnacompany"))
    name = draw(st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=1,
        max_size=200,
    ))
    logo_media_id = draw(st.none() | _id_strategy("media"))
    description = draw(_safe_text_or_empty)
    return DnaCompany(
        id=company_id,
        name=name,
        logo_media_id=logo_media_id,
        description=description,
    )


@st.composite
def dna_profile_strategy(draw: DrawFn) -> DnaProfile:
    """Generate a valid DnaProfile instance."""
    profile_id = draw(_id_strategy("dnaprofile"))
    person_id = draw(_id_strategy("person"))
    company_id = draw(_id_strategy("dnacompany"))
    test_type = draw(st.sampled_from(_DNA_TEST_TYPES))
    kit_name = draw(st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=0,
        max_size=200,
    ))
    kit_id = draw(st.text(
        alphabet=st.characters(categories=("L", "N")),
        min_size=0,
        max_size=100,
    ))
    admin_person_id = draw(st.none() | _id_strategy("person"))
    admin_status = draw(_safe_text_or_empty)
    notes = draw(_safe_text_or_empty)
    return DnaProfile(
        id=profile_id,
        person_id=person_id,
        company_id=company_id,
        test_type=test_type,
        kit_name=kit_name,
        kit_id=kit_id,
        admin_person_id=admin_person_id,
        admin_status=admin_status,
        notes=notes,
    )


@st.composite
def dna_match_strategy(draw: DrawFn) -> DnaMatch:
    """Generate a valid DnaMatch instance with values in valid ranges."""
    match_id = draw(_id_strategy("dnamatch"))
    profile1_id = draw(_id_strategy("dnaprofile"))
    profile2_id = draw(_id_strategy("dnaprofile"))
    shared_cm = draw(st.floats(min_value=0.0, max_value=7400.0, allow_nan=False))
    shared_percentage = draw(st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
    segment_count = draw(st.integers(min_value=0, max_value=10000))
    largest_segment_cm = draw(st.floats(min_value=0.0, max_value=300.0, allow_nan=False))
    match_source = draw(st.sampled_from(_DNA_MATCH_SOURCES))
    notes = draw(_safe_text_or_empty)
    return DnaMatch(
        id=match_id,
        profile1_id=profile1_id,
        profile2_id=profile2_id,
        shared_cm=shared_cm,
        shared_percentage=shared_percentage,
        segment_count=segment_count,
        largest_segment_cm=largest_segment_cm,
        match_source=match_source,
        notes=notes,
    )


@st.composite
def dna_segment_strategy(draw: DrawFn) -> DnaSegment:
    """Generate a valid DnaSegment with start_position < end_position and cm > 0."""
    segment_id = draw(_id_strategy("dnasegment"))
    match_id = draw(_id_strategy("dnamatch"))
    chromosome = draw(st.sampled_from(_CHROMOSOMES))

    start_position = draw(st.integers(min_value=1, max_value=250_000_000))
    end_position = draw(st.integers(min_value=start_position + 1, max_value=250_000_001))

    cm = draw(st.floats(min_value=0.01, max_value=300.0, allow_nan=False))
    snp_count = draw(st.integers(min_value=0, max_value=100_000))

    return DnaSegment(
        id=segment_id,
        match_id=match_id,
        chromosome=chromosome,
        start_position=start_position,
        end_position=end_position,
        cm=cm,
        snp_count=snp_count,
    )


@st.composite
def dna_cluster_strategy(draw: DrawFn) -> DnaCluster:
    """Generate a valid DnaCluster with a name of 1-200 characters."""
    cluster_id = draw(_id_strategy("dnacluster"))
    name = draw(st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=1,
        max_size=200,
    ))
    notes = draw(_safe_text_or_empty)
    company_ids = draw(st.lists(_id_strategy("dnacompany"), min_size=0, max_size=3))
    person_ids = draw(st.lists(_id_strategy("person"), min_size=0, max_size=3))
    dna_match_ids = draw(st.lists(_id_strategy("dnamatch"), min_size=0, max_size=3))
    color = draw(st.none() | st.sampled_from(["#FF0000", "#00FF00", "#0000FF", "#FFFF00"]))
    return DnaCluster(
        id=cluster_id,
        name=name,
        notes=notes,
        company_ids=company_ids,
        person_ids=person_ids,
        dna_match_ids=dna_match_ids,
        color=color,
    )


@st.composite
def dna_triangulation_strategy(draw: DrawFn) -> DnaTriangulation:
    """Generate a valid DnaTriangulation (>=3 profiles)."""
    tri_id = draw(_id_strategy("dnatri"))
    company_id = draw(_id_strategy("dnacompany"))

    profile_ids = draw(st.lists(
        _id_strategy("dnaprofile"), min_size=3, max_size=5, unique=True,
    ))
    shared_cm = draw(st.floats(min_value=0.01, max_value=3500.0, allow_nan=False))
    segment_count = draw(st.integers(min_value=1, max_value=100))
    largest_segment_cm = draw(st.floats(min_value=0.01, max_value=300.0, allow_nan=False))
    cluster_id = draw(st.none() | _id_strategy("dnacluster"))
    notes = draw(_safe_text_or_empty)

    return DnaTriangulation(
        id=tri_id,
        company_id=company_id,
        profile_ids=profile_ids,
        shared_cm=shared_cm,
        segment_count=segment_count,
        largest_segment_cm=largest_segment_cm,
        cluster_id=cluster_id,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 3.7 – ResearchNote strategy
# ---------------------------------------------------------------------------


@st.composite
def research_note_strategy(draw: DrawFn) -> ResearchNote:
    """Generate a valid ResearchNote instance."""
    note_id = draw(_id_strategy("note"))
    title = draw(_safe_text)
    text = draw(_safe_text)
    linked_entities = draw(st.lists(linked_entity_strategy(), min_size=0, max_size=3))
    return ResearchNote(
        id=note_id,
        title=title,
        text=text,
        linked_entities=linked_entities,
    )


# ---------------------------------------------------------------------------
# 3.8 – ProjectMetadata and ProjectData strategies
# ---------------------------------------------------------------------------


@st.composite
def project_metadata_strategy(draw: DrawFn) -> ProjectMetadata:
    """Generate a valid ProjectMetadata instance."""
    title = draw(st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=1,
        max_size=200,
    ))
    main_person_id = draw(st.none() | _id_strategy("person"))
    created_by = draw(st.just("Släktbuske") | _safe_text)
    language = draw(st.sampled_from(["sv-SE", "en-US", "de-DE"]))
    return ProjectMetadata(
        title=title,
        main_person_id=main_person_id,
        created_by=created_by,
        language=language,
    )


@st.composite
def project_data_strategy(draw: DrawFn) -> ProjectData:
    """Generate a valid ProjectData instance with small lists of entities."""
    project = draw(project_metadata_strategy())
    persons = draw(st.lists(person_strategy(), min_size=0, max_size=3))
    families = draw(st.lists(family_strategy(), min_size=0, max_size=2))
    events = draw(st.lists(event_strategy(), min_size=0, max_size=3))
    places = draw(st.lists(place_strategy(), min_size=0, max_size=3))
    sources = draw(st.lists(source_strategy(), min_size=0, max_size=2))
    media = draw(st.lists(media_item_strategy(), min_size=0, max_size=2))
    repositories = draw(st.lists(repository_strategy(), min_size=0, max_size=2))
    dna_companies = draw(st.lists(dna_company_strategy(), min_size=0, max_size=2))
    dna_profiles = draw(st.lists(dna_profile_strategy(), min_size=0, max_size=2))
    dna_matches = draw(st.lists(dna_match_strategy(), min_size=0, max_size=2))
    dna_segments = draw(st.lists(dna_segment_strategy(), min_size=0, max_size=2))
    dna_clusters = draw(st.lists(dna_cluster_strategy(), min_size=0, max_size=2))
    dna_triangulations = draw(st.lists(dna_triangulation_strategy(), min_size=0, max_size=2))
    research_notes = draw(st.lists(research_note_strategy(), min_size=0, max_size=2))

    return ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=project,
        persons=persons,
        families=families,
        events=events,
        places=places,
        sources=sources,
        media=media,
        repositories=repositories,
        dna_companies=dna_companies,
        dna_profiles=dna_profiles,
        dna_matches=dna_matches,
        dna_segments=dna_segments,
        dna_clusters=dna_clusters,
        dna_triangulations=dna_triangulations,
        research_notes=research_notes,
    )
