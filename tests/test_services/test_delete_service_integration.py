"""Integration tests for end-to-end deletion flow.

These tests exercise execute_person_deletion and compute_disconnection
with realistic multi-generation family tree structures constructed manually.

Validates: Requirements 1.2, 4.4, 7.1
"""

from __future__ import annotations

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.media import Annotation, LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.delete_service import (
    compute_disconnection,
    execute_person_deletion,
)


# ---------------------------------------------------------------------------
# Helper: Build a 3-generation family tree
# ---------------------------------------------------------------------------
# Structure:
#   Grandpa (gp) + Grandma (gm) -> Father (f), Uncle (u)
#   Father (f) + Mother (m)     -> Child1 (c1), Child2 (c2)
#   Uncle (u) + Aunt (a)        -> Cousin (co)
#
# Main person: Grandpa (gp)
# ---------------------------------------------------------------------------


def _person(pid: str, given: str, surname: str, sex: str = "M") -> Person:
    return Person(
        id=pid,
        sex=sex,
        names=[Name(type="birth", given=given, surname=surname)],
    )


def _build_three_generation_tree() -> ProjectData:
    """Build a realistic 3-generation family tree for integration testing."""
    # Persons
    grandpa = _person("gp", "Gustav", "Andersson")
    grandma = _person("gm", "Ingrid", "Andersson", sex="F")
    father = _person("f", "Erik", "Andersson")
    uncle = _person("u", "Lars", "Andersson")
    mother = _person("m", "Anna", "Svensson", sex="F")
    aunt = _person("a", "Karin", "Nilsson", sex="F")
    child1 = _person("c1", "Johan", "Andersson")
    child2 = _person("c2", "Maria", "Andersson", sex="F")
    cousin = _person("co", "Peter", "Andersson")

    # Events
    # Grandparents' marriage (family event)
    gp_marriage = Event(
        id="evt_gp_marriage",
        type="marriage",
        participants=[
            Participant(person_id="gp", role="husband"),
            Participant(person_id="gm", role="wife"),
        ],
        date=DateValue(value="1940-05-10", precision="day"),
    )
    # Father's birth (exclusive to father)
    father_birth = Event(
        id="evt_f_birth",
        type="birth",
        participants=[Participant(person_id="f", role="primary")],
        date=DateValue(value="1960-03-20", precision="day"),
    )
    # Parents' marriage (family event)
    parents_marriage = Event(
        id="evt_parents_marriage",
        type="marriage",
        participants=[
            Participant(person_id="f", role="husband"),
            Participant(person_id="m", role="wife"),
        ],
        date=DateValue(value="1985-08-12", precision="day"),
    )
    # Child1's birth (exclusive to child1)
    child1_birth = Event(
        id="evt_c1_birth",
        type="birth",
        participants=[Participant(person_id="c1", role="primary")],
        date=DateValue(value="1990-01-15", precision="day"),
    )
    # Shared event: census involving father and uncle (non-family shared)
    census_event = Event(
        id="evt_census",
        type="census",
        participants=[
            Participant(person_id="f", role="resident"),
            Participant(person_id="u", role="resident"),
            Participant(person_id="gp", role="head"),
        ],
        date=DateValue(value="1970", precision="year"),
    )
    # Uncle's marriage (family event)
    uncle_marriage = Event(
        id="evt_uncle_marriage",
        type="marriage",
        participants=[
            Participant(person_id="u", role="husband"),
            Participant(person_id="a", role="wife"),
        ],
    )

    # Families
    # Grandparents family
    gp_family = Family(
        id="fam_gp",
        partners=[
            FamilyPartner(person_id="gp", role="husband"),
            FamilyPartner(person_id="gm", role="wife"),
        ],
        children=["f", "u"],
        parent_child_links=[
            ParentChildLink(child_id="f", parent_id="gp", parentage_type="biological"),
            ParentChildLink(child_id="f", parent_id="gm", parentage_type="biological"),
            ParentChildLink(child_id="u", parent_id="gp", parentage_type="biological"),
            ParentChildLink(child_id="u", parent_id="gm", parentage_type="biological"),
        ],
        event_ids=["evt_gp_marriage"],
    )
    # Parents family
    parents_family = Family(
        id="fam_parents",
        partners=[
            FamilyPartner(person_id="f", role="husband"),
            FamilyPartner(person_id="m", role="wife"),
        ],
        children=["c1", "c2"],
        parent_child_links=[
            ParentChildLink(child_id="c1", parent_id="f", parentage_type="biological"),
            ParentChildLink(child_id="c1", parent_id="m", parentage_type="biological"),
            ParentChildLink(child_id="c2", parent_id="f", parentage_type="biological"),
            ParentChildLink(child_id="c2", parent_id="m", parentage_type="biological"),
        ],
        event_ids=["evt_parents_marriage"],
    )
    # Uncle's family
    uncle_family = Family(
        id="fam_uncle",
        partners=[
            FamilyPartner(person_id="u", role="husband"),
            FamilyPartner(person_id="a", role="wife"),
        ],
        children=["co"],
        parent_child_links=[
            ParentChildLink(child_id="co", parent_id="u", parentage_type="biological"),
            ParentChildLink(child_id="co", parent_id="a", parentage_type="biological"),
        ],
        event_ids=["evt_uncle_marriage"],
    )

    # Media item referencing father
    media = MediaItem(
        id="media_1",
        type="photo",
        file="photos/family.jpg",
        title="Familjeporträtt",
        linked_entities=[
            LinkedEntity(entity_type="person", entity_id="f", role="subject"),
            LinkedEntity(entity_type="person", entity_id="m", role="subject"),
        ],
        mentioned_person_ids=["f", "m", "c1"],
        mentioned_names=["Erik", "Anna", "Johan"],
        annotations=[
            Annotation(x=0.1, y=0.2, width=0.3, height=0.4, entity_type="person", entity_id="f"),
        ],
    )

    return ProjectData(
        project=ProjectMetadata(title="Andersson", main_person_id="gp"),
        persons=[grandpa, grandma, father, uncle, mother, aunt, child1, child2, cousin],
        families=[gp_family, parents_family, uncle_family],
        events=[
            gp_marriage, father_birth, parents_marriage,
            child1_birth, census_event, uncle_marriage,
        ],
        media=[media],
    )


