"""Property test for the project round trip with merge data.

Feature: person-comparison-and-merge, Property 1: Project round trip with
merge data.

**Validates: Requirements 32.6**
"""

from __future__ import annotations

from dataclasses import asdict

from hypothesis import given, strategies as st

from slaktbusken.model.merge_candidate import (
    ARCHIVED_ROLES,
    CANDIDATE_ASSESSMENTS,
    ArchivedCandidate,
    MergeCandidate,
    MergeCandidateComment,
    MergedIdentityMapping,
    MergeHistoryEntry,
)
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.serialization import deserialize, serialize

_SWEDISH = "åäöÅÄÖéü"
_text = st.text(
    alphabet=st.one_of(
        st.sampled_from(list(_SWEDISH + " ,.-'\"\n")),
        st.characters(blacklist_categories=("Cs",)),
    ),
    max_size=30,
)
_ident = st.text(
    alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789_" + _SWEDISH)),
    min_size=1,
    max_size=10,
)
_opt_ident = st.one_of(st.none(), _ident)


@st.composite
def _comments(draw) -> list[MergeCandidateComment]:
    ids = draw(st.lists(_ident, max_size=6, unique=True))
    return [
        MergeCandidateComment(id=i, date=draw(_text), text=draw(_text)) for i in ids
    ]


@st.composite
def _candidates(draw) -> MergeCandidate:
    return MergeCandidate(
        id=draw(_ident),
        person_1_id=draw(_ident),
        person_2_id=draw(_ident),
        assessment=draw(st.sampled_from(CANDIDATE_ASSESSMENTS)),
        enabled=draw(st.booleans()),
        research_case_id=draw(_opt_ident),
        comments=draw(_comments()),
    )


@st.composite
def _archived(draw) -> ArchivedCandidate:
    return ArchivedCandidate(
        id=draw(_ident),
        person_1_id=draw(_ident),
        person_2_id=draw(_ident),
        assessment=draw(st.sampled_from(CANDIDATE_ASSESSMENTS)),
        enabled=draw(st.booleans()),
        research_case_id=draw(_opt_ident),
        comments=draw(_comments()),
        role=draw(st.sampled_from(ARCHIVED_ROLES)),
    )


_mappings = st.builds(MergedIdentityMapping, gedcom_id=_ident, fingerprint=_opt_ident)

_history = st.builds(
    MergeHistoryEntry,
    id=_ident,
    surviving_person_id=_ident,
    merged_person_id=_ident,
    merged_person_name=_text,
    merged_person_lifespan=_text,
    merge_date=_text,
    merge_candidate_id=_opt_ident,
    archived_candidates=st.lists(_archived(), max_size=4),
    identity_mappings=st.lists(_mappings, max_size=4),
)


@given(
    candidates=st.lists(_candidates(), max_size=6),
    history=st.lists(_history, max_size=4),
    title=_text,
)
def test_project_round_trip_with_merge_data(candidates, history, title):
    """Feature: person-comparison-and-merge, Property 1: Project round trip
    with merge data. **Validates: Requirements 32.6**"""
    data = ProjectData(project=ProjectMetadata(title=title))
    data.merge_candidates = candidates
    data.merge_history = history

    first = serialize(data)
    loaded = deserialize(first)

    assert serialize(loaded) == first
    assert [asdict(c) for c in loaded.merge_candidates] == [
        asdict(c) for c in candidates
    ]
    assert [asdict(h) for h in loaded.merge_history] == [asdict(h) for h in history]
    # Order of collections, ids and comment order are preserved.
    assert [c.id for c in loaded.merge_candidates] == [c.id for c in candidates]
    assert [[m.id for m in c.comments] for c in loaded.merge_candidates] == [
        [m.id for m in c.comments] for c in candidates
    ]
    assert not loaded.merge_load_findings
