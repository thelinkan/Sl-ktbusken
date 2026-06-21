"""Bug condition exploration test: Spurious family on add parent.

Feature: spurious-family-on-add-parent, Property 1: Bug Condition

This test encodes the EXPECTED behavior. When run on UNFIXED code, these tests
are expected to FAIL, confirming the bug exists.

Bug overview:
1. Creation bug: `handle_placeholder_click` creates a Family with
   `children=[active_id]` but WITHOUT any `parent_child_links` when role
   is "father" or "mother" and `family_id` is empty.
2. Display bug: `_find_children` returns ALL children from a family where a
   person is a partner, regardless of whether `parent_child_links` connect
   that parent to those children.

**Validates: Requirements 1.1, 1.2**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
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

_role_st = st.sampled_from(["father", "mother"])


def _make_project_data(families: list[Family]) -> ProjectData:
    """Build a minimal ProjectData with the given families."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        families=families,
    )


# ---------------------------------------------------------------------------
# Test: Creation bug — Family created without ParentChildLink
# ---------------------------------------------------------------------------


class TestCreationBugExploration:
    """Test that simulates how handle_placeholder_click creates a Family for
    a father/mother with empty family_id — and asserts that parent_child_links
    is non-empty (the expected correct behavior).

    On UNFIXED code this test WILL FAIL because the code creates
    Family(..., parent_child_links=[]) (default empty list).

    **Validates: Requirements 1.1, 1.2**
    """

    @given(
        parent_id=_person_id_st,
        child_id=_person_id_st,
        role=_role_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_new_parent_family_has_parent_child_links(
        self,
        parent_id: str,
        child_id: str,
        role: str,
    ) -> None:
        """Property 1 (Creation): When a new Family is created for a parent
        (father/mother) with an empty family_id and a non-null active_id,
        it SHALL contain a ParentChildLink connecting the parent to the child.

        This test replicates the exact Family construction from
        handle_placeholder_click's else branch (no existing family_id).

        Feature: spurious-family-on-add-parent, Property 1: Bug Condition
        **Validates: Requirements 1.1, 1.2**
        """
        # Ensure parent and child are different
        if parent_id == child_id:
            child_id = child_id + "_child"

        # Simulate what handle_placeholder_click does:
        # It creates a Family exactly like this (the buggy code)
        partner_role = "father" if role == "father" else "mother"
        new_family = Family(
            id="fam_test",
            partners=[FamilyPartner(person_id=parent_id, role=partner_role)],
            children=[child_id],
            # NOTE: The current buggy code does NOT pass parent_child_links,
            # so it defaults to []. We are asserting expected behavior below.
        )

        # Expected behavior: parent_child_links SHOULD be non-empty
        assert len(new_family.parent_child_links) > 0, (
            f"BUG CONFIRMED: Family created for role={role!r} with "
            f"parent_id={parent_id!r}, child_id={child_id!r} has "
            f"parent_child_links=[] — no ParentChildLink was created. "
            f"Expected at least one ParentChildLink("
            f"child_id={child_id!r}, parent_id={parent_id!r}, "
            f"parentage_type='biological')."
        )

        # If we get here, also verify the link content
        link = new_family.parent_child_links[0]
        assert link.child_id == child_id
        assert link.parent_id == parent_id
        assert link.parentage_type == "biological"


# ---------------------------------------------------------------------------
# Test: Display bug — _find_children returns children without link validation
# ---------------------------------------------------------------------------


class TestDisplayBugExploration:
    """Test that _find_children only returns children that have a valid
    ParentChildLink connecting them to the queried parent.

    On UNFIXED code this test WILL FAIL because _find_children returns ALL
    children from families where the person is a partner, regardless of
    whether parent_child_links exist.

    **Validates: Requirements 1.1, 1.2**
    """

    @given(
        parent_id=_person_id_st,
        child_id=_person_id_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_find_children_requires_parent_child_link(
        self,
        parent_id: str,
        child_id: str,
    ) -> None:
        """Property 1 (Display): _find_children SHALL return an empty list
        when a person is a partner in a family that has children but NO
        parent_child_links connecting that parent to those children.

        This demonstrates the display bug: the current code returns
        children regardless of link existence.

        Feature: spurious-family-on-add-parent, Property 1: Bug Condition
        **Validates: Requirements 1.1, 1.2**
        """
        # Ensure parent and child are different
        if parent_id == child_id:
            child_id = child_id + "_child"

        # Create a family with children but NO parent_child_links
        # This simulates the state created by the buggy handle_placeholder_click
        family = Family(
            id="fam_display_test",
            partners=[FamilyPartner(person_id=parent_id, role="father")],
            children=[child_id],
            parent_child_links=[],  # No links!
        )

        project_data = _make_project_data([family])

        # Expected behavior: _find_children should return [] because
        # there is no ParentChildLink connecting parent_id to child_id
        result = _find_children(project_data, parent_id)

        assert result == [], (
            f"BUG CONFIRMED: _find_children returned {result!r} for "
            f"parent_id={parent_id!r} despite family having "
            f"parent_child_links=[]. Expected empty list. "
            f"The function incorrectly returns children based solely on "
            f"presence in family.children without verifying parent_child_links."
        )
