# Feature: kontrollera-personer, Property 9: Incest detection
"""Property-based tests for incest detection in structure checks.

For any family where two partners share at least one parent (siblings/half-siblings)
or where one partner is the parent of the other, and the incest check is enabled,
a finding SHALL be produced. For families where partners have no such relationship,
no incest finding SHALL be produced.

**Validates: Requirements 9.1**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.persistence.settings_io import LogicCheckConfig, PersonCheckConfig
from slaktbusken.services.checks.structure_checks import check_incest
from slaktbusken.services.person_check_engine import CheckContext


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

person_id_st = st.text(
    alphabet="abcdefghijklmnop0123456789", min_size=4, max_size=8
)


def make_person(pid: str, sex: str = "M") -> Person:
    """Create a minimal Person for testing."""
    return Person(id=pid, sex=sex, names=[Name(type="birth", given="Test", surname="Person")])


def make_family(partner_ids: list[str]) -> Family:
    """Create a Family with the given partner IDs."""
    return Family(
        id="fam1",
        partners=[FamilyPartner(person_id=pid, role="partner") for pid in partner_ids],
        children=[],
    )


def make_config(incest_enabled: bool = True) -> PersonCheckConfig:
    """Create a PersonCheckConfig with incest check enabled/disabled."""
    config = PersonCheckConfig()
    config.logic_checks.no_incest = incest_enabled
    return config


def make_context(
    siblings_of: dict[str, set[str]] | None = None,
    parents_of: dict[str, list[str]] | None = None,
) -> CheckContext:
    """Create a minimal CheckContext with specified relationships."""
    ctx = CheckContext()
    ctx.siblings_of = siblings_of or {}
    ctx.parents_of = parents_of or {}
    return ctx


# ---------------------------------------------------------------------------
# Property 9: Incest detection
# ---------------------------------------------------------------------------


class TestIncestDetectionProperty:
    """Feature: kontrollera-personer, Property 9: Incest detection

    For any family where two partners share at least one parent
    (siblings/half-siblings) or where one partner is the parent of the other,
    and the incest check is enabled, a finding SHALL be produced. For families
    where partners have no such relationship, no incest finding SHALL be produced.

    **Validates: Requirements 9.1**
    """

    @given(
        shared_parent=person_id_st,
        person_a_id=person_id_st,
        person_b_id=person_id_st,
    )
    @settings(max_examples=200)
    def test_siblings_produce_finding(
        self, shared_parent: str, person_a_id: str, person_b_id: str
    ) -> None:
        """Partners who are siblings (share a parent) produce a finding."""
        # Ensure distinct IDs
        if person_a_id == person_b_id or person_a_id == shared_parent or person_b_id == shared_parent:
            return  # Skip degenerate case

        person = make_person(person_a_id)
        family = make_family([person_a_id, person_b_id])
        config = make_config(incest_enabled=True)
        context = make_context(
            siblings_of={
                person_a_id: {person_b_id},
                person_b_id: {person_a_id},
            },
            parents_of={
                person_a_id: [shared_parent],
                person_b_id: [shared_parent],
            },
        )

        findings = check_incest(person, [], [family], config, context)

        assert len(findings) >= 1
        assert any("incest" in f.message.lower() for f in findings)

    @given(
        parent_id=person_id_st,
        child_id=person_id_st,
    )
    @settings(max_examples=200)
    def test_parent_child_partners_produce_finding(
        self, parent_id: str, child_id: str
    ) -> None:
        """Partners where one is parent of the other produce a finding."""
        if parent_id == child_id:
            return  # Skip degenerate case

        # Test from the child's perspective (parent is partner)
        person = make_person(child_id)
        family = make_family([child_id, parent_id])
        config = make_config(incest_enabled=True)
        context = make_context(
            parents_of={child_id: [parent_id]},
        )

        findings = check_incest(person, [], [family], config, context)

        assert len(findings) >= 1
        assert any("incest" in f.message.lower() for f in findings)

    @given(
        parent_id=person_id_st,
        child_id=person_id_st,
    )
    @settings(max_examples=200)
    def test_parent_as_subject_produces_finding(
        self, parent_id: str, child_id: str
    ) -> None:
        """When checked from parent's perspective (parent is partner of child), finding produced."""
        if parent_id == child_id:
            return  # Skip degenerate case

        # Test from the parent's perspective
        person = make_person(parent_id)
        family = make_family([parent_id, child_id])
        config = make_config(incest_enabled=True)
        context = make_context(
            parents_of={child_id: [parent_id]},
        )

        findings = check_incest(person, [], [family], config, context)

        assert len(findings) >= 1
        assert any("incest" in f.message.lower() for f in findings)

    @given(
        person_a_id=person_id_st,
        person_b_id=person_id_st,
        unrelated_parent_a=person_id_st,
        unrelated_parent_b=person_id_st,
    )
    @settings(max_examples=200)
    def test_unrelated_partners_produce_no_finding(
        self,
        person_a_id: str,
        person_b_id: str,
        unrelated_parent_a: str,
        unrelated_parent_b: str,
    ) -> None:
        """Partners with no sibling or parent-child relationship produce no finding."""
        # Ensure all IDs are distinct
        ids = {person_a_id, person_b_id, unrelated_parent_a, unrelated_parent_b}
        if len(ids) < 4:
            return  # Skip cases with collisions

        person = make_person(person_a_id)
        family = make_family([person_a_id, person_b_id])
        config = make_config(incest_enabled=True)
        # Parents are different and neither partner is parent of the other
        context = make_context(
            siblings_of={},
            parents_of={
                person_a_id: [unrelated_parent_a],
                person_b_id: [unrelated_parent_b],
            },
        )

        findings = check_incest(person, [], [family], config, context)

        assert len(findings) == 0

    @given(
        person_a_id=person_id_st,
        person_b_id=person_id_st,
        shared_parent=person_id_st,
    )
    @settings(max_examples=200)
    def test_disabled_check_produces_no_finding(
        self, person_a_id: str, person_b_id: str, shared_parent: str
    ) -> None:
        """When incest check is disabled, no finding regardless of relationship."""
        if person_a_id == person_b_id or person_a_id == shared_parent or person_b_id == shared_parent:
            return

        person = make_person(person_a_id)
        family = make_family([person_a_id, person_b_id])
        config = make_config(incest_enabled=False)
        # Even siblings should produce no finding when disabled
        context = make_context(
            siblings_of={
                person_a_id: {person_b_id},
                person_b_id: {person_a_id},
            },
            parents_of={
                person_a_id: [shared_parent],
                person_b_id: [shared_parent],
            },
        )

        findings = check_incest(person, [], [family], config, context)

        assert len(findings) == 0
