"""Example-based tests for ParentService biological-parent family moving.

These cover the bugfix where adding a biological parent B to a child who is
already in a single-parent family {A, child} should MOVE the child into the
existing couple family {A, B} instead of creating overlapping families.
"""

from __future__ import annotations

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.diagram_lookup import find_parent_families
from slaktbusken.services.parent_service import ParentService


def _person(person_id: str, sex: str) -> Person:
    return Person(
        id=person_id,
        sex=sex,
        names=[Name(type="birth", given=person_id, surname="Test")],
    )


def _bio_link(child_id: str, parent_id: str) -> ParentChildLink:
    return ParentChildLink(
        child_id=child_id, parent_id=parent_id, parentage_type="biological"
    )


def _families_listing_child(data: ProjectData, child_id: str) -> list[Family]:
    return [f for f in data.families if child_id in f.children]


def test_move_child_into_existing_couple_family() -> None:
    """Single-parent F1={A,child} + couple F2={A,B}: adding B moves child to F2."""
    a = _person("A", "M")
    b = _person("B", "F")
    child = _person("child", "U")

    f1 = Family(
        id="F1",
        partners=[FamilyPartner(person_id="A", role="father")],
        children=["child"],
        parent_child_links=[_bio_link("child", "A")],
    )
    f2 = Family(
        id="F2",
        partners=[
            FamilyPartner(person_id="A", role="father"),
            FamilyPartner(person_id="B", role="mother"),
        ],
        children=[],
        parent_child_links=[],
    )

    data = ProjectData(
        project=ProjectMetadata(title="t"),
        persons=[a, b, child],
        families=[f1, f2],
    )

    service = ParentService(data)
    service.add_parent("child", "B", "biological")

    # F1 removed (no children left); only F2 lists the child.
    family_ids = {f.id for f in data.families}
    assert "F1" not in family_ids
    assert "F2" in family_ids

    listing = _families_listing_child(data, "child")
    assert len(listing) == 1
    assert listing[0].id == "F2"

    # F2 has biological links to both A and B.
    bio_parents = {
        link.parent_id
        for link in f2.parent_child_links
        if link.child_id == "child" and link.parentage_type == "biological"
    }
    assert bio_parents == {"A", "B"}

    # find_parent_families reports only F2.
    found = find_parent_families(data, "child")
    assert [f.id for f in found] == ["F2"]


def test_old_family_kept_when_it_has_another_child() -> None:
    """F1={A,child,C}: moving child to F2={A,B} keeps F1 with C and C's links."""
    a = _person("A", "M")
    b = _person("B", "F")
    child = _person("child", "U")
    c = _person("C", "U")

    f1 = Family(
        id="F1",
        partners=[FamilyPartner(person_id="A", role="father")],
        children=["child", "C"],
        parent_child_links=[_bio_link("child", "A"), _bio_link("C", "A")],
    )
    f2 = Family(
        id="F2",
        partners=[
            FamilyPartner(person_id="A", role="father"),
            FamilyPartner(person_id="B", role="mother"),
        ],
        children=[],
        parent_child_links=[],
    )

    data = ProjectData(
        project=ProjectMetadata(title="t"),
        persons=[a, b, child, c],
        families=[f1, f2],
    )

    service = ParentService(data)
    service.add_parent("child", "B", "biological")

    # F1 kept with C only.
    assert "F1" in {f.id for f in data.families}
    assert f1.children == ["C"]
    c_links = [link for link in f1.parent_child_links if link.child_id == "C"]
    assert len(c_links) == 1
    assert all(link.child_id != "child" for link in f1.parent_child_links)

    # Edited child moved to F2 with links to A and B.
    listing = _families_listing_child(data, "child")
    assert [f.id for f in listing] == ["F2"]
    bio_parents = {
        link.parent_id
        for link in f2.parent_child_links
        if link.child_id == "child"
    }
    assert bio_parents == {"A", "B"}


