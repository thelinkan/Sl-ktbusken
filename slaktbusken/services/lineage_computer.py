"""Lineage computation service for ancestor and descendant traversal.

LineageComputer provides BFS-based traversal through Family objects to
determine direct ancestors and descendants of a given person. It includes
cycle detection to handle circular references gracefully.
"""

from __future__ import annotations

import logging
from collections import deque

from slaktbusken.model.project import ProjectData

logger = logging.getLogger(__name__)


class LineageComputer:
    """Computes direct ancestor and descendant sets for a given person.

    Uses BFS traversal through Family objects to find lineage relationships.
    Includes cycle detection via visited sets to prevent infinite loops when
    circular references exist in the data.
    """

    def __init__(self, project_data: ProjectData) -> None:
        """Initialize with project data containing families and persons.

        Args:
            project_data: The root project data container with family definitions.
        """
        self._project_data = project_data

    def get_ancestors(self, person_id: str) -> set[str]:
        """Return set of person IDs that are direct ancestors of person_id.

        Traverses upward through Family objects: for each family where the
        person appears as a child, collects partner person_ids as parents,
        then continues upward recursively.

        Does NOT include person_id itself in the returned set.

        Args:
            person_id: The ID of the person whose ancestors to find.

        Returns:
            A set of person IDs representing all direct ancestors.
        """
        ancestors: set[str] = set()
        visited: set[str] = set()
        queue: deque[str] = deque()

        queue.append(person_id)
        visited.add(person_id)

        while queue:
            current_id = queue.popleft()

            for family in self._project_data.families:
                if current_id not in family.children:
                    continue

                for partner in family.partners:
                    parent_id = partner.person_id
                    if parent_id in visited:
                        if parent_id != person_id:
                            logger.warning(
                                "Cycle detected in ancestor traversal: "
                                "person '%s' already visited while computing "
                                "ancestors of '%s'",
                                parent_id,
                                person_id,
                            )
                        continue

                    visited.add(parent_id)
                    ancestors.add(parent_id)
                    queue.append(parent_id)

        return ancestors

    def get_descendants(self, person_id: str) -> set[str]:
        """Return set of person IDs that are direct descendants of person_id.

        Traverses downward through Family objects: for each family where the
        person appears as a partner, collects children, then continues
        downward recursively.

        Does NOT include person_id itself in the returned set.

        Args:
            person_id: The ID of the person whose descendants to find.

        Returns:
            A set of person IDs representing all direct descendants.
        """
        descendants: set[str] = set()
        visited: set[str] = set()
        queue: deque[str] = deque()

        queue.append(person_id)
        visited.add(person_id)

        while queue:
            current_id = queue.popleft()

            for family in self._project_data.families:
                is_partner = any(
                    p.person_id == current_id for p in family.partners
                )
                if not is_partner:
                    continue

                for child_id in family.children:
                    if child_id in visited:
                        if child_id != person_id:
                            logger.warning(
                                "Cycle detected in descendant traversal: "
                                "person '%s' already visited while computing "
                                "descendants of '%s'",
                                child_id,
                                person_id,
                            )
                        continue

                    visited.add(child_id)
                    descendants.add(child_id)
                    queue.append(child_id)

        return descendants
