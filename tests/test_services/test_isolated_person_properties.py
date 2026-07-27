# Feature: kontrollera-personer, Property 10: Isolated person detection
"""Property-based tests for isolated person detection.

For any person who does not appear in any Family (not as partner, child,
or via parent_child_links), and the "must have relations" check is enabled,
a finding SHALL be produced. For persons appearing in at least one family,
no isolation finding SHALL be produced.

**Validates: Requirements 9.2**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.persistence.settings_io import PersonCheckConfig, LogicCheckConfig
from slaktbusken.services.checks.structure_checks import check_must_have_relations
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
def person_st(draw: st.DrawFn) -> Person:
    """Generate a Person with a random name and sex."""
    pid = draw(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=5, max_size=10)
    )
    sex = draw(sex_st)
    given = draw(given_name_st)
    surname = draw(surname_st)
    return Person(
        id=pid, sex=sex, names=[Name(type="birth", given=given, surname=surname)]
    )


@st.composite
def family_with_person_st(draw: st.DrawFn, person_id: str) -> Family:
    """Generate a Family that includes the given person (as partner or child)."""
    family_id = draw(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=5, max_size=10)
    )
    # Decide if person is partner or child
    role = draw(st.sampled_from(["partner", "child"]))

    if role == "partner":
        # Person is a partner in this family
        other_id = draw(
            st.text(
                alphabet="abcdefghijklmnop0123456789", min_size=5, max_size=10
            )
        )
        partners = [
            FamilyPartner(person_id=person_id, role="husband"),
            FamilyPartner(person_id=other_id, role="wife"),
        ]
        children: list[str] = []
    else:
        # Person is a child in this family
        parent1_id = draw(
            st.text(
                alphabet="abcdefghijklmnop0123456789", min_size=5, max_size=10
            )
        )
        parent2_id = draw(
            st.text(
                alphabet="abcdefghijklmnop0123456789", min_size=5, max_size=10
            )
        )
        partners = [
            FamilyPartner(person_id=parent1_id, role="husband"),
            FamilyPartner(person_id=parent2_id, role="wife"),
        ]
        children = [person_id]

    return Family(id=family_id, partners=partners, children=children)


# ---------------------------------------------------------------------------
# Property 10: Isolated person detection
# ---------------------------------------------------------------------------


class TestIsolatedPersonProperty:
    """Feature: kontrollera-personer, Property 10: Isolated person detection

    For any person who does not appear in any Family (not as partner, child,
    or via parent_child_links), and the "must have relations" check is enabled,
    a finding SHALL be produced. For persons appearing in at least one family,
    no isolation finding SHALL be produced.

    **Validates: Requirements 9.2**
    """

    @given(person=person_st())
    @settings(max_examples=200)
    def test_isolated_person_produces_finding(self, person: Person) -> None:
        """A person with no family entries produces a finding."""
        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(must_have_relations=True)
        )
        context = CheckContext()
        # Person NOT in families_by_person → isolated
        context.families_by_person = {}

        findings = check_must_have_relations(
            person=person,
            events=[],
            families=[],
            config=config,
            context=context,
        )

        assert len(findings) == 1
        assert findings[0].person_id == person.id
        assert "familjerelationer" in findings[0].message.lower()

    @given(data=st.data())
    @settings(max_examples=200)
    def test_connected_person_produces_no_finding(self, data: st.DataObject) -> None:
        """A person who appears in at least one family produces no finding."""
        person = data.draw(person_st())
        family = data.draw(family_with_person_st(person_id=person.id))

        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(must_have_relations=True)
        )
        context = CheckContext()
        # Person IS in families_by_person → connected
        context.families_by_person = {person.id: [family]}

        findings = check_must_have_relations(
            person=person,
            events=[],
            families=[family],
            config=config,
            context=context,
        )

        assert len(findings) == 0

    @given(person=person_st())
    @settings(max_examples=200)
    def test_check_disabled_produces_no_finding(self, person: Person) -> None:
        """When the must_have_relations check is disabled, no finding is produced."""
        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(must_have_relations=False)
        )
        context = CheckContext()
        # Person is isolated but check is disabled
        context.families_by_person = {}

        findings = check_must_have_relations(
            person=person,
            events=[],
            families=[],
            config=config,
            context=context,
        )

        assert len(findings) == 0