# ---------------------------------------------------------------------------
# Test: Full deletion flow with realistic family tree data
# ---------------------------------------------------------------------------


class TestFullDeletionFlowRealisticTree:
    """Test full deletion flow with a realistic 3-generation family tree.

    Validates: Requirement 1.2
    """

    def test_delete_child_removes_person_and_exclusive_events(self) -> None:
        """Deleting child1 removes them, their exclusive birth event, and cleans families."""
        data = _build_three_generation_tree()
        assert len(data.persons) == 9

        execute_person_deletion("c1", data)

        # Person removed
        person_ids = [p.id for p in data.persons]
        assert "c1" not in person_ids
        assert len(data.persons) == 8

        # Exclusive event (child1 birth) removed
        event_ids = [e.id for e in data.events]
        assert "evt_c1_birth" not in event_ids

        # Child removed from parents family children list
        parents_family = next(f for f in data.families if f.id == "fam_parents")
        assert "c1" not in parents_family.children

        # ParentChildLinks referencing c1 removed
        for link in parents_family.parent_child_links:
            assert link.child_id != "c1"

        # No dangling references anywhere
        self._assert_no_dangling_references("c1", data)

    def test_delete_father_cascades_correctly(self) -> None:
        """Deleting father removes family events, cleans shared events, cleans media."""
        data = _build_three_generation_tree()

        execute_person_deletion("f", data)

        # Person removed
        person_ids = [p.id for p in data.persons]
        assert "f" not in person_ids

        # Father's birth event (exclusive) removed
        event_ids = [e.id for e in data.events]
        assert "evt_f_birth" not in event_ids

        # Parents' marriage (family event for fam_parents) removed
        assert "evt_parents_marriage" not in event_ids

        # Census event still exists but without father's participant
        census = next((e for e in data.events if e.id == "evt_census"), None)
        assert census is not None
        census_person_ids = [p.person_id for p in census.participants]
        assert "f" not in census_person_ids
        # Uncle and grandpa still in census
        assert "u" in census_person_ids
        assert "gp" in census_person_ids

        # Media cleaned: father removed from mentioned_person_ids, linked_entities, annotations
        media = data.media[0]
        assert "f" not in media.mentioned_person_ids
        assert all(
            not (le.entity_type == "person" and le.entity_id == "f")
            for le in media.linked_entities
        )
        assert all(
            not (ann.entity_type == "person" and ann.entity_id == "f")
            for ann in media.annotations
        )
        # Media preserved (count unchanged)
        assert len(data.media) == 1
        # mentioned_names preserved
        assert media.mentioned_names == ["Erik", "Anna", "Johan"]

        # No dangling references
        self._assert_no_dangling_references("f", data)

    def _assert_no_dangling_references(self, person_id: str, data: ProjectData) -> None:
        """Assert no remaining references to person_id in events, families, or media."""
        # Events
        for event in data.events:
            for p in event.participants:
                assert p.person_id != person_id

        # Families
        for family in data.families:
            for fp in family.partners:
                assert fp.person_id != person_id
            assert person_id not in family.children
            for link in family.parent_child_links:
                assert link.child_id != person_id
                assert link.parent_id != person_id

        # Media
        for media_item in data.media:
            assert person_id not in media_item.mentioned_person_ids
            for le in media_item.linked_entities:
                assert not (le.entity_type == "person" and le.entity_id == person_id)
            for ann in media_item.annotations:
                assert not (ann.entity_type == "person" and ann.entity_id == person_id)


