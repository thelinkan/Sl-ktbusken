"""Candidate index, indicator colour and tooltip lines (Qt-free).

``CandidateIndex.build`` makes one pass over ``merge_candidates`` and
``merge_history``; row and box code only does dictionary lookups. The single
``indicator_colour`` function is the only place Indicator_Precedence exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from slaktbusken.model.merge_candidate import MergeCandidate, MergeHistoryEntry
from slaktbusken.model.project import ProjectData
from slaktbusken.services.person_summary import UNKNOWN_PERSON, PersonSummaryIndex
from slaktbusken.services.redirect_resolution import RedirectResolver

BLUE = "blue"
ORANGE = "orange"
GREY = "grey"
NONE = "none"

MAX_TOOLTIP_LINES = 5

_CONFIRMED, _OPEN, _REJECTED, _DISABLED, _MERGED = 0, 1, 2, 3, 4

_PREFIX = {
    "confirmed": "Bekräftad dublett med",
    "possible": "Möjlig dublett med",
    "unreviewed": "Ej granskad kandidat:",
    "rejected": "Inte samma person som",
    "disabled": "Dublettkontroll avstängd:",
    "merged": "Slogs samman med",
}


@dataclass(frozen=True)
class PersonCandidateRelations:
    """Candidate and history relations of one person."""

    has_active_confirmed: bool = False
    has_active_possible: bool = False
    has_active_unreviewed: bool = False
    has_rejected: bool = False
    has_disabled: bool = False
    has_history: bool = False
    candidates: tuple[MergeCandidate, ...] = ()
    history: tuple[MergeHistoryEntry, ...] = ()


_EMPTY = PersonCandidateRelations()


def indicator_colour(rel: PersonCandidateRelations) -> str:
    """Return 'blue', 'orange', 'grey' or 'none'. The only place the rule exists."""
    if rel.has_active_confirmed:
        return BLUE
    if rel.has_active_possible or rel.has_active_unreviewed:
        return ORANGE
    if rel.has_rejected or rel.has_disabled or rel.has_history:
        return GREY
    return NONE


def _relations(
    candidates: list[MergeCandidate], history: list[MergeHistoryEntry]
) -> PersonCandidateRelations:
    enabled = [c for c in candidates if c.enabled]
    return PersonCandidateRelations(
        has_active_confirmed=any(c.assessment == "confirmed" for c in enabled),
        has_active_possible=any(c.assessment == "possible" for c in enabled),
        has_active_unreviewed=any(c.assessment == "unreviewed" for c in enabled),
        has_rejected=any(c.assessment == "rejected" for c in enabled),
        has_disabled=any(not c.enabled for c in candidates),
        has_history=bool(history),
        candidates=tuple(candidates),
        history=tuple(history),
    )


def _lifespan_with_parens(lifespan: str) -> str:
    """``1829–1890`` becomes ``(1829–1890)``; ``(1829)``/``(–1890)`` stay; empty stays."""
    text = (lifespan or "").strip()
    if not text:
        return ""
    if text.startswith("("):
        return text
    return f"({text})"


def _line(kind: str, name: str, lifespan: str) -> str:
    text = f"{_PREFIX[kind]} {name}"
    life = _lifespan_with_parens(lifespan)
    return f"{text} {life}" if life else text


class CandidateIndex:
    """Read-only per-person candidate relations, built in one pass."""

    def __init__(
        self,
        by_person: dict[str, list[MergeCandidate]],
        by_pair: dict[tuple[str, str], MergeCandidate],
        history_by_person: dict[str, list[MergeHistoryEntry]],
    ) -> None:
        self._by_person = by_person
        self._by_pair = by_pair
        self._history = history_by_person
        self._relations: dict[str, PersonCandidateRelations] = {}

    @classmethod
    def build(cls, data: ProjectData) -> "CandidateIndex":
        by_person: dict[str, list[MergeCandidate]] = {}
        by_pair: dict[tuple[str, str], MergeCandidate] = {}
        for cand in data.merge_candidates:
            by_person.setdefault(cand.person_1_id, []).append(cand)
            if cand.person_2_id != cand.person_1_id:
                by_person.setdefault(cand.person_2_id, []).append(cand)
            key = tuple(sorted((cand.person_1_id, cand.person_2_id)))
            by_pair.setdefault(key, cand)  # type: ignore[arg-type]
        history_by_person: dict[str, list[MergeHistoryEntry]] = {}
        if data.merge_history:
            resolver = RedirectResolver(data.merge_history)
            for entry in data.merge_history:
                survivor = resolver.resolve(entry.surviving_person_id)
                if survivor is not None:
                    history_by_person.setdefault(survivor, []).append(entry)
        return cls(by_person, by_pair, history_by_person)

    def relations(self, person_id: str) -> PersonCandidateRelations:
        cached = self._relations.get(person_id)
        if cached is not None:
            return cached
        cands = self._by_person.get(person_id)
        hist = self._history.get(person_id)
        rel = _relations(cands or [], hist or []) if (cands or hist) else _EMPTY
        self._relations[person_id] = rel
        return rel

    def colour(self, person_id: str) -> str:
        if person_id not in self._relations and not (
            self._by_person.get(person_id) or self._history.get(person_id)
        ):
            return NONE  # the shared empty relations; nothing to cache
        return indicator_colour(self.relations(person_id))

    def candidates_for(self, person_id: str) -> tuple[MergeCandidate, ...]:
        return tuple(self._by_person.get(person_id, ()))

    def candidate_for_pair(self, a: str, b: str) -> MergeCandidate | None:
        return self._by_pair.get(tuple(sorted((a, b))))  # type: ignore[arg-type]

    def tooltip_lines(
        self, person_id: str, summaries: PersonSummaryIndex
    ) -> list[str]:
        """Tooltip lines ordered by group then name; at most five plus a summary."""
        rel = self.relations(person_id)
        items: list[tuple[int, str, str, str]] = []  # rank, name key, id, text
        for cand in rel.candidates:
            other = (
                cand.person_2_id
                if cand.person_1_id == person_id
                else cand.person_1_id
            )
            summary = summaries.get(other)
            if summary is None:
                name, life = UNKNOWN_PERSON, ""
            else:
                name = summary.name or other
                life = summary.lifespan_text
            if not cand.enabled:
                rank, kind = _DISABLED, "disabled"
            elif cand.assessment == "confirmed":
                rank, kind = _CONFIRMED, "confirmed"
            elif cand.assessment == "rejected":
                rank, kind = _REJECTED, "rejected"
            elif cand.assessment == "possible":
                rank, kind = _OPEN, "possible"
            else:
                rank, kind = _OPEN, "unreviewed"
            items.append((rank, name.casefold(), cand.id, _line(kind, name, life)))
        for entry in rel.history:
            name = entry.merged_person_name or UNKNOWN_PERSON
            life = entry.merged_person_lifespan if entry.merged_person_name else ""
            items.append(
                (_MERGED, name.casefold(), entry.id, _line("merged", name, life))
            )
        items.sort(key=lambda i: (i[0], i[1], i[2]))
        lines = [i[3] for i in items[:MAX_TOOLTIP_LINES]]
        total = len(items)
        if total > MAX_TOOLTIP_LINES:
            lines.append(
                f"… och {total - MAX_TOOLTIP_LINES} till (totalt {total} relationer)"
            )
        return lines
