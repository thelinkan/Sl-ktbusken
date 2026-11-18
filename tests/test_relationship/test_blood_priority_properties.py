"""Property test for blood priority and relationship classification.

Feature: foster-parents, Property 6: any all-blood path => no non-blood path
returned; a mixed path classifies as blood at the path level; a pure foster
connection classifies as "foster"; a pure adoptive connection classifies as
"adoption".

**Validates: Requirements 8.2, 8.3, 9.1, 9.3, 9.4**

The property has two complementary facets:

FACET A - classification mapping, exercised directly against
``RelationshipCalculator._classify_relationship_type`` over lists of parentage
types. It pins the precedence independently of any graph:

    all biological        -> "blood"
    else any "adoptive"   -> "adoption"
    else any "foster"     -> "foster"
    else                  -> "legal"

FACET B - blood priority at the PATH level, exercised against
``RelationshipCalculator.find_relationships(blood_priority=True)`` over small
hand-built family graphs. When a blood path and a non-blood (foster/adoptive)
path both connect two people, only blood paths come back; when only a non-blood
path exists, exactly one path comes back and its ``relationship_type`` is
"foster" for a pure-foster connection and "adoption" for a pure-adoptive one.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.relationship.calculator import RelationshipCalculator


# ---------------------------------------------------------------------------
# Helpers (same conventions as tests/test_relationship/test_calculator.py)
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


def _calc(*families_and_persons) -> RelationshipCalculator:
    """Build a calculator over a minimal project."""
    return RelationshipCalculator(_make_project(*families_and_persons))


def _classify_expected(parentage_types: list[str]) -> str:
    """Independently derived classification precedence (Property 6, FACET A).

    This is deliberately a separate implementation of the specified precedence,
    so the test pins the behaviour rather than mirroring production structure.
    """
    if not parentage_types:
        return "legal"
    if all(pt == "biological" for pt in parentage_types):
        return "blood"
    if any(pt == "adoptive" for pt in parentage_types):
        return "adoption"
    if any(pt == "foster" for pt in parentage_types):
        return "foster"
    return "legal"


# ---------------------------------------------------------------------------
# FACET A: classification mapping over _classify_relationship_type
# ---------------------------------------------------------------------------

_PARENTAGE_TYPES = ["biological", "foster", "adoptive", "legal", "step"]


@given(
    parentage_types=st.lists(
        st.sampled_from(_PARENTAGE_TYPES), min_size=1, max_size=6
    )
)
@settings(max_examples=100, deadline=None)
def test_classification_precedence(parentage_types: list[str]) -> None:
    """FACET A: _classify_relationship_type honours the specified precedence.

    Feature: foster-parents, Property 6 (classification facet): for any
    non-empty mix of parentage types, all-blood => "blood", else adoptive =>
    "adoption", else foster => "foster", else "legal". This encodes
    "mixed => (adoptive -> adoption / foster -> foster)", "pure foster =>
    foster", "pure adoptive => adoption", and all-blood => blood.

    **Validates: Requirements 8.2, 8.3, 9.1, 9.3, 9.4**
    """
    calc = _calc(_make_person("p0", "M"))
    expected = _classify_expected(parentage_types)
    assert calc._classify_relationship_type(parentage_types) == expected


# ---------------------------------------------------------------------------
# FACET B: blood priority at the path level over find_relationships
# ---------------------------------------------------------------------------


def _build_competing_graph(non_blood_type: str, with_blood_path: bool):
    """Build a small graph linking ``child`` and ``grandparent``.

    ``child`` always has a non-blood (foster/adoptive) parent ``nb_parent``.
    When ``with_blood_path`` is True, ``child`` also has a *biological* parent
    ``bio_parent`` whose own biological parent is ``grandparent``; and
    ``nb_parent``'s biological parent is also ``grandparent`` (so the two
    parents are blood-related). That makes a pure-blood path
    child -> bio_parent -> grandparent available to compete with the non-blood
    path child -(nb)-> nb_parent -> grandparent.

    When ``with_blood_path`` is False, ``child`` has ONLY the non-blood parent,
    so the only connection between ``child`` and ``nb_parent`` is the single
    non-blood edge.

    Returns ``(project, child_id, target_id)`` where ``target_id`` is
    ``grandparent`` when a blood path competes and ``nb_parent`` otherwise.
    """
    grandparent = _make_person("grandparent", "M")
    nb_parent = _make_person("nb_parent", "M")
    child = _make_person("child", "M")

    persons = [grandparent, nb_parent, child]
    families = []

    # grandparent -> nb_parent (biological), so nb_parent has a blood lineage.
    families.append(
        Family(
            id="fam_gp_nb",
            partners=[FamilyPartner(person_id="grandparent", role="father")],
            children=["nb_parent"],
            parent_child_links=[
                ParentChildLink(
                    child_id="nb_parent",
                    parent_id="grandparent",
                    parentage_type="biological",
                )
            ],
        )
    )

    # child -(non-blood)-> nb_parent: the non-blood placement link.
    families.append(
        Family(
            id="fam_nb",
            partners=[FamilyPartner(person_id="nb_parent", role="father")],
            children=["child"],
            parent_child_links=[
                ParentChildLink(
                    child_id="child",
                    parent_id="nb_parent",
                    parentage_type=non_blood_type,
                )
            ],
        )
    )

    if with_blood_path:
        # child also has a biological parent whose parent is grandparent,
        # giving a competing all-blood path child -> bio_parent -> grandparent.
        bio_parent = _make_person("bio_parent", "M")
        persons.append(bio_parent)
        families.append(
            Family(
                id="fam_gp_bio",
                partners=[FamilyPartner(person_id="grandparent", role="father")],
                children=["bio_parent"],
                parent_child_links=[
                    ParentChildLink(
                        child_id="bio_parent",
                        parent_id="grandparent",
                        parentage_type="biological",
                    )
                ],
            )
        )
        families.append(
            Family(
                id="fam_bio",
                partners=[FamilyPartner(person_id="bio_parent", role="father")],
                children=["child"],
                parent_child_links=[
                    ParentChildLink(
                        child_id="child",
                        parent_id="bio_parent",
                        parentage_type="biological",
                    )
                ],
            )
        )
        target_id = "grandparent"
    else:
        target_id = "nb_parent"

    project = _make_project(*persons, *families)
    return project, "child", target_id


@given(
    non_blood_type=st.sampled_from(["foster", "adoptive"]),
    with_blood_path=st.booleans(),
)
@settings(max_examples=100, deadline=None)
def test_blood_priority_path_selection(
    non_blood_type: str, with_blood_path: bool
) -> None:
    """FACET B: blood priority drops non-blood paths when a blood path exists.

    Feature: foster-parents, Property 6 (path facet): with blood_priority=True,
    when a blood path competes with a non-blood path, every returned path is
    "blood" (no path traverses a foster/adoptive edge); when only a non-blood
    path exists, a single non-blood path is returned whose relationship_type is
    "foster" for a pure-foster connection and "adoption" for a pure-adoptive
    connection.

    **Validates: Requirements 8.2, 8.3, 9.1, 9.3, 9.4**
    """
    project, child_id, target_id = _build_competing_graph(
        non_blood_type, with_blood_path
    )
    calc = RelationshipCalculator(project)
    paths = calc.find_relationships(
        child_id, target_id, blood_priority=True, closest_only=False
    )

    assert paths, "expected at least one path between the two persons"

    if with_blood_path:
        # Any all-blood path => only blood paths returned (Req 8.2/8.3/9.3).
        assert all(p.relationship_type == "blood" for p in paths)
    else:
        # Only a non-blood path exists => a single non-blood path, classified
        # per the non-blood type (Req 9.1 foster, plus the adoptive branch).
        assert len(paths) == 1
        expected_type = "foster" if non_blood_type == "foster" else "adoption"
        assert paths[0].relationship_type == expected_type
