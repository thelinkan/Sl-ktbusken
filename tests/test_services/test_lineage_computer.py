"""Unit tests for LineageComputer.

Tests cover:
- get_ancestors BFS traversal through family parent links
- get_descendants BFS traversal through family child links
- Exclusion of the queried person from results
- Cycle detection (circular references)
- Empty results for persons with no ancestors/descendants

Requirements: 3.1, 3.4, 4.1, 4.4
"""

from __future__ import annotations

import logging

import pytest

from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.lineage_computer import LineageComputer


def _make_project(families: list[Family]) -> ProjectData:
    """Helper to create a ProjectData with given families."""
    return ProjectData(families=families, project=ProjectMetadata(title="Test"))


@pytest.fixture
def three_generation_project() -> ProjectData:
    """A three-generation family tree.

    grandpa + grandma -> parent
    parent + spouse -> child
    """
    families = [
        Family(
            id="f1",
            partners=[
                FamilyPartner("grandpa", "father"),
                FamilyPartner("grandma", "mother"),
            ],
            children=["parent"],
        ),
        Family(
            id="f2",
            partners=[
                FamilyPartner("parent", "father"),
                FamilyPartner("spouse", "mother"),
            ],
            children=["child"],
        ),
    ]
    return _make_project(families)


class TestGetAncestors:
    """Tests for LineageComputer.get_ancestors."""

    def test_direct_parents(self, three_generation_project: ProjectData) -> None:
        lc = LineageComputer(three_generation_project)
        ancestors = lc.get_ancestors("child")
        assert "parent" in ancestors
        assert "spouse" in ancestors

    def test_grandparents_included(self, three_generation_project: ProjectData) -> None:
        lc = LineageComputer(three_generation_project)
        ancestors = lc.get_ancestors("child")
        assert "grandpa" in ancestors
        assert "grandma" in ancestors

    def test_person_not_in_own_ancestors(
        self, three_generation_project: ProjectData
    ) -> None:
        lc = LineageComputer(three_generation_project)
        ancestors = lc.get_ancestors("child")
        assert "child" not in ancestors

    def test_no_ancestors_for_root(self, three_generation_project: ProjectData) -> None:
        lc = LineageComputer(three_generation_project)
        assert lc.get_ancestors("grandpa") == set()

    def test_empty_families(self) -> None:
        project = _make_project([])
        lc = LineageComputer(project)
        assert lc.get_ancestors("anyone") == set()

    def test_isolated_person_no_families(self) -> None:
        """A person not in any family returns empty ancestors.

        Other families exist in the project, but the queried person
        is not referenced in any of them.
        """
        families = [
            Family(
                id="f1",
                partners=[FamilyPartner("other_parent", "father")],
                children=["other_child"],
            ),
        ]
        project = _make_project(families)
        lc = LineageComputer(project)
        assert lc.get_ancestors("isolated_person") == set()

    def test_sibling_branches_ancestors(self) -> None:
        """From a grandchild, ancestors include all upward through sibling branches.

        Structure:
          grandparent -> child_a, child_b
          child_a -> grandchild_a
        Ancestors of grandchild_a should be child_a and grandparent.
        """
        families = [
            Family(
                id="f1",
                partners=[FamilyPartner("grandparent", "father")],
                children=["child_a", "child_b"],
            ),
            Family(
                id="f2",
                partners=[FamilyPartner("child_a", "father")],
                children=["grandchild_a"],
            ),
        ]
        project = _make_project(families)
        lc = LineageComputer(project)
        ancestors = lc.get_ancestors("grandchild_a")
        assert ancestors == {"child_a", "grandparent"}

    def test_cycle_detection_ancestors(self, caplog: pytest.LogCaptureFixture) -> None:
        """Circular parent references should not cause infinite loops."""
        # A -> B -> C -> B (3-node cycle triggers warning on re-visiting B)
        families = [
            Family(
                id="f1",
                partners=[FamilyPartner("B", "father")],
                children=["A"],
            ),
            Family(
                id="f2",
                partners=[FamilyPartner("C", "father")],
                children=["B"],
            ),
            Family(
                id="f3",
                partners=[FamilyPartner("B", "father")],
                children=["C"],
            ),
        ]
        project = _make_project(families)
        lc = LineageComputer(project)

        with caplog.at_level(logging.WARNING):
            ancestors = lc.get_ancestors("A")

        assert "B" in ancestors
        assert "C" in ancestors
        assert "A" not in ancestors
        assert "Cycle detected" in caplog.text


