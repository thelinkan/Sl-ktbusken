"""Adjacency graph construction from ProjectData for relationship calculation.

Builds a graph where nodes are person IDs and edges represent parent-child,
child-parent, and partner relationships within families.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from slaktbusken.model.project import ProjectData


@dataclass
class Edge:
    """A directed edge in the relationship graph.

    Attributes:
        target: The person ID this edge points to.
        edge_type: One of 'parent', 'child', or 'partner'.
        parentage_type: The nature of the relationship (e.g., 'biological',
            'legal', 'adoptive', 'foster', 'step', 'unknown_donor').
            For partner edges, this is 'partner'.
    """

    target: str
    edge_type: str
    parentage_type: str


@dataclass
class RelationshipGraph:
    """Adjacency graph representation of family relationships.

    Attributes:
        adjacency: Mapping from person ID to list of outgoing edges.
        person_ids: Set of all person IDs present in the graph.
    """

    adjacency: Dict[str, List[Edge]] = field(default_factory=dict)
    person_ids: Set[str] = field(default_factory=set)

    def add_edge(self, source: str, edge: Edge) -> None:
        """Add a directed edge from source to edge.target.

        Args:
            source: The person ID the edge originates from.
            edge: The Edge instance to add.
        """
        self.person_ids.add(source)
        self.person_ids.add(edge.target)
        if source not in self.adjacency:
            self.adjacency[source] = []
        self.adjacency[source].append(edge)

    def get_edges(self, person_id: str) -> List[Edge]:
        """Get all outgoing edges for a person.

        Args:
            person_id: The person ID to look up.

        Returns:
            List of Edge instances from this person. Empty list if not found.
        """
        return self.adjacency.get(person_id, [])


def build_relationship_graph(data: ProjectData) -> RelationshipGraph:
    """Build an adjacency graph from ProjectData.

    Processes all families to create edges for:
    - Parent-to-child (edge_type='parent', meaning "this person IS a parent OF target")
    - Child-to-parent (edge_type='child', meaning "this person IS a child OF target")
    - Partner edges (bidirectional between partners in a family)

    The parentage_type on parent/child edges comes from ParentChildLink entries.
    Children without explicit ParentChildLink entries for a given parent are
    skipped (only explicit links create edges).

    Args:
        data: The ProjectData containing families with partners, children,
            and parent_child_links.

    Returns:
        A RelationshipGraph with all relationship edges.
    """
    graph = RelationshipGraph()

    for family in data.families:
        # Add partner edges (bidirectional)
        partner_ids = [p.person_id for p in family.partners]
        for i, pid_a in enumerate(partner_ids):
            for pid_b in partner_ids[i + 1:]:
                graph.add_edge(pid_a, Edge(
                    target=pid_b,
                    edge_type="partner",
                    parentage_type="partner",
                ))
                graph.add_edge(pid_b, Edge(
                    target=pid_a,
                    edge_type="partner",
                    parentage_type="partner",
                ))

        # Add parent-child edges from explicit ParentChildLink entries
        for link in family.parent_child_links:
            if link.parent_id is None:
                # Unknown donor - no edge to create
                continue

            # Parent → Child edge (edge_type='parent' means "I am parent of target")
            graph.add_edge(link.parent_id, Edge(
                target=link.child_id,
                edge_type="parent",
                parentage_type=link.parentage_type,
            ))

            # Child → Parent edge (edge_type='child' means "I am child of target")
            graph.add_edge(link.child_id, Edge(
                target=link.parent_id,
                edge_type="child",
                parentage_type=link.parentage_type,
            ))

    return graph
