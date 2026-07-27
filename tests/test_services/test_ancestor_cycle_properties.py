# Feature: kontrollera-personer, Property 11: Ancestor cycle detection
"""Property-based tests for ancestor cycle detection.

For any family graph containing a cycle (a person is their own ancestor
through parent-child links), and the cycle check is enabled, a finding
SHALL be produced for that person. For acyclic graphs, no cycle finding
SHALL be produced.

**Validates: Requirements 9.3**
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.persistence.settings_io import PersonCheckConfig, LogicCheckConfig
from slaktbusken.services.checks.structure_checks import (
    check_no_ancestor_cycle,
    _has_ancestor_cycle,
)
from slaktbusken.services.person_check_engine import CheckContext


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

sex_st = st.sampled_from(["M", "F", "U"])

given_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L",)), min_size=2, max_size=10
)

surname_st = st.text(
    alphabet=st.characters(whitelist_categories=("L",)), min_size=2, max_size=12
)


@st.composite
def person_st(draw: st.DrawFn, person_id: str | None = None) -> Person:
    """Generate a Person with a random name and sex."""
    pid = person_id if person_id else draw(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=5, max_size=10)
    )
    sex = draw(sex_st)
    given = draw(given_name_st)
    surname = draw(surname_st)
    return Person(
        id=pid, sex=sex, names=[Name(type="birth", given=given, surname=surname)]
    )


@st.composite
def acyclic_parents_of(draw: st.DrawFn) -> tuple[str, dict[str, list[str]]]:
    """Generate an acyclic parent graph and return (target_person_id, parents_of).

    Constructs a tree of persons with IDs p0..pN where each person only has
    parents with higher indices (ensuring no cycles are possible).
    """
    num_persons = draw(st.integers(min_value=2, max_value=15))
    person_ids = [f"p{i}" for i in range(num_persons)]

    parents_of: dict[str, list[str]] = {}

    # For each person (except the last ones which are "roots"), assign
    # parents from persons with higher indices (guaranteeing acyclicity).
    for i in range(num_persons):
        # Possible parents are only persons with index > i (higher in tree)
        possible_parents = person_ids[i + 1:]
        if possible_parents:
            num_parents = draw(st.integers(min_value=0, max_value=min(2, len(possible_parents))))
            if num_parents > 0:
                chosen = draw(
                    st.lists(
                        st.sampled_from(possible_parents),
                        min_size=num_parents,
                        max_size=num_parents,
                        unique=True,
                    )
                )
                parents_of[person_ids[i]] = chosen

    # Target person is p0 (has the longest potential ancestor chain)
    return person_ids[0], parents_of


@st.composite
def cyclic_parents_of(draw: st.DrawFn) -> tuple[str, dict[str, list[str]]]:
    """Generate a parent graph with a guaranteed cycle involving the target person.

    Creates a chain: p0 -> p1 -> p2 -> ... -> pN -> p0 (cycle back to target).
    """
    chain_length = draw(st.integers(min_value=2, max_value=8))
    person_ids = [f"p{i}" for i in range(chain_length)]

    parents_of: dict[str, list[str]] = {}

    # Build chain: p0's parent is p1, p1's parent is p2, ..., p(N-1)'s parent is p0
    for i in range(chain_length):
        next_idx = (i + 1) % chain_length
        parents_of[person_ids[i]] = [person_ids[next_idx]]

    # Optionally add extra non-cyclic branches
    num_extra = draw(st.integers(min_value=0, max_value=3))
    for j in range(num_extra):
        extra_id = f"extra{j}"
        # Extra person's parent is one of the cycle members (but extra is not in cycle)
        parent_in_cycle = draw(st.sampled_from(person_ids))
        parents_of[extra_id] = [parent_in_cycle]

    # Target person is p0 (which is in the cycle)
    return person_ids[0], parents_of


# ---------------------------------------------------------------------------
# Property 11: Ancestor cycle detection
# ---------------------------------------------------------------------------


class TestAncestorCycleProperty:
    """Feature: kontrollera-personer, Property 11: Ancestor cycle detection

    For any family graph containing a cycle (a person is their own ancestor
    through parent-child links), and the cycle check is enabled, a finding
    SHALL be produced for that person. For acyclic graphs, no cycle finding
    SHALL be produced.

    **Validates: Requirements 9.3**
    """

    # --- Tests for _has_ancestor_cycle helper directly ---

    @given(data=cyclic_parents_of())
    @settings(max_examples=200)
    def test_has_ancestor_cycle_detects_cycle(
        self, data: tuple[str, dict[str, list[str]]]
    ) -> None:
        """_has_ancestor_cycle returns True when a cycle exists."""
        person_id, parents_of = data
        assert _has_ancestor_cycle(person_id, parents_of) is True

    @given(data=acyclic_parents_of())
    @settings(max_examples=200)
    def test_has_ancestor_cycle_no_false_positive(
        self, data: tuple[str, dict[str, list[str]]]
    ) -> None:
        """_has_ancestor_cycle returns False for acyclic graphs."""
        person_id, parents_of = data
        assert _has_ancestor_cycle(person_id, parents_of) is False

    # --- Tests for check_no_ancestor_cycle (full check function) ---

    @given(data=st.data())
    @settings(max_examples=200)
    def test_cyclic_graph_produces_finding(self, data: st.DataObject) -> None:
        """A person in a cyclic ancestor graph produces a finding."""
        person_id, parents_of = data.draw(cyclic_parents_of())
        person = data.draw(person_st(person_id=person_id))

        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(no_ancestor_cycle=True)
        )
        context = CheckContext()
        context.parents_of = parents_of

        findings = check_no_ancestor_cycle(
            person=person,
            events=[],
            families=[],
            config=config,
            context=context,
        )

        assert len(findings) == 1
        assert findings[0].person_id == person.id
        assert "förfader" in findings[0].message.lower() or "cykel" in findings[0].message.lower()

    @given(data=st.data())
    @settings(max_examples=200)
    def test_acyclic_graph_produces_no_finding(self, data: st.DataObject) -> None:
        """A person in an acyclic ancestor graph produces no finding."""
        person_id, parents_of = data.draw(acyclic_parents_of())
        person = data.draw(person_st(person_id=person_id))

        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(no_ancestor_cycle=True)
        )
        context = CheckContext()
        context.parents_of = parents_of

        findings = check_no_ancestor_cycle(
            person=person,
            events=[],
            families=[],
            config=config,
            context=context,
        )

        assert len(findings) == 0

    @given(data=st.data())
    @settings(max_examples=200)
    def test_check_disabled_produces_no_finding(self, data: st.DataObject) -> None:
        """When the no_ancestor_cycle check is disabled, no finding is produced."""
        person_id, parents_of = data.draw(cyclic_parents_of())
        person = data.draw(person_st(person_id=person_id))

        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(no_ancestor_cycle=False)
        )
        context = CheckContext()
        context.parents_of = parents_of

        findings = check_no_ancestor_cycle(
            person=person,
            events=[],
            families=[],
            config=config,
            context=context,
        )

        assert len(findings) == 0
