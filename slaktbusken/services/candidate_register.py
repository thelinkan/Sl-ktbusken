"""Candidate register logic: rows, filtering, search and sorting (Qt-free).

Used by the register window (requirement 15) through a proxy model. All
functions are pure and never modify the project data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from slaktbusken.model.merge_candidate import (
    MergeCandidate,
    MergeCandidateComment,
    assessment_label,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import is_valid_calendar_date
from slaktbusken.services.parent_service import _format_person_name

COLUMN_HEADERS = (
    "Person 1",
    "Person 2",
    "Bedömning",
    "Aktiv",
    "Senaste kommentar",
    "Forskningsärende",
)

DEFAULT_ASSESSMENTS = frozenset({"unreviewed", "possible", "confirmed"})
MAX_SEARCH_LENGTH = 200
NO_MATCH_MESSAGE = "Inga kandidater matchar."


@dataclass(frozen=True)
class RegisterFilters:
    """Active filters. ``None`` means the filter is not active.

    The default view (no filters) shows enabled candidates whose assessment is
    unreviewed, possible or confirmed (15.5, 5.2).
    """

    assessments: Optional[frozenset[str]] = None  # None -> default three
    enabled: Optional[bool] = None  # None -> only enabled candidates
    person_id: Optional[str] = None
    candidate_text: str = ""  # candidate id or name text
    research_case_id: Optional[str] = None


@dataclass(frozen=True)
class RegisterRow:
    """Display values for one candidate."""

    candidate: MergeCandidate
    person_1_name: str
    person_2_name: str
    assessment_text: str
    enabled: bool
    latest_comment: str
    case_title: str


def latest_comment(
    comments: list[MergeCandidateComment],
) -> Optional[MergeCandidateComment]:
    """Comment with the latest non-empty date; else the last stored; else None (15.9).

    Dates are ``ÅÅÅÅ``, ``ÅÅÅÅ-MM`` or ``ÅÅÅÅ-MM-DD`` so string order is date
    order. On equal dates the later comment in stored order wins.
    """
    if not comments:
        return None
    best: Optional[MergeCandidateComment] = None
    for comment in comments:
        date = (comment.date or "").strip()
        if not date or not is_valid_calendar_date(date):
            continue
        if best is None or date >= best.date.strip():
            best = comment
    return best if best is not None else comments[-1]


def latest_comment_text(comments: list[MergeCandidateComment]) -> str:
    """Text of the latest comment, empty when there is none."""
    comment = latest_comment(comments)
    return comment.text if comment is not None else ""


def _person_names(data: ProjectData) -> dict[str, str]:
    return {p.id: _format_person_name(p) for p in data.persons}


def _name(names: dict[str, str], person_id: str) -> str:
    return names.get(person_id) or person_id  # missing name shows the id (15.11)


def build_rows(data: ProjectData) -> list[RegisterRow]:
    """One row per merge candidate, in stored order."""
    names = _person_names(data)
    titles = {c.id: c.title for c in data.research_cases}
    rows: list[RegisterRow] = []
    for cand in data.merge_candidates:
        rows.append(
            RegisterRow(
                candidate=cand,
                person_1_name=_name(names, cand.person_1_id),
                person_2_name=_name(names, cand.person_2_id),
                assessment_text=assessment_label(cand.assessment),
                enabled=cand.enabled,
                latest_comment=latest_comment_text(cand.comments),
                case_title=titles.get(cand.research_case_id or "", "")
                if cand.research_case_id
                else "",
            )
        )
    return rows


def _contains(haystack: str, needle_lower: str) -> bool:
    return needle_lower in haystack.lower()


def _person_matches(row: RegisterRow, needle: str) -> bool:
    c = row.candidate
    return any(
        _contains(v, needle)
        for v in (row.person_1_name, row.person_2_name, c.person_1_id, c.person_2_id)
    )


def _search_matches(row: RegisterRow, needle: str) -> bool:
    if _person_matches(row, needle):
        return True
    if _contains(row.case_title, needle):
        return True
    return any(_contains(cm.text, needle) for cm in row.candidate.comments)


def _passes_filters(row: RegisterRow, f: RegisterFilters) -> bool:
    c = row.candidate
    allowed = f.assessments if f.assessments is not None else DEFAULT_ASSESSMENTS
    if c.assessment not in allowed:
        return False
    if f.enabled is None:
        if not c.enabled:
            return False
    elif c.enabled != f.enabled:
        return False
    if f.person_id and f.person_id not in (c.person_1_id, c.person_2_id):
        return False
    if f.candidate_text:
        needle = f.candidate_text.strip().lower()
        if needle and not (_contains(c.id, needle) or _person_matches(row, needle)):
            return False
    if f.research_case_id and c.research_case_id != f.research_case_id:
        return False
    return True


def filter_rows(
    rows: Iterable[RegisterRow],
    filters: Optional[RegisterFilters] = None,
    search: str = "",
) -> list[RegisterRow]:
    """Apply filters and search together (15.3 to 15.5, 5.2 to 5.4).

    A non-empty search includes disabled candidates when either person
    matches the query, even if the enabled filter would hide them (5.4). The
    other filters (assessment, person, case) still apply.
    """
    f = filters or RegisterFilters()
    needle = search.strip()[:MAX_SEARCH_LENGTH].lower()
    result: list[RegisterRow] = []
    for row in rows:
        if needle:
            if not _search_matches(row, needle):
                continue
            if f.enabled is None and not row.candidate.enabled:
                # Disabled rows are only included through a person match.
                if not _person_matches(row, needle):
                    continue
                f_row = RegisterFilters(
                    assessments=f.assessments,
                    enabled=False,
                    person_id=f.person_id,
                    candidate_text=f.candidate_text,
                    research_case_id=f.research_case_id,
                )
                if not _passes_filters(row, f_row):
                    continue
                result.append(row)
                continue
        if _passes_filters(row, f):
            result.append(row)
    return result


def _sort_key(row: RegisterRow, column: int):
    if column == 0:
        return row.person_1_name.casefold()
    if column == 1:
        return row.person_2_name.casefold()
    if column == 2:
        return row.assessment_text.casefold()
    if column == 3:
        return 1 if row.enabled else 0
    if column == 4:
        return row.latest_comment.casefold()
    if column == 5:
        return row.case_title.casefold()
    raise ValueError(f"Unknown column {column}")


def sort_rows(
    rows: Iterable[RegisterRow], column: int, descending: bool = False
) -> list[RegisterRow]:
    """Sort by column index 0..5; stable, so ties keep stored order (15.2)."""
    return sorted(rows, key=lambda r: _sort_key(r, column), reverse=descending)


def query_register(
    data: ProjectData,
    filters: Optional[RegisterFilters] = None,
    search: str = "",
    sort_column: Optional[int] = None,
    descending: bool = False,
) -> list[RegisterRow]:
    """Build, filter and sort in one call. Empty result -> show NO_MATCH_MESSAGE."""
    rows = filter_rows(build_rows(data), filters, search)
    if sort_column is not None:
        rows = sort_rows(rows, sort_column, descending)
    return rows
