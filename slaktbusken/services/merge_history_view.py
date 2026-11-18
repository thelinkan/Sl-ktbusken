"""Qt-free view model of the Merge_History (Requirement 36, design 15.12).

``build_history_rows`` returns one frozen :class:`HistoryRow` per stored
``MergeHistoryEntry``, newest first. Stored fields are copied unchanged
(36.16); the survivor is resolved through :class:`RedirectResolver`.
"""

from __future__ import annotations

from dataclasses import dataclass

from slaktbusken.model.merge_candidate import ArchivedCandidate, MergeHistoryEntry
from slaktbusken.model.project import ProjectData
from slaktbusken.services.person_summary import UNKNOWN_PERSON, PersonSummaryIndex
from slaktbusken.services.redirect_resolution import RedirectResolver, _sort_key

EMPTY_HISTORY_TEXT = "Inga sammanslagningar finns."
NO_SUMMARY_TEXT = "Ingen sammanfattning sparades."
UNRESOLVED_SURVIVOR_TEXT = "Behållen person kan inte fastställas."
NO_ARCHIVED_CANDIDATE_TEXT = "Ingen kandidat arkiverades."

SURVIVOR_RESOLVED = "resolved"
SURVIVOR_CYCLE = "cycle"
SURVIVOR_AMBIGUOUS = "ambiguous"
SURVIVOR_MISSING = "missing"


@dataclass(frozen=True)
class ArchivedCandidateRow:
    """Summary of one archived candidate: other person, assessment, comments."""

    candidate_id: str
    other_person_id: str
    other_person_name: str
    assessment: str
    comment_count: int


@dataclass(frozen=True)
class HistoryRow:
    entry_id: str
    merged_name: str
    merged_lifespan: str
    merged_id: str
    merge_date: str
    survivor_id: str | None
    survivor_name: str
    survivor_state: str
    can_navigate: bool
    summary_lines: tuple[str, ...]
    archived: tuple[ArchivedCandidateRow, ...]

    @property
    def display_name(self) -> str:
        return self.merged_name or UNKNOWN_PERSON

    @property
    def survivor_text(self) -> str:
        return self.survivor_name if self.survivor_id else UNRESOLVED_SURVIVOR_TEXT

    @property
    def summary_text_lines(self) -> tuple[str, ...]:
        return self.summary_lines or (NO_SUMMARY_TEXT,)


def _survivor_state(
    resolver: RedirectResolver,
    entry: MergeHistoryEntry,
    summaries: PersonSummaryIndex,
) -> tuple[str | None, str]:
    ambiguous = set(resolver.ambiguous_ids())
    if entry.merged_person_id in ambiguous:
        return None, SURVIVOR_AMBIGUOUS
    survivor = resolver.resolve(entry.surviving_person_id)
    if survivor is None:
        if entry.surviving_person_id in ambiguous:
            return None, SURVIVOR_AMBIGUOUS
        return None, SURVIVOR_CYCLE
    if survivor not in summaries:
        return None, SURVIVOR_MISSING
    return survivor, SURVIVOR_RESOLVED


def _archived_row(
    archived: ArchivedCandidate, merged_id: str, summaries: PersonSummaryIndex
) -> ArchivedCandidateRow:
    if archived.person_1_id == merged_id:
        other = archived.person_2_id
    else:
        other = archived.person_1_id
    return ArchivedCandidateRow(
        candidate_id=archived.id,
        other_person_id=other,
        other_person_name=summaries.name(other),
        assessment=archived.assessment,
        comment_count=len(archived.comments),
    )


def build_history_rows(
    data: ProjectData, person_id: str | None = None
) -> list[HistoryRow]:
    """Rows for all entries (``person_id`` None) or for one resolved survivor."""
    history = data.merge_history
    if not history:
        return []
    resolver = RedirectResolver(history)
    if person_id is None:
        entries = sorted(history, key=_sort_key, reverse=True)
    else:
        entries = list(reversed(resolver.merged_into(person_id)))
    summaries = PersonSummaryIndex.build(data)
    rows: list[HistoryRow] = []
    for entry in entries:
        survivor_id, state = _survivor_state(resolver, entry, summaries)
        rows.append(
            HistoryRow(
                entry_id=entry.id,
                merged_name=entry.merged_person_name,
                merged_lifespan=entry.merged_person_lifespan,
                merged_id=entry.merged_person_id,
                merge_date=entry.merge_date,
                survivor_id=survivor_id,
                survivor_name=summaries.name(survivor_id) if survivor_id else "",
                survivor_state=state,
                can_navigate=survivor_id is not None,
                summary_lines=tuple(entry.summary_lines),
                archived=tuple(
                    _archived_row(a, entry.merged_person_id, summaries)
                    for a in entry.archived_candidates
                ),
            )
        )
    return rows
