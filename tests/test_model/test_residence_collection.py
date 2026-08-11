"""Unit tests for the Project ``residences`` collection and residence ids.

Covers Requirements 1.2 (the Project holds Residence_Facts in a `residences`
collection alongside `events`, empty for a new Project, in insertion order) and
1.12 (a Residence_Fact id is unique project-wide and never reused).
"""

from __future__ import annotations

from dataclasses import fields

from slaktbusken.model import IDGenerator, ProjectData, ResidenceFact


def _fact(fact_id: str, person_id: str = "person_1", place_id: str = "place_1") -> ResidenceFact:
    return ResidenceFact(id=fact_id, person_id=person_id, place_id=place_id)


def test_new_project_has_empty_residences_collection():
    data = ProjectData()
    assert data.residences == []


def test_residences_collections_are_not_shared_between_projects():
    first = ProjectData()
    second = ProjectData()
    first.residences.append(_fact("residence_1"))
    assert second.residences == []


def test_residences_is_declared_directly_after_events():
    names = [f.name for f in fields(ProjectData)]
    assert names[names.index("events") + 1] == "residences"


def test_residences_preserves_insertion_order():
    data = ProjectData()
    added = [_fact(f"residence_{i}") for i in range(1, 6)]
    for fact in added:
        data.residences.append(fact)

    assert [fact.id for fact in data.residences] == [fact.id for fact in added]

    # Removing one keeps the relative order of the survivors.
    data.residences.remove(added[1])
    assert [fact.id for fact in data.residences] == [
        "residence_1",
        "residence_3",
        "residence_4",
        "residence_5",
    ]


def test_residence_ids_use_the_residence_prefix():
    gen = IDGenerator(set())
    assert gen.generate("residence") == "residence_1"
    assert gen.generate("residence") == "residence_2"


def test_residence_ids_are_unique_project_wide():
    data = ProjectData()
    gen = IDGenerator({"person_1", "place_1", "event_1"})
    for _ in range(3):
        data.residences.append(_fact(gen.generate("residence")))

    all_ids = (
        [p.id for p in data.persons]
        + [p.id for p in data.places]
        + [e.id for e in data.events]
        + [r.id for r in data.residences]
    )
    assert len(all_ids) == len(set(all_ids))
    assert not {"person_1", "place_1", "event_1"} & {r.id for r in data.residences}


def test_residence_id_is_never_reused_after_deletion():
    data = ProjectData()
    gen = IDGenerator(set())
    first = _fact(gen.generate("residence"))
    second = _fact(gen.generate("residence"))
    data.residences.extend([first, second])

    data.residences.remove(second)
    gen_after_delete = IDGenerator(gen.used_ids)
    third_id = gen_after_delete.generate("residence")

    assert third_id not in {first.id, second.id}
    assert third_id == "residence_3"
