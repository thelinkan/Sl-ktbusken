"""Property 5: Validation of assessments, comments and dates.

**Validates: Requirements 3.2, 4.3, 4.4**
"""

from __future__ import annotations

import calendar
import re

from hypothesis import given, strategies as st

from slaktbusken.model.merge_candidate import (
    MergeCandidate,
    MergeCandidateComment,
    MergeHistoryEntry,
)
from slaktbusken.model.validators import (
    validate_merge_candidate,
    validate_merge_candidate_comment,
    validate_merge_history_entry,
)

BAD_ASSESSMENT = "Ogiltig bedömning för sammanslagningskandidaten."
BAD_DATE = "Kommentarens datum är inte ett giltigt datum."
VALID_ASSESSMENTS = ("unreviewed", "possible", "confirmed", "rejected")

_DATE_RE = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")


def _is_real_date(value: str) -> bool:
    """Independent oracle: ÅÅÅÅ, ÅÅÅÅ-MM or ÅÅÅÅ-MM-DD naming a real date."""
    m = _DATE_RE.fullmatch(value)
    if not m:
        return False
    year, month, day = m.groups()
    if month is None:
        return True
    if not 1 <= int(month) <= 12:
        return False
    if day is None:
        return True
    return 1 <= int(day) <= calendar.monthrange(int(year), int(month))[1]


def _candidate(assessment: str = "possible", comments=None) -> MergeCandidate:
    return MergeCandidate(
        id="c1",
        person_1_id="p1",
        person_2_id="p2",
        assessment=assessment,
        comments=comments or [],
    )


def _comment(date: str, text: str = "Anteckning") -> MergeCandidateComment:
    return MergeCandidateComment(id="k1", date=date, text=text)


# Strings that look like dates, including impossible ones.
_datelike = st.builds(
    lambda y, m, d, form: (
        f"{y:04d}"
        if form == 0
        else f"{y:04d}-{m:02d}"
        if form == 1
        else f"{y:04d}-{m:02d}-{d:02d}"
    ),
    st.integers(0, 9999),
    st.integers(0, 14),
    st.integers(0, 35),
    st.integers(0, 2),
)
_any_date = st.one_of(_datelike, st.text(max_size=12))


@given(st.sampled_from(VALID_ASSESSMENTS))
def test_valid_assessment_gives_no_message(assessment):
    assert validate_merge_candidate(_candidate(assessment)) == []


@given(st.text(max_size=30).filter(lambda s: s not in VALID_ASSESSMENTS))
def test_invalid_assessment_gives_exactly_one_message(assessment):
    errors = validate_merge_candidate(_candidate(assessment))
    assert errors.count(BAD_ASSESSMENT) == 1
    assert len(errors) == 1


def test_empty_assessment_is_invalid():
    assert validate_merge_candidate(_candidate("")) == [BAD_ASSESSMENT]


@given(_any_date)
def test_comment_date_message_iff_non_empty_and_not_real_date(date):
    errors = validate_merge_candidate_comment(_comment(date))
    expected = 1 if date != "" and not _is_real_date(date) else 0
    assert errors.count(BAD_DATE) == expected
    assert len(errors) == expected


@given(st.lists(_any_date, max_size=6))
def test_one_date_message_per_bad_comment(dates):
    comments = [
        MergeCandidateComment(id=f"k{i}", date=d, text="x") for i, d in enumerate(dates)
    ]
    errors = validate_merge_candidate(_candidate(comments=comments))
    bad = sum(1 for d in dates if d != "" and not _is_real_date(d))
    comment_errors = [
        e for c in comments for e in validate_merge_candidate_comment(c)
    ]
    assert comment_errors.count(BAD_DATE) == bad
    assert errors == []


@given(st.sampled_from(["", " ", "\t\n  ", "   \u00a0 "]))
def test_empty_or_whitespace_comment_text_rejected(text):
    assert len(validate_merge_candidate_comment(_comment("", text))) == 1


@given(st.integers(5001, 5100))
def test_over_long_comment_text_rejected(n):
    assert len(validate_merge_candidate_comment(_comment("", "a" * n))) == 1


@given(
    st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
    st.sampled_from(["", "2020", "2020-02", "2020-02-29", "1999-12-31"]),
)
def test_valid_comment_gives_empty_list(text, date):
    assert validate_merge_candidate_comment(_comment(date, text)) == []


@given(
    st.dates(min_value=__import__("datetime").date(1, 1, 1)),
)
def test_valid_history_entry_gives_empty_list(d):
    entry = MergeHistoryEntry(
        id="h1",
        surviving_person_id="p1",
        merged_person_id="p2",
        merged_person_name="N",
        merged_person_lifespan="",
        merge_date=d.isoformat(),
    )
    assert validate_merge_history_entry(entry) == []
