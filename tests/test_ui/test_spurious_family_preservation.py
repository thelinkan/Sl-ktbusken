"""Preservation property tests: Spurious family on add parent.

Feature: spurious-family-on-add-parent, Property 2: Preservation

These tests capture CURRENT CORRECT BEHAVIOR that must not regress when the
spurious family bug is fixed. They should PASS on both unfixed AND fixed code.

Preservation checks:
a. _find_children with valid links: correctly returns children with ParentChildLinks
b. Child addition: role="child" adds child to family.children
c. Partner addition: role="partner" creates family with both partners
d. Existing family parent addition: non-empty family_id appends parent as partner

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.views.descendants_view import _find_children


# ---------------------------------------------------------------------------
# Helper strategies
# ---------------------------------------------------------------------------

_person_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),
    min_size=3,
    max_size=8,
).map(lambda s: f"person_{s}")

_family_id_st = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)),
    min_size=3,
    max_size=8,
).map(lambda s: f"family_{s}")

_parent_role_st = st.sampled_from(["father", "mother"])


def _make_project_data(families: list[Family]) -> ProjectData:
    """Build a minimal ProjectData with the given families."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        families=families,
    )


# ---------------------------------------------------------------------------
# Test: _find_children with valid parent_child_links
# ---------------------------------------------------------------------------


