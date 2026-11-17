"""Stable_View of a project: everything a GEDCOM round trip should keep, no ids.

``stable_view(data)`` turns ``ProjectData`` into a ``StableView``: for each
section (persons, families, events, residences, sources, repositories, totals)
a tuple of ``Item`` objects in a fixed order. The view contains no generated
id, so two projects that differ only in ids and in list order have equal views.

Keys
----
* ``person_key`` (design C12): the sorted tuple of ``(name type, given,
  surname)``, the sex and the birth date. It is the identity of a person item.
* ``person_ref``: the key *without* name types and sex. Events, families and
  residences refer to persons by this reference, so that a changed name type or
  sex shows up once (on the person) and does not spread to every event and
  family of that person. This is a deliberate narrowing of "person key" in the
  event key of the design.
* Event identity: type, custom type name, date, place chain and the sorted
  participant references. Participant *roles* are a field, not part of the
  identity, so a role change is one classified difference (K28) and not a
  missing and an extra event.

Every ``Item`` also has a ``loose`` key. The comparator uses it to pair items
whose identities differ, so that it can report *what* differs.

Items with equal identity get an ordinal (their position after sorting by
content), which makes ``(identity, ordinal)`` unique.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from slaktbusken.model.event import DateValue, Event, SourceRef
from slaktbusken.model.event_citations import event_citations
from slaktbusken.model.family import Family
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact

SECTIONS: tuple[str, ...] = (
    "persons",
    "families",
    "events",
    "residences",
    "sources",
    "repositories",
    "totals",
)


@dataclass(frozen=True)
class Item:
    """One comparable record of the view."""

    identity: tuple
    ordinal: int
    loose: tuple
    fields: dict[str, Any]

    @property
    def key(self) -> tuple:
        return (self.identity, self.ordinal)


@dataclass
class StableView:
    sections: dict[str, tuple[Item, ...]] = field(default_factory=dict)
    counts: dict[str, Any] = field(default_factory=dict)

    def items(self, section: str) -> tuple[Item, ...]:
        return self.sections.get(section, ())


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _s(value: Optional[str]) -> str:
    return "" if value is None else value


def _unset_if_blank(value: Optional[str]) -> str:
    """Residence role and notes as the importer reads them: a blank
    ``_SLK_HHROLE`` or ``_SLK_RNOTES`` counts as absent (``read_residence_texts``),
    so a whitespace-only text equals an empty one."""
    return value if value and value.strip() else ""


def _order(value: Any) -> str:
    """Total order for mixed tuples (None, str, int) without type errors."""
    return repr(value)


def _sorted(values: Iterable[Any]) -> tuple:
    return tuple(sorted(values, key=_order))


def date_tuple(date: Optional[DateValue]) -> tuple:
    if date is None:
        return ()
    return (
        _s(date.value),
        _s(date.value_to),
        _s(date.precision),
        _s(date.qualifier),
        _s(date.calendar),
    )


def place_chain(place_id: Optional[str], places_by_id: dict) -> tuple:
    """Place names from the root to the place itself; ``()`` for no place."""
    names: list[str] = []
    seen: set[str] = set()
    current = place_id
    while current is not None and current not in seen:
        seen.add(current)
        place = places_by_id.get(current)
        if place is None:
            names.append(f"?{current}")
            break
        names.append(place.name)
        current = place.parent_place_id
    return tuple(reversed(names))


def name_tuple(name: Name) -> tuple[str, str, str]:
    return (_s(name.type), _s(name.given), _s(name.surname))


def person_key(person: Person, birth_date: str = "") -> tuple:
    """Identity of a person: typed names (sorted), sex and birth date."""
    names = _sorted(name_tuple(n) for n in person.names)
    return (names, _s(person.sex), _s(birth_date))


def person_ref(person: Person, birth_date: str = "") -> tuple:
    """Reference to a person from other items: names without type, birth date."""
    names = _sorted((n.given or "", n.surname or "") for n in person.names)
    return (names, _s(birth_date))


def _with_ordinals(
    section: str, entries: list[tuple[tuple, tuple, dict[str, Any]]]
) -> tuple[Item, ...]:
    """Sort entries and number equal identities, giving a stable unique key."""
    ordered = sorted(entries, key=lambda e: (_order(e[0]), _order(e[2])))
    counters: dict[str, int] = {}
    items: list[Item] = []
    for identity, loose, fields in ordered:
        marker = _order(identity)
        ordinal = counters.get(marker, 0)
        counters[marker] = ordinal + 1
        items.append(Item(identity, ordinal, loose, fields))
    return tuple(items)


# --------------------------------------------------------------------------
# Section builders
# --------------------------------------------------------------------------


class _Context:
    def __init__(self, data: ProjectData) -> None:
        self.data = data
        self.places = {p.id: p for p in data.places}
        self.sources = {s.id: s for s in data.sources}
        self.repositories = {r.id: r for r in data.repositories}
        self.leverantorer = {x.id: x for x in data.leverantorer}
        self.kalltyper = {x.id: x for x in data.kalltyper}
        self.events = {e.id: e for e in data.events}
        self.persons = {p.id: p for p in data.persons}

        self.birth: dict[str, str] = {}
        for event in data.events:
            if event.type != "birth" or event.date is None:
                continue
            for participant in event.participants:
                self.birth.setdefault(participant.person_id, _s(event.date.value))

    def ref(self, person_id: str) -> tuple:
        person = self.persons.get(person_id)
        if person is None:
            return (f"?{person_id}",)
        return person_ref(person, self.birth.get(person_id, ""))

    def chain(self, place_ref) -> tuple:
        return place_chain(None if place_ref is None else place_ref.place_id, self.places)

    def source_title(self, source_id: str) -> str:
        source = self.sources.get(source_id)
        return f"?{source_id}" if source is None else source.title

    def event_identity(self, event: Event) -> tuple:
        participants = _sorted(self.ref(p.person_id) for p in event.participants)
        return (
            _s(event.type),
            _s(event.custom_type_name),
            date_tuple(event.date),
            self.chain(event.place),
            participants,
        )

    def event_loose(self, event: Event) -> tuple:
        return self.event_identity(event)[:4]

    def event_ref(self, event_id: Optional[str]) -> Optional[tuple]:
        event = self.events.get(event_id) if event_id else None
        return None if event is None else self.event_identity(event)

    def citation(self, context: str, ref: SourceRef) -> tuple:
        return (
            context,
            self.source_title(ref.source_id),
            _s(ref.quality),
            _s(ref.note),
            tuple(ref.aspects),
        )


def _persons(ctx: _Context) -> tuple[Item, ...]:
    entries = []
    for person in ctx.data.persons:
        birth = ctx.birth.get(person.id, "")
        links = []
        for name in person.names:
            ref = ctx.event_ref(name.event_id)
            if ref is not None:
                links.append((_s(name.given), _s(name.surname), ref))
        fields = {
            "names": _sorted(name_tuple(n) for n in person.names),
            "sex": _s(person.sex),
            "birth": birth,
            "notes": _s(person.notes),
            "title": _s(person.title),
            "occupation": _s(person.occupation),
            "name_event_links": _sorted(links),
            "has_profile_media": bool(person.profile_media_id),
        }
        entries.append((person_key(person, birth), person_ref(person, birth), fields))
    return _with_ordinals("persons", entries)


def _events(ctx: _Context) -> tuple[Item, ...]:
    entries = []
    for event in ctx.data.events:
        citations = _sorted(ctx.citation(c.context.value, c.ref) for c in event_citations(event))
        fields = {
            "participants": _sorted(
                (ctx.ref(p.person_id), _s(p.role)) for p in event.participants
            ),
            "from_place": ctx.chain(event.from_place),
            "citations": citations,
            "cause": _s(event.cause_of_death),
            "media_count": len(event.media_ids),
        }
        entries.append((ctx.event_identity(event), ctx.event_loose(event), fields))
    return _with_ordinals("events", entries)


def _families(ctx: _Context) -> tuple[Item, ...]:
    entries = []
    for family in ctx.data.families:
        partners = _sorted(ctx.ref(p.person_id) for p in family.partners)
        children = _sorted(ctx.ref(c) for c in family.children)
        parentage = _sorted(
            (
                ctx.ref(link.child_id),
                "" if link.parent_id is None else ctx.ref(link.parent_id),
                _s(link.parentage_type),
            )
            for link in family.parent_child_links
        )
        event_refs = _sorted(
            ref
            for ref in (ctx.event_ref(eid) for eid in family.event_ids)
            if ref is not None
        )
        fields = {
            "partners": _sorted((ctx.ref(p.person_id), _s(p.role)) for p in family.partners),
            "children": children,
            "parentage": parentage,
            "event_refs": event_refs,
        }
        entries.append(((partners, children), (partners,), fields))
    return _with_ordinals("families", entries)


def _endpoint(endpoint: Endpoint) -> tuple:
    return (
        _s(endpoint.earliest),
        _s(endpoint.latest),
        _s(endpoint.precision),
        _s(endpoint.note),
    )


def _observation(ctx: _Context, obs: Observation) -> tuple:
    ref = obs.source_ref
    return (
        ctx.source_title(ref.source_id),
        _s(obs.observed_from),
        _s(obs.observed_to),
        _s(obs.page_note),
        _s(ref.quality),
        _s(ref.note),
        tuple(ref.aspects),
    )


def _residences(ctx: _Context) -> tuple[Item, ...]:
    entries = []
    for fact in ctx.data.residences:
        person = ctx.ref(fact.person_id)
        chain = place_chain(fact.place_id, ctx.places)
        identity = (
            person,
            chain,
            (_s(fact.start.earliest), _s(fact.start.latest)),
            (_s(fact.end.earliest), _s(fact.end.latest)),
        )
        fields = {
            "start": _endpoint(fact.start),
            "end": _endpoint(fact.end),
            "start_event": ctx.event_ref(fact.start.event_id),
            "end_event": ctx.event_ref(fact.end.event_id),
            "role": _unset_if_blank(fact.role_in_household),
            "notes": _unset_if_blank(fact.notes),
            "observations": _sorted(_observation(ctx, o) for o in fact.observations),
        }
        entries.append((identity, (person, chain), fields))
    return _with_ordinals("residences", entries)


def _repository_ref(ctx: _Context, ref) -> tuple:
    repo = ctx.repositories.get(ref.repository_id)
    repo_key = (f"?{ref.repository_id}", "", "") if repo is None else (
        repo.name,
        _s(repo.type),
        _s(repo.address),
    )
    return (
        repo_key,
        _s(ref.call_number),
        _s(ref.source_type),
        ref.image_number,
        ref.page_number,
        _s(ref.media_type),
        _s(ref.media_name),
        _s(ref.notes),
    )


def _sources(ctx: _Context) -> tuple[Item, ...]:
    entries = []
    for source in ctx.data.sources:
        leverantor = ctx.leverantorer.get(source.leverantor_id)
        kalltyp = ctx.kalltyper.get(source.kalltyp_id)
        structured = _sorted(
            (key, type(value).__name__, value)
            for key, value in source.structured_reference.fields.items()
        )
        fields = {
            "source_type": _s(source.source_type),
            "provider": _s(source.provider),
            "leverantor": "" if leverantor is None else leverantor.name,
            "kalltyp": "" if kalltyp is None else kalltyp.name,
            "reference_text": _s(source.reference_text),
            "structured_reference": structured,
            "repository_refs": _sorted(_repository_ref(ctx, r) for r in source.repository_refs),
            "provider_ref": _s(source.provider_ref),
            "short_note": _s(source.short_note),
            "free_note": _s(source.free_note),
            "arkivreferens": _s(source.arkivreferens),
            "arkivreferenser": tuple(
                (_s(a.leverantor_name), _s(a.reference_value)) for a in source.arkivreferenser
            ),
            "media_ids": len(source.media_ids),
        }
        entries.append(((_s(source.title),), (_s(source.title),), fields))
    return _with_ordinals("sources", entries)


def _repositories(ctx: _Context) -> tuple[Item, ...]:
    entries = []
    for repo in ctx.data.repositories:
        identity = (_s(repo.name), _s(repo.type), _s(repo.address))
        fields = {
            "phone": tuple(repo.phone),
            "email": tuple(repo.email),
            "web": tuple(repo.web),
            "notes": _s(repo.notes),
            "external_ids": tuple(repo.external_ids),
        }
        entries.append((identity, (identity[0],), fields))
    return _with_ordinals("repositories", entries)


def _totals(ctx: _Context) -> tuple[Item, ...]:
    return (Item(("media",), 0, ("media",), {"count": len(ctx.data.media)}),)


def stable_view(data: ProjectData) -> StableView:
    """Build the Stable_View of *data*. The input is not modified."""
    ctx = _Context(data)
    sections = {
        "persons": _persons(ctx),
        "families": _families(ctx),
        "events": _events(ctx),
        "residences": _residences(ctx),
        "sources": _sources(ctx),
        "repositories": _repositories(ctx),
        "totals": _totals(ctx),
    }
    per_type: dict[str, int] = {}
    for event in data.events:
        per_type[event.type] = per_type.get(event.type, 0) + 1
    counts = {
        "persons": len(data.persons),
        "families": len(data.families),
        "events": len(data.events),
        "events_per_type": dict(sorted(per_type.items())),
        "residences": len(data.residences),
        "sources": len(data.sources),
        "repositories": len(data.repositories),
        "media": len(data.media),
    }
    return StableView(sections=sections, counts=counts)
