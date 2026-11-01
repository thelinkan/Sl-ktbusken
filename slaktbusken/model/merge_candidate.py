"""Merge candidates, comments and merge history.

A candidate says that two person records *may* be the same individual. It is
not a confirmed identity and never changes a person. Merge history records
that one person record was folded into another. Plain dataclasses, no Qt and
no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

CANDIDATE_ASSESSMENTS = ("unreviewed", "possible", "confirmed", "rejected")

ASSESSMENT_LABELS_SV = {
    "unreviewed": "Ej granskad",
    "possible": "Möjlig dubblett",
    "confirmed": "Bekräftad dublett",
    "rejected": "Inte samma person",
}

MAX_COMMENTS_PER_CANDIDATE = 500
MAX_COMMENT_TEXT = 5000

ARCHIVED_ROLES = ("direct", "collision", "self_after_redirect")


def pair_key(a: str, b: str) -> tuple[str, str]:
    """Unordered pair identity: (A, B) and (B, A) give the same key."""
    return (a, b) if a <= b else (b, a)


def assessment_label(assessment: str) -> str:
    """Swedish label for an assessment; the raw value if unknown."""
    return ASSESSMENT_LABELS_SV.get(assessment, assessment)


@dataclass
class MergeCandidateComment:
    """A dated note on one candidate."""

    id: str
    date: str = ""
    text: str = ""


@dataclass
class MergeCandidate:
    """Two person records that may be the same individual."""

    id: str
    person_1_id: str
    person_2_id: str
    assessment: str = "unreviewed"
    enabled: bool = True
    research_case_id: Optional[str] = None
    comments: list[MergeCandidateComment] = field(default_factory=list)


@dataclass
class ArchivedCandidate:
    """Full original content of a candidate removed from the active list by a merge."""

    id: str
    person_1_id: str
    person_2_id: str
    assessment: str
    enabled: bool
    research_case_id: Optional[str] = None
    comments: list[MergeCandidateComment] = field(default_factory=list)
    role: str = "direct"


@dataclass
class MergedIdentityMapping:
    """A GEDCOM identity that belonged to the retired person."""

    gedcom_id: str
    fingerprint: Optional[str] = None


@dataclass
class MergeHistoryEntry:
    """Permanent record that one person record was folded into another."""

    id: str
    surviving_person_id: str
    merged_person_id: str
    merged_person_name: str
    merged_person_lifespan: str
    merge_date: str
    merge_candidate_id: Optional[str] = None
    archived_candidates: list[ArchivedCandidate] = field(default_factory=list)
    identity_mappings: list[MergedIdentityMapping] = field(default_factory=list)


@dataclass
class LoadFinding:
    """A problem found while loading merge data (transient, never serialised)."""

    section: str
    entry_id: Optional[str]
    fields: tuple[str, ...]
    kind: str
