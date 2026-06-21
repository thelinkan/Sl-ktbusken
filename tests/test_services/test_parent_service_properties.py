"""Property-based tests for ParentService.

Feature: redigera-person-media, Property 1: Parent relationship creation produces correct structures
Feature: redigera-person-media, Property 2: Parentage type update changes only the type field
Feature: redigera-person-media, Property 3: Parent relationship removal preserves other links
Feature: redigera-person-media, Property 4: Maximum two parents per parentage type validation
Feature: redigera-person-media, Property 5: Duplicate parent relationship detection

Validates: Requirements 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.11
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Person, Name
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.parent_service import ParentService
from slaktbusken.services.project_service import ValidationError


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_VALID_PARENTAGE_TYPES = ["biological", "foster", "adoptive", "donation"]
_VALID_SEX_VALUES = ["M", "F", "X", "U"]


def _make_person(person_id: str, sex: str, given: str = "Test", surname: str = "Person") -> Person:
    """Create a Person with a minimal name entry."""
    return Person(
        id=person_id,
        sex=sex,
        names=[Name(type="birth", given=given, surname=surname)],
    )


@st.composite
def parent_add_scenario(draw: st.DrawFn) -> tuple[ProjectData, str, str, str]:
    """Generate a scenario for adding a parent relationship.

    Returns (project_data, child_id, parent_id, parentage_type) where:
    - project_data contains at least a child person and a parent person
    - child_id and parent_id are distinct person IDs in the project
    - parentage_type is a valid type
    """
    # Generate two distinct person IDs
    child_id = draw(st.from_regex(r"person_[1-9][0-9]{0,2}", fullmatch=True))
    parent_id = draw(
        st.from_regex(r"person_[1-9][0-9]{0,2}", fullmatch=True).filter(
            lambda pid: pid != child_id
        )
    )

    child_sex = draw(st.sampled_from(_VALID_SEX_VALUES))
    parent_sex = draw(st.sampled_from(_VALID_SEX_VALUES))

    child_given = draw(st.text(alphabet=st.characters(categories=("L",)), min_size=2, max_size=10))
    child_surname = draw(st.text(alphabet=st.characters(categories=("L",)), min_size=2, max_size=10))
    parent_given = draw(st.text(alphabet=st.characters(categories=("L",)), min_size=2, max_size=10))
    parent_surname = draw(st.text(alphabet=st.characters(categories=("L",)), min_size=2, max_size=10))

    child_person = Person(
        id=child_id,
        sex=child_sex,
        names=[Name(type="birth", given=child_given, surname=child_surname)],
    )
    parent_person = Person(
        id=parent_id,
        sex=parent_sex,
        names=[Name(type="birth", given=parent_given, surname=parent_surname)],
    )

    parentage_type = draw(st.sampled_from(_VALID_PARENTAGE_TYPES))

    project_data = ProjectData(
        project=ProjectMetadata(title="Property Test"),
        persons=[child_person, parent_person],
        families=[],
    )

    return project_data, child_id, parent_id, parentage_type


@st.composite
def parent_trio_strategy(draw: st.DrawFn) -> tuple[Person, Person, Person, Person, str]:
    """Generate a child, father (M), mother (F), and a third parent with same sex as one.

    Returns (child, father, mother, third_parent, parentage_type).
    """
    ids = draw(
        st.lists(
            st.text(
                alphabet=st.characters(categories=("L", "N")),
                min_size=3,
                max_size=8,
            ),
            min_size=4,
            max_size=4,
            unique=True,
        )
    )
    child_id, father_id, mother_id, third_id = ids

    child = Person(
        id=child_id,
        sex=draw(st.sampled_from(["M", "F", "X", "U"])),
        names=[Name(type="birth", given="Child", surname="Test")],
    )
    father = Person(
        id=father_id,
        sex="M",
        names=[Name(type="birth", given="Father", surname="Test")],
    )
    mother = Person(
        id=mother_id,
        sex="F",
        names=[Name(type="birth", given="Mother", surname="Test")],
    )
    third_sex = draw(st.sampled_from(["M", "F"]))
    third_parent = Person(
        id=third_id,
        sex=third_sex,
        names=[Name(type="birth", given="Third", surname="Parent")],
    )

    parentage_type = draw(st.sampled_from(_VALID_PARENTAGE_TYPES))
    return child, father, mother, third_parent, parentage_type


@st.composite
def parentage_update_scenario(
    draw: st.DrawFn,
) -> tuple[ProjectData, str, str, str, str]:
    """Generate a scenario for updating a parentage type.

    Returns (project_data, child_id, parent_id, old_type, new_type) where:
    - A parent relationship already exists with old_type
    - new_type is different from old_type
    """
    child_id = draw(st.from_regex(r"person_[1-9][0-9]{0,2}", fullmatch=True))
    parent_id = draw(
        st.from_regex(r"person_[1-9][0-9]{0,2}", fullmatch=True).filter(
            lambda pid: pid != child_id
        )
    )

    child_sex = draw(st.sampled_from(_VALID_SEX_VALUES))
    parent_sex = draw(st.sampled_from(_VALID_SEX_VALUES))

    child_person = Person(
        id=child_id,
        sex=child_sex,
        names=[Name(type="birth", given="Child", surname="Upd")],
    )
    parent_person = Person(
        id=parent_id,
        sex=parent_sex,
        names=[Name(type="birth", given="Parent", surname="Upd")],
    )

    old_type = draw(st.sampled_from(_VALID_PARENTAGE_TYPES))
    new_type = draw(
        st.sampled_from([t for t in _VALID_PARENTAGE_TYPES if t != old_type])
    )

    project_data = ProjectData(
        project=ProjectMetadata(title="Property Test"),
        persons=[child_person, parent_person],
        families=[],
    )

    service = ParentService(project_data)
    service.add_parent(child_id, parent_id, old_type)

    return project_data, child_id, parent_id, old_type, new_type


@st.composite
def duplicate_parent_scenario(draw: st.DrawFn) -> tuple[ProjectData, str, str, str]:
    """Generate a scenario for testing duplicate parent detection.

    Returns (project_data, child_id, parent_id, parentage_type).
    """
    ids = draw(
        st.lists(
            st.text(
                alphabet=st.characters(categories=("L", "N")),
                min_size=3,
                max_size=8,
            ),
            min_size=2,
            max_size=2,
            unique=True,
        )
    )
    child_id, parent_id = ids

    child = Person(
        id=child_id,
        sex=draw(st.sampled_from(_VALID_SEX_VALUES)),
        names=[Name(type="birth", given="Child", surname="Test")],
    )
    parent = Person(
        id=parent_id,
        sex=draw(st.sampled_from(_VALID_SEX_VALUES)),
        names=[Name(type="birth", given="Parent", surname="Test")],
    )

    parentage_type = draw(st.sampled_from(_VALID_PARENTAGE_TYPES))

    project_data = ProjectData(
        project=ProjectMetadata(title="Property Test"),
        persons=[child, parent],
        families=[],
    )

    return project_data, child_id, parent_id, parentage_type


# ---------------------------------------------------------------------------
# Property 1: Parent relationship creation produces correct structures
# ---------------------------------------------------------------------------


class TestParentRelationshipCreation:
    """Feature: redigera-person-media, Property 1: Parent relationship creation produces correct structures

    For any valid child person, parent person, and parentage_type, when add_parent
    is called successfully, the project data SHALL contain a Family where the child
    is in the children list, the parent is a partner, and a ParentChildLink exists
    with matching child_id, parent_id, and parentage_type.

    **Validates: Requirements 1.4, 1.5, 1.6**
    """

    @given(scenario=parent_add_scenario())
    @settings(max_examples=100, deadline=None)
    def test_add_parent_creates_correct_structures(
        self, scenario: tuple[ProjectData, str, str, str]
    ) -> None:
        """Property 1: Parent relationship creation produces correct structures.

        Feature: redigera-person-media, Property 1: Parent relationship creation produces correct structures
        **Validates: Requirements 1.4, 1.5, 1.6**
        """
        project_data, child_id, parent_id, parentage_type = scenario

        service = ParentService(project_data)
        link = service.add_parent(child_id, parent_id, parentage_type)

        # Verify the returned link has correct fields
        assert link.child_id == child_id
        assert link.parent_id == parent_id
        assert link.parentage_type == parentage_type

        # Find a Family containing this link
        family_found = False
        for family in project_data.families:
            if link in family.parent_child_links:
                # Child must be in children list
                assert child_id in family.children, (
                    f"child_id '{child_id}' not in family.children: {family.children}"
                )
                # Parent must be a partner
                partner_ids = {p.person_id for p in family.partners}
                assert parent_id in partner_ids, (
                    f"parent_id '{parent_id}' not in family.partners: {partner_ids}"
                )
                family_found = True
                break

        assert family_found, (
            "No Family found containing the created ParentChildLink"
        )


# ---------------------------------------------------------------------------
# Property 2: Parentage type update changes only the type field
# ---------------------------------------------------------------------------


class TestParentageTypeUpdate:
    """Feature: redigera-person-media, Property 2: Parentage type update changes only the type field

    **Validates: Requirements 1.7**
    """

    @given(scenario=parentage_update_scenario())
    @settings(max_examples=100, deadline=None)
    def test_update_parentage_type_changes_only_type(
        self, scenario: tuple[ProjectData, str, str, str, str]
    ) -> None:
        """Property 2: Updating parentage type changes only the type field,
        leaving child_id and parent_id unchanged.

        Feature: redigera-person-media, Property 2: Parentage type update changes only the type field
        **Validates: Requirements 1.7**
        """
        project_data, child_id, parent_id, old_type, new_type = scenario

        service = ParentService(project_data)
        service.update_parentage_type(child_id, parent_id, old_type, new_type)

        # Find the link after update
        link_found = False
        for family in project_data.families:
            for link in family.parent_child_links:
                if link.child_id == child_id and link.parent_id == parent_id:
                    assert link.parentage_type == new_type, (
                        f"Expected parentage_type '{new_type}', got '{link.parentage_type}'"
                    )
                    link_found = True
                    break
            if link_found:
                break

        assert link_found, (
            f"No ParentChildLink found for child_id='{child_id}', "
            f"parent_id='{parent_id}' after update"
        )


# ---------------------------------------------------------------------------
# Property 3: Parent relationship removal preserves other links
# ---------------------------------------------------------------------------


class TestParentRemovalPreservesOtherLinks:
    """Feature: redigera-person-media, Property 3: Parent relationship removal preserves other links

    **Validates: Requirements 1.8**
    """

    @given(
        num_extra_parents=st.integers(min_value=1, max_value=3),
        removal_index=st.integers(min_value=0, max_value=10),
        parentage_type_indices=st.lists(
            st.integers(min_value=0, max_value=3),
            min_size=4,
            max_size=4,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_removal_preserves_other_links(
        self,
        num_extra_parents: int,
        removal_index: int,
        parentage_type_indices: list[int],
    ) -> None:
        """Property 3: Removing one parent link preserves all other links.

        Feature: redigera-person-media, Property 3: Parent relationship removal preserves other links
        **Validates: Requirements 1.8**
        """
        child = _make_person("child_1", "U")

        # Create parents with alternating sexes and varying parentage types
        # to avoid triggering max-parent-per-type validation.
        parent_configs: list[tuple[str, str, str]] = []
        sex_options = ["M", "F"]

        for i in range(num_extra_parents + 1):
            pid = f"parent_{i + 1}"
            sex = sex_options[i % 2]
            ptype = _VALID_PARENTAGE_TYPES[parentage_type_indices[i] % len(_VALID_PARENTAGE_TYPES)]
            parent_configs.append((pid, sex, ptype))

        # De-duplicate: ensure no two parents with the same role+parentage_type
        seen: set[tuple[str, str]] = set()
        unique_configs: list[tuple[str, str, str]] = []
        for pid, sex, ptype in parent_configs:
            role = "father" if sex == "M" else ("mother" if sex == "F" else "partner")
            key = (role, ptype)
            if key not in seen:
                seen.add(key)
                unique_configs.append((pid, sex, ptype))

        # Need at least 2 links to test removal preserves others
        if len(unique_configs) < 2:
            unique_configs.append(("parent_extra", "F", "foster"))

        persons = [child] + [
            _make_person(pid, sex) for pid, sex, _ in unique_configs
        ]

        project_data = ProjectData(
            project=ProjectMetadata(title="Property Test"),
            persons=persons,
            families=[],
        )
        service = ParentService(project_data)

        # Add all parent links
        for pid, _sex, ptype in unique_configs:
            service.add_parent("child_1", pid, ptype)

        # Collect all links BEFORE removal
        all_links_before: list[tuple[str, str | None, str]] = []
        for family in project_data.families:
            for link in family.parent_child_links:
                all_links_before.append(
                    (link.child_id, link.parent_id, link.parentage_type)
                )

        assert len(all_links_before) >= 2

        # Pick which link to remove
        idx_to_remove = removal_index % len(all_links_before)
        removed_link = all_links_before[idx_to_remove]

        service.remove_parent(removed_link[0], removed_link[1], removed_link[2])

        # Collect all links AFTER removal
        all_links_after: list[tuple[str, str | None, str]] = []
        for family in project_data.families:
            for link in family.parent_child_links:
                all_links_after.append(
                    (link.child_id, link.parent_id, link.parentage_type)
                )

        # Removed link is gone
        assert removed_link not in all_links_after, (
            f"Removed link {removed_link} still found after removal"
        )

        # All other links preserved
        expected_remaining = [
            lnk for i, lnk in enumerate(all_links_before) if i != idx_to_remove
        ]
        for lnk in expected_remaining:
            assert lnk in all_links_after, (
                f"Link {lnk} was expected to remain but is missing.\n"
                f"  Before: {all_links_before}\n"
                f"  After:  {all_links_after}"
            )

        assert len(all_links_after) == len(all_links_before) - 1


# ---------------------------------------------------------------------------
# Property 4: Maximum two parents per parentage type validation
# ---------------------------------------------------------------------------


class TestMaxTwoParentsPerParentageType:
    """Feature: redigera-person-media, Property 4: Maximum two parents per parentage type validation

    **Validates: Requirements 1.9**
    """

    @given(data=parent_trio_strategy())
    @settings(max_examples=100, deadline=None)
    def test_third_parent_same_role_rejected(
        self, data: tuple[Person, Person, Person, Person, str]
    ) -> None:
        """Property 4: Adding a third parent of the same parentage_type when two parents
        (one father-role, one mother-role) already exist SHALL be rejected.

        Feature: redigera-person-media, Property 4: Maximum two parents per parentage type validation
        **Validates: Requirements 1.9**
        """
        child, father, mother, third_parent, parentage_type = data

        project_data = ProjectData(
            project=ProjectMetadata(title="Property Test"),
            persons=[child, father, mother, third_parent],
            families=[],
        )

        service = ParentService(project_data)

        # Add father — should succeed
        service.add_parent(child.id, father.id, parentage_type)

        # Add mother — should succeed
        service.add_parent(child.id, mother.id, parentage_type)

        # Third parent (same role as father or mother) — should fail
        errors = service.validate_add(child.id, third_parent.id, parentage_type)
        assert len(errors) > 0, (
            f"Expected validation error when adding third parent "
            f"(sex={third_parent.sex}) with parentage_type='{parentage_type}'"
        )

        # add_parent should raise ValidationError
        raised = False
        try:
            service.add_parent(child.id, third_parent.id, parentage_type)
        except ValidationError:
            raised = True

        assert raised, "Expected ValidationError for third parent addition"


# ---------------------------------------------------------------------------
# Property 5: Duplicate parent relationship detection
# ---------------------------------------------------------------------------


class TestDuplicateParentDetection:
    """Feature: redigera-person-media, Property 5: Duplicate parent relationship detection

    **Validates: Requirements 1.11**

    For any existing ParentChildLink between a child and parent with a specific
    parentage_type, attempting to add the same combination again SHALL be rejected.
    """

    @given(scenario=duplicate_parent_scenario())
    @settings(max_examples=100, deadline=None)
    def test_duplicate_parent_is_rejected(
        self, scenario: tuple[ProjectData, str, str, str]
    ) -> None:
        """Property 5: Duplicate parent relationship detection.

        Feature: redigera-person-media, Property 5: Duplicate parent relationship detection
        **Validates: Requirements 1.11**
        """
        project_data, child_id, parent_id, parentage_type = scenario

        service = ParentService(project_data)

        # First addition should succeed
        service.add_parent(child_id, parent_id, parentage_type)

        # validate_add should now return errors for the duplicate
        errors = service.validate_add(child_id, parent_id, parentage_type)
        assert len(errors) > 0, (
            f"Expected validation errors for duplicate parent relationship "
            f"(child={child_id}, parent={parent_id}, type={parentage_type})"
        )
        assert "Denna föräldrarelation finns redan." in errors

        # add_parent should raise ValidationError
        try:
            service.add_parent(child_id, parent_id, parentage_type)
            assert False, "Expected ValidationError for duplicate add_parent"
        except ValidationError as exc:
            assert "Denna föräldrarelation finns redan." in exc.errors
