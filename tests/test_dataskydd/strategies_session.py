"""Strategies and mutation operations for the edit-session properties.

``project_strategy`` builds a small project that has something in every
collection an edit session can touch. ``ops_strategy`` draws sequences of
``(operation, number)`` pairs; ``apply_op`` applies one of them to a live
``ProjectData`` the way editors do (including assigning a new list to a field,
as ``PersonEditor._on_remove_event`` does).

Some operations are deliberate no-ops or cancel each other (rename to the same
value, add then remove), so sequences that net to no change are common.
"""

from __future__ import annotations

from hypothesis import strategies as st

from slaktbusken.model.dna import DnaCompany
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.record_origin import RecordOrigin
from slaktbusken.model.research_case import ResearchCase
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.model.source import Kalltyp, Leverantor, Repository, Source


def make_session_project(
    n_persons: int, n_places: int, n_sources: int, n_events: int, n_residences: int
) -> ProjectData:
    """A project with persons, families, events, residences, places, sources and more."""
    data = ProjectData(project=ProjectMetadata(title="Sessionstest"))
    data.persons = [
        Person(
            id=f"person_{i}",
            sex="M" if i % 2 == 0 else "F",
            names=[Name(type="birth", given=f"Förnamn{i}", surname="Efternamn")],
        )
        for i in range(n_persons)
    ]
    data.places = [
        Place(id=f"place_{i}", type="parish", name=f"Plats {i}") for i in range(n_places)
    ]
    data.sources = [
        Source(id=f"source_{i}", provider="Arkiv Digital", source_type="church_book",
               title=f"Källa {i}")
        for i in range(n_sources)
    ]
    data.events = [
        Event(
            id=f"event_{i}",
            type="birth",
            participants=[Participant(person_id=f"person_{i % n_persons}", role="principal")],
            date=DateValue(value=f"{1700 + i}", precision="year"),
            place=PlaceRef(place_id=f"place_{i % n_places}"),
        )
        for i in range(n_events)
    ]
    data.residences = [
        ResidenceFact(
            id=f"res_{i}",
            person_id=f"person_{i % n_persons}",
            place_id=f"place_{i % n_places}",
            origins=[
                RecordOrigin(
                    owner_kind="person", owner_id=f"person_{i % n_persons}",
                    owner_xref=f"@I{i}@", tag_key="RESI", index=i, record_hash=f"h{i}",
                )
            ],
        )
        for i in range(n_residences)
    ]
    if n_persons >= 2:
        data.families = [
            Family(
                id="family_0",
                partners=[FamilyPartner(person_id="person_0", role="partner")],
                children=["person_1"],
            )
        ]
    data.media = [MediaItem(id="media_0", type="photo", file="a.jpg", title="Foto")]
    data.repositories = [Repository(id="repo_0", name="Arkivet", type="archive")]
    data.leverantorer = [Leverantor(id="lev_0", name="Leverantör")]
    data.kalltyper = [Kalltyp(id="kt_0", leverantor_id="lev_0", name="Kyrkbok")]
    data.research_cases = [ResearchCase(id="case_0")]
    data.connection_overrides = {"person_1": "foster"}
    return data


project_strategy = st.builds(
    make_session_project,
    n_persons=st.integers(2, 6),
    n_places=st.integers(1, 4),
    n_sources=st.integers(1, 3),
    n_events=st.integers(1, 6),
    n_residences=st.integers(1, 4),
)


def _pick(items: list, n: int):
    return items[n % len(items)] if items else None


def _op_add_event(d: ProjectData, n: int) -> None:
    d.events.append(Event(id=f"event_new_{n}", type="death", participants=[]))


def _op_edit_event(d: ProjectData, n: int) -> None:
    e = _pick(d.events, n)
    if e is not None:
        e.type = "baptism" if e.type != "baptism" else "birth"


def _op_remove_event_reassign(d: ProjectData, n: int) -> None:
    e = _pick(d.events, n)
    if e is not None:
        d.events = [x for x in d.events if x.id != e.id]


def _op_remove_event_inplace(d: ProjectData, n: int) -> None:
    e = _pick(d.events, n)
    if e is not None:
        d.events.remove(e)


def _op_reverse_events(d: ProjectData, n: int) -> None:
    d.events.reverse()


