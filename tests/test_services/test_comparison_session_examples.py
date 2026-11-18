"""Example tests for same-ID relatives and same-named siblings (Req 32.7).

Qt-free session-level tests. Two persons are the same only when their ids are
identical (Requirements 12.1, 12.7); siblings are part of a family view (10.5).
"""

from __future__ import annotations

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.merge_candidate import MergeCandidate
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.candidate_index import CandidateIndex
from slaktbusken.services.comparison_session import ComparisonSession
from slaktbusken.services.diagram_lookup import DiagramLookup


def _person(pid: str, given: str, surname: str = "Andersson", sex: str = "M") -> Person:
    return Person(id=pid, sex=sex, names=[Name("birth", given, surname)])


def _project() -> ProjectData:
    persons = [
        _person("anders", "Anders"),
        _person("brita", "Brita", sex="F"),
        _person("karin", "Karin", sex="F"),
        _person("kalle1", "Kalle"),  # died young
        _person("kalle2", "Kalle"),  # same name, grew up
        _person("lisa", "Lisa", sex="F"),
        _person("kalle3", "Kalle"),  # half-brother in the second family
        _person("olof", "Olof"),
    ]
    families = [
        Family(
            id="f1",
            partners=[FamilyPartner("anders", "husband"), FamilyPartner("brita", "wife")],
            children=["kalle1", "kalle2", "lisa"],
        ),
        Family(
            id="f2",
            partners=[FamilyPartner("anders", "husband"), FamilyPartner("karin", "wife")],
            children=["kalle3", "olof"],
        ),
    ]
    events = [
        Event("b1", "birth", [Participant("kalle1", "self")], DateValue("1850-03-12", "day")),
        Event("d1", "death", [Participant("kalle1", "self")], DateValue("1851-01-02", "day")),
        Event("b2", "birth", [Participant("kalle2", "self")], DateValue("1852-05-01", "day")),
        Event("b3", "birth", [Participant("kalle3", "self")], DateValue("1852-05-01", "day")),
    ]
    return ProjectData(
        project=ProjectMetadata(title="T"), persons=persons, families=families, events=events
    )


def _family_view(lookup: DiagramLookup, data: ProjectData, focus: str) -> set[str]:
    """Ids a family view of ``focus`` shows: itself, parents, siblings, partners, children."""
    visible = {focus, *lookup.siblings_of(focus)}
    for fam in lookup.parent_families_by_child.get(focus, []):
        visible.update(p.person_id for p in fam.partners)
    for fam in lookup.partner_families_by_person.get(focus, []):
        visible.update(p.person_id for p in fam.partners)
        visible.update(fam.children)
    return visible


def test_same_relative_id_in_both_views_is_shared_person() -> None:
    data = _project()
    lookup = DiagramLookup.build(data)
    left = _family_view(lookup, data, "kalle2")
    right = _family_view(lookup, data, "kalle3")
    shared = ComparisonSession.shared_person_ids(left, right)
    assert shared == {"anders"}


def test_same_named_siblings_in_one_view_are_not_shared_or_paired() -> None:
    data = _project()
    lookup = DiagramLookup.build(data)
    view = _family_view(lookup, data, "kalle2")
    assert {"kalle1", "kalle2"} <= view
    # Same view on both sides: only identical ids are shared, so the two
    # Kalles are each shared with themselves and never with each other.
    shared = ComparisonSession.shared_person_ids(view, view)
    assert shared == view
    index = CandidateIndex.build(data)
    assert ComparisonSession.candidate_relation("kalle1", "kalle2", index) is None
    assert ComparisonSession.candidate_relation("kalle2", "kalle1", index) is None
    # A left view without the dead sibling shares nothing with him on the right.
    assert ComparisonSession.shared_person_ids({"kalle2"}, {"kalle1"}) == set()


def test_same_named_people_across_views_have_no_shared_marker() -> None:
    data = _project()
    lookup = DiagramLookup.build(data)
    left = _family_view(lookup, data, "kalle1")
    right = _family_view(lookup, data, "kalle3")
    shared = ComparisonSession.shared_person_ids(left, right)
    assert "kalle1" not in shared and "kalle3" not in shared
    assert "kalle2" not in shared
    assert shared == {"anders"}


def test_siblings_are_included_in_family_view() -> None:
    data = _project()
    lookup = DiagramLookup.build(data)
    assert lookup.siblings_of("kalle1") == ["kalle2", "lisa"]
    assert lookup.siblings_of("kalle1", "f1") == ["kalle2", "lisa"]
    assert lookup.siblings_of("anders") == []
    view = _family_view(lookup, data, "kalle1")
    assert {"kalle2", "lisa"} <= view


def test_different_ids_are_never_paired_by_name_date_or_sex() -> None:
    data = _project()
    index = CandidateIndex.build(data)
    # kalle2 and kalle3: same name, sex and birth date, different ids.
    assert ComparisonSession.candidate_relation("kalle2", "kalle3", index) is None
    assert ComparisonSession.shared_person_ids(["kalle2"], ["kalle3"]) == set()
    # A saved candidate is the only relation, and only for that pair.
    data.merge_candidates.append(MergeCandidate("c1", "kalle2", "kalle3"))
    index = CandidateIndex.build(data)
    found = ComparisonSession.candidate_relation("kalle3", "kalle2", index)
    assert found is not None and found.id == "c1"
    assert ComparisonSession.candidate_relation("kalle1", "kalle3", index) is None
    assert ComparisonSession.candidate_relation("kalle2", "kalle2", index) is None
