"""Relationship calculation package.

Provides tools for computing genealogical and legal relationships
between persons in a family tree, with Swedish kinship terminology.
"""

from slaktbusken.relationship.calculator import RelationshipCalculator, RelationshipPath
from slaktbusken.relationship.graph_builder import (
    Edge,
    RelationshipGraph,
    build_relationship_graph,
)
from slaktbusken.relationship.kinship_terms import SwedishKinshipTerms, get_kinship_term

__all__ = [
    "RelationshipCalculator",
    "RelationshipPath",
    "Edge",
    "RelationshipGraph",
    "build_relationship_graph",
    "SwedishKinshipTerms",
    "get_kinship_term",
]
