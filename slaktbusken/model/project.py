"""Project metadata and root container data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from slaktbusken.model.dna import (
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Person
from slaktbusken.model.place import Place
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.model.source import Repository, Source


@dataclass
class ProjectMetadata:
    """Top-level descriptive metadata for a project."""

    title: str
    main_person_id: Optional[str] = None
    created_by: str = "Släktbuske"
    language: str = "sv-SE"


@dataclass
class ProjectData:
    """The root container holding all project entities."""

    format: str = "släktbuske-file"
    version: str = "0.1"
    project: ProjectMetadata = field(default_factory=lambda: ProjectMetadata(title=""))
    persons: list[Person] = field(default_factory=list)
    families: list[Family] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    places: list[Place] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    media: list[MediaItem] = field(default_factory=list)
    repositories: list[Repository] = field(default_factory=list)
    dna_companies: list[DnaCompany] = field(default_factory=list)
    dna_profiles: list[DnaProfile] = field(default_factory=list)
    dna_matches: list[DnaMatch] = field(default_factory=list)
    dna_segments: list[DnaSegment] = field(default_factory=list)
    dna_clusters: list[DnaCluster] = field(default_factory=list)
    dna_triangulations: list[DnaTriangulation] = field(default_factory=list)
    research_notes: list[ResearchNote] = field(default_factory=list)
