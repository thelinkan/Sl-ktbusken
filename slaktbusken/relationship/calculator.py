"""Relationship calculator using bidirectional BFS.

Computes genealogical and legal relationships between two persons by
finding common ancestors and constructing paths through the family graph.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from slaktbusken.model.project import ProjectData
from slaktbusken.relationship.graph_builder import (
    Edge,
    RelationshipGraph,
    build_relationship_graph,
)
from slaktbusken.relationship.kinship_terms import (
    SwedishKinshipTerms,
    is_blood_parentage,
)


@dataclass
class RelationshipPath:
    """A computed relationship path between two persons.

    Attributes:
        person_a_id: The ID of the first person.
        person_b_id: The ID of the second person.
        common_ancestor_ids: IDs of common ancestors in this path.
        path_nodes: Ordered list of person IDs from A to B.
        path_edges: Edge types between adjacent nodes ('parent', 'child', 'partner').
        generations_a: Steps from A to common ancestor.
        generations_b: Steps from common ancestor down to B.
        relationship_type: 'blood', 'legal', or 'adoption'.
        swedish_term: The Swedish kinship term (e.g., 'kusin', 'morbror').
    """

    person_a_id: str
    person_b_id: str
    common_ancestor_ids: list[str]
    path_nodes: list[str]
    path_edges: list[str]
    generations_a: int
    generations_b: int
    relationship_type: str
    swedish_term: str


class RelationshipCalculator:
    """Bidirectional BFS-based relationship finder.

    Finds all relationship paths between two persons by:
    1. Building an adjacency graph from project data
    2. BFS from both persons to find common ancestors
    3. Constructing paths through those ancestors
    4. Classifying each path with Swedish kinship terms

    Attributes:
        max_generations: Maximum generations to search in each direction.
        max_paths: Maximum number of paths to return.
    """

    def __init__(self, data: ProjectData) -> None:
        """Initialize the calculator with project data.

        Args:
            data: The ProjectData containing persons and families.
        """
        self._data = data
        self._graph = build_relationship_graph(data)
        self._kinship = SwedishKinshipTerms()
        self._person_sex_map: Dict[str, str] = {
            p.id: p.sex for p in data.persons
        }

    def find_relationships(
        self,
        person_a_id: str,
        person_b_id: str,
        include_legal: bool = True,
        closest_only: bool = True,
        blood_priority: bool = True,
        max_generations: int = 30,
        max_paths: int = 50,
    ) -> list[RelationshipPath]:
        """Find relationship paths between two persons.

        Uses bidirectional BFS to find common ancestors, then constructs
        and classifies paths.

        If blood_priority is True (default):
        - First collect all blood (genealogical) paths.
        - If at least one blood path exists, return only blood paths.
        - If NO blood path exists, fall back to returning only the
          single closest non-blood path (spouse/adoption/foster).
        - If no path of any kind exists, return an empty list.

        Args:
            person_a_id: ID of the first person.
            person_b_id: ID of the second person.
            include_legal: Whether to include legal relationships.
            closest_only: If True, return only the closest relationship(s).
            blood_priority: If True, prefer blood paths over non-blood.
            max_generations: Maximum generations to traverse.
            max_paths: Maximum number of paths to return.

        Returns:
            List of RelationshipPath instances, sorted by total distance.
        """
        if person_a_id == person_b_id:
            return []

        # Check that both persons exist in graph
        if (person_a_id not in self._graph.person_ids or
                person_b_id not in self._graph.person_ids):
            return []

        # BFS from both sides to find ancestors with paths
        ancestors_a = self._bfs_ancestors(
            person_a_id, max_generations, include_legal
        )
        ancestors_b = self._bfs_ancestors(
            person_b_id, max_generations, include_legal
        )

        # Find common ancestors
        common = set(ancestors_a.keys()) & set(ancestors_b.keys())

        # Also check direct paths (one person is ancestor of the other)
        all_paths: list[RelationshipPath] = []

        if person_a_id in ancestors_b:
            # A is an ancestor of B
            paths_from_b = ancestors_b[person_a_id]
            for path_info in paths_from_b:
                rel_path = self._build_direct_path(
                    person_a_id, person_b_id,
                    path_info, is_a_ancestor=True
                )
                if rel_path:
                    all_paths.append(rel_path)

        if person_b_id in ancestors_a:
            # B is an ancestor of A
            paths_from_a = ancestors_a[person_b_id]
            for path_info in paths_from_a:
                rel_path = self._build_direct_path(
                    person_a_id, person_b_id,
                    path_info, is_a_ancestor=False
                )
                if rel_path:
                    all_paths.append(rel_path)

        # Paths through common ancestors, filtering redundant ones.
        # A path through ancestor C is redundant if BOTH sides pass
        # through the SAME closer common ancestor C' on their way to C.
        # This means A and B already have a closer relationship via C',
        # and the path via C is just the same connection viewed from
        # further back. However, if A reaches C through one intermediate
        # lineage and B reaches C through a DIFFERENT intermediate lineage,
        # the path is NOT redundant — it represents a distinct relationship.
        for ancestor_id in common:
            if ancestor_id == person_a_id or ancestor_id == person_b_id:
                continue  # Already handled above
            paths_a = ancestors_a[ancestor_id]
            paths_b = ancestors_b[ancestor_id]
            for pa in paths_a:
                for pb in paths_b:
                    # Intermediate nodes on each side (excluding start and end)
                    intermediate_a = set(pa.nodes[1:-1])
                    intermediate_b = set(pb.nodes[1:-1])
                    # The path is redundant only if both sides share a
                    # common intermediate node that is itself a common
                    # ancestor. That means both A and B reach ancestor C
                    # through the same closer common ancestor C'.
                    shared_intermediates = intermediate_a & intermediate_b
                    if shared_intermediates & common:
                        continue
                    rel_path = self._build_path_through_ancestor(
                        person_a_id, person_b_id, ancestor_id, pa, pb
                    )
                    if rel_path:
                        all_paths.append(rel_path)

        # Also find partner-only direct connections
        partner_paths = self._find_direct_partner_paths(
            person_a_id, person_b_id
        )
        all_paths.extend(partner_paths)

        # Find paths that go through partner edges (in-law, spouse-of-relative)
        if include_legal:
            partner_extended = self._find_partner_extended_paths(
                person_a_id, person_b_id, max_generations
            )
            all_paths.extend(partner_extended)

        if not all_paths:
            return []

        # Deduplicate paths by path_nodes
        all_paths = self._deduplicate_paths(all_paths)

        # Apply blood_priority logic
        if blood_priority:
            blood_paths = [p for p in all_paths if p.relationship_type == "blood"]
            if blood_paths:
                # Return only blood paths
                all_paths = blood_paths
            else:
                # No blood paths - return only the single closest non-blood path
                all_paths.sort(
                    key=lambda p: p.generations_a + p.generations_b
                )
                all_paths = all_paths[:1]
        elif not include_legal:
            all_paths = [p for p in all_paths if p.relationship_type == "blood"]

        # Sort by total generational distance
        all_paths.sort(key=lambda p: p.generations_a + p.generations_b)

        if closest_only and all_paths:
            min_dist = all_paths[0].generations_a + all_paths[0].generations_b
            all_paths = [
                p for p in all_paths
                if p.generations_a + p.generations_b == min_dist
            ]

        return all_paths[:max_paths]

    def describe_relationship(self, path: RelationshipPath) -> str:
        """Return the Swedish-language description for a relationship path.

        Args:
            path: The RelationshipPath to describe.

        Returns:
            Swedish kinship term string.
        """
        return path.swedish_term

    def _bfs_ancestors(
        self,
        start_id: str,
        max_generations: int,
        include_legal: bool,
    ) -> Dict[str, List[_PathInfo]]:
        """BFS upward from a person to find all reachable ancestors.

        Traverses 'child' edges (going up to parents) to find ancestors.

        Args:
            start_id: Person ID to start from.
            max_generations: Maximum depth to search.
            include_legal: Whether to traverse non-blood edges.

        Returns:
            Dict mapping ancestor_id to list of PathInfo (path, generations,
            edge types, parentage types).
        """
        # Map: person_id -> list of (path_nodes, path_edges, parentage_types)
        result: Dict[str, List[_PathInfo]] = {}
        result[start_id] = [_PathInfo(
            nodes=[start_id],
            edges=[],
            parentage_types=[],
            generations=0,
        )]

        # BFS queue: (person_id, current_path_nodes, current_edges, parentage_types, depth)
        queue: deque[Tuple[str, List[str], List[str], List[str], int]] = deque()
        queue.append((start_id, [start_id], [], [], 0))

        visited_edges: Set[Tuple[str, str]] = set()

        while queue:
            current_id, path_nodes, path_edges, parentage_types, depth = queue.popleft()

            if depth >= max_generations:
                continue

            for edge in self._graph.get_edges(current_id):
                # Only traverse 'child' edges (going up to parents)
                if edge.edge_type != "child":
                    continue

                # Skip non-blood if not including legal
                if not include_legal and not is_blood_parentage(edge.parentage_type):
                    continue

                edge_key = (current_id, edge.target)
                if edge_key in visited_edges:
                    continue
                visited_edges.add(edge_key)

                new_nodes = path_nodes + [edge.target]
                new_edges = path_edges + ["child"]
                new_parentage = parentage_types + [edge.parentage_type]
                new_depth = depth + 1

                path_info = _PathInfo(
                    nodes=new_nodes,
                    edges=new_edges,
                    parentage_types=new_parentage,
                    generations=new_depth,
                )

                if edge.target not in result:
                    result[edge.target] = []
                result[edge.target].append(path_info)

                queue.append((
                    edge.target, new_nodes, new_edges,
                    new_parentage, new_depth
                ))

        return result

    def _build_direct_path(
        self,
        person_a_id: str,
        person_b_id: str,
        path_info: "_PathInfo",
        is_a_ancestor: bool,
    ) -> Optional[RelationshipPath]:
        """Build a path where one person is a direct ancestor of the other.

        Args:
            person_a_id: ID of person A.
            person_b_id: ID of person B.
            path_info: Path info from BFS.
            is_a_ancestor: True if A is ancestor of B.

        Returns:
            RelationshipPath or None if invalid.
        """
        if is_a_ancestor:
            # A is ancestor of B. path_info is from B's BFS going up to A.
            # Path nodes from B to A: path_info.nodes
            # We need path from A to B, so reverse
            nodes = list(reversed(path_info.nodes))
            edges = ["parent"] * len(path_info.edges)
            generations_a = 0
            generations_b = path_info.generations
            ancestor_id = person_a_id
        else:
            # B is ancestor of A. path_info is from A's BFS going up to B.
            nodes = path_info.nodes
            edges = ["child"] * len(path_info.edges)
            generations_a = path_info.generations
            generations_b = 0
            ancestor_id = person_b_id

        rel_type = self._classify_relationship_type(path_info.parentage_types)
        sex_b = self._person_sex_map.get(person_b_id, "U")

        term = self._kinship.get_term(
            generations_a=generations_a,
            generations_b=generations_b,
            sex_of_relative=sex_b,
            relationship_type=rel_type,
        )

        return RelationshipPath(
            person_a_id=person_a_id,
            person_b_id=person_b_id,
            common_ancestor_ids=[ancestor_id],
            path_nodes=nodes,
            path_edges=edges,
            generations_a=generations_a,
            generations_b=generations_b,
            relationship_type=rel_type,
            swedish_term=term,
        )

    def _build_path_through_ancestor(
        self,
        person_a_id: str,
        person_b_id: str,
        ancestor_id: str,
        path_a: "_PathInfo",
        path_b: "_PathInfo",
    ) -> Optional[RelationshipPath]:
        """Build a path connecting two persons through a common ancestor.

        Args:
            person_a_id: ID of person A.
            person_b_id: ID of person B.
            ancestor_id: ID of the common ancestor.
            path_a: Path from A up to ancestor.
            path_b: Path from B up to ancestor.

        Returns:
            RelationshipPath or None if invalid.
        """
        # path_a.nodes: [A, ..., ancestor] (going up from A)
        # path_b.nodes: [B, ..., ancestor] (going up from B)
        # Full path: A -> ... -> ancestor -> ... -> B
        # = path_a.nodes + reversed(path_b.nodes[:-1])  (excluding duplicate ancestor)

        path_b_down = list(reversed(path_b.nodes[:-1]))
        nodes = path_a.nodes + path_b_down

        # Edges from A to ancestor are 'child' (going up)
        edges_up = ["child"] * path_a.generations
        # Edges from ancestor to B are 'parent' (going down)
        edges_down = ["parent"] * path_b.generations

        edges = edges_up + edges_down

        all_parentage = path_a.parentage_types + path_b.parentage_types
        rel_type = self._classify_relationship_type(all_parentage)

        sex_b = self._person_sex_map.get(person_b_id, "U")

        term = self._kinship.get_term(
            generations_a=path_a.generations,
            generations_b=path_b.generations,
            sex_of_relative=sex_b,
            relationship_type=rel_type,
        )

        return RelationshipPath(
            person_a_id=person_a_id,
            person_b_id=person_b_id,
            common_ancestor_ids=[ancestor_id],
            path_nodes=nodes,
            path_edges=edges,
            generations_a=path_a.generations,
            generations_b=path_b.generations,
            relationship_type=rel_type,
            swedish_term=term,
        )

    def _find_direct_partner_paths(
        self,
        person_a_id: str,
        person_b_id: str,
    ) -> list[RelationshipPath]:
        """Find direct partner connections between two persons.

        Args:
            person_a_id: ID of person A.
            person_b_id: ID of person B.

        Returns:
            List of RelationshipPath for partner connections.
        """
        paths: list[RelationshipPath] = []

        for edge in self._graph.get_edges(person_a_id):
            if edge.edge_type == "partner" and edge.target == person_b_id:
                sex_b = self._person_sex_map.get(person_b_id, "U")
                if sex_b == "M":
                    term = "make"
                elif sex_b == "F":
                    term = "maka"
                else:
                    term = "partner"

                paths.append(RelationshipPath(
                    person_a_id=person_a_id,
                    person_b_id=person_b_id,
                    common_ancestor_ids=[],
                    path_nodes=[person_a_id, person_b_id],
                    path_edges=["partner"],
                    generations_a=0,
                    generations_b=0,
                    relationship_type="legal",
                    swedish_term=term,
                ))
                break

        return paths

    def _find_partner_extended_paths(
        self,
        person_a_id: str,
        person_b_id: str,
        max_generations: int,
    ) -> list[RelationshipPath]:
        """Find paths that include a partner edge (in-law, spouse-of-relative).

        Searches for paths: A --(blood/legal)--> X --(partner)--> B
        or A --(partner)--> X --(blood/legal)--> B.

        Args:
            person_a_id: ID of person A.
            person_b_id: ID of person B.
            max_generations: Maximum generations to traverse.

        Returns:
            List of RelationshipPath instances for partner-extended paths.
        """
        paths: list[RelationshipPath] = []

        # Strategy: use general BFS from A that traverses all edge types
        # to find B, tracking the path. Limit to paths with exactly one
        # partner edge to avoid explosion.
        visited: Set[str] = set()
        # Queue: (current_id, path_nodes, path_edges, parentage_types,
        #          partner_count, depth)
        queue: deque = deque()
        queue.append((person_a_id, [person_a_id], [], [], 0, 0))
        visited.add(person_a_id)

        while queue:
            (current_id, path_nodes, path_edges, parentage_types,
             partner_count, depth) = queue.popleft()

            if depth > max_generations:
                continue

            if current_id == person_b_id and len(path_nodes) > 1:
                # Found a path from A to B
                if partner_count > 0:
                    # This is a partner-extended path
                    rel_path = self._build_partner_extended_path(
                        person_a_id, person_b_id,
                        path_nodes, path_edges, parentage_types
                    )
                    if rel_path:
                        paths.append(rel_path)
                continue

            for edge in self._graph.get_edges(current_id):
                next_id = edge.target
                if next_id in visited:
                    continue

                new_partner_count = partner_count
                if edge.edge_type == "partner":
                    new_partner_count += 1

                # Limit to at most 1 partner edge to keep paths sensible
                if new_partner_count > 1:
                    continue

                visited.add(next_id)
                queue.append((
                    next_id,
                    path_nodes + [next_id],
                    path_edges + [edge.edge_type],
                    parentage_types + [edge.parentage_type],
                    new_partner_count,
                    depth + 1,
                ))

        return paths

    def _build_partner_extended_path(
        self,
        person_a_id: str,
        person_b_id: str,
        path_nodes: list[str],
        path_edges: list[str],
        parentage_types: list[str],
    ) -> Optional[RelationshipPath]:
        """Build a RelationshipPath for a partner-extended connection.

        The path goes through a partner edge. We identify the partner edge
        position and compute the Swedish term accordingly.

        Args:
            person_a_id: ID of person A.
            person_b_id: ID of person B.
            path_nodes: Nodes in the path.
            path_edges: Edge types in the path.
            parentage_types: Parentage types for each edge.

        Returns:
            RelationshipPath or None.
        """
        # Find the partner edge position
        partner_idx = None
        for i, et in enumerate(path_edges):
            if et == "partner":
                partner_idx = i
                break

        if partner_idx is None:
            return None

        # The person before the partner edge is the "relative"
        # The person after is the "partner-of-relative" = person B
        # Or: A is partner of someone who is related to B

        # Count generations: edges before partner are from A's side,
        # edges after partner are from B's side
        # But the direction matters.

        # Let's determine the term based on what B is relative to A:
        # The path without the partner edge gives us the blood/legal
        # relationship from A to the partner-node or from partner-node to B.

        # Simpler approach: compute the kinship term of the person on the
        # other side of the partner edge relative to person A, then
        # apply the in-law/partner wrapper.

        # Edges before partner: A to relative_of_b
        edges_before = path_edges[:partner_idx]
        edges_after = path_edges[partner_idx + 1:]

        sex_b = self._person_sex_map.get(person_b_id, "U")

        if partner_idx == 0:
            # A --partner--> X --blood--> B
            # B is blood relative of A's spouse
            # Compute what B is to X (A's spouse)
            gen_a_side = 0
            gen_b_side = len(edges_after)
            # Count "child" edges going down (parent edges)
            # from X to B
            child_edges = [e for e in edges_after if e == "parent"]
            parent_edges = [e for e in edges_after if e == "child"]
            # If all edges are 'parent' (going down from X to B), B is descendant of X
            # If all edges are 'child' (going up from X to B), B is ancestor of X
            # The gen counts are how the blood relative relates to the spouse
            # Then apply in-law terminology
            base_term = self._compute_base_term_from_edges(
                edges_after, parentage_types[partner_idx + 1:], person_b_id
            )
            term = self._kinship._get_in_law_or_partner_term(base_term, sex_b)
        elif partner_idx == len(path_edges) - 1:
            # A --blood--> X --partner--> B
            # X is blood relative of A, B is partner of X
            # Compute what X is to A, then B is "gift med X-term"
            relative_id = path_nodes[partner_idx]
            sex_relative = self._person_sex_map.get(relative_id, "U")
            base_term = self._compute_base_term_from_edges(
                edges_before, parentage_types[:partner_idx], relative_id
            )
            term = self._kinship._get_in_law_or_partner_term(base_term, sex_b)
        else:
            # Partner edge in the middle - complex path
            # A --edges--> X --partner--> Y --edges--> B
            # Simplify: just describe as "gift med" + relationship
            relative_id = path_nodes[partner_idx]
            sex_relative = self._person_sex_map.get(relative_id, "U")
            base_term = self._compute_base_term_from_edges(
                edges_before, parentage_types[:partner_idx], relative_id
            )
            term = self._kinship._get_in_law_or_partner_term(base_term, sex_b)

        # Determine overall relationship type
        non_partner_parentage = [
            pt for i, pt in enumerate(parentage_types) if path_edges[i] != "partner"
        ]
        if non_partner_parentage and all(
            is_blood_parentage(pt) for pt in non_partner_parentage
        ):
            rel_type = "legal"  # Still legal because of partner edge
        else:
            rel_type = "legal"

        # Compute generation counts
        # For partner-extended paths, gen counts reflect distance
        gen_a = len(edges_before)
        gen_b = len(edges_after)

        return RelationshipPath(
            person_a_id=person_a_id,
            person_b_id=person_b_id,
            common_ancestor_ids=[],
            path_nodes=path_nodes,
            path_edges=path_edges,
            generations_a=gen_a,
            generations_b=gen_b,
            relationship_type=rel_type,
            swedish_term=term,
        )

    def _compute_base_term_from_edges(
        self,
        edges: list[str],
        parentage_types: list[str],
        target_id: str,
    ) -> str:
        """Compute the kinship base term from a sequence of edges.

        Determines generations_a and generations_b from the edge sequence
        and returns the Swedish term.

        Args:
            edges: List of edge types ('child' or 'parent').
            parentage_types: Parentage types for each edge.
            target_id: The person at the end of the edges.

        Returns:
            Swedish kinship term for the blood/legal relationship.
        """
        if not edges:
            return "partner"

        # Count 'child' edges (going up) and 'parent' edges (going down)
        up_count = sum(1 for e in edges if e == "child")
        down_count = sum(1 for e in edges if e == "parent")

        sex = self._person_sex_map.get(target_id, "U")
        rel_type = self._classify_relationship_type(parentage_types)

        return self._kinship.get_term(
            generations_a=up_count,
            generations_b=down_count,
            sex_of_relative=sex,
            relationship_type=rel_type,
        )

    def _classify_relationship_type(
        self, parentage_types: list[str]
    ) -> str:
        """Classify the overall relationship type from parentage types.

        Args:
            parentage_types: List of parentage type strings along the path.

        Returns:
            'blood' if all are biological, 'adoption' if any adoptive,
            'legal' otherwise.
        """
        if not parentage_types:
            return "legal"

        if all(is_blood_parentage(pt) for pt in parentage_types):
            return "blood"

        if any(pt == "adoptive" for pt in parentage_types):
            return "adoption"

        return "legal"

    def _deduplicate_paths(
        self, paths: list[RelationshipPath]
    ) -> list[RelationshipPath]:
        """Remove duplicate paths based on path_nodes.

        Args:
            paths: List of paths to deduplicate.

        Returns:
            Deduplicated list preserving order.
        """
        seen: Set[tuple] = set()
        result: list[RelationshipPath] = []
        for path in paths:
            key = tuple(path.path_nodes)
            if key not in seen:
                seen.add(key)
                result.append(path)
        return result


@dataclass
class _PathInfo:
    """Internal path information used during BFS.

    Attributes:
        nodes: Ordered list of person IDs along the path.
        edges: Edge types traversed.
        parentage_types: Parentage types for each edge.
        generations: Number of generations traversed.
    """

    nodes: list[str]
    edges: list[str]
    parentage_types: list[str]
    generations: int