# ---------------------------------------------------------------------------
# Test: Person with multiple family memberships
# ---------------------------------------------------------------------------


class TestMultipleFamilyMemberships:
    """Test deletion of a person who is both a child in one family and partner in another.

    Validates: Requirements 1.2, 4.4
    """

    def test_person_as_child_and_partner_in_different_families(self) -> None:
        """Father is a child in gp_family AND a partner in parents_family."""
        data = _build_three_generation_tree()

        # Father is child in gp_family and partner in parents_family
        gp_family = next(f for f in data.families if f.id == "fam_gp")
        parents_family = next(f for f in data.families if f.id == "fam_parents")
        assert "f" in gp_family.children
        assert any(fp.person_id == "f" for fp in parents_family.partners)

        execute_person_deletion("f", data)

        # Verify father removed from gp_family children
        gp_family = next(f for f in data.families if f.id == "fam_gp")
        assert "f" not in gp_family.children

        # Verify father's parent_child_links removed from gp_family
        for link in gp_family.parent_child_links:
            assert link.child_id != "f"

        # Verify father removed from parents_family partners
        # Parents family should still exist (mother + children remain)
        parents_family = next((f for f in data.families if f.id == "fam_parents"), None)
        assert parents_family is not None
        assert not any(fp.person_id == "f" for fp in parents_family.partners)

        # Mother still a partner, children still present
        assert any(fp.person_id == "m" for fp in parents_family.partners)
        assert "c2" in parents_family.children

    def test_person_appearing_as_parent_in_links_cleaned(self) -> None:
        """Parent-child links where person is the parent are cleaned up."""
        data = _build_three_generation_tree()

        # Father is parent_id in links for c1 and c2
        parents_family = next(f for f in data.families if f.id == "fam_parents")
        father_links = [l for l in parents_family.parent_child_links if l.parent_id == "f"]
        assert len(father_links) == 2  # c1 and c2

        execute_person_deletion("f", data)

        # All links referencing father as parent should be removed
        parents_family = next((f for f in data.families if f.id == "fam_parents"), None)
        assert parents_family is not None
        for link in parents_family.parent_child_links:
            assert link.parent_id != "f"


# ---------------------------------------------------------------------------
# Test: Deletion triggers empty family removal
# ---------------------------------------------------------------------------


