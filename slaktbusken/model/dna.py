"""DNA-related data containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DnaCompany:
    """A DNA testing company."""

    id: str
    name: str
    logo_media_id: Optional[str] = None
    description: str = ""


@dataclass
class DnaProfile:
    """A DNA test profile/kit belonging to a person."""

    id: str
    person_id: str
    company_id: str
    test_type: str
    kit_name: str = ""
    kit_id: str = ""
    admin_person_id: Optional[str] = None
    admin_status: str = ""
    notes: str = ""


@dataclass
class DnaMatch:
    """A DNA match between two profiles."""

    id: str
    profile1_id: str
    profile2_id: str
    shared_cm: float = 0.0
    shared_percentage: float = 0.0
    segment_count: int = 0
    largest_segment_cm: float = 0.0
    match_source: str = "internal"
    notes: str = ""


@dataclass
class DnaSegment:
    """A shared DNA segment associated with a match."""

    id: str
    match_id: str
    chromosome: str
    start_position: int
    end_position: int
    cm: float
    snp_count: int = 0


@dataclass
class DnaCluster:
    """A grouping of DNA matches and persons into a cluster."""

    id: str
    name: str
    notes: str = ""
    company_ids: list[str] = field(default_factory=list)
    person_ids: list[str] = field(default_factory=list)
    dna_match_ids: list[str] = field(default_factory=list)
    color: Optional[str] = None


@dataclass
class DnaTriangulation:
    """A triangulated DNA match between three or more profiles."""

    id: str
    company_id: str
    profile_ids: list[str]
    shared_cm: float = 0.0
    segment_count: int = 0
    largest_segment_cm: float = 0.0
    cluster_id: Optional[str] = None
    notes: str = ""