def _op_add_residence(d: ProjectData, n: int) -> None:
    d.residences.append(ResidenceFact(id=f"res_new_{n}", person_id="person_0", place_id="place_0"))


def _op_delete_residence(d: ProjectData, n: int) -> None:
    r = _pick(d.residences, n)
    if r is not None:
        d.residences = [x for x in d.residences if x.id != r.id]


def _op_add_residence_origin(d: ProjectData, n: int) -> None:
    r = _pick(d.residences, n)
    if r is not None:
        r.origins.append(
            RecordOrigin(owner_kind="person", owner_id=r.person_id, owner_xref="@X@",
                         tag_key="RESI", index=n, record_hash=f"x{n}")
        )


def _op_add_family(d: ProjectData, n: int) -> None:
    d.families.append(Family(id=f"family_new_{n}", partners=[], children=[]))


def _op_edit_family(d: ProjectData, n: int) -> None:
    f = _pick(d.families, n)
    if f is not None:
        f.children.append(f"person_{n % 2}")


def _op_remove_family(d: ProjectData, n: int) -> None:
    f = _pick(d.families, n)
    if f is not None:
        d.families.remove(f)


def _op_add_place(d: ProjectData, n: int) -> None:
    d.places.append(Place(id=f"place_new_{n}", type="parish", name="Ny plats"))


def _op_rename_place(d: ProjectData, n: int) -> None:
    p = _pick(d.places, n)
    if p is not None:
        p.name = p.name + "x"


def _op_rename_place_same(d: ProjectData, n: int) -> None:
    p = _pick(d.places, n)
    if p is not None:
        p.name = str(p.name)


def _op_remove_place(d: ProjectData, n: int) -> None:
    p = _pick(d.places, n)
    if p is not None:
        d.places = [x for x in d.places if x is not p]


def _op_add_remove_place(d: ProjectData, n: int) -> None:
    """Net no change: add a place and remove it again."""
    p = Place(id=f"place_tmp_{n}", type="parish", name="Tillfällig")
    d.places.append(p)
    d.places.remove(p)


def _op_add_source(d: ProjectData, n: int) -> None:
    d.sources.append(Source(id=f"source_new_{n}", provider="p", source_type="t", title="Ny"))


def _op_remove_source(d: ProjectData, n: int) -> None:
    s = _pick(d.sources, n)
    if s is not None:
        d.sources.remove(s)


def _op_add_media(d: ProjectData, n: int) -> None:
    d.media.append(MediaItem(id=f"media_new_{n}", type="photo", file="b.jpg", title="Ny"))


def _op_add_repository(d: ProjectData, n: int) -> None:
    d.repositories.append(Repository(id=f"repo_new_{n}", name="Ny", type="archive"))


def _op_add_leverantor(d: ProjectData, n: int) -> None:
    d.leverantorer.append(Leverantor(id=f"lev_new_{n}", name="Ny"))


def _op_add_kalltyp(d: ProjectData, n: int) -> None:
    d.kalltyper.append(Kalltyp(id=f"kt_new_{n}", leverantor_id="lev_0", name="Ny"))


def _op_add_research_case(d: ProjectData, n: int) -> None:
    d.research_cases.append(ResearchCase(id=f"case_new_{n}"))


def _op_add_dna_company(d: ProjectData, n: int) -> None:
    d.dna_companies.append(DnaCompany(id=f"dnaco_{n}", name="Bolag"))


def _op_edit_person(d: ProjectData, n: int) -> None:
    p = _pick(d.persons, n)
    if p is not None:
        p.notes = f"Anteckning {n}"


def _op_edit_title(d: ProjectData, n: int) -> None:
    d.project.title = d.project.title + "!"


def _op_set_main_person(d: ProjectData, n: int) -> None:
    d.project.main_person_id = f"person_{n}"


def _op_set_override(d: ProjectData, n: int) -> None:
    d.connection_overrides[f"person_{n}"] = "adoptive"


def _op_remove_override(d: ProjectData, n: int) -> None:
    d.connection_overrides.clear()


OPS = {
    name[len("_op_"):]: func for name, func in sorted(globals().items())
    if name.startswith("_op_")
}

ops_strategy = st.lists(
    st.tuples(st.sampled_from(sorted(OPS)), st.integers(0, 50)), max_size=10
)


def apply_op(data: ProjectData, op: str, n: int) -> None:
    """Apply the named operation to *data*."""
    OPS[op](data, n)
