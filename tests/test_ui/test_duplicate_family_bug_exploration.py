"""Bug condition exploration test: Duplicate family on sequential parent addition.

Feature: family-relationship-creation-bug, Property 1: Bug Condition

This test encodes the EXPECTED behavior. When run on UNFIXED code, these tests
are expected to FAIL, confirming the bug exists.

Bug overview:
When adding a second parent to a child via the context menu (which always passes
`family_id=""`), `handle_placeholder_click` unconditionally creates a NEW family
instead of finding the existing family where the child is already a member and
adding the new parent there. This results in duplicate families — one per parent —
each containing the same child.

**Validates: Requirements 1.1, 1.2, 2.1, 2.2**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata


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

_second_parent_role_st = st.sampled_from(["father", "mother"])

_first_parent_role_st = st.sampled_from(["father", "mother"])


def _make_person(person_id: str, sex: str = "U") -> Person:
    """Create a minimal Person."""
    return Person(id=person_id, sex=sex, names=[Name(type="birth", given="", surname="")])


def _make_project_data(
    persons: list[Person],
    families: list[Family],
) -> ProjectData:
    """Build a minimal ProjectData with the given persons and families."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        families=families,
    )


# ---------------------------------------------------------------------------
# Test: Bug Condition — Sequential parent addition creates duplicate families
# ---------------------------------------------------------------------------


class TestDuplicateFamilyBugExploration:
    """Test that simulates how handle_placeholder_click creates a duplicate
    family when adding a second parent via context menu (empty family_id)
    to a child that already exists in a family.

    On UNFIXED code this test WILL FAIL because the else branch unconditionally
    creates a new family without searching for an existing family where the
    child is already a member.

    **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
    """

    @given(
        child_id=_person_id_st,
        first_parent_id=_person_id_st,
        second_parent_id=_person_id_st,
        existing_family_id=_family_id_st,
        first_parent_role=_first_parent_role_st,
        second_parent_role=_second_parent_role_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_second_parent_added_to_existing_family(
        self,
        child_id: str,
        first_parent_id: str,
        second_parent_id: str,
        existing_family_id: str,
        first_parent_role: str,
        second_parent_role: str,
    ) -> None:
        """Property 1 (Bug Condition): When a child (P1) already exists in a
        family (family_1) with one parent (P2), and a second parent (P3) is
        added via handle_placeholder_click with role="father"/"mother" and
        family_id="", the child SHALL exist in exactly ONE family as a child,
        that family SHALL have both parents as partners, and
        parent_child_links for both parents SHALL exist in that same family.

        Feature: family-relationship-creation-bug, Property 1: Bug Condition
        **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
        """
        # Ensure all IDs are distinct
        if child_id == first_parent_id:
            first_parent_id = first_parent_id + "_p1"
        if child_id == second_parent_id:
            second_parent_id = second_parent_id + "_p2"
        if first_parent_id == second_parent_id:
            second_parent_id = second_parent_id + "_p2"

        # --- SETUP: Child already exists in a family with one parent ---
        existing_family = Family(
            id=existing_family_id,
            partners=[FamilyPartner(person_id=first_parent_id, role=first_parent_role)],
            children=[child_id],
            parent_child_links=[
                ParentChildLink(
                    child_id=child_id,
                    parent_id=first_parent_id,
                    parentage_type="biological",
                )
            ],
        )

        persons = [
            _make_person(child_id, "U"),
            _make_person(first_parent_id, "M" if first_parent_role == "father" else "F"),
            _make_person(second_parent_id, "M" if second_parent_role == "father" else "F"),
        ]

        data = _make_project_data(persons=persons, families=[existing_family])

        # --- SIMULATE: What handle_placeholder_click's else branch does (FIXED) ---
        # After the fix, when family_id="" and role is "father"/"mother", the code
        # first searches for an existing family where active_id is in f.children.
        # If found, it adds the new parent to that family instead of creating a new one.
        partner_role = "father" if second_parent_role == "father" else "mother"
        active_id = child_id  # The child is the active person

        # Search for existing family where child is already a member
        existing_fam = None
        for f in data.families:
            if active_id in f.children:
                existing_fam = f
                break

        if existing_fam:
            # Add new parent to existing family
            existing_fam.partners.append(
                FamilyPartner(person_id=second_parent_id, role=partner_role)
            )
            existing_fam.parent_child_links.append(
                ParentChildLink(child_id=active_id, parent_id=second_parent_id, parentage_type="biological")
            )
        else:
            # No existing family — create new one (first parent addition)
            new_family_id = "family_new_generated"
            new_family = Family(
                id=new_family_id,
                partners=[FamilyPartner(person_id=second_parent_id, role=partner_role)],
                children=[active_id] if active_id else [],
                parent_child_links=[
                    ParentChildLink(
                        child_id=active_id,
                        parent_id=second_parent_id,
                        parentage_type="biological",
                    )
                ] if active_id else [],
            )
            data.families.append(new_family)

        # --- ASSERT: Expected correct behavior ---
        # The child should exist in exactly ONE family as a child
        families_containing_child = [
            f for f in data.families if child_id in f.children
        ]

        assert len(families_containing_child) == 1, (
            f"BUG CONFIRMED: Child {child_id!r} exists in "
            f"{len(families_containing_child)} families as a child "
            f"(expected exactly 1). "
            f"Families: {[f.id for f in families_containing_child]}. "
            f"The else branch in handle_placeholder_click created a duplicate "
            f"family instead of adding the second parent to the existing family."
        )

        # The single family should have both parents as partners
        the_family = families_containing_child[0]
        partner_ids = {p.person_id for p in the_family.partners}

        assert first_parent_id in partner_ids, (
            f"Expected first parent {first_parent_id!r} in family partners, "
            f"got {partner_ids}"
        )
        assert second_parent_id in partner_ids, (
            f"Expected second parent {second_parent_id!r} in family partners, "
            f"got {partner_ids}"
        )

        # Both parents should have parent_child_links in the same family
        linked_parent_ids = {
            link.parent_id
            for link in the_family.parent_child_links
            if link.child_id == child_id
        }

        assert first_parent_id in linked_parent_ids, (
            f"Expected parent_child_link for first parent {first_parent_id!r} "
            f"in the family, got links with parent_ids={linked_parent_ids}"
        )
        assert second_parent_id in linked_parent_ids, (
            f"Expected parent_child_link for second parent {second_parent_id!r} "
            f"in the family, got links with parent_ids={linked_parent_ids}"
        )
