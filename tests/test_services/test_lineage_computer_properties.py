"""Property-based tests for LineageComputer.

Feature: ui-enhancements, Property 3: Ancestor computation correctness
Feature: ui-enhancements, Property 4: Descendant computation correctness
Feature: ui-enhancements, Property 5: Main person excluded from lineage sets

Validates: Requirements 3.1, 3.4, 4.1
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.lineage_computer import LineageComputer


# ---------------------------------------------------------------------------
# Strategy: random family graphs
# ---------------------------------------------------------------------------

def _person_ids_strategy(min_size: int = 2, max_size: int = 15) -> st.SearchStrategy:
    """Generate a list of unique person IDs."""
    return st.lists(
        st.text(
            alphabet=st.characters(categories=("L", "N")),
            min_size=1,
            max_size=6,
        ),
        min_size=min_size,
        max_size=max_size,
        unique=True,
    )


@st.composite
def family_graph_strategy(draw: st.DrawFn) -> tuple[ProjectData, list[str]]:
    """Generate a random family graph with 2-15 persons and 1-10 families.

    Returns a tuple of (ProjectData, list_of_person_ids) so tests can pick
    a person to query.
    """
    person_ids = draw(_person_ids_strategy(min_size=2, max_size=15))
    num_families = draw(st.integers(min_value=1, max_value=min(10, len(person_ids))))

    families: list[Family] = []
    for i in range(num_families):
        # Pick 1-3 partners from available persons
        num_partners = draw(st.integers(min_value=1, max_value=min(3, len(person_ids))))
        partner_ids = draw(
            st.lists(
                st.sampled_from(person_ids),
                min_size=num_partners,
                max_size=num_partners,
            )
        )
        partners = [FamilyPartner(pid, "partner") for pid in partner_ids]

        # Pick 0-4 children from available persons
        max_children = min(4, len(person_ids))
        children = draw(
            st.lists(
                st.sampled_from(person_ids),
                min_size=0,
                max_size=max_children,
            )
        )

        families.append(
            Family(
                id=f"fam_{i}",
                partners=partners,
                children=children,
            )
        )

    project_data = ProjectData(
        project=ProjectMetadata(title="Property Test"),
        families=families,
    )
    return project_data, person_ids


# ---------------------------------------------------------------------------
# Naive oracle functions for comparison
# ---------------------------------------------------------------------------

def naive_ancestors(project_data: ProjectData, person_id: str) -> set[str]:
    """Recursively collect ancestors by traversing parent (partner) links upward.

    For each family where person is a child, collect all partners as parents,
    then recurse for each parent. Uses a visited set to handle cycles.
    """
    ancestors: set[str] = set()
    visited: set[str] = {person_id}

    def _recurse(current_id: str) -> None:
        for family in project_data.families:
            if current_id not in family.children:
                continue
            for partner in family.partners:
                parent_id = partner.person_id
                if parent_id in visited:
                    continue
                visited.add(parent_id)
                ancestors.add(parent_id)
                _recurse(parent_id)

    _recurse(person_id)
    return ancestors


def naive_descendants(project_data: ProjectData, person_id: str) -> set[str]:
    """Recursively collect descendants by traversing child links downward.

    For each family where person is a partner, collect all children,
    then recurse for each child. Uses a visited set to handle cycles.
    """
    descendants: set[str] = set()
    visited: set[str] = {person_id}

    def _recurse(current_id: str) -> None:
        for family in project_data.families:
            is_partner = any(p.person_id == current_id for p in family.partners)
            if not is_partner:
                continue
            for child_id in family.children:
                if child_id in visited:
                    continue
                visited.add(child_id)
                descendants.add(child_id)
                _recurse(child_id)

    _recurse(person_id)
    return descendants


# ---------------------------------------------------------------------------
# Property 3: Ancestor computation correctness
# ---------------------------------------------------------------------------

class TestAncestorComputationCorrectness:
    """Feature: ui-enhancements, Property 3: Ancestor computation correctness

    For random family graphs, verify that the ancestor set returned by
    LineageComputer.get_ancestors matches a naive recursive traversal
    of parent links.

    **Validates: Requirements 3.1, 3.4**
    """

    @given(data=family_graph_strategy())
    @settings(max_examples=100, deadline=None)
    def test_ancestors_match_naive_oracle(
        self, data: tuple[ProjectData, list[str]]
    ) -> None:
        """Property 3: Ancestor set matches naive recursive traversal of parent links.

        Feature: ui-enhancements, Property 3: Ancestor computation correctness
        **Validates: Requirements 3.1, 3.4**
        """
        project_data, person_ids = data
        # Test for every person in the graph
        lc = LineageComputer(project_data)

        for person_id in person_ids:
            actual = lc.get_ancestors(person_id)
            expected = naive_ancestors(project_data, person_id)
            assert actual == expected, (
                f"Ancestor mismatch for '{person_id}':\n"
                f"  actual:   {actual}\n"
                f"  expected: {expected}\n"
                f"  diff (actual - expected): {actual - expected}\n"
                f"  diff (expected - actual): {expected - actual}"
            )


# ---------------------------------------------------------------------------
# Property 4: Descendant computation correctness
# ---------------------------------------------------------------------------

class TestDescendantComputationCorrectness:
    """Feature: ui-enhancements, Property 4: Descendant computation correctness

    For random family graphs, verify that the descendant set returned by
    LineageComputer.get_descendants matches a naive recursive traversal
    of child links.

    **Validates: Requirements 3.1, 4.1**
    """

    @given(data=family_graph_strategy())
    @settings(max_examples=100, deadline=None)
    def test_descendants_match_naive_oracle(
        self, data: tuple[ProjectData, list[str]]
    ) -> None:
        """Property 4: Descendant set matches naive recursive traversal of child links.

        Feature: ui-enhancements, Property 4: Descendant computation correctness
        **Validates: Requirements 3.1, 4.1**
        """
        project_data, person_ids = data
        lc = LineageComputer(project_data)

        for person_id in person_ids:
            actual = lc.get_descendants(person_id)
            expected = naive_descendants(project_data, person_id)
            assert actual == expected, (
                f"Descendant mismatch for '{person_id}':\n"
                f"  actual:   {actual}\n"
                f"  expected: {expected}\n"
                f"  diff (actual - expected): {actual - expected}\n"
                f"  diff (expected - actual): {expected - actual}"
            )


# ---------------------------------------------------------------------------
# Property 5: Main person excluded from lineage sets
# ---------------------------------------------------------------------------

class TestMainPersonExcludedFromLineageSets:
    """Feature: ui-enhancements, Property 5: Main person excluded from lineage sets

    For any graph and person P, verify that P is never included in
    get_ancestors(P) or get_descendants(P).

    **Validates: Requirements 3.4, 4.1**
    """

    @given(data=family_graph_strategy())
    @settings(max_examples=100, deadline=None)
    def test_person_not_in_own_ancestors_or_descendants(
        self, data: tuple[ProjectData, list[str]]
    ) -> None:
        """Property 5: Person P is never in get_ancestors(P) or get_descendants(P).

        Feature: ui-enhancements, Property 5: Main person excluded from lineage sets
        **Validates: Requirements 3.4, 4.1**
        """
        project_data, person_ids = data
        lc = LineageComputer(project_data)

        for person_id in person_ids:
            ancestors = lc.get_ancestors(person_id)
            descendants = lc.get_descendants(person_id)

            assert person_id not in ancestors, (
                f"Person '{person_id}' found in their own ancestor set: {ancestors}"
            )
            assert person_id not in descendants, (
                f"Person '{person_id}' found in their own descendant set: {descendants}"
            )
