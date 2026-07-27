# Feature: kontrollera-personer, Property 13: Connectivity to main person
"""Property-based tests for connectivity to main person.

For any project with a defined main person, all persons not reachable via BFS
through family relationships from the main person SHALL produce a finding when
the connectivity check is enabled. All reachable persons SHALL produce no such
finding.

**Validates: Requirements 9.6**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.persistence.settings_io import PersonCheckConfig, LogicCheckConfig
from slaktbusken.services.checks.structure_checks import (
    check_connected_to_main_person,
    reset_connectivity_cache,
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
def connected_family_graph(draw: st.DrawFn) -> tuple[str, str, list[Family], dict[str, list[Family]]]:
    """Generate a family graph where main_person and target are connected.

    Returns (main_person_id, target_id, families_list, families_by_person).
    """
    main_id = "main_" + draw(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=3, max_size=6)
    )
    target_id = "target_" + draw(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=3, max_size=6)
    )

    # Build a chain of families connecting main to target
    # Simple case: both are in the same family
    connection_type = draw(st.sampled_from(["same_family", "chain"]))

    families: list[Family] = []
    families_by_person: dict[str, list[Family]] = {}

    if connection_type == "same_family":
        # Both in same family (as partners or one as child)
        role_type = draw(st.sampled_from(["both_partners", "parent_child"]))
        if role_type == "both_partners":
            family = Family(
                id="f1",
                partners=[
                    FamilyPartner(person_id=main_id, role="partner"),
                    FamilyPartner(person_id=target_id, role="partner"),
                ],
                children=[],
            )
        else:
            family = Family(
                id="f1",
                partners=[FamilyPartner(person_id=main_id, role="partner")],
                children=[target_id],
            )
        families = [family]
        families_by_person = {
            main_id: [family],
            target_id: [family],
        }
    else:
        # Chain: main -> intermediate -> target (two families)
        intermediate_id = "inter_" + draw(
            st.text(alphabet="abcdefghijklmnop0123456789", min_size=3, max_size=6)
        )
        family1 = Family(
            id="f1",
            partners=[
                FamilyPartner(person_id=main_id, role="partner"),
                FamilyPartner(person_id=intermediate_id, role="partner"),
            ],
            children=[],
        )
        family2 = Family(
            id="f2",
            partners=[FamilyPartner(person_id=intermediate_id, role="partner")],
            children=[target_id],
        )
        families = [family1, family2]
        families_by_person = {
            main_id: [family1],
            intermediate_id: [family1, family2],
            target_id: [family2],
        }

    return main_id, target_id, families, families_by_person


@st.composite
def disconnected_family_graph(draw: st.DrawFn) -> tuple[str, str, list[Family], dict[str, list[Family]]]:
    """Generate a family graph where main_person and target are NOT connected.

    Returns (main_person_id, target_id, families_list, families_by_person).
    """
    main_id = "main_" + draw(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=3, max_size=6)
    )
    target_id = "target_" + draw(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=3, max_size=6)
    )

    # Main person has their own family, target has a separate family
    other_main_partner = "mp_" + draw(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=3, max_size=6)
    )
    other_target_partner = "tp_" + draw(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=3, max_size=6)
    )

    family_main = Family(
        id="f_main",
        partners=[
            FamilyPartner(person_id=main_id, role="partner"),
            FamilyPartner(person_id=other_main_partner, role="partner"),
        ],
        children=[],
    )
    family_target = Family(
        id="f_target",
        partners=[
            FamilyPartner(person_id=target_id, role="partner"),
            FamilyPartner(person_id=other_target_partner, role="partner"),
        ],
        children=[],
    )

    families = [family_main, family_target]
    families_by_person = {
        main_id: [family_main],
        other_main_partner: [family_main],
        target_id: [family_target],
        other_target_partner: [family_target],
    }

    return main_id, target_id, families, families_by_person


# ---------------------------------------------------------------------------
# Property 13: Connectivity to main person
# ---------------------------------------------------------------------------


class TestConnectivityToMainPersonProperty:
    """Feature: kontrollera-personer, Property 13: Connectivity to main person

    For any project with a defined main person, all persons not reachable via
    BFS through family relationships from the main person SHALL produce a
    finding when the connectivity check is enabled. All reachable persons SHALL
    produce no such finding.

    **Validates: Requirements 9.6**
    """

    @given(data=st.data())
    @settings(max_examples=200)
    def test_reachable_person_produces_no_finding(self, data: st.DataObject) -> None:
        """A person reachable from main person through families → no finding."""
        reset_connectivity_cache()

        main_id, target_id, families, families_by_person = data.draw(
            connected_family_graph()
        )
        target_person = data.draw(person_st(person_id=target_id))

        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(connected_to_main_person=True)
        )
        context = CheckContext()
        context.families_by_person = families_by_person
        context.main_person_id = main_id

        findings = check_connected_to_main_person(
            person=target_person,
            events=[],
            families=families_by_person.get(target_id, []),
            config=config,
            context=context,
        )

        assert len(findings) == 0

    @given(data=st.data())
    @settings(max_examples=200)
    def test_disconnected_person_produces_finding(self, data: st.DataObject) -> None:
        """A person NOT reachable from main person (disconnected) → finding."""
        reset_connectivity_cache()

        main_id, target_id, families, families_by_person = data.draw(
            disconnected_family_graph()
        )
        target_person = data.draw(person_st(person_id=target_id))

        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(connected_to_main_person=True)
        )
        context = CheckContext()
        context.families_by_person = families_by_person
        context.main_person_id = main_id

        findings = check_connected_to_main_person(
            person=target_person,
            events=[],
            families=families_by_person.get(target_id, []),
            config=config,
            context=context,
        )

        assert len(findings) == 1
        assert findings[0].person_id == target_id
        assert "koppling" in findings[0].message.lower()

    @given(data=st.data())
    @settings(max_examples=200)
    def test_no_main_person_produces_no_finding(self, data: st.DataObject) -> None:
        """When no main person is defined (main_person_id = None) → no finding (Req 9.7)."""
        reset_connectivity_cache()

        target_person = data.draw(person_st())

        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(connected_to_main_person=True)
        )
        context = CheckContext()
        context.families_by_person = {}
        context.main_person_id = None  # No main person defined

        findings = check_connected_to_main_person(
            person=target_person,
            events=[],
            families=[],
            config=config,
            context=context,
        )

        assert len(findings) == 0

    @given(data=st.data())
    @settings(max_examples=200)
    def test_check_disabled_produces_no_finding(self, data: st.DataObject) -> None:
        """When the connectivity check is disabled → no finding."""
        reset_connectivity_cache()

        main_id, target_id, families, families_by_person = data.draw(
            disconnected_family_graph()
        )
        target_person = data.draw(person_st(person_id=target_id))

        config = PersonCheckConfig(
            logic_checks=LogicCheckConfig(connected_to_main_person=False)
        )
        context = CheckContext()
        context.families_by_person = families_by_person
        context.main_person_id = main_id

        findings = check_connected_to_main_person(
            person=target_person,
            events=[],
            families=families_by_person.get(target_id, []),
            config=config,
            context=context,
        )

        assert len(findings) == 0
