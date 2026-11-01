"""Property 19: Indicator colour precedence.

**Validates: Requirements 17.11, 19.1, 19.2, 19.3, 19.4, 19.5, 28.4**
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, strategies as st

from slaktbusken.model.merge_candidate import (
    CANDIDATE_ASSESSMENTS,
    MergeCandidate,
    MergeHistoryEntry,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.services.candidate_index import (
    BLUE,
    GREY,
    NONE,
    ORANGE,
    CandidateIndex,
    PersonCandidateRelations,
    indicator_colour,
)

SUBJECT = "person_subject"

# (assessment, enabled, subject_is_first) for each candidate of the subject.
candidate_specs = st.lists(
    st.tuples(st.sampled_from(CANDIDATE_ASSESSMENTS), st.booleans(), st.booleans()),
    max_size=8,
)


def expected_colour(specs, history_count: int) -> str:
    """Independent oracle written straight from the property statement."""
    enabled = [a for a, en, _ in specs if en]
    if "confirmed" in enabled:
        return BLUE
    if "possible" in enabled or "unreviewed" in enabled:
        return ORANGE
    if "rejected" in enabled or any(not en for _, en, _ in specs) or history_count:
        return GREY
    return NONE


def _project(specs, history_count: int) -> ProjectData:
    data = ProjectData()
    for i, (assessment, enabled, first) in enumerate(specs):
        other = f"other_{i}"
        a, b = (SUBJECT, other) if first else (other, SUBJECT)
        data.merge_candidates.append(
            MergeCandidate(
                id=f"cand_{i}",
                person_1_id=a,
                person_2_id=b,
                assessment=assessment,
                enabled=enabled,
            )
        )
    for k in range(history_count):
        data.merge_history.append(
            MergeHistoryEntry(
                id=f"merge_{k}",
                surviving_person_id=SUBJECT,
                merged_person_id=f"retired_{k}",
                merged_person_name="N",
                merged_person_lifespan="",
                merge_date="2024-01-01",
            )
        )
    return data


@given(specs=candidate_specs, history_count=st.integers(min_value=0, max_value=3))
def test_colour_precedence_through_index(specs, history_count):
    index = CandidateIndex.build(_project(specs, history_count))
    assert index.colour(SUBJECT) == expected_colour(specs, history_count)


@given(
    confirmed=st.booleans(),
    possible=st.booleans(),
    unreviewed=st.booleans(),
    rejected=st.booleans(),
    disabled=st.booleans(),
    history=st.booleans(),
)
def test_colour_function_precedence(
    confirmed, possible, unreviewed, rejected, disabled, history
):
    rel = PersonCandidateRelations(
        has_active_confirmed=confirmed,
        has_active_possible=possible,
        has_active_unreviewed=unreviewed,
        has_rejected=rejected,
        has_disabled=disabled,
        has_history=history,
    )
    if confirmed:
        expected = BLUE
    elif possible or unreviewed:
        expected = ORANGE
    elif rejected or disabled or history:
        expected = GREY
    else:
        expected = NONE
    assert indicator_colour(rel) == expected


@given(specs=candidate_specs, history_count=st.integers(min_value=0, max_value=3))
def test_same_function_for_all_consumers(specs, history_count):
    """Every consumer asks the index, which delegates to indicator_colour."""
    index = CandidateIndex.build(_project(specs, history_count))
    assert index.colour(SUBJECT) == indicator_colour(index.relations(SUBJECT))


def test_unknown_person_has_no_indicator():
    assert CandidateIndex.build(ProjectData()).colour("nobody") == NONE


def test_precedence_exists_only_in_candidate_index():
    """Static check: no other module re-implements the precedence."""
    root = Path(__file__).resolve().parents[2] / "slaktbusken"
    owner = root / "services" / "candidate_index.py"
    markers = ("has_active_confirmed", "has_active_possible", "has_active_unreviewed")
    offenders = []
    for path in root.rglob("*.py"):
        if path == owner:
            continue
        text = path.read_text(encoding="utf-8")
        if any(m in text for m in markers):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
    # The owner defines the rule exactly once.
    assert owner.read_text(encoding="utf-8").count("def indicator_colour(") == 1
