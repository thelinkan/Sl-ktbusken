"""Substring search over persons for the comparison slot search (Qt-free)."""

from __future__ import annotations

from dataclasses import dataclass

from slaktbusken.model.project import ProjectData
from slaktbusken.services.person_summary import PersonSummaryIndex

MIN_QUERY_LENGTH = 2
MAX_RESULTS = 50


@dataclass(frozen=True)
class PersonSearchResult:
    """One search hit with enough detail to tell same-named persons apart."""

    person_id: str
    name: str
    life_dates: str
    birth_place: str

    @property
    def display_text(self) -> str:
        """``Anna Svensson   f. 1829-03-04 Ljusdal   d. 1890   [person_12]``"""
        parts = [self.name or self.person_id]
        if self.life_dates:
            parts.append(self.life_dates)
        parts.append(f"[{self.person_id}]")
        return "   ".join(parts)


class PersonSearchIndex:
    """Precomputed lower-cased haystacks; a search is one linear ``in`` pass."""

    def __init__(self, entries: list[tuple[str, PersonSearchResult]]) -> None:
        self._entries = entries

    @classmethod
    def build(
        cls, data: ProjectData, summaries: PersonSummaryIndex | None = None
    ) -> "PersonSearchIndex":
        summaries = summaries or PersonSummaryIndex.build(data)
        entries: list[tuple[str, PersonSearchResult]] = []
        for person in data.persons:
            summary = summaries.get(person.id)
            if summary is None:
                continue
            haystack_parts = [person.id, summary.birth_date, summary.death_date]
            for name in person.names:
                haystack_parts.append(name.given)
                haystack_parts.append(name.surname)
                haystack_parts.append(f"{name.given} {name.surname}")
            life = " ".join(
                text for text in (summary.birth_text, summary.death_text) if text
            )
            result = PersonSearchResult(
                person_id=person.id,
                name=summary.name,
                life_dates=life,
                birth_place=summary.birth_place,
            )
            entries.append(("\n".join(haystack_parts).lower(), result))
        entries.sort(key=lambda e: (e[1].name.lower(), e[1].person_id))
        return cls(entries)

    def search(self, text: str, limit: int = MAX_RESULTS) -> list[PersonSearchResult]:
        """Up to ``limit`` (max 50) matches in name order; fewer than two
        characters gives no results."""
        query = (text or "").strip().lower()
        if len(query) < MIN_QUERY_LENGTH:
            return []
        limit = min(limit, MAX_RESULTS)
        results: list[PersonSearchResult] = []
        for haystack, result in self._entries:
            if query in haystack:
                results.append(result)
                if len(results) >= limit:
                    break
        return results
