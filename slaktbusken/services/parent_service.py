"""Service for managing parent-child relationships.

ParentService encapsulates business logic for adding, updating, and removing
parent relationships, including Family lookup/creation and validation of
duplicate and max-parent constraints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.project_service import ValidationError


_VALID_PARENTAGE_TYPES = {"biological", "foster", "adoptive", "donation"}


def _role_for_sex(sex: str) -> str:
    """Map a person's sex field to a FamilyPartner role."""
    if sex == "M":
        return "father"
    if sex == "F":
        return "mother"
    return "partner"


def _format_person_name(person: Person) -> str:
    """Format a person's display name as 'given surname' from their first Name entry."""
    if not person.names:
        return person.id
    name = person.names[0]
    parts = []
    if name.given:
        parts.append(name.given)
    if name.surname:
        parts.append(name.surname)
    return " ".join(parts) if parts else person.id


@dataclass
class ParentInfo:
    """Display information for a parent relationship."""

    parent_id: str
    parent_name: str
    parentage_type: str
    family_id: str


class ParentService:
    """Business logic for managing parent-child relationships."""

    def __init__(self, project_data: ProjectData) -> None:
        self._project_data = project_data
        existing_ids: set[str] = set()
        for family in project_data.families:
            existing_ids.add(family.id)
        for person in project_data.persons:
            existing_ids.add(person.id)
        self._id_generator = IDGenerator(existing_ids)

    def _find_person(self, person_id: str) -> Optional[Person]:
        """Find a person by ID in project data."""
        for person in self._project_data.persons:
            if person.id == person_id:
                return person
        return None

    def get_parents_for_person(self, person_id: str) -> list[ParentInfo]:
        """Return all parents linked to person_id with their display info."""
        results: list[ParentInfo] = []
        for family in self._project_data.families:
            for link in family.parent_child_links:
                if link.child_id == person_id and link.parent_id is not None:
                    parent = self._find_person(link.parent_id)
                    parent_name = _format_person_name(parent) if parent else link.parent_id
                    results.append(
                        ParentInfo(
                            parent_id=link.parent_id,
                            parent_name=parent_name,
                            parentage_type=link.parentage_type,
                            family_id=family.id,
                        )
                    )
        return results

    def validate_add(
        self, child_id: str, parent_id: str, parentage_type: str
    ) -> list[str]:
        """Return validation errors (empty list = valid).

        Checks:
        - Duplicate: same parent + same parentage_type already linked to child.
        - Max parents: at most two parents per parentage_type (one father-role, one mother-role).
        """
        errors: list[str] = []

        # Check duplicate: same parent_id + same parentage_type for this child
        for family in self._project_data.families:
            for link in family.parent_child_links:
                if (
                    link.child_id == child_id
                    and link.parent_id == parent_id
                    and link.parentage_type == parentage_type
                ):
                    errors.append("Denna föräldrarelation finns redan.")
                    return errors

        # Check max parents per parentage type
        # Determine the role of the new parent based on their sex
        new_parent = self._find_person(parent_id)
        if new_parent is not None:
            new_role = _role_for_sex(new_parent.sex)
        else:
            new_role = "partner"

        # Count existing parents of the same role for the same parentage_type
        same_role_count = 0
        for family in self._project_data.families:
            for link in family.parent_child_links:
                if (
                    link.child_id == child_id
                    and link.parentage_type == parentage_type
                    and link.parent_id is not None
                ):
                    existing_parent = self._find_person(link.parent_id)
                    if existing_parent is not None:
                        existing_role = _role_for_sex(existing_parent.sex)
                    else:
                        existing_role = "partner"
                    if existing_role == new_role:
                        same_role_count += 1

        if same_role_count >= 1:
            errors.append(
                "Maximalt två föräldrar per föräldratyp (en far, en mor)."
            )

        return errors

    def add_parent(
        self, child_id: str, parent_id: str, parentage_type: str
    ) -> ParentChildLink:
        """Add a parent relationship. Creates/updates Family as needed.

        Raises:
            ValidationError: If duplicate or max-parent constraint violated.
        """
        errors = self.validate_add(child_id, parent_id, parentage_type)
        if errors:
            raise ValidationError(errors)

        link = ParentChildLink(
            child_id=child_id,
            parent_id=parent_id,
            parentage_type=parentage_type,
        )

        # Determine role for the parent
        parent = self._find_person(parent_id)
        role = _role_for_sex(parent.sex) if parent else "partner"

        # Find an existing family where child is a child
        # Prefer a family whose existing links match the parentage_type
        candidate_families: list[Family] = []
        for family in self._project_data.families:
            if child_id in family.children:
                candidate_families.append(family)

        target_family: Optional[Family] = None

        if candidate_families:
            # If multiple families, prefer the one with matching parentage_type
            for family in candidate_families:
                for existing_link in family.parent_child_links:
                    if existing_link.parentage_type == parentage_type:
                        target_family = family
                        break
                if target_family:
                    break

            # If no family with matching parentage_type, use the first one
            if target_family is None:
                target_family = candidate_families[0]

            # Add parent as partner if not already present
            partner_ids = {p.person_id for p in target_family.partners}
            if parent_id not in partner_ids:
                target_family.partners.append(
                    FamilyPartner(person_id=parent_id, role=role)
                )

            # Add the link
            target_family.parent_child_links.append(link)
        else:
            # Create a new Family
            new_family_id = self._id_generator.generate("family")
            target_family = Family(
                id=new_family_id,
                partners=[FamilyPartner(person_id=parent_id, role=role)],
                children=[child_id],
                parent_child_links=[link],
            )
            self._project_data.families.append(target_family)

        return link

    def update_parentage_type(
        self, child_id: str, parent_id: str, old_type: str, new_type: str
    ) -> None:
        """Change the parentage_type of an existing link."""
        for family in self._project_data.families:
            for link in family.parent_child_links:
                if (
                    link.child_id == child_id
                    and link.parent_id == parent_id
                    and link.parentage_type == old_type
                ):
                    link.parentage_type = new_type
                    return

    def remove_parent(
        self, child_id: str, parent_id: str, parentage_type: str
    ) -> None:
        """Remove a parent-child link from the containing Family."""
        for family in self._project_data.families:
            for link in family.parent_child_links:
                if (
                    link.child_id == child_id
                    and link.parent_id == parent_id
                    and link.parentage_type == parentage_type
                ):
                    family.parent_child_links.remove(link)
                    return
