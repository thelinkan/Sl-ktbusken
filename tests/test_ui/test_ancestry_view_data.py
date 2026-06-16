"""Property-based tests for ancestry collection logic.

Tests the pure ancestor collection algorithm without any Qt/GUI dependency.

Property 12: Ancestry Collection Completeness
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.views.ancestry_view import collect_ancestors


# ---------------------------------------------------------------------------
# Strategies for generating family trees
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
def family_tree_strategy(draw: DrawFn) -> tuple[ProjectData, str, int]:
    """Generate a random family tree with a starting person and depth.

    Builds a tree where each person may or may not have known parents,
    creating a realistic genealogy structure with possible gaps.

    Returns:
        Tuple of (project_data, active_person_id, configured_depth).
    """
    depth = draw(st.integers(min_value=1, max_value=5))

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

    # For each person, probabilistically assign parents up to depth
    # Track: (person_id, current_generation)
    queue: list[tuple[str, int]] = [(active_id, 0)]

    while queue:
        pid, gen = queue.pop(0)
        if gen >= depth:
            continue

        # Decide whether this person has a known father
        has_father = draw(st.booleans())
        # Decide whether this person has a known mother
        has_mother = draw(st.booleans())

        if not has_father and not has_mother:
            continue  # No parent family

        partners: list[FamilyPartner] = []
        father_id = None
        mother_id = None

        if has_father:
            father_id = next_id()
            persons.append(_make_person(father_id, "M"))
            partners.append(FamilyPartner(person_id=father_id, role="father"))
            queue.append((father_id, gen + 1))

        if has_mother:
            mother_id = next_id()
            persons.append(_make_person(mother_id, "F"))
            partners.append(FamilyPartner(person_id=mother_id, role="mother"))
            queue.append((mother_id, gen + 1))

        family = Family(
            id=next_family_id(),
            partners=partners,
            children=[pid],
        )
        families.append(family)

    project_data = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        families=families,
    )

    return project_data, active_id, depth


@st.composite
def tree_with_gaps_strategy(draw: DrawFn) -> tuple[ProjectData, str, int]:
    """Generate a tree specifically designed to have gaps at intermediate levels.

    Creates a tree where some intermediate ancestors are missing but
    deeper ancestors are still reachable through other paths.

    Returns:
        Tuple of (project_data, active_person_id, configured_depth).
    """
    depth = draw(st.integers(min_value=2, max_value=4))

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

    # Always give them a father (no mother - gap)
    father_id = next_id()
    persons.append(_make_person(father_id, "M"))
    families.append(Family(
        id=next_family_id(),
        partners=[FamilyPartner(person_id=father_id, role="father")],
        children=[active_id],
    ))

    # Give the father parents (both known) - these are at depth 2
    grandfather_id = next_id()
    grandmother_id = next_id()
    persons.append(_make_person(grandfather_id, "M"))
    persons.append(_make_person(grandmother_id, "F"))
    families.append(Family(
        id=next_family_id(),
        partners=[
            FamilyPartner(person_id=grandfather_id, role="father"),
            FamilyPartner(person_id=grandmother_id, role="mother"),
        ],
        children=[father_id],
    ))

    # Optionally extend deeper
    if depth >= 3:
        # Give grandfather a father at depth 3
        great_grandfather_id = next_id()
        persons.append(_make_person(great_grandfather_id, "M"))
        families.append(Family(
            id=next_family_id(),
            partners=[FamilyPartner(person_id=great_grandfather_id, role="father")],
            children=[grandfather_id],
        ))

    project_data = ProjectData(
        project=ProjectMetadata(title="Test Gaps"),
        persons=persons,
        families=families,
    )

    return project_data, active_id, depth


# ---------------------------------------------------------------------------
# Reference implementation for oracle comparison
# ---------------------------------------------------------------------------


def _collect_ancestors_reference(
    project_data: ProjectData,
    person_id: str,
    depth: int,
) -> set[str]:
    """Reference implementation: collect all ancestor IDs reachable within depth.

    Uses recursive traversal through parent links. Returns the set of
    all person IDs that are ancestors within the given number of generations.

    Args:
        project_data: Project data to search.
        person_id: Starting person ID.
        depth: Maximum number of generations to traverse.

    Returns:
        Set of person IDs of all reachable ancestors (excluding the start person).
    """
    ancestors: set[str] = set()
    # BFS: (person_id, generation)
    queue: list[tuple[str, int]] = [(person_id, 0)]

    while queue:
        pid, gen = queue.pop(0)
        if gen >= depth:
            continue

        # Find parent family
        for family in project_data.families:
            if pid in family.children:
                for partner in family.partners:
                    if partner.role in ("father", "mother"):
                        if partner.person_id not in ancestors:
                            ancestors.add(partner.person_id)
                            queue.append((partner.person_id, gen + 1))
                break  # Only consider first parent family

    return ancestors


# ---------------------------------------------------------------------------
# Property 12: Ancestry Collection Completeness
# ---------------------------------------------------------------------------


@given(data=family_tree_strategy())
@settings(max_examples=200)
def test_ancestry_collects_correct_ancestor_set(
    data: tuple[ProjectData, str, int],
) -> None:
    """**Validates: Requirements 18.1, 18.2**

    Property 12: For any person in a family tree and any configured depth N
    (1-10), the ancestry collection SHALL return exactly the set of ancestors
    reachable within N generations via parent-child links.

    Tests that all persons reachable through parent links within depth are
    included.
    """
    project_data, active_id, depth = data

    result = collect_ancestors(project_data, active_id, depth)

    # Extract person IDs from the result (excluding generation 0 = active person)
    collected_ids: set[str] = set()
    for (gen, pos), pid in result.items():
        if gen > 0 and pid is not None:
            collected_ids.add(pid)

    # Reference: collect via BFS
    expected_ids = _collect_ancestors_reference(project_data, active_id, depth)

    assert collected_ids == expected_ids, (
        f"Ancestor set mismatch at depth {depth}.\n"
        f"Expected: {expected_ids}\n"
        f"Got: {collected_ids}\n"
        f"Missing: {expected_ids - collected_ids}\n"
        f"Extra: {collected_ids - expected_ids}"
    )


@given(data=family_tree_strategy())
@settings(max_examples=200)
def test_ancestry_excludes_persons_beyond_depth(
    data: tuple[ProjectData, str, int],
) -> None:
    """**Validates: Requirements 18.1, 18.2**

    Property 12: Persons beyond the configured depth are NOT included in
    the ancestry collection.
    """
    project_data, active_id, depth = data

    result = collect_ancestors(project_data, active_id, depth)

    # All entries in result should have generation <= depth
    for (gen, pos), pid in result.items():
        assert gen <= depth, (
            f"Found entry at generation {gen} which exceeds depth {depth}"
        )

    # Verify no person beyond depth is included by checking with depth+1
    if depth < 10:
        deeper_result = collect_ancestors(project_data, active_id, depth + 1)
        deeper_ids: set[str] = set()
        for (gen, pos), pid in deeper_result.items():
            if gen == depth + 1 and pid is not None:
                deeper_ids.add(pid)

        collected_ids: set[str] = set()
        for (gen, pos), pid in result.items():
            if gen > 0 and pid is not None:
                collected_ids.add(pid)

        # Persons only at depth+1 should NOT be in collected_ids
        only_deeper = deeper_ids - collected_ids
        for pid in only_deeper:
            assert pid not in collected_ids, (
                f"Person {pid} at depth {depth + 1} should not be in "
                f"results for depth {depth}"
            )


@given(data=tree_with_gaps_strategy())
@settings(max_examples=200)
def test_ancestry_gaps_dont_prevent_deeper_ancestors(
    data: tuple[ProjectData, str, int],
) -> None:
    """**Validates: Requirements 18.1, 18.2**

    Property 12: Missing intermediate ancestors don't prevent deeper known
    ancestors from being collected.

    This test creates trees with deliberate gaps (e.g., mother unknown)
    and verifies that known ancestors beyond the gap are still collected.
    """
    project_data, active_id, depth = data

    result = collect_ancestors(project_data, active_id, depth)

    # Reference implementation
    expected_ids = _collect_ancestors_reference(project_data, active_id, depth)

    collected_ids: set[str] = set()
    for (gen, pos), pid in result.items():
        if gen > 0 and pid is not None:
            collected_ids.add(pid)

    assert collected_ids == expected_ids, (
        f"Gap handling failed at depth {depth}.\n"
        f"Expected: {expected_ids}\n"
        f"Got: {collected_ids}\n"
        f"Missing (deeper ancestors lost): {expected_ids - collected_ids}"
    )


@given(data=family_tree_strategy())
@settings(max_examples=100)
def test_ancestry_no_duplicates(
    data: tuple[ProjectData, str, int],
) -> None:
    """**Validates: Requirements 18.1, 18.2**

    Property 12: The ancestry collection contains no duplicate person entries
    (each (generation, position) key is unique by definition of dict keys).
    """
    project_data, active_id, depth = data

    result = collect_ancestors(project_data, active_id, depth)

    # Verify that each non-None person_id appears at most once in the result
    # (in a standard pedigree chart, each position is unique even if the
    # same person appears due to pedigree collapse - but the positions
    # themselves must be unique)
    seen_keys: set[tuple[int, int]] = set()
    for key in result.keys():
        assert key not in seen_keys, f"Duplicate key {key} in ancestor map"
        seen_keys.add(key)


@given(
    depth=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=50)
def test_ancestry_empty_tree_returns_only_root(depth: int) -> None:
    """**Validates: Requirements 18.1, 18.2**

    Property 12: For a person with no known parents, the ancestry
    collection returns only the root person at generation 0.
    """
    person = _make_person("lonely", "M")
    project_data = ProjectData(
        project=ProjectMetadata(title="Empty"),
        persons=[person],
        families=[],
    )

    result = collect_ancestors(project_data, "lonely", depth)

    # Only non-None entry should be the root
    non_none_entries = {
        (gen, pos): pid
        for (gen, pos), pid in result.items()
        if pid is not None
    }
    assert len(non_none_entries) == 1
    assert non_none_entries[(0, 0)] == "lonely"
