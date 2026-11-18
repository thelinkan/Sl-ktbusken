"""Strategies and helpers for the event assembler properties.

Small alphabets for source ids, notes and aspects make identical references
common, so deduplication of moved references is exercised. ``form_from_event``
builds the form state the Event_Editor shows for a loaded event.
"""

from __future__ import annotations

import copy

from hypothesis import strategies as st

from slaktbusken.model.date_semantics import effective_qualifier
from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.event_citations import CitationContext, event_citations
from slaktbusken.model.project import ProjectData
from slaktbusken.model.record_origin import RecordOrigin
from slaktbusken.model.source import Source
from slaktbusken.ui.editors.event_assembler import (
    CitationRow,
    DateFormState,
    EventFormState,
)

PLACE_IDS = ["place_1", "place_2", "place_3", "place_4"]
SOURCE_IDS = ["src_1", "src_2", "src_3"]
EVENT_TYPES = ["birth", "death", "marriage", "flytt", "baptism", "custom"]


def make_project(n_places: int = 4) -> ProjectData:
    """A project holding the sources and places the strategies refer to."""
    from slaktbusken.model.place import Place

    data = ProjectData()
    data.sources = [
        Source(id=sid, provider="", source_type="other", title=f"Källa {sid}")
        for sid in SOURCE_IDS
    ]
    data.places = [
        Place(id=pid, type="parish", name=f"Plats {pid}") for pid in PLACE_IDS[:n_places]
    ]
    return data


source_ref_st = st.builds(
    SourceRef,
    source_id=st.sampled_from(SOURCE_IDS),
    quality=st.sampled_from(["primary", "secondary", "tertiary"]),
    note=st.sampled_from(["", "s. 1", "s. 2"]),
    aspects=st.lists(st.sampled_from(["a", "b"]), max_size=2),
)
source_refs_st = st.lists(source_ref_st, max_size=4)

_iso_year = st.integers(1500, 1999).map(lambda y: f"{y:04d}")
_iso_month = st.tuples(st.integers(1500, 1999), st.integers(1, 12)).map(
    lambda t: f"{t[0]:04d}-{t[1]:02d}"
)
_iso_day = st.tuples(
    st.integers(1500, 1999), st.integers(1, 12), st.integers(1, 28)
).map(lambda t: f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}")
iso_st = st.one_of(_iso_year, _iso_month, _iso_day)

original_text_st = st.one_of(
    st.none(), st.text(alphabet="abc 12-", min_size=1, max_size=12).filter(str.strip)
)


@st.composite
def date_value_st(draw, with_original_text: bool = False) -> DateValue:
    qualifier = draw(
        st.sampled_from(
            ["exact", "about", "before", "after", "between", "from_to", "unparsed", "interpreted"]
        )
    )
    calendar = draw(st.sampled_from(["gregorian", "julian"]))
    refs = draw(source_refs_st)
    original = draw(original_text_st)
    if with_original_text or qualifier in ("unparsed", "interpreted"):
        original = draw(st.text(alphabet="abc 12-", min_size=1, max_size=12).filter(str.strip))
    if qualifier == "unparsed":
        return DateValue(
            value="",
            precision="approximate",
            source_refs=refs,
            qualifier="unparsed",
            calendar=calendar,
            original_text=original,
        )
    value = draw(iso_st)
    value_to = draw(iso_st) if qualifier in ("between", "from_to") else None
    precision = "approximate" if qualifier != "exact" else (
        "year" if len(value) == 4 else "month" if len(value) == 7 else "day"
    )
    return DateValue(
        value=value,
        precision=precision,
        source_refs=refs,
        qualifier=qualifier,
        value_to=value_to,
        calendar=calendar,
        original_text=original,
    )


place_ref_st = st.builds(
    PlaceRef, place_id=st.sampled_from(PLACE_IDS), source_refs=source_refs_st
)

