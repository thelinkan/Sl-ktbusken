"""Deterministic large-project generator for performance measurements."""

from __future__ import annotations

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Source

_EVENT_TYPES = ("birth", "death", "baptism")


def make_project(n_persons: int = 10_000) -> ProjectData:
    """Build a project with n_persons persons, about 2.5 events per person.

    Families, places and sources scale as 0.4, 0.2 and 0.08 per person
    (4,000, 2,000 and 800 for 10,000 persons). No randomness is used.
    """
    n_fam = n_persons * 4 // 10
    n_places = n_persons * 2 // 10
    n_sources = n_persons * 8 // 100
    data = ProjectData(project=ProjectMetadata(title="Stort projekt"))

    data.places = [
        Place(id=f"place_{i}", type="parish", name=f"Plats {i}",
              notes="Anteckning " * 3)
        for i in range(n_places)
    ]
    data.sources = [
        Source(id=f"source_{i}", provider="Arkiv Digital", source_type="kyrkobok",
               title=f"Källa {i}", reference_text=f"Referens {i}")
        for i in range(n_sources)
    ]
    data.persons = [
        Person(id=f"person_{i}", sex="M" if i % 2 == 0 else "F",
               names=[Name(type="birth", given=f"Förnamn{i}", surname=f"Efternamn{i % 500}")],
               notes="Anteckning om personen.")
        for i in range(n_persons)
    ]

    n_events = n_persons * 5 // 2
    events: list[Event] = []
    for i in range(n_events):
        owner = f"person_{i % n_persons}"
        src = f"source_{i % n_sources}" if n_sources else None
        refs = [SourceRef(source_id=src, quality="primary")] if src else []
        events.append(Event(
            id=f"event_{i}",
            type=_EVENT_TYPES[i % 3],
            participants=[Participant(person_id=owner, role="principal")],
            date=DateValue(value=f"{1700 + i % 250}-{1 + i % 12:02d}-{1 + i % 28:02d}",
                           precision="exact", source_refs=list(refs)),
            place=PlaceRef(place_id=f"place_{i % n_places}", source_refs=[]),
        ))
    data.events = events

    for f in range(n_fam):
        a, b = (2 * f) % n_persons, (2 * f + 1) % n_persons
        kids = [f"person_{(3 * f + k + 7) % n_persons}" for k in range(2)]
        data.families.append(Family(
            id=f"family_{f}",
            partners=[FamilyPartner(person_id=f"person_{a}", role="partner"),
                      FamilyPartner(person_id=f"person_{b}", role="partner")],
            children=kids,
            parent_child_links=[
                ParentChildLink(child_id=k, parent_id=f"person_{a}",
                                parentage_type="biological")
                for k in kids
            ],
        ))
    return data
