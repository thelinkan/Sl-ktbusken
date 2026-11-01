"""Property 20: Tooltip content and ordering.

**Validates: Requirements 19.6, 19.7, 19.8**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.model.merge_candidate import MergeCandidate, MergeHistoryEntry
from slaktbusken.model.project import ProjectData
from slaktbusken.services.candidate_index import MAX_TOOLTIP_LINES, CandidateIndex
from slaktbusken.services.person_summary import (
    PersonSummary,
    PersonSummaryIndex,
    format_lifespan,
)

SUBJECT = "P0"

PREFIX = {
    "confirmed": "Bekräftad dublett med",
    "possible": "Möjlig dublett med",
    "unreviewed": "Ej granskad kandidat:",
    "rejected": "Inte samma person som",
    "disabled": "Dublettkontroll avstängd:",
    "merged": "Slogs samman med",
}
GROUP = {
    "confirmed": 0,
    "possible": 1,
    "unreviewed": 1,
    "rejected": 2,
    "disabled": 3,
    "merged": 4,
}
YEAR = st.one_of(st.just(""), st.integers(1000, 2100).map(str))
NAME = st.text(alphabet="abcdeförsÅÄÖABC", min_size=1, max_size=6)


@st.composite
def relations(draw):
    n = draw(st.integers(min_value=1, max_value=12))
    names = draw(st.lists(NAME, min_size=n, max_size=n, unique_by=str.casefold))
    out = []
    for i, name in enumerate(names):
        kind = draw(st.sampled_from(sorted(PREFIX)))
        out.append((f"Q{i:02d}", kind, name, draw(YEAR), draw(YEAR)))
    return out


def _paren(birth: str, death: str) -> str:
    if birth and death:
        return f" ({birth}\u2013{death})"
    if birth:
        return f" ({birth})"
    if death:
        return f" (\u2013{death})"
    return ""


def _build(rels):
    data = ProjectData()
    summaries = {}
    for i, (pid, kind, name, birth, death) in enumerate(rels):
        if kind == "merged":
            data.merge_history.append(
                MergeHistoryEntry(
                    id=f"merge_{i:02d}",
                    surviving_person_id=SUBJECT,
                    merged_person_id=pid,
                    merged_person_name=name,
                    merged_person_lifespan=format_lifespan(birth, death),
                    merge_date="2024-01-01",
                )
            )
            continue
        assessment = "possible" if kind == "disabled" else kind
        data.merge_candidates.append(
            MergeCandidate(
                id=f"cand_{i:02d}",
                person_1_id=SUBJECT if i % 2 else pid,
                person_2_id=pid if i % 2 else SUBJECT,
                assessment=assessment,
                enabled=kind != "disabled",
            )
        )
        summaries[pid] = PersonSummary(pid, name, "", "", "", "", birth, death)
    return data, PersonSummaryIndex(summaries)


@given(relations())
def test_tooltip_content_and_ordering(rels):
    data, summaries = _build(rels)
    lines = CandidateIndex.build(data).tooltip_lines(SUBJECT, summaries)

    expected = sorted(
        rels, key=lambda r: (GROUP[r[1]], r[2].casefold(), r[0])
    )
    expected_lines = [
        f"{PREFIX[k]} {name}{_paren(b, d)}" for _, k, name, b, d in expected
    ]
    total = len(rels)
    if total <= MAX_TOOLTIP_LINES:
        assert lines == expected_lines
    else:
        assert MAX_TOOLTIP_LINES == 5
        assert lines[:5] == expected_lines[:5]
        assert len(lines) == 6
        assert str(total) in lines[5]
        assert str(total - 5) in lines[5]


def test_unknown_person_falls_back_without_lifespan():
    data = ProjectData()
    data.merge_candidates.append(
        MergeCandidate(id="c1", person_1_id=SUBJECT, person_2_id="ghost")
    )
    data.merge_candidates.append(
        MergeCandidate(
            id="c2", person_1_id=SUBJECT, person_2_id="Q1", assessment="confirmed"
        )
    )
    summaries = PersonSummaryIndex(
        {"Q1": PersonSummary("Q1", "Anna", "", "", "", "", "1829", "1890")}
    )
    lines = CandidateIndex.build(data).tooltip_lines(SUBJECT, summaries)
    assert lines == [
        "Bekräftad dublett med Anna (1829\u20131890)",
        "Ej granskad kandidat: Okänd person",
    ]


def test_summary_line_states_total():
    data = ProjectData()
    ids = [f"Q{i}" for i in range(7)]
    for i, pid in enumerate(ids):
        data.merge_candidates.append(
            MergeCandidate(id=f"c{i}", person_1_id=SUBJECT, person_2_id=pid)
        )
    summaries = PersonSummaryIndex(
        {p: PersonSummary(p, f"N{p}", "", "", "", "", "", "") for p in ids}
    )
    lines = CandidateIndex.build(data).tooltip_lines(SUBJECT, summaries)
    assert len(lines) == 6
    assert "totalt 7" in lines[5]