origin_st = st.builds(
    RecordOrigin,
    owner_kind=st.sampled_from(["INDI", "FAM"]),
    owner_id=st.sampled_from(["person_1", "family_1"]),
    owner_xref=st.just("@I1@"),
    tag_key=st.sampled_from(["BIRT", "EVEN:flytt"]),
    index=st.integers(0, 3),
    record_hash=st.text(alphabet="0123456789abcdef", min_size=8, max_size=8),
    uid=st.one_of(st.none(), st.just("uid-1")),
    instance=st.integers(0, 2),
)

participants_st = st.lists(
    st.builds(
        Participant,
        person_id=st.sampled_from(["person_1", "person_2"]),
        role=st.sampled_from(["huvudperson", "make"]),
    ),
    min_size=1,
    max_size=2,
)


@st.composite
def event_st(draw, with_original_text: bool = False, require_date: bool = False) -> Event:
    date = draw(st.one_of(st.none(), date_value_st(with_original_text)))
    if require_date and date is None:
        date = draw(date_value_st(with_original_text))
    return Event(
        id="event_1",
        type=draw(st.sampled_from(EVENT_TYPES)),
        participants=draw(participants_st),
        date=date,
        place=draw(st.one_of(st.none(), place_ref_st)),
        media_ids=draw(st.lists(st.sampled_from(["media_1", "media_2"]), max_size=2, unique=True)),
        custom_type_name=draw(st.one_of(st.none(), st.just("Eget"))),
        cause_of_death=draw(st.one_of(st.none(), st.just("Sjukdom"))),
        from_place=draw(st.one_of(st.none(), place_ref_st)),
        source_refs=draw(source_refs_st),
        origin=draw(st.one_of(st.none(), origin_st)),
    )


def form_from_event(event: Event) -> EventFormState:
    """The form state the editor shows right after loading ``event``."""
    return EventFormState(
        type=event.type,
        custom_type_name=event.custom_type_name,
        cause_of_death=event.cause_of_death,
        date=DateFormState.from_date(event.date),
        place_id=event.place.place_id if event.place else None,
        from_place_id=event.from_place.place_id if event.from_place else None,
        citation_rows=[
            CitationRow(context=c.context, ref=copy.deepcopy(c.ref))
            for c in event_citations(event)
        ],
        participants=copy.deepcopy(event.participants),
        media_ids=list(event.media_ids),
    )


def ref_key(ref: SourceRef) -> tuple:
    return (ref.source_id, ref.quality, ref.note, tuple(ref.aspects))


def distinct_ref_keys(event: Event) -> set[tuple]:
    return {ref_key(c.ref) for c in event_citations(event)}


def refs_in_context(event: Event, context: CitationContext) -> list[SourceRef]:
    return [c.ref for c in event_citations(event) if c.context == context]


def event_with_all_contexts(
    *,
    date_value: str = "1850-03-04",
    place_id: str = "place_1",
    from_place_id: str | None = "place_2",
    type: str = "flytt",
) -> Event:
    """A concrete event with one distinct citation in each context."""
    return Event(
        id="event_1",
        type=type,
        participants=[Participant(person_id="person_1", role="huvudperson")],
        date=DateValue(
            value=date_value,
            precision="day",
            source_refs=[SourceRef("src_1", "primary", "datum")],
        ),
        place=PlaceRef(place_id, [SourceRef("src_2", "secondary", "plats")])
        if place_id
        else None,
        from_place=PlaceRef(from_place_id, [SourceRef("src_3", "tertiary", "från")])
        if from_place_id
        else None,
        source_refs=[SourceRef("src_1", "primary", "händelse")],
    )


def unparsed_event(original_text: str = "ca vid midsommar 1850") -> Event:
    """An event whose date was not understood at import."""
    return Event(
        id="event_1",
        type="birth",
        participants=[Participant(person_id="person_1", role="huvudperson")],
        date=DateValue(
            value="",
            precision="approximate",
            qualifier="unparsed",
            original_text=original_text,
            source_refs=[SourceRef("src_1", "primary", "datum")],
        ),
    )


def is_unparsed(event: Event) -> bool:
    return event.date is not None and effective_qualifier(event.date) == "unparsed"
