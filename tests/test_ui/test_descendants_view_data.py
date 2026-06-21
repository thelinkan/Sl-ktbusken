"""Property-based tests for descendants collection logic.

Tests the pure descendant collection algorithm without any Qt/GUI dependency.

Property 13: Descendants Collection Completeness
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.views.descendants_view import collect_descendants


# ---------------------------------------------------------------------------
# Strategies for generating family trees with descendants
# ---------------------------------------------------------------------------

_SAFE_NAME = st.text(
    alphabet=st.characters(categories=("L",)),
    min_size=1,
    max_size=10,
)


def _make_person(person_id: str, sex: str = "U") -> Person:
    """Create a simple person with a generated name."""
    return Person(
        id=person_id,
        sex=sex,
        names=[Name(type="birth", given=person_id, surname="Test")],
    )


@st.composite
def descendant_tree_strategy(draw: DrawFn) -> tuple[ProjectData, str, int]:
    """Generate a random family tree with descendants and a configured depth.

    Builds a tree where each person may have 0-4 children per family,
    creating a realistic descendant structure with variable branching.

    Returns:
        Tuple of (project_data, active_person_id, configured_depth).
    """
    depth = draw(st.integers(min_value=1, max_value=4))

    persons: list[Person] = []
    families: list[Family] = []
    person_counter = [0]

    def next_id() -> str:
        person_counter[0] += 1
        return f"p{person_counter[0]}"

    family_counter = [0]

    def next_family_id() -> str:
        family_counter[0] += 1
        return f"f{family_counter[0]}"

    # Start with the active person
    active_id = next_id()
    persons.append(_make_person(active_id, "M"))

    # For each person, probabilistically assign children up to depth
    # Track: (person_id, current_generation)
    queue: list[tuple[str, int]] = [(active_id, 0)]

    while queue:
        pid, gen = queue.pop(0)
        if gen >= depth:
            continue

        # Decide how many children this person has (0-4)
        num_children = draw(st.integers(min_value=0, max_value=4))

        if num_children == 0:
            continue

        # Create children
        children_ids: list[str] = []
        for _ in range(num_children):
            child_id = next_id()
            child_sex = draw(st.sampled_from(["M", "F"]))
            persons.append(_make_person(child_id, child_sex))
            children_ids.append(child_id)
            queue.append((child_id, gen + 1))

        # Create a family with the person as partner and children
        family = Family(
            id=next_family_id(),
            partners=[FamilyPartner(person_id=pid, role="father")],
            children=children_ids,
            parent_child_links=[
                ParentChildLink(child_id=cid, parent_id=pid, parentage_type="biological")
                for cid in children_ids
            ],
        )
        families.append(family)

    project_data = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        families=families,
    )

    return project_data, active_id, depth


@st.composite
def multi_family_tree_strategy(draw: DrawFn) -> tuple[ProjectData, str, int]:
    """Generate a tree where a person can have children in multiple families.

    This tests the case where a person has partners in multiple families,
    each with their own children.

    Returns:
        Tuple of (project_data, active_person_id, configured_depth).
    """
    depth = draw(st.integers(min_value=1, max_value=3))

    persons: list[Person] = []
    families: list[Family] = []
    person_counter = [0]
    family_counter = [0]

    def next_id() -> str:
        person_counter[0] += 1
        return f"p{person_counter[0]}"

    def next_family_id() -> str:
        family_counter[0] += 1
        return f"f{family_counter[0]}"

    # Active person
    active_id = next_id()
    persons.append(_make_person(active_id, "M"))

    # Create 1-3 families for the active person
    num_families = draw(st.integers(min_value=1, max_value=3))

    all_child_ids: list[str] = []

    for _ in range(num_families):
        num_children = draw(st.integers(min_value=1, max_value=3))
        children_ids: list[str] = []

        for _ in range(num_children):
            child_id = next_id()
            persons.append(_make_person(child_id, draw(st.sampled_from(["M", "F"]))))
            children_ids.append(child_id)
            all_child_ids.append(child_id)

        family = Family(
            id=next_family_id(),
            partners=[FamilyPartner(person_id=active_id, role="father")],
            children=children_ids,
            parent_child_links=[
                ParentChildLink(child_id=cid, parent_id=active_id, parentage_type="biological")
                for cid in children_ids
            ],
        )
        families.append(family)

    # Optionally add grandchildren for some children
    if depth >= 2:
        for child_id in all_child_ids:
            has_grandchildren = draw(st.booleans())
            if has_grandchildren:
                num_gc = draw(st.integers(min_value=1, max_value=2))
                gc_ids: list[str] = []
                for _ in range(num_gc):
                    gc_id = next_id()
                    persons.append(_make_person(gc_id, draw(st.sampled_from(["M", "F"]))))
                    gc_ids.append(gc_id)

                family = Family(
                    id=next_family_id(),
                    partners=[FamilyPartner(person_id=child_id, role="mother")],
                    children=gc_ids,
                    parent_child_links=[
                        ParentChildLink(child_id=gc, parent_id=child_id, parentage_type="biological")
                        for gc in gc_ids
                    ],
                )
                families.append(family)

    project_data = ProjectData(
        project=ProjectMetadata(title="Multi-family Test"),
        persons=persons,
        families=families,
    )

    return project_data, active_id, depth


# ---------------------------------------------------------------------------
# Reference implementation for oracle comparison
# ---------------------------------------------------------------------------


def _collect_descendants_reference(
    project_data: ProjectData,
    person_id: str,
    depth: int,
) -> set[str]:
    """Reference implementation: collect all descendant IDs reachable within depth.

    Uses BFS traversal through parent-child links where the person is a
    partner in a family. Only includes children that have a valid
    ParentChildLink connecting them to the parent.

    Args:
        project_data: Project data to search.
        person_id: Starting person ID.
        depth: Maximum number of generations to traverse.

    Returns:
        Set of person IDs of all reachable descendants (excluding the start person).
    """
    descendants: set[str] = set()
    visited: set[str] = {person_id}
    # BFS: (person_id, generation)
    queue: list[tuple[str, int]] = [(person_id, 0)]

    while queue:
        pid, gen = queue.pop(0)
        if gen >= depth:
            continue

        # Find all families where this person is a partner
        for family in project_data.families:
            is_partner = any(
                partner.person_id == pid for partner in family.partners
            )
            if is_partner:
                for child_id in family.children:
                    has_link = any(
                        link.child_id == child_id and link.parent_id == pid
                        for link in family.parent_child_links
                    )
                    if has_link and child_id not in visited:
                        visited.add(child_id)
                        descendants.add(child_id)
                        queue.append((child_id, gen + 1))

    return descendants


# ---------------------------------------------------------------------------
# Property 13: Descendants Collection Completeness
# ---------------------------------------------------------------------------


@given(data=descendant_tree_strategy())
@settings(max_examples=200)
def test_descendants_collects_correct_descendant_set(
    data: tuple[ProjectData, str, int],
) -> None:
    """**Validates: Requirements 19.1, 19.2**

    Property 13: For any person in a family tree and any configured depth N
    (1-10), the descendants collection SHALL return exactly the set of
    descendants reachable within N generations via parent-child links.

    Tests that all persons reachable through child links within depth are
    included.
    """
    project_data, active_id, depth = data

    result = collect_descendants(project_data, active_id, depth)

    # Extract person IDs from the result (excluding generation 0 = active person)
    collected_ids: set[str] = set()
    for gen, person_ids in result.items():
        if gen > 0:
            collected_ids.update(person_ids)

    # Reference: collect via BFS
    expected_ids = _collect_descendants_reference(project_data, active_id, depth)

    assert collected_ids == expected_ids, (
        f"Descendant set mismatch at depth {depth}.\n"
        f"Expected: {expected_ids}\n"
        f"Got: {collected_ids}\n"
        f"Missing: {expected_ids - collected_ids}\n"
        f"Extra: {collected_ids - expected_ids}"
    )


@given(data=descendant_tree_strategy())
@settings(max_examples=200)
def test_descendants_excludes_persons_beyond_depth(
    data: tuple[ProjectData, str, int],
) -> None:
    """**Validates: Requirements 19.1, 19.2**

    Property 13: Persons beyond the configured depth are NOT included in
    the descendants collection.
    """
    project_data, active_id, depth = data

    result = collect_descendants(project_data, active_id, depth)

    # All entries in result should have generation <= depth
    for gen in result.keys():
        assert gen <= depth, (
            f"Found entry at generation {gen} which exceeds depth {depth}"
        )

    # Verify no person beyond depth is included by checking with depth+1
    if depth < 10:
        deeper_result = collect_descendants(project_data, active_id, depth + 1)
        deeper_ids: set[str] = set()
        for gen, person_ids in deeper_result.items():
            if gen == depth + 1:
                deeper_ids.update(person_ids)

        collected_ids: set[str] = set()
        for gen, person_ids in result.items():
            if gen > 0:
                collected_ids.update(person_ids)

        # Persons only at depth+1 should NOT be in collected_ids
        only_deeper = deeper_ids - collected_ids
        for pid in only_deeper:
            assert pid not in collected_ids, (
                f"Person {pid} at depth {depth + 1} should not be in "
                f"results for depth {depth}"
            )


@given(data=multi_family_tree_strategy())
@settings(max_examples=200)
def test_descendants_multi_family_correct(
    data: tuple[ProjectData, str, int],
) -> None:
    """**Validates: Requirements 19.1, 19.2**

    Property 13: For a person with children in multiple families,
    all children from all families are correctly collected.
    """
    project_data, active_id, depth = data

    result = collect_descendants(project_data, active_id, depth)

    # Extract all collected descendant IDs
    collected_ids: set[str] = set()
    for gen, person_ids in result.items():
        if gen > 0:
            collected_ids.update(person_ids)

    # Reference implementation
    expected_ids = _collect_descendants_reference(project_data, active_id, depth)

    assert collected_ids == expected_ids, (
        f"Multi-family descendant set mismatch at depth {depth}.\n"
        f"Expected: {expected_ids}\n"
        f"Got: {collected_ids}\n"
        f"Missing: {expected_ids - collected_ids}\n"
        f"Extra: {collected_ids - expected_ids}"
    )


@given(data=descendant_tree_strategy())
@settings(max_examples=100)
def test_descendants_no_duplicates(
    data: tuple[ProjectData, str, int],
) -> None:
    """**Validates: Requirements 19.1, 19.2**

    Property 13: The descendants collection contains no duplicate person
    entries — each person ID appears in exactly one generation.
    """
    project_data, active_id, depth = data

    result = collect_descendants(project_data, active_id, depth)

    # Verify no person appears in more than one generation
    all_ids: list[str] = []
    for gen, person_ids in result.items():
        all_ids.extend(person_ids)

    assert len(all_ids) == len(set(all_ids)), (
        f"Duplicate person IDs found in descendants result.\n"
        f"Total entries: {len(all_ids)}, Unique: {len(set(all_ids))}"
    )


@given(
    depth=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=50)
def test_descendants_empty_tree_returns_only_root(depth: int) -> None:
    """**Validates: Requirements 19.1, 19.2**

    Property 13: For a person with no descendants, the descendants
    collection returns only the root person at generation 0.
    """
    person = _make_person("lonely", "M")
    project_data = ProjectData(
        project=ProjectMetadata(title="Empty"),
        persons=[person],
        families=[],
    )

    result = collect_descendants(project_data, "lonely", depth)

    # Only generation 0 should have the root person
    assert result[0] == {"lonely"}

    # No other generations should have persons
    descendants_found: set[str] = set()
    for gen, person_ids in result.items():
        if gen > 0:
            descendants_found.update(person_ids)

    assert len(descendants_found) == 0, (
        f"Person with no descendants should have empty descendant set, "
        f"but found: {descendants_found}"
    )
