"""Property 12: Slot search.

**Validates: Requirements 9.7**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.services.person_search import (
    MAX_RESULTS,
    PersonSearchIndex,
)

_TEXT = st.text(alphabet="abAB åÅ-1", min_size=0, max_size=4)
_DATES = st.sampled_from(["", "1829", "1829-03-04", "1890-11", "ABT 1700"])
_PLACES = st.sampled_from(["", "Ljusdal", "Delsbo"])


@st.composite
def projects(draw):
    count = draw(st.integers(min_value=0, max_value=70))
    data = ProjectData()
    data.places = [
        Place(id="pl_Ljusdal", type="socken", name="Ljusdal"),
        Place(id="pl_Delsbo", type="socken", name="Delsbo"),
    ]
    for i in range(count):
        pid = f"P{i}"
        names = [
            Name(type="birth", given=draw(_TEXT), surname=draw(_TEXT))
            for _ in range(draw(st.integers(min_value=0, max_value=2)))
        ]
        data.persons.append(Person(id=pid, sex="unknown", names=names))
        for kind in ("birth", "death"):
            date, place = draw(_DATES), draw(_PLACES)
            if date or place:
                data.events.append(
                    Event(
                        id=f"E_{kind}_{i}",
                        type=kind,
                        participants=[Participant(person_id=pid, role="principal")],
                        date=DateValue(value=date, precision="day") if date else None,
                        place=PlaceRef(place_id=f"pl_{place}") if place else None,
                    )
                )
    return data


def _birth_death(data: ProjectData, pid: str) -> tuple[str, str, str]:
    birth = death = place = ""
    for ev in data.events:
        if ev.participants[0].person_id != pid:
            continue
        value = ev.date.value if ev.date else ""
        if ev.type == "birth":
            birth = value
            place = ev.place.place_id[3:] if ev.place else ""
        else:
            death = value
    return birth, death, place


def _expected_ids(data: ProjectData, query: str) -> set[str]:
    q = query.strip().lower()
    out = set()
    for person in data.persons:
        birth, death, _ = _birth_death(data, person.id)
        parts = [person.id, birth, death]
        for n in person.names:
            parts += [n.given, n.surname, f"{n.given} {n.surname}"]
        if any(q in part.lower() for part in parts):
            out.add(person.id)
    return out


_QUERY = st.text(alphabet="abAB åÅ-1P", min_size=0, max_size=4)


@given(projects(), _QUERY)
def test_property_12_slot_search(data, query):
    index = PersonSearchIndex.build(data)
    results = index.search(query)
    ids = [r.person_id for r in results]

    # Fewer than two characters never searches.
    if len(query.strip()) < 2:
        assert results == []
        return

    expected = _expected_ids(data, query)

    # Every result contains the query; no duplicates; at most 50.
    assert set(ids) <= expected
    assert len(ids) == len(set(ids))
    assert len(results) <= MAX_RESULTS
    # When at most 50 match, all of them are returned.
    if len(expected) <= MAX_RESULTS:
        assert set(ids) == expected
    else:
        assert len(results) == MAX_RESULTS

    # Case-insensitive.
    assert [r.person_id for r in index.search(query.upper())] == ids
    assert [r.person_id for r in index.search(query.lower())] == ids

    # Results carry name, life dates, birth place and id.
    for r in results:
        person = next(p for p in data.persons if p.id == r.person_id)
        birth, death, place = _birth_death(data, r.person_id)
        if person.names:
            assert r.name == f"{person.names[0].given} {person.names[0].surname}".strip()
        assert r.birth_place == place
        assert birth in r.life_dates and death in r.life_dates
        assert f"[{r.person_id}]" in r.display_text


@given(st.integers(min_value=51, max_value=120))
def test_property_12_cap_and_same_name_distinguishable(n):
    data = ProjectData()
    for i in range(n):
        pid = f"P{i}"
        data.persons.append(
            Person(id=pid, sex="unknown", names=[Name(type="birth", given="Anna", surname="Ek")])
        )
    index = PersonSearchIndex.build(data)
    results = index.search("anna")
    assert len(results) == MAX_RESULTS
    assert len({r.display_text for r in results}) == MAX_RESULTS
    assert index.search("a") == []
    assert len(index.search("P1")) == len([i for i in range(n) if f"P{i}".lower().find("p1") >= 0][:MAX_RESULTS])