def test_parentage_types_preserved_on_moved_and_new_links() -> None:
    """Moved A-link keeps its type; new B-link is biological."""
    a = _person("A", "M")
    b = _person("B", "F")
    child = _person("child", "U")

    f1 = Family(
        id="F1",
        partners=[FamilyPartner(person_id="A", role="father")],
        children=["child"],
        parent_child_links=[_bio_link("child", "A")],
    )
    f2 = Family(
        id="F2",
        partners=[
            FamilyPartner(person_id="A", role="father"),
            FamilyPartner(person_id="B", role="mother"),
        ],
        children=[],
        parent_child_links=[],
    )

    data = ProjectData(
        project=ProjectMetadata(title="t"),
        persons=[a, b, child],
        families=[f1, f2],
    )

    service = ParentService(data)
    service.add_parent("child", "B", "biological")

    by_parent = {
        link.parent_id: link.parentage_type
        for link in f2.parent_child_links
        if link.child_id == "child"
    }
    assert by_parent["A"] == "biological"
    assert by_parent["B"] == "biological"


def test_no_matching_couple_keeps_current_behaviour() -> None:
    """No couple family exists: B is added to the child's existing family, no move."""
    a = _person("A", "M")
    b = _person("B", "F")
    child = _person("child", "U")

    f1 = Family(
        id="F1",
        partners=[FamilyPartner(person_id="A", role="father")],
        children=["child"],
        parent_child_links=[_bio_link("child", "A")],
    )

    data = ProjectData(
        project=ProjectMetadata(title="t"),
        persons=[a, b, child],
        families=[f1],
    )

    service = ParentService(data)
    service.add_parent("child", "B", "biological")

    # Unchanged behaviour: B added to F1, no new/other family, F1 still lists child.
    assert [f.id for f in data.families] == ["F1"]
    partner_ids = {p.person_id for p in f1.partners}
    assert partner_ids == {"A", "B"}
    bio_parents = {
        link.parent_id
        for link in f1.parent_child_links
        if link.child_id == "child"
    }
    assert bio_parents == {"A", "B"}


def test_foster_does_not_move_families() -> None:
    """foster add_parent keeps current behaviour (no move into couple family)."""
    a = _person("A", "M")
    b = _person("B", "F")
    child = _person("child", "U")

    f1 = Family(
        id="F1",
        partners=[FamilyPartner(person_id="A", role="father")],
        children=["child"],
        parent_child_links=[_bio_link("child", "A")],
    )
    f2 = Family(
        id="F2",
        partners=[
            FamilyPartner(person_id="A", role="father"),
            FamilyPartner(person_id="B", role="mother"),
        ],
        children=[],
        parent_child_links=[],
    )

    data = ProjectData(
        project=ProjectMetadata(title="t"),
        persons=[a, b, child],
        families=[f1, f2],
    )

    service = ParentService(data)
    service.add_parent("child", "B", "foster")

    # No move: child stays in F1, F2 unchanged (no child).
    assert "F1" in {f.id for f in data.families}
    assert "child" in f1.children
    assert "child" not in f2.children
    # The foster link to B landed in F1 (existing family), not F2.
    f1_parents = {
        link.parent_id
        for link in f1.parent_child_links
        if link.child_id == "child"
    }
    assert f1_parents == {"A", "B"}


def test_adoptive_does_not_move_families() -> None:
    """adoptive add_parent keeps current behaviour (no move into couple family)."""
    a = _person("A", "M")
    b = _person("B", "F")
    child = _person("child", "U")

    f1 = Family(
        id="F1",
        partners=[FamilyPartner(person_id="A", role="father")],
        children=["child"],
        parent_child_links=[_bio_link("child", "A")],
    )
    f2 = Family(
        id="F2",
        partners=[
            FamilyPartner(person_id="A", role="father"),
            FamilyPartner(person_id="B", role="mother"),
        ],
        children=[],
        parent_child_links=[],
    )

    data = ProjectData(
        project=ProjectMetadata(title="t"),
        persons=[a, b, child],
        families=[f1, f2],
    )

    service = ParentService(data)
    service.add_parent("child", "B", "adoptive")

    assert "F1" in {f.id for f in data.families}
    assert "child" in f1.children
    assert "child" not in f2.children
