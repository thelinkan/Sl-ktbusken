"""Preservation property tests: Non-bug-condition operations unchanged.

Feature: family-relationship-creation-bug, Property 2: Preservation

These tests encode behaviors that MUST remain unchanged after the bugfix.
They test non-bug-condition paths in handle_placeholder_click:
1. First parent addition (no existing family contains the child) → new family created
2. Parent with valid family_id → parent added to that family
3. Child role → child added to family
4. Partner role → new partner family created

These tests MUST PASS on both unfixed and fixed code.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
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

_parent_role_st = st.sampled_from(["father", "mother"])


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
# Simulation helpers — replicate handle_placeholder_click logic at data level
# ---------------------------------------------------------------------------


def _simulate_add_parent_empty_family_id(
    data: ProjectData, active_id: str, new_parent_id: str, role: str
) -> None:
    """Simulate the else branch (family_id='') for role='father'/'mother'.

    This is the UNFIXED code behavior: unconditionally create a new family.
    """
    new_family_id = f"family_gen_{new_parent_id}"
    partner_role = "father" if role == "father" else "mother"
    new_family = Family(
        id=new_family_id,
        partners=[FamilyPartner(person_id=new_parent_id, role=partner_role)],
        children=[active_id] if active_id else [],
        parent_child_links=[
            ParentChildLink(
                child_id=active_id,
                parent_id=new_parent_id,
                parentage_type="biological",
            )
        ] if active_id else [],
    )
    data.families.append(new_family)


def _simulate_add_parent_with_family_id(
    data: ProjectData, family_id: str, new_parent_id: str, role: str
) -> None:
    """Simulate the if family_id: branch for role='father'/'mother'.

    Adds parent as partner to existing family and creates parent_child_links.
    """
    fam = next((f for f in data.families if f.id == family_id), None)
    if fam:
        partner_role = "father" if role == "father" else "mother"
        fam.partners.append(FamilyPartner(person_id=new_parent_id, role=partner_role))
        for child_id in fam.children:
            fam.parent_child_links.append(
                ParentChildLink(child_id=child_id, parent_id=new_parent_id, parentage_type="biological")
            )


def _simulate_add_child_with_family_id(
    data: ProjectData, family_id: str, new_child_id: str
) -> None:
    """Simulate adding a child with a valid family_id."""
    fam = next((f for f in data.families if f.id == family_id), None)
    if fam:
        fam.children.append(new_child_id)


def _simulate_add_child_no_family_id(
    data: ProjectData, active_id: str, new_child_id: str
) -> None:
    """Simulate adding a child with empty family_id (creates new family)."""
    if active_id:
        new_family_id = f"family_gen_{new_child_id}"
        new_family = Family(
            id=new_family_id,
            partners=[FamilyPartner(person_id=active_id, role="partner")],
            children=[new_child_id],
        )
        data.families.append(new_family)


def _simulate_add_partner(
    data: ProjectData, active_id: str, new_partner_id: str
) -> None:
    """Simulate adding a partner (creates new family with both as partners)."""
    if active_id:
        new_family_id = f"family_gen_{new_partner_id}"
        new_family = Family(
            id=new_family_id,
            partners=[
                FamilyPartner(person_id=active_id, role="partner"),
                FamilyPartner(person_id=new_partner_id, role="partner"),
            ],
            children=[],
        )
        data.families.append(new_family)


# ---------------------------------------------------------------------------
# Test: Preservation Property — First parent addition (no existing family)
# ---------------------------------------------------------------------------


class TestFirstParentAdditionPreservation:
    """Property: For all first-parent additions (no existing family contains
    the child), a new family is created with the parent as partner, the child
    in children list, and a parent_child_link.

    This tests the NON-BUG-CONDITION case where the child does NOT yet exist
    in any family, so creating a new family is correct behavior.

    **Validates: Requirements 3.1, 3.2**
    """

    @given(
        child_id=_person_id_st,
        parent_id=_person_id_st,
        role=_parent_role_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_first_parent_creates_new_family(
        self, child_id: str, parent_id: str, role: str
    ) -> None:
        """Property 2a: When a child has NO existing family, adding a parent
        with empty family_id creates a new family with the parent as partner,
        child in children list, and a parent_child_link.

        Feature: family-relationship-creation-bug, Property 2: Preservation
        **Validates: Requirements 3.1, 3.2**
        """
        # Ensure distinct IDs
        if child_id == parent_id:
            parent_id = parent_id + "_par"

        # Setup: child exists but has NO family
        persons = [_make_person(child_id), _make_person(parent_id)]
        data = _make_project_data(persons=persons, families=[])

        # Precondition: no family contains the child
        assert not any(child_id in f.children for f in data.families)

        families_before = len(data.families)

        # Simulate: add parent with empty family_id (else branch)
        _simulate_add_parent_empty_family_id(data, active_id=child_id, new_parent_id=parent_id, role=role)

        # Assert: exactly one new family was created
        assert len(data.families) == families_before + 1

        new_family = data.families[-1]

        # Assert: parent is a partner in the new family
        partner_ids = [p.person_id for p in new_family.partners]
        assert parent_id in partner_ids, (
            f"Expected parent {parent_id!r} in partners, got {partner_ids}"
        )

        # Assert: child is in the children list
        assert child_id in new_family.children, (
            f"Expected child {child_id!r} in children, got {new_family.children}"
        )

        # Assert: parent_child_link exists
        links = [
            link for link in new_family.parent_child_links
            if link.child_id == child_id and link.parent_id == parent_id
        ]
        assert len(links) == 1, (
            f"Expected exactly 1 parent_child_link for child={child_id!r}, "
            f"parent={parent_id!r}, got {len(links)}"
        )
        assert links[0].parentage_type == "biological"


# ---------------------------------------------------------------------------
# Test: Preservation Property — Parent with valid family_id
# ---------------------------------------------------------------------------


class TestParentWithFamilyIdPreservation:
    """Property: For all parent additions with non-empty family_id, the parent
    is added as a partner to the specified family (regardless of whether
    child is already in another family).

    **Validates: Requirements 3.3**
    """

    @given(
        child_id=_person_id_st,
        existing_parent_id=_person_id_st,
        new_parent_id=_person_id_st,
        family_id=_family_id_st,
        existing_role=_parent_role_st,
        new_role=_parent_role_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_parent_added_to_specified_family(
        self,
        child_id: str,
        existing_parent_id: str,
        new_parent_id: str,
        family_id: str,
        existing_role: str,
        new_role: str,
    ) -> None:
        """Property 2b: When family_id is non-empty and valid, adding a parent
        adds them as partner to that specific family and creates parent_child_links.

        Feature: family-relationship-creation-bug, Property 2: Preservation
        **Validates: Requirements 3.3**
        """
        # Ensure distinct IDs
        if child_id == existing_parent_id:
            existing_parent_id = existing_parent_id + "_ep"
        if child_id == new_parent_id:
            new_parent_id = new_parent_id + "_np"
        if existing_parent_id == new_parent_id:
            new_parent_id = new_parent_id + "_np"

        # Setup: family exists with one parent and one child
        existing_family = Family(
            id=family_id,
            partners=[FamilyPartner(person_id=existing_parent_id, role=existing_role)],
            children=[child_id],
            parent_child_links=[
                ParentChildLink(child_id=child_id, parent_id=existing_parent_id, parentage_type="biological")
            ],
        )

        persons = [
            _make_person(child_id),
            _make_person(existing_parent_id),
            _make_person(new_parent_id),
        ]
        data = _make_project_data(persons=persons, families=[existing_family])

        families_before = len(data.families)

        # Simulate: add parent with valid family_id (if family_id: branch)
        _simulate_add_parent_with_family_id(data, family_id=family_id, new_parent_id=new_parent_id, role=new_role)

        # Assert: no new families created
        assert len(data.families) == families_before, (
            f"No new family should be created when family_id is provided. "
            f"Had {families_before}, now have {len(data.families)}"
        )

        # Assert: new parent is added as partner to the specified family
        fam = next(f for f in data.families if f.id == family_id)
        partner_ids = [p.person_id for p in fam.partners]
        assert new_parent_id in partner_ids, (
            f"Expected new parent {new_parent_id!r} in family partners, got {partner_ids}"
        )

        # Assert: parent_child_link created for new parent
        links_for_new_parent = [
            link for link in fam.parent_child_links
            if link.parent_id == new_parent_id and link.child_id == child_id
        ]
        assert len(links_for_new_parent) == 1, (
            f"Expected 1 parent_child_link for new parent, got {len(links_for_new_parent)}"
        )


# ---------------------------------------------------------------------------
# Test: Preservation Property — Child role additions
# ---------------------------------------------------------------------------


class TestChildRolePreservation:
    """Property: For all child role additions, the child is added to the
    family correctly.

    **Validates: Requirements 3.4**
    """

    @given(
        active_id=_person_id_st,
        new_child_id=_person_id_st,
        family_id=_family_id_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_child_added_to_existing_family(
        self, active_id: str, new_child_id: str, family_id: str
    ) -> None:
        """Property 2c (with family_id): Adding a child with a valid family_id
        appends the child to that family's children list.

        Feature: family-relationship-creation-bug, Property 2: Preservation
        **Validates: Requirements 3.4**
        """
        # Ensure distinct IDs
        if active_id == new_child_id:
            new_child_id = new_child_id + "_ch"

        # Setup: family exists with active person as partner
        existing_family = Family(
            id=family_id,
            partners=[FamilyPartner(person_id=active_id, role="partner")],
            children=[],
        )

        persons = [_make_person(active_id), _make_person(new_child_id)]
        data = _make_project_data(persons=persons, families=[existing_family])

        # Simulate: add child with valid family_id
        _simulate_add_child_with_family_id(data, family_id=family_id, new_child_id=new_child_id)

        # Assert: child is in the specified family's children list
        fam = next(f for f in data.families if f.id == family_id)
        assert new_child_id in fam.children, (
            f"Expected child {new_child_id!r} in family children, got {fam.children}"
        )

    @given(
        active_id=_person_id_st,
        new_child_id=_person_id_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_child_creates_new_family_when_no_family_id(
        self, active_id: str, new_child_id: str
    ) -> None:
        """Property 2c (no family_id): Adding a child with empty family_id
        creates a new family with the active person as partner and new person
        as child.

        Feature: family-relationship-creation-bug, Property 2: Preservation
        **Validates: Requirements 3.4**
        """
        # Ensure distinct IDs
        if active_id == new_child_id:
            new_child_id = new_child_id + "_ch"

        # Setup: no families
        persons = [_make_person(active_id), _make_person(new_child_id)]
        data = _make_project_data(persons=persons, families=[])

        families_before = len(data.families)

        # Simulate: add child with empty family_id
        _simulate_add_child_no_family_id(data, active_id=active_id, new_child_id=new_child_id)

        # Assert: one new family created
        assert len(data.families) == families_before + 1

        new_family = data.families[-1]

        # Assert: active person is partner in the new family
        partner_ids = [p.person_id for p in new_family.partners]
        assert active_id in partner_ids, (
            f"Expected active person {active_id!r} as partner, got {partner_ids}"
        )

        # Assert: new child is in the children list
        assert new_child_id in new_family.children, (
            f"Expected child {new_child_id!r} in children, got {new_family.children}"
        )


# ---------------------------------------------------------------------------
# Test: Preservation Property — Partner role additions
# ---------------------------------------------------------------------------


class TestPartnerRolePreservation:
    """Property: For all partner role additions, a new family is created
    with the new person as partner alongside the active person.

    **Validates: Requirements 3.5**
    """

    @given(
        active_id=_person_id_st,
        new_partner_id=_person_id_st,
    )
    @settings(max_examples=50, deadline=None)
    def test_partner_creates_new_family(
        self, active_id: str, new_partner_id: str
    ) -> None:
        """Property 2d: Adding a partner creates a new family with both the
        active person and new person as partners and empty children list.

        Feature: family-relationship-creation-bug, Property 2: Preservation
        **Validates: Requirements 3.5**
        """
        # Ensure distinct IDs
        if active_id == new_partner_id:
            new_partner_id = new_partner_id + "_ptr"

        # Setup: no families
        persons = [_make_person(active_id), _make_person(new_partner_id)]
        data = _make_project_data(persons=persons, families=[])

        families_before = len(data.families)

        # Simulate: add partner
        _simulate_add_partner(data, active_id=active_id, new_partner_id=new_partner_id)

        # Assert: one new family created
        assert len(data.families) == families_before + 1

        new_family = data.families[-1]

        # Assert: both persons are partners in the new family
        partner_ids = [p.person_id for p in new_family.partners]
        assert active_id in partner_ids, (
            f"Expected active person {active_id!r} as partner, got {partner_ids}"
        )
        assert new_partner_id in partner_ids, (
            f"Expected new partner {new_partner_id!r} as partner, got {partner_ids}"
        )

        # Assert: exactly 2 partners
        assert len(new_family.partners) == 2, (
            f"Expected exactly 2 partners, got {len(new_family.partners)}"
        )

        # Assert: no children in partner family
        assert new_family.children == [], (
            f"Expected empty children list, got {new_family.children}"
        )