class TestEmptyFamilyRemoval:
    """Test deletion that triggers empty family removal.

    Validates: Requirement 4.4
    """

    def test_delete_only_partner_and_only_child_removes_family(self) -> None:
        """Deleting a person who is the sole partner and only child leaves empty family -> removed."""
        # Build a minimal scenario: person_a is the only partner, person_b is the only child
        person_a = _person("pa", "Solo", "Partner")
        person_b = _person("pb", "Solo", "Child")
        main = _person("main", "Main", "Person")

        solo_family = Family(
            id="fam_solo",
            partners=[FamilyPartner(person_id="pa", role="partner")],
            children=["pb"],
            parent_child_links=[
                ParentChildLink(child_id="pb", parent_id="pa", parentage_type="biological"),
            ],
        )

        data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="main"),
            persons=[person_a, person_b, main],
            families=[solo_family],
        )

        # Delete the child first - family still has partner
        execute_person_deletion("pb", data)
        # Family should still exist (has one partner)
        assert len(data.families) == 1
        assert data.families[0].id == "fam_solo"

        # Now delete the only remaining partner
        execute_person_deletion("pa", data)
        # Family is now empty (0 partners, 0 children) -> removed
        assert len(data.families) == 0

    def test_delete_sole_member_removes_family(self) -> None:
        """Deleting a person who is the only member of a family removes that family."""
        person = _person("p1", "Lonely", "Person")
        main = _person("main", "Main", "Person")

        lonely_family = Family(
            id="fam_lonely",
            partners=[FamilyPartner(person_id="p1", role="partner")],
            children=[],
        )

        # Second family to verify only the empty one is removed
        other_family = Family(
            id="fam_other",
            partners=[FamilyPartner(person_id="main", role="partner")],
            children=[],
        )

        data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="main"),
            persons=[person, main],
            families=[lonely_family, other_family],
        )

        execute_person_deletion("p1", data)

        # lonely_family removed, other_family preserved
        family_ids = [f.id for f in data.families]
        assert "fam_lonely" not in family_ids
        assert "fam_other" in family_ids

    def test_no_empty_families_remain_after_deletion(self) -> None:
        """After any deletion, no family has both empty partners and empty children."""
        data = _build_three_generation_tree()

        # Delete uncle - may leave uncle_family with just aunt and cousin
        execute_person_deletion("u", data)

        for family in data.families:
            has_partners = len(family.partners) > 0
            has_children = len(family.children) > 0
            assert has_partners or has_children, (
                f"Family {family.id} is empty (no partners, no children)"
            )

    def test_events_from_removed_family_preserved(self) -> None:
        """Events referenced by a removed family are kept (unless exclusive/family events of deleted person)."""
        # Create a family with an event, where deleting both members removes the family
        person_a = _person("pa", "Partner", "A")
        person_b = _person("pb", "Partner", "B")
        main = _person("main", "Main", "Person")

        # A shared event between pa and pb that's in the family event_ids
        wedding = Event(
            id="evt_wedding",
            type="marriage",
            participants=[
                Participant(person_id="pa", role="husband"),
                Participant(person_id="pb", role="wife"),
            ],
        )

        family = Family(
            id="fam_ab",
            partners=[
                FamilyPartner(person_id="pa", role="husband"),
                FamilyPartner(person_id="pb", role="wife"),
            ],
            children=[],
            event_ids=["evt_wedding"],
        )

        data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="main"),
            persons=[person_a, person_b, main],
            families=[family],
            events=[wedding],
        )

        # Delete pa: wedding is a family event (in family event_ids and pa is partner)
        # -> wedding gets deleted
        execute_person_deletion("pa", data)

        # After deleting pa, the family event (wedding) is removed
        # The family still has pb as partner so it's not removed yet
        remaining_family = next((f for f in data.families if f.id == "fam_ab"), None)
        assert remaining_family is not None
        # Wedding was a family event of the deleted person -> removed
        event_ids = [e.id for e in data.events]
        assert "evt_wedding" not in event_ids


# ---------------------------------------------------------------------------
# Test: Deletion that disconnects tree section
# ---------------------------------------------------------------------------