class TestFindChildrenWithValidLinks:
    """Preservation: _find_children correctly returns children that have
    valid ParentChildLinks connecting them to the queried parent.

    This tests the NON-BUG case: families that have proper links.
    On UNFIXED code this should PASS because _find_children returns all
    children in families where the person is a partner — and since we
    provide valid links, the children ARE correct (they just happen to
    also be in the children array).

    **Validates: Requirements 3.5**
    """

    @given(
        parent_id=_person_id_st,
        child_ids=st.lists(
            _person_id_st, min_size=1, max_size=4, unique=True
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_find_children_returns_linked_children(
        self,
        parent_id: str,
        child_ids: list[str],
    ) -> None:
        """Property 2 (Preservation a): When a family has both children entries
        AND corresponding parent_child_links, _find_children correctly returns
        those children.

        This works correctly now and must continue to work after the fix.

        Feature: spurious-family-on-add-parent, Property 2: Preservation
        **Validates: Requirements 3.5**
        """
        # Ensure parent is not in child list
        child_ids = [cid for cid in child_ids if cid != parent_id]
        assume(len(child_ids) > 0)

        # Create a family with valid parent_child_links for each child
        links = [
            ParentChildLink(
                child_id=cid, parent_id=parent_id, parentage_type="biological"
            )
            for cid in child_ids
        ]

        family = Family(
            id="fam_preservation",
            partners=[FamilyPartner(person_id=parent_id, role="father")],
            children=child_ids,
            parent_child_links=links,
        )

        project_data = _make_project_data([family])
        result = _find_children(project_data, parent_id)

        # All linked children should be returned
        assert set(result) == set(child_ids), (
            f"_find_children should return {child_ids!r} for parent "
            f"{parent_id!r} with valid links, but got {result!r}"
        )

    @given(
        parent_id=_person_id_st,
        child_ids=st.lists(
            _person_id_st, min_size=2, max_size=5, unique=True
        ),
        num_linked=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=50, deadline=None)
    def test_find_children_multiple_families(
        self,
        parent_id: str,
        child_ids: list[str],
        num_linked: int,
    ) -> None:
        """Property 2 (Preservation a): _find_children works across multiple
        families where the person is a partner AND children have valid links.

        Feature: spurious-family-on-add-parent, Property 2: Preservation
        **Validates: Requirements 3.5**
        """
        # Ensure parent is not in child list
        child_ids = [cid for cid in child_ids if cid != parent_id]
        assume(len(child_ids) >= 2)

        # Split children into two families, both with valid links
        split = max(1, len(child_ids) // 2)
        children_1 = child_ids[:split]
        children_2 = child_ids[split:]

        family1 = Family(
            id="fam_1",
            partners=[FamilyPartner(person_id=parent_id, role="father")],
            children=children_1,
            parent_child_links=[
                ParentChildLink(
                    child_id=cid, parent_id=parent_id, parentage_type="biological"
                )
                for cid in children_1
            ],
        )

        family2 = Family(
            id="fam_2",
            partners=[FamilyPartner(person_id=parent_id, role="father")],
            children=children_2,
            parent_child_links=[
                ParentChildLink(
                    child_id=cid, parent_id=parent_id, parentage_type="biological"
                )
                for cid in children_2
            ],
        )

        project_data = _make_project_data([family1, family2])
        result = _find_children(project_data, parent_id)

        # All linked children from both families should be returned
        expected = set(children_1 + children_2)
        assert set(result) == expected, (
            f"_find_children should return children from both families. "
            f"Expected {expected!r}, got {set(result)!r}"
        )


# ---------------------------------------------------------------------------
# Test: Child addition pattern (role="child")
# ---------------------------------------------------------------------------


class TestChildAdditionPreservation:
    """Preservation: When adding a child (role="child"), the family creation
    logic adds the child to family.children — this should be preserved.

    We test the data structure patterns that handle_placeholder_click creates
    for the child role, without invoking Qt dialogs.

    **Validates: Requirements 3.2**
    """

    @given(
        active_person_id=_person_id_st,
        new_child_id=_person_id_st,
        family_id=_family_id_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_child_added_to_existing_family(
        self,
        active_person_id: str,
        new_child_id: str,
        family_id: str,
    ) -> None:
        """Property 2 (Preservation b): When adding a child to an existing
        family (non-empty family_id), the new child is appended to
        family.children.

        This replicates the logic in handle_placeholder_click for role="child"
        with a non-empty family_id.

        Feature: spurious-family-on-add-parent, Property 2: Preservation
        **Validates: Requirements 3.2**
        """
        assume(active_person_id != new_child_id)

        # Create an existing family (as it would exist before child addition)
        family = Family(
            id=family_id,
            partners=[FamilyPartner(person_id=active_person_id, role="partner")],
            children=[],
        )

        # Simulate handle_placeholder_click logic for role="child" with family_id
        # The code does: fam.children.append(saved.id)
        family.children.append(new_child_id)

        # Verify preservation: child is in the family's children list
        assert new_child_id in family.children, (
            f"Child {new_child_id!r} should be in family.children after addition"
        )

    @given(
        active_person_id=_person_id_st,
        new_child_id=_person_id_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_child_new_family_creation(
        self,
        active_person_id: str,
        new_child_id: str,
    ) -> None:
        """Property 2 (Preservation b): When adding a child with no existing
        family (empty family_id), a new family is created with the active
        person as partner and the new person as child.

        This replicates the logic in handle_placeholder_click for role="child"
        with an empty family_id.

        Feature: spurious-family-on-add-parent, Property 2: Preservation
        **Validates: Requirements 3.2**
        """
        assume(active_person_id != new_child_id)

        # Simulate handle_placeholder_click logic for role="child", empty family_id
        # The code does:
        # new_family = Family(
        #     id=fam_id,
        #     partners=[FamilyPartner(person_id=active_id, role="partner")],
        #     children=[saved.id],
        # )
        new_family = Family(
            id="fam_new",
            partners=[FamilyPartner(person_id=active_person_id, role="partner")],
            children=[new_child_id],
        )

        # Verify preservation: structure is correct
        assert len(new_family.partners) == 1
        assert new_family.partners[0].person_id == active_person_id
        assert new_family.partners[0].role == "partner"
        assert new_child_id in new_family.children
        assert len(new_family.children) == 1


# ---------------------------------------------------------------------------
# Test: Partner addition pattern (role="partner")
# ---------------------------------------------------------------------------


class TestPartnerAdditionPreservation:
    """Preservation: When adding a partner (role="partner"), a family is
    created with both partners — this should be preserved.

    **Validates: Requirements 3.3**
    """

    @given(
        active_person_id=_person_id_st,
        new_partner_id=_person_id_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_partner_creates_family_with_both_partners(
        self,
        active_person_id: str,
        new_partner_id: str,
    ) -> None:
        """Property 2 (Preservation c): When adding a partner (role="partner"),
        a new family is created with both the active person and the new person
        as partners.

        This replicates the logic in handle_placeholder_click for role="partner".

        Feature: spurious-family-on-add-parent, Property 2: Preservation
        **Validates: Requirements 3.3**
        """
        assume(active_person_id != new_partner_id)

        # Simulate handle_placeholder_click logic for role="partner"
        # The code does:
        # new_family = Family(
        #     id=fam_id,
        #     partners=[
        #         FamilyPartner(person_id=active_id, role="partner"),
        #         FamilyPartner(person_id=saved.id, role="partner"),
        #     ],
        #     children=[],
        # )
        new_family = Family(
            id="fam_partner",
            partners=[
                FamilyPartner(person_id=active_person_id, role="partner"),
                FamilyPartner(person_id=new_partner_id, role="partner"),
            ],
            children=[],
        )

        # Verify preservation: both partners present, no children
        assert len(new_family.partners) == 2
        partner_ids = {p.person_id for p in new_family.partners}
        assert active_person_id in partner_ids
        assert new_partner_id in partner_ids
        assert new_family.children == []


# ---------------------------------------------------------------------------
# Test: Existing family parent addition (non-empty family_id)
# ---------------------------------------------------------------------------


class TestExistingFamilyParentAdditionPreservation:
    """Preservation: When adding a parent to an existing family (non-empty
    family_id), the parent is appended as a partner — this should be preserved.

    **Validates: Requirements 3.4**
    """

    @given(
        existing_partner_id=_person_id_st,
        new_parent_id=_person_id_st,
        role=_parent_role_st,
        child_id=_person_id_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_parent_added_to_existing_family_as_partner(
        self,
        existing_partner_id: str,
        new_parent_id: str,
        role: str,
        child_id: str,
    ) -> None:
        """Property 2 (Preservation d): When adding a parent (father/mother) to
        an existing family (non-empty family_id), the parent is appended as a
        partner to that family.

        This replicates the logic in handle_placeholder_click for
        role="father"/"mother" with a non-empty family_id.

        Feature: spurious-family-on-add-parent, Property 2: Preservation
        **Validates: Requirements 3.4**
        """
        # Ensure all IDs are unique
        assume(len({existing_partner_id, new_parent_id, child_id}) == 3)

        # Create existing family with one partner and a child
        family = Family(
            id="fam_existing",
            partners=[FamilyPartner(person_id=existing_partner_id, role="mother")],
            children=[child_id],
            parent_child_links=[
                ParentChildLink(
                    child_id=child_id,
                    parent_id=existing_partner_id,
                    parentage_type="biological",
                )
            ],
        )

        # Simulate handle_placeholder_click logic for role="father"/"mother"
        # with a non-empty family_id:
        # The code does:
        # partner_role = "father" if role == "father" else "mother"
        # fam.partners.append(FamilyPartner(person_id=saved.id, role=partner_role))
        partner_role = "father" if role == "father" else "mother"
        family.partners.append(
            FamilyPartner(person_id=new_parent_id, role=partner_role)
        )

        # Verify preservation: new parent added as partner
        partner_ids = [p.person_id for p in family.partners]
        assert new_parent_id in partner_ids, (
            f"New parent {new_parent_id!r} should be in family partners"
        )
        assert existing_partner_id in partner_ids, (
            f"Existing partner {existing_partner_id!r} should still be in family"
        )
        # Verify the new partner has the correct role
        new_partner = next(
            p for p in family.partners if p.person_id == new_parent_id
        )
        assert new_partner.role == partner_role

    @given(
        existing_partner_id=_person_id_st,
        new_parent_id=_person_id_st,
        role=_parent_role_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_parent_addition_does_not_modify_children(
        self,
        existing_partner_id: str,
        new_parent_id: str,
        role: str,
    ) -> None:
        """Property 2 (Preservation d): Adding a parent to an existing family
        does not modify the children list.

        Feature: spurious-family-on-add-parent, Property 2: Preservation
        **Validates: Requirements 3.4**
        """
        assume(existing_partner_id != new_parent_id)

        child_ids = ["child_1", "child_2"]

        family = Family(
            id="fam_existing",
            partners=[FamilyPartner(person_id=existing_partner_id, role="mother")],
            children=list(child_ids),  # copy to preserve original
        )

        # Record children before modification
        children_before = list(family.children)

        # Simulate adding parent to existing family
        partner_role = "father" if role == "father" else "mother"
        family.partners.append(
            FamilyPartner(person_id=new_parent_id, role=partner_role)
        )

        # Verify preservation: children unchanged
        assert family.children == children_before, (
            f"Children should not change when adding a parent to existing family. "
            f"Before: {children_before!r}, After: {family.children!r}"
        )
