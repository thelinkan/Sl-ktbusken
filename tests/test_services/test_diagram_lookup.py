"""Equivalence tests for DiagramLookup (finding 7).

Every ``display_data`` and every ``_find_*`` helper of the three diagram views
must give identical output with and without an active lookup.
"""

from __future__ import annotations

import random

import pytest

from slaktbusken.model.dna import DnaCluster, DnaCompany, DnaProfile
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services import diagram_lookup
from slaktbusken.services.diagram_lookup import DiagramLookup
from slaktbusken.ui.views import ancestry_view, descendants_view, family_view

_VIEWS = (family_view, ancestry_view, descendants_view)


def _build_project(seed: int = 7, n_persons: int = 60) -> ProjectData:
    rng = random.Random(seed)
    persons = [
        Person(
            id=f"p{i}",
            sex=rng.choice(["male", "female"]),
            names=[Name(type="birth", given=f"Namn{i}", surname=f"Efternamn{i % 7}")]
            + ([Name(type="married", given="X", surname="Y")] if i % 5 == 0 else []),
            occupation="Bonde" if i % 3 == 0 else None,
        )
        for i in range(n_persons)
    ]
    places = [Place(id=f"pl{i}", type="parish", name=f"Socken{i}") for i in range(6)]
    # A duplicated place id and a duplicated person id exercise first-match-wins.
    places.append(Place(id="pl0", type="parish", name="Dubblett"))
    persons.append(Person(id="p1", sex="male", names=[Name(type="birth", given="Dup", surname="Dup")]))

    families: list[Family] = []
    for i in range(0, n_persons - 4, 4):
        families.append(
            Family(
                id=f"f{i}",
                partners=[
                    FamilyPartner(person_id=f"p{i}", role="father"),
                    FamilyPartner(person_id=f"p{i + 1}", role="mother"),
                ],
                children=[f"p{i + 2}", f"p{i + 3}", f"p{i + 2}"],  # repeated child
            )
        )
    # Second partner family for p0 and a family where p2 is both child and partner.
    families.append(
        Family(
            id="fx",
            partners=[
                FamilyPartner(person_id="p0", role="father"),
                FamilyPartner(person_id="p9", role="mother"),
            ],
            children=["p10"],
        )
    )

    events: list[Event] = []
    n = 0
    for p in persons[:n_persons]:
        pid = p.id
        for etype in ("birth", "death", "marriage", "residence"):
            if rng.random() < 0.6:
                n += 1
                events.append(
                    Event(
                        id=f"e{n}",
                        type=etype,
                        participants=[Participant(person_id=pid, role="subject")]
                        + ([Participant(person_id=pid, role="witness")] if n % 11 == 0 else []),
                        date=DateValue(value=f"{1800 + rng.randint(0, 150)}-01-01", precision="exact")
                        if rng.random() < 0.8
                        else None,
                        place=PlaceRef(place_id=rng.choice(["pl0", "pl3", "missing"]))
                        if rng.random() < 0.7
                        else None,
                        cause_of_death="Ålder" if etype == "death" and rng.random() < 0.5 else None,
                    )
                )
    # A second birth event for one person: the later event must win in both paths.
    events.append(
        Event(
            id="e_dup",
            type="birth",
            participants=[Participant(person_id="p5", role="subject")],
            date=DateValue(value="1901-02-03", precision="exact"),
        )
    )

    companies = [DnaCompany(id="c1", name="MyHeritage"), DnaCompany(id="c2", name="Ancestry")]
    profiles = [
        DnaProfile(id=f"dp{i}", person_id=f"p{i}", company_id=rng.choice(["c1", "c2"]), test_type="autosomal")
        for i in range(0, n_persons, 3)
    ]
    profiles.append(DnaProfile(id="dpx", person_id="p0", company_id="c2", test_type="y-dna"))
    clusters = [
        DnaCluster(
            id=f"cl{i}",
            name=f"Kluster {i % 4}",
            person_ids=[f"p{j}" for j in range(i, n_persons, 5)] + [f"p{i}"],
            color="#FF0000",
        )
        for i in range(8)
    ]
    return ProjectData(
        project=ProjectMetadata(title="Test", main_person_id="p0"),
        persons=persons,
        families=families,
        events=events,
        places=places,
        dna_companies=companies,
        dna_profiles=profiles,
        dna_clusters=clusters,
    )


@pytest.fixture(autouse=True)
def _clear_lookup():
    diagram_lookup.set_active_lookup(None)
    yield
    diagram_lookup.set_active_lookup(None)


@pytest.fixture(scope="module")
def project() -> ProjectData:
    return _build_project()


def test_display_data_identical_with_and_without_lookup(project: ProjectData) -> None:
    for view in _VIEWS:
        diagram_lookup.set_active_lookup(None)
        without = [view._build_display_data(p, project) for p in project.persons]

        diagram_lookup.begin_lookup(project)
        assert diagram_lookup.active_lookup(project) is not None
        with_lookup = [view._build_display_data(p, project) for p in project.persons]

        assert with_lookup == without, view.__name__


def test_find_helpers_identical_with_and_without_lookup(project: ProjectData) -> None:
    ids = [p.id for p in project.persons] + ["nobody"]

    def snapshot():
        out = []
        for pid in ids:
            fp = family_view._find_person(project, pid)
            out.append(("person", pid, id(fp) if fp else None))
            out.append(("parents", pid, [f.id for f in family_view._find_parent_families(project, pid)]))
            pf = family_view._find_parent_family(project, pid)
            out.append(("parent", pid, pf.id if pf else None))
            pf2 = ancestry_view._find_parent_family(project, pid)
            out.append(("aparent", pid, pf2.id if pf2 else None))
            out.append(("partners", pid, [f.id for f in family_view._find_partner_families(project, pid)]))
            out.append(("dperson", pid, id(descendants_view._find_person(project, pid)) if descendants_view._find_person(project, pid) else None))
        for fid in [f.id for f in project.families] + ["nofam"]:
            f = family_view._find_family_by_id(project, fid)
            out.append(("family", fid, f.id if f else None))
        for plid in ["pl0", "pl3", "missing"]:
            pl = family_view._find_place(project, plid)
            out.append(("place", plid, pl.name if pl else None))
        return out

    without = snapshot()
    diagram_lookup.begin_lookup(project)
    assert snapshot() == without


def test_lookup_ignored_when_data_changed(project: ProjectData) -> None:
    other = _build_project(seed=1, n_persons=20)
    diagram_lookup.begin_lookup(project)
    assert diagram_lookup.active_lookup(other) is None
    assert diagram_lookup.active_lookup(project) is not None


def test_siblings_exposed_for_family_view(project: ProjectData) -> None:
    lookup = DiagramLookup.build(project)
    assert lookup.siblings_of("p2") == ["p3"]
    assert lookup.siblings_of("p3", "f0") == ["p2", "p2"]  # same list the view builds
    assert lookup.siblings_of("p0") == []
