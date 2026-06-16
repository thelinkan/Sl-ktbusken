"""Tests for the RelationshipCalculator.

Contains both property-based tests (Property 8) and unit tests for
specific relationship scenarios (subtask 15.6).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.relationship.calculator import RelationshipCalculator, RelationshipPath
from slaktbusken.relationship.graph_builder import build_relationship_graph


# ---------------------------------------------------------------------------
# Helpers for building test families
# ---------------------------------------------------------------------------


def _make_person(pid: str, sex: str = "M") -> Person:
    """Create a minimal Person for testing."""
    return Person(
        id=pid, sex=sex, names=[Name(type="birth", given="Test", surname="Person")]
    )


def _make_project(*families_and_persons) -> ProjectData:
    """Create a ProjectData from persons and families."""
    persons = [x for x in families_and_persons if isinstance(x, Person)]
    families = [x for x in families_and_persons if isinstance(x, Family)]
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        families=families,
    )


# ---------------------------------------------------------------------------
# Property Test (Property 8): Connected persons have valid paths
# **Validates: Requirements 15.1, 15.2, 15.4**
# ---------------------------------------------------------------------------


@st.composite
def small_family_tree(draw: DrawFn):
    """Generate a small connected family tree for property testing.

    Creates 3-8 persons connected via parent-child links ensuring at least
    one connection between the first and last person.
    """
    num_persons = draw(st.integers(min_value=3, max_value=8))
    sexes = draw(st.lists(
        st.sampled_from(["M", "F"]),
        min_size=num_persons, max_size=num_persons
    ))
    persons = [_make_person(f"p{i}", sexes[i]) for i in range(num_persons)]

    # Create a chain of parent-child links to ensure connectivity
    families = []
    for i in range(num_persons - 1):
        parent = persons[i]
        child = persons[i + 1]
        # Determine parent role based on sex
        role = "father" if parent.sex == "M" else "mother"
        family = Family(
            id=f"fam_{i}",
            partners=[FamilyPartner(person_id=parent.id, role=role)],
            children=[child.id],
            parent_child_links=[
                ParentChildLink(
                    child_id=child.id,
                    parent_id=parent.id,
                    parentage_type="biological",
                )
            ],
        )
        families.append(family)

    # Pick two distinct persons to test
    idx_a = draw(st.integers(min_value=0, max_value=num_persons - 1))
    idx_b = draw(st.integers(min_value=0, max_value=num_persons - 1))
    assume(idx_a != idx_b)

    project = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        families=families,
    )
    return project, persons[idx_a].id, persons[idx_b].id


@given(data=small_family_tree())
@settings(max_examples=50, deadline=None)
def test_property_connected_persons_have_valid_paths(data):
    """Property 8: Connected persons have valid paths with correct edges.

    **Validates: Requirements 15.1, 15.2, 15.4**

    For any two connected persons in a family tree:
    - At least one path must be found
    - path_nodes starts with person_a_id and ends with person_b_id
    - Each adjacent pair in path_nodes has a valid edge in the graph
    - path_edges has length = len(path_nodes) - 1
    - Each edge type is one of 'parent', 'child', 'partner'
    """
    project, person_a_id, person_b_id = data

    calc = RelationshipCalculator(project)
    paths = calc.find_relationships(
        person_a_id, person_b_id,
        blood_priority=False,
        closest_only=False,
    )

    # Both persons are connected in our generated tree
    assert len(paths) > 0, (
        f"No path found between {person_a_id} and {person_b_id}"
    )

    graph = build_relationship_graph(project)

    for path in paths:
        # path_nodes starts with A, ends with B
        assert path.path_nodes[0] == person_a_id
        assert path.path_nodes[-1] == person_b_id

        # path_edges has correct length
        assert len(path.path_edges) == len(path.path_nodes) - 1

        # Each edge type is valid
        for edge_type in path.path_edges:
            assert edge_type in ("parent", "child", "partner")

        # Each adjacent pair has a valid edge in the graph
        for i in range(len(path.path_nodes) - 1):
            src = path.path_nodes[i]
            tgt = path.path_nodes[i + 1]
            edge_type = path.path_edges[i]
            edges = graph.get_edges(src)
            matching = [
                e for e in edges
                if e.target == tgt and e.edge_type == edge_type
            ]
            assert len(matching) > 0, (
                f"No {edge_type} edge from {src} to {tgt} in graph"
            )


# ---------------------------------------------------------------------------
# Unit Tests (Subtask 15.6): Specific relationship scenarios
# ---------------------------------------------------------------------------


class TestParentChild:
    """Tests for parent-child relationships."""

    def test_father_child(self):
        """Father is recognized as 'far'."""
        father = _make_person("father", "M")
        child = _make_person("child", "M")
        family = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="father", role="father")],
            children=["child"],
            parent_child_links=[
                ParentChildLink(child_id="child", parent_id="father",
                                parentage_type="biological")
            ],
        )
        project = _make_project(father, child, family)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("child", "father")

        assert len(paths) >= 1
        assert paths[0].swedish_term == "far"
        assert paths[0].relationship_type == "blood"
        assert paths[0].path_nodes[0] == "child"
        assert paths[0].path_nodes[-1] == "father"

    def test_mother_child(self):
        """Mother is recognized as 'mor'."""
        mother = _make_person("mother", "F")
        child = _make_person("child", "F")
        family = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="mother", role="mother")],
            children=["child"],
            parent_child_links=[
                ParentChildLink(child_id="child", parent_id="mother",
                                parentage_type="biological")
            ],
        )
        project = _make_project(mother, child, family)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("child", "mother")

        assert len(paths) >= 1
        assert paths[0].swedish_term == "mor"

    def test_son(self):
        """Son is recognized as 'son'."""
        father = _make_person("father", "M")
        son = _make_person("son", "M")
        family = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="father", role="father")],
            children=["son"],
            parent_child_links=[
                ParentChildLink(child_id="son", parent_id="father",
                                parentage_type="biological")
            ],
        )
        project = _make_project(father, son, family)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("father", "son")

        assert len(paths) >= 1
        assert paths[0].swedish_term == "son"


class TestSibling:
    """Tests for sibling relationships."""

    def test_brother(self):
        """Brother is recognized as 'bror'."""
        father = _make_person("father", "M")
        child_a = _make_person("child_a", "M")
        child_b = _make_person("child_b", "M")
        family = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="father", role="father")],
            children=["child_a", "child_b"],
            parent_child_links=[
                ParentChildLink(child_id="child_a", parent_id="father",
                                parentage_type="biological"),
                ParentChildLink(child_id="child_b", parent_id="father",
                                parentage_type="biological"),
            ],
        )
        project = _make_project(father, child_a, child_b, family)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("child_a", "child_b")

        assert len(paths) >= 1
        assert paths[0].swedish_term == "bror"
        assert paths[0].relationship_type == "blood"

    def test_sister(self):
        """Sister is recognized as 'syster'."""
        father = _make_person("father", "M")
        child_a = _make_person("child_a", "M")
        child_b = _make_person("child_b", "F")
        family = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="father", role="father")],
            children=["child_a", "child_b"],
            parent_child_links=[
                ParentChildLink(child_id="child_a", parent_id="father",
                                parentage_type="biological"),
                ParentChildLink(child_id="child_b", parent_id="father",
                                parentage_type="biological"),
            ],
        )
        project = _make_project(father, child_a, child_b, family)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("child_a", "child_b")

        assert len(paths) >= 1
        assert paths[0].swedish_term == "syster"


class TestUncleAunt:
    """Tests for uncle/aunt relationships."""

    def test_uncle_farbror_morbror(self):
        """Uncle is recognized as 'farbror/morbror'."""
        grandfather = _make_person("grandpa", "M")
        father = _make_person("father", "M")
        uncle = _make_person("uncle", "M")
        child = _make_person("child", "M")

        # Grandfather's family: father and uncle are siblings
        fam1 = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="grandpa", role="father")],
            children=["father", "uncle"],
            parent_child_links=[
                ParentChildLink(child_id="father", parent_id="grandpa",
                                parentage_type="biological"),
                ParentChildLink(child_id="uncle", parent_id="grandpa",
                                parentage_type="biological"),
            ],
        )
        # Father's family: child
        fam2 = Family(
            id="fam2",
            partners=[FamilyPartner(person_id="father", role="father")],
            children=["child"],
            parent_child_links=[
                ParentChildLink(child_id="child", parent_id="father",
                                parentage_type="biological"),
            ],
        )
        project = _make_project(
            grandfather, father, uncle, child, fam1, fam2
        )
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("child", "uncle")

        assert len(paths) >= 1
        assert paths[0].swedish_term == "farbror/morbror"
        assert paths[0].relationship_type == "blood"

    def test_aunt_faster_moster(self):
        """Aunt is recognized as 'faster/moster'."""
        grandfather = _make_person("grandpa", "M")
        father = _make_person("father", "M")
        aunt = _make_person("aunt", "F")
        child = _make_person("child", "M")

        fam1 = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="grandpa", role="father")],
            children=["father", "aunt"],
            parent_child_links=[
                ParentChildLink(child_id="father", parent_id="grandpa",
                                parentage_type="biological"),
                ParentChildLink(child_id="aunt", parent_id="grandpa",
                                parentage_type="biological"),
            ],
        )
        fam2 = Family(
            id="fam2",
            partners=[FamilyPartner(person_id="father", role="father")],
            children=["child"],
            parent_child_links=[
                ParentChildLink(child_id="child", parent_id="father",
                                parentage_type="biological"),
            ],
        )
        project = _make_project(
            grandfather, father, aunt, child, fam1, fam2
        )
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("child", "aunt")

        assert len(paths) >= 1
        assert paths[0].swedish_term == "faster/moster"


class TestCousin:
    """Tests for cousin relationships."""

    def test_first_cousin_kusin(self):
        """First cousin (kusin/tvåmänning)."""
        grandpa = _make_person("grandpa", "M")
        parent_a = _make_person("parent_a", "M")
        parent_b = _make_person("parent_b", "M")
        cousin_a = _make_person("cousin_a", "M")
        cousin_b = _make_person("cousin_b", "M")

        fam_gp = Family(
            id="fam_gp",
            partners=[FamilyPartner(person_id="grandpa", role="father")],
            children=["parent_a", "parent_b"],
            parent_child_links=[
                ParentChildLink(child_id="parent_a", parent_id="grandpa",
                                parentage_type="biological"),
                ParentChildLink(child_id="parent_b", parent_id="grandpa",
                                parentage_type="biological"),
            ],
        )
        fam_a = Family(
            id="fam_a",
            partners=[FamilyPartner(person_id="parent_a", role="father")],
            children=["cousin_a"],
            parent_child_links=[
                ParentChildLink(child_id="cousin_a", parent_id="parent_a",
                                parentage_type="biological"),
            ],
        )
        fam_b = Family(
            id="fam_b",
            partners=[FamilyPartner(person_id="parent_b", role="father")],
            children=["cousin_b"],
            parent_child_links=[
                ParentChildLink(child_id="cousin_b", parent_id="parent_b",
                                parentage_type="biological"),
            ],
        )
        project = _make_project(
            grandpa, parent_a, parent_b, cousin_a, cousin_b,
            fam_gp, fam_a, fam_b
        )
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("cousin_a", "cousin_b")

        assert len(paths) >= 1
        assert paths[0].swedish_term == "kusin"
        assert paths[0].generations_a == 2
        assert paths[0].generations_b == 2


class TestRemovedCousin:
    """Tests for removed cousin relationships."""

    def test_second_cousin_once_removed(self):
        """Second cousin once removed: tremänning, ett släktled bort."""
        # Build: great-grandpa -> grandpa_a, grandpa_b
        #        grandpa_a -> parent_a -> person_a
        #        grandpa_b -> parent_b -> cousin_b -> child_b
        # person_a and child_b: gen_a=3, gen_b=4 -> min=3 (tremänning), removal=1
        ggp = _make_person("ggp", "M")
        gp_a = _make_person("gp_a", "M")
        gp_b = _make_person("gp_b", "M")
        pa = _make_person("pa", "M")
        pb = _make_person("pb", "M")
        person_a = _make_person("person_a", "M")
        cousin_b = _make_person("cousin_b", "M")
        child_b = _make_person("child_b", "M")

        fam_ggp = Family(
            id="fam_ggp",
            partners=[FamilyPartner(person_id="ggp", role="father")],
            children=["gp_a", "gp_b"],
            parent_child_links=[
                ParentChildLink(child_id="gp_a", parent_id="ggp",
                                parentage_type="biological"),
                ParentChildLink(child_id="gp_b", parent_id="ggp",
                                parentage_type="biological"),
            ],
        )
        fam_gpa = Family(
            id="fam_gpa",
            partners=[FamilyPartner(person_id="gp_a", role="father")],
            children=["pa"],
            parent_child_links=[
                ParentChildLink(child_id="pa", parent_id="gp_a",
                                parentage_type="biological"),
            ],
        )
        fam_gpb = Family(
            id="fam_gpb",
            partners=[FamilyPartner(person_id="gp_b", role="father")],
            children=["pb"],
            parent_child_links=[
                ParentChildLink(child_id="pb", parent_id="gp_b",
                                parentage_type="biological"),
            ],
        )
        fam_pa = Family(
            id="fam_pa",
            partners=[FamilyPartner(person_id="pa", role="father")],
            children=["person_a"],
            parent_child_links=[
                ParentChildLink(child_id="person_a", parent_id="pa",
                                parentage_type="biological"),
            ],
        )
        fam_pb = Family(
            id="fam_pb",
            partners=[FamilyPartner(person_id="pb", role="father")],
            children=["cousin_b"],
            parent_child_links=[
                ParentChildLink(child_id="cousin_b", parent_id="pb",
                                parentage_type="biological"),
            ],
        )
        fam_cb = Family(
            id="fam_cb",
            partners=[FamilyPartner(person_id="cousin_b", role="father")],
            children=["child_b"],
            parent_child_links=[
                ParentChildLink(child_id="child_b", parent_id="cousin_b",
                                parentage_type="biological"),
            ],
        )
        project = _make_project(
            ggp, gp_a, gp_b, pa, pb, person_a, cousin_b, child_b,
            fam_ggp, fam_gpa, fam_gpb, fam_pa, fam_pb, fam_cb
        )
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("person_a", "child_b")

        assert len(paths) >= 1
        assert paths[0].swedish_term == "tremänning, ett släktled bort"


class TestSpouseOfDistantRelative:
    """Tests for spouse-of-distant-relative: gift med X."""

    def test_gift_med_femmanning_tva_slaktled_bort(self):
        """Spouse of a fourth cousin twice removed: gift med femmänning, två släktled bort.

        We need: person_a related to person_x as femmänning, två släktled bort,
        and person_b is partner of person_x.
        femmänning, två släktled bort: min(gen_a, gen_b)=5, removal=2
        So gen_a=5, gen_b=7 (or gen_a=7, gen_b=5).
        Let's use gen_a=5 from person_a to common ancestor,
        gen_b=7 from person_x to common ancestor.
        Then person_b is partner of person_x.
        """
        # Build a deep tree: ancestor -> 5 gens down to person_a
        #                     ancestor -> 7 gens down to person_x
        #                     person_x is partner of person_b
        persons = []
        families = []

        ancestor = _make_person("anc", "M")
        persons.append(ancestor)

        # Branch A: ancestor -> a1 -> a2 -> a3 -> a4 -> person_a (5 gens)
        prev = "anc"
        branch_a_ids = []
        for i in range(1, 5):
            pid = f"a{i}"
            persons.append(_make_person(pid, "M"))
            branch_a_ids.append(pid)
            families.append(Family(
                id=f"fam_a{i}",
                partners=[FamilyPartner(person_id=prev, role="father")],
                children=[pid],
                parent_child_links=[
                    ParentChildLink(child_id=pid, parent_id=prev,
                                    parentage_type="biological")
                ],
            ))
            prev = pid

        person_a = _make_person("person_a", "M")
        persons.append(person_a)
        families.append(Family(
            id="fam_a_last",
            partners=[FamilyPartner(person_id=prev, role="father")],
            children=["person_a"],
            parent_child_links=[
                ParentChildLink(child_id="person_a", parent_id=prev,
                                parentage_type="biological")
            ],
        ))

        # Branch B: ancestor -> b1 -> b2 -> b3 -> b4 -> b5 -> b6 -> person_x (7 gens)
        prev = "anc"
        for i in range(1, 7):
            pid = f"b{i}"
            persons.append(_make_person(pid, "M"))
            families.append(Family(
                id=f"fam_b{i}",
                partners=[FamilyPartner(person_id=prev, role="father")],
                children=[pid],
                parent_child_links=[
                    ParentChildLink(child_id=pid, parent_id=prev,
                                    parentage_type="biological")
                ],
            ))
            prev = pid

        person_x = _make_person("person_x", "M")
        persons.append(person_x)
        families.append(Family(
            id="fam_b_last",
            partners=[FamilyPartner(person_id=prev, role="father")],
            children=["person_x"],
            parent_child_links=[
                ParentChildLink(child_id="person_x", parent_id=prev,
                                parentage_type="biological")
            ],
        ))

        # person_b is partner of person_x
        person_b = _make_person("person_b", "F")
        persons.append(person_b)
        families.append(Family(
            id="fam_partner",
            partners=[
                FamilyPartner(person_id="person_x", role="husband"),
                FamilyPartner(person_id="person_b", role="wife"),
            ],
            children=[],
            parent_child_links=[],
        ))

        project = _make_project(*persons, *families)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships(
            "person_a", "person_b",
            blood_priority=False, closest_only=False,
        )

        # Should find a path through the partner link
        assert len(paths) >= 1
        # The closest path to person_b should go via person_x's partner edge
        partner_paths = [
            p for p in paths if "partner" in p.path_edges
        ]
        assert len(partner_paths) >= 1
        # The term should be "gift med femmänning, två släktled bort"
        assert partner_paths[0].swedish_term == "gift med femmänning, två släktled bort"


class TestInLaw:
    """Tests for in-law relationships."""

    def test_svarfar(self):
        """Father-in-law is recognized as 'svärfar'."""
        father_in_law = _make_person("fil", "M")
        spouse = _make_person("spouse", "F")
        person_a = _make_person("person_a", "M")

        # father_in_law is parent of spouse
        fam1 = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="fil", role="father")],
            children=["spouse"],
            parent_child_links=[
                ParentChildLink(child_id="spouse", parent_id="fil",
                                parentage_type="biological")
            ],
        )
        # person_a is partner of spouse
        fam2 = Family(
            id="fam2",
            partners=[
                FamilyPartner(person_id="person_a", role="husband"),
                FamilyPartner(person_id="spouse", role="wife"),
            ],
            children=[],
            parent_child_links=[],
        )
        project = _make_project(
            father_in_law, spouse, person_a, fam1, fam2
        )
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships(
            "person_a", "fil", blood_priority=False, closest_only=False
        )

        assert len(paths) >= 1
        partner_paths = [p for p in paths if "partner" in p.path_edges]
        assert len(partner_paths) >= 1
        assert partner_paths[0].swedish_term == "svärfar"

    def test_svarmor(self):
        """Mother-in-law is recognized as 'svärmor'."""
        mother_in_law = _make_person("mil", "F")
        spouse = _make_person("spouse", "M")
        person_a = _make_person("person_a", "F")

        fam1 = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="mil", role="mother")],
            children=["spouse"],
            parent_child_links=[
                ParentChildLink(child_id="spouse", parent_id="mil",
                                parentage_type="biological")
            ],
        )
        fam2 = Family(
            id="fam2",
            partners=[
                FamilyPartner(person_id="spouse", role="husband"),
                FamilyPartner(person_id="person_a", role="wife"),
            ],
            children=[],
            parent_child_links=[],
        )
        project = _make_project(
            mother_in_law, spouse, person_a, fam1, fam2
        )
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships(
            "person_a", "mil", blood_priority=False, closest_only=False
        )

        assert len(paths) >= 1
        partner_paths = [p for p in paths if "partner" in p.path_edges]
        assert len(partner_paths) >= 1
        assert partner_paths[0].swedish_term == "svärmor"


class TestHalfSibling:
    """Tests for half-sibling relationships."""

    def test_half_sibling_same_father(self):
        """Half-siblings sharing a father are still 'bror'/'syster' (blood)."""
        father = _make_person("father", "M")
        mother_a = _make_person("mother_a", "F")
        mother_b = _make_person("mother_b", "F")
        child_a = _make_person("child_a", "M")
        child_b = _make_person("child_b", "F")

        fam1 = Family(
            id="fam1",
            partners=[
                FamilyPartner(person_id="father", role="father"),
                FamilyPartner(person_id="mother_a", role="mother"),
            ],
            children=["child_a"],
            parent_child_links=[
                ParentChildLink(child_id="child_a", parent_id="father",
                                parentage_type="biological"),
                ParentChildLink(child_id="child_a", parent_id="mother_a",
                                parentage_type="biological"),
            ],
        )
        fam2 = Family(
            id="fam2",
            partners=[
                FamilyPartner(person_id="father", role="father"),
                FamilyPartner(person_id="mother_b", role="mother"),
            ],
            children=["child_b"],
            parent_child_links=[
                ParentChildLink(child_id="child_b", parent_id="father",
                                parentage_type="biological"),
                ParentChildLink(child_id="child_b", parent_id="mother_b",
                                parentage_type="biological"),
            ],
        )
        project = _make_project(
            father, mother_a, mother_b, child_a, child_b, fam1, fam2
        )
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("child_a", "child_b")

        assert len(paths) >= 1
        # Half-siblings through shared father are siblings (blood)
        assert paths[0].swedish_term == "syster"
        assert paths[0].relationship_type == "blood"


class TestNoConnection:
    """Tests for no connection found."""

    def test_no_connection(self):
        """Two unrelated persons return empty result."""
        person_a = _make_person("person_a", "M")
        person_b = _make_person("person_b", "F")

        # No family connecting them
        project = _make_project(person_a, person_b)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("person_a", "person_b")

        assert paths == []

    def test_person_not_in_data(self):
        """Person not in graph returns empty result."""
        person_a = _make_person("person_a", "M")
        project = _make_project(person_a)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("person_a", "nonexistent")

        assert paths == []


class TestBloodPriorityFallback:
    """Tests for blood_priority mode fallback behavior."""

    def test_blood_priority_returns_only_blood_when_exists(self):
        """When blood paths exist, blood_priority=True returns only blood."""
        father = _make_person("father", "M")
        child = _make_person("child", "M")
        family = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="father", role="father")],
            children=["child"],
            parent_child_links=[
                ParentChildLink(child_id="child", parent_id="father",
                                parentage_type="biological"),
            ],
        )
        project = _make_project(father, child, family)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships(
            "child", "father", blood_priority=True
        )

        assert len(paths) >= 1
        assert all(p.relationship_type == "blood" for p in paths)

    def test_blood_priority_fallback_to_nonblood(self):
        """When no blood path exists, blood_priority returns closest non-blood."""
        # Two persons connected only through adoption (non-blood)
        adoptive_parent = _make_person("adopt_parent", "M")
        child = _make_person("child", "M")
        family = Family(
            id="fam1",
            partners=[FamilyPartner(person_id="adopt_parent", role="father")],
            children=["child"],
            parent_child_links=[
                ParentChildLink(child_id="child", parent_id="adopt_parent",
                                parentage_type="adoptive"),
            ],
        )
        project = _make_project(adoptive_parent, child, family)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships(
            "child", "adopt_parent", blood_priority=True
        )

        # Should return exactly one non-blood path (fallback)
        assert len(paths) == 1
        assert paths[0].relationship_type != "blood"

    def test_blood_priority_no_path_at_all(self):
        """When no path at all exists, returns empty list."""
        person_a = _make_person("a", "M")
        person_b = _make_person("b", "F")
        project = _make_project(person_a, person_b)
        calc = RelationshipCalculator(project)
        paths = calc.find_relationships("a", "b", blood_priority=True)

        assert paths == []
