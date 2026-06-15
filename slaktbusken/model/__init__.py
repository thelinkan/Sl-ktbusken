"""Domain data model for Släktbusken.

Exposes all public dataclasses and the :class:`IDGenerator` so they can be
imported directly from ``slaktbusken.model``.
"""

from __future__ import annotations

from slaktbusken.model.dna import (
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.model.source import (
    Repository,
    RepositoryRef,
    Source,
    StructuredReference,
)
from slaktbusken.model.validators import (
    validate_dna_cluster,
    validate_dna_match,
    validate_dna_profile,
    validate_dna_segment,
    validate_dna_triangulation,
    validate_event,
    validate_family,
    validate_media_item,
    validate_person,
    validate_place,
    validate_repository,
    validate_source,
)

__all__ = [
    # ID generation
    "IDGenerator",
    # Person
    "Name",
    "Person",
    # Family
    "Family",
    "FamilyPartner",
    "ParentChildLink",
    # Event
    "DateValue",
    "Event",
    "Participant",
    "PlaceRef",
    "SourceRef",
    # Place
    "Place",
    # Source
    "Repository",
    "RepositoryRef",
    "Source",
    "StructuredReference",
    # Media
    "LinkedEntity",
    "MediaItem",
    # DNA
    "DnaCluster",
    "DnaCompany",
    "DnaMatch",
    "DnaProfile",
    "DnaSegment",
    "DnaTriangulation",
    # Research notes
    "ResearchNote",
    # Project
    "ProjectData",
    "ProjectMetadata",
    # Validators
    "validate_dna_cluster",
    "validate_dna_match",
    "validate_dna_profile",
    "validate_dna_segment",
    "validate_dna_triangulation",
    "validate_event",
    "validate_family",
    "validate_media_item",
    "validate_person",
    "validate_place",
    "validate_repository",
    "validate_source",
]