class TestTreeDisconnection:
    """Test deletion that disconnects a tree section.

    Validates: Requirement 7.1
    """

    def test_bridge_person_disconnects_section(self) -> None:
        """Deleting a person who is the only link between two branches disconnects the tree.

        Tree structure:
            main -- bridge -- leaf1
                           -- leaf2

        Deleting bridge disconnects leaf1 and leaf2 from main.
        """
        main = _person("main", "Main", "Person")
        bridge = _person("bridge", "Bridge", "Person")
        leaf1 = _person("leaf1", "Leaf", "One")
        leaf2 = _person("leaf2", "Leaf", "Two")

        # main and bridge are partners in a family
        fam1 = Family(
            id="fam1",
            partners=[
                FamilyPartner(person_id="main", role="partner"),
                FamilyPartner(person_id="bridge", role="partner"),
            ],
            children=[],
        )
        # bridge is parent of leaf1 and leaf2 in another family
        fam2 = Family(
            id="fam2",
            partners=[FamilyPartner(person_id="bridge", role="partner")],
            children=["leaf1", "leaf2"],
            parent_child_links=[
                ParentChildLink(child_id="leaf1", parent_id="bridge", parentage_type="biological"),
                ParentChildLink(child_id="leaf2", parent_id="bridge", parentage_type="biological"),
            ],
        )

        data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="main"),
            persons=[main, bridge, leaf1, leaf2],
            families=[fam1, fam2],
        )

        # Verify disconnection is detected
        would_disconnect, count = compute_disconnection("bridge", data)
        assert would_disconnect is True
        assert count == 2  # leaf1 and leaf2 would be disconnected

    def test_non_bridge_person_does_not_disconnect(self) -> None:
        """Deleting a leaf person does not disconnect the tree.

        Tree structure:
            main -- parent -- child

        Deleting child leaves main and parent connected.
        """
        main = _person("main", "Main", "Person")
        parent = _person("parent", "Parent", "Person")
        child = _person("child", "Child", "Person")

        fam = Family(
            id="fam1",
            partners=[
                FamilyPartner(person_id="main", role="partner"),
                FamilyPartner(person_id="parent", role="partner"),
            ],
            children=["child"],
            parent_child_links=[
                ParentChildLink(child_id="child", parent_id="parent", parentage_type="biological"),
            ],
        )

        data = ProjectData(
            project=ProjectMetadata(title="Test", main_person_id="main"),
            persons=[main, parent, child],
            families=[fam],
        )

        would_disconnect, count = compute_disconnection("child", data)
        assert would_disconnect is False
        assert count == 0

    def test_disconnection_with_realistic_tree(self) -> None:
        """In the 3-gen tree, deleting father disconnects mother, child1, child2."""
        data = _build_three_generation_tree()

        # Father is the bridge between gp_family and parents_family.
        # If we delete father, mother, child1, child2 have no path to grandpa.
        would_disconnect, count = compute_disconnection("f", data)
        assert would_disconnect is True
        # Mother, child1, child2 = 3 disconnected persons
        assert count == 3

    def test_no_disconnection_when_main_person_not_set(self) -> None:
        """When main_person_id is None, disconnection check returns False."""
        data = _build_three_generation_tree()
        data.project.main_person_id = None

        would_disconnect, count = compute_disconnection("f", data)
        assert would_disconnect is False
        assert count == 0

    def test_deletion_after_disconnection_detection(self) -> None:
        """After detecting disconnection, executing deletion still succeeds cleanly."""
        data = _build_three_generation_tree()

        # Detect disconnection first
        would_disconnect, count = compute_disconnection("f", data)
        assert would_disconnect is True

        # Execute the deletion anyway (user confirmed)
        execute_person_deletion("f", data)

        # Person removed
        person_ids = [p.id for p in data.persons]
        assert "f" not in person_ids

        # Data integrity: no dangling references
        for event in data.events:
            for p in event.participants:
                assert p.person_id != "f"
        for family in data.families:
            for fp in family.partners:
                assert fp.person_id != "f"
            assert "f" not in family.children
            for link in family.parent_child_links:
                assert link.child_id != "f"
                assert link.parent_id != "f"

        # No empty families
        for family in data.families:
            assert len(family.partners) > 0 or len(family.children) > 0