class TestGetDescendants:
    """Tests for LineageComputer.get_descendants."""

    def test_direct_children(self, three_generation_project: ProjectData) -> None:
        lc = LineageComputer(three_generation_project)
        descendants = lc.get_descendants("parent")
        assert "child" in descendants

    def test_grandchildren_included(self) -> None:
        families = [
            Family(
                id="f1",
                partners=[FamilyPartner("grandpa", "father")],
                children=["parent"],
            ),
            Family(
                id="f2",
                partners=[FamilyPartner("parent", "father")],
                children=["child"],
            ),
        ]
        project = _make_project(families)
        lc = LineageComputer(project)
        descendants = lc.get_descendants("grandpa")
        assert descendants == {"parent", "child"}

    def test_person_not_in_own_descendants(
        self, three_generation_project: ProjectData
    ) -> None:
        lc = LineageComputer(three_generation_project)
        descendants = lc.get_descendants("grandpa")
        assert "grandpa" not in descendants

    def test_no_descendants_for_leaf(
        self, three_generation_project: ProjectData
    ) -> None:
        lc = LineageComputer(three_generation_project)
        assert lc.get_descendants("child") == set()

    def test_empty_families(self) -> None:
        project = _make_project([])
        lc = LineageComputer(project)
        assert lc.get_descendants("anyone") == set()

    def test_cycle_detection_descendants(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Circular child references should not cause infinite loops."""
        # A -> B -> C -> B (3-node cycle triggers warning on re-visiting B)
        families = [
            Family(
                id="f1",
                partners=[FamilyPartner("A", "father")],
                children=["B"],
            ),
            Family(
                id="f2",
                partners=[FamilyPartner("B", "father")],
                children=["C"],
            ),
            Family(
                id="f3",
                partners=[FamilyPartner("C", "father")],
                children=["B"],
            ),
        ]
        project = _make_project(families)
        lc = LineageComputer(project)

        with caplog.at_level(logging.WARNING):
            descendants = lc.get_descendants("A")

        assert "B" in descendants
        assert "C" in descendants
        assert "A" not in descendants
        assert "Cycle detected" in caplog.text

    def test_multiple_children_per_family(self) -> None:
        """All children of a family where the person is a partner are included."""
        families = [
            Family(
                id="f1",
                partners=[FamilyPartner("parent", "father")],
                children=["child1", "child2", "child3"],
            ),
        ]
        project = _make_project(families)
        lc = LineageComputer(project)
        descendants = lc.get_descendants("parent")
        assert descendants == {"child1", "child2", "child3"}

    def test_sibling_branches(self) -> None:
        """A parent with two children, each having their own descendants.

        Structure:
          grandparent -> child_a, child_b
          child_a -> grandchild_a1, grandchild_a2
          child_b -> grandchild_b1
        """
        families = [
            Family(
                id="f1",
                partners=[FamilyPartner("grandparent", "father")],
                children=["child_a", "child_b"],
            ),
            Family(
                id="f2",
                partners=[FamilyPartner("child_a", "father")],
                children=["grandchild_a1", "grandchild_a2"],
            ),
            Family(
                id="f3",
                partners=[FamilyPartner("child_b", "father")],
                children=["grandchild_b1"],
            ),
        ]
        project = _make_project(families)
        lc = LineageComputer(project)
        descendants = lc.get_descendants("grandparent")
        assert descendants == {
            "child_a",
            "child_b",
            "grandchild_a1",
            "grandchild_a2",
            "grandchild_b1",
        }

    def test_isolated_person_no_families(self) -> None:
        """A person not in any family returns empty descendants.

        Other families exist in the project, but the queried person
        is not referenced in any of them.
        """
        families = [
            Family(
                id="f1",
                partners=[FamilyPartner("other_parent", "father")],
                children=["other_child"],
            ),
        ]
        project = _make_project(families)
        lc = LineageComputer(project)
        assert lc.get_descendants("isolated_person") == set()
