"""Substring search over persons for the comparison slot search (Qt-free)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from slaktbusken.model.project import ProjectData
from slaktbusken.services.person_summary import PersonSummaryIndex
from slaktbusken.services.redirect_resolution import RedirectResolver

MIN_QUERY_LENGTH = 2
MAX_RESULTS = 50


@dataclass(frozen=True)
class PersonSearchResult:
    """One search hit with enough detail to tell same-named persons apart."""

    person_id: str
    name: str
    life_dates: str
    birth_place: str
    retired_label: str = ""

    @property
    def display_text(self) -> str:
        """``Anna Svensson   f. 1829-03-04 Ljusdal   d. 1890   [person_12]``"""
        parts = [self.name or self.person_id]
        if self.life_dates:
            parts.append(self.life_dates)
        parts.append(f"[{self.person_id}]")
        if self.retired_label:
            parts.append(self.retired_label)
        return "   ".join(parts)


def _retired_label(entry) -> str:
    """``Sammanslagen med <namn> (<år–år>)`` from the stored entry."""
    label = f"Sammanslagen med {entry.merged_person_name or entry.merged_person_id}"
    if entry.merged_person_lifespan:
        label += f" ({entry.merged_person_lifespan})"
    return label


class PersonSearchIndex:
    """Precomputed lower-cased haystacks; a search is one linear ``in`` pass."""

    def __init__(
        self,
        entries: list[tuple[str, PersonSearchResult]] | None = None,
        *,
        _source: tuple[ProjectData, PersonSummaryIndex] | None = None,
    ) -> None:
        self._built: list[tuple[str, PersonSearchResult]] | None = entries
        self._source = _source
        self._retired: dict[str, str] = {}
        self._labels: dict[str, str] = {}
        self._resolver: RedirectResolver | None = None
        if _source is not None and _source[0].merge_history:
            history = _source[0].merge_history
            self._resolver = RedirectResolver(history)
            for entry in history:
                self._retired.setdefault(
                    entry.merged_person_id.lower(), entry.merged_person_id
                )
                self._labels.setdefault(entry.merged_person_id, _retired_label(entry))

    @property
    def _entries(self) -> list[tuple[str, PersonSearchResult]]:
        if self._built is None:
            data, summaries = self._source  # type: ignore[misc]
            self._built = self._make_entries(data, summaries)
            self._source = None
        return self._built

    @classmethod
    def build(
        cls, data: ProjectData, summaries: PersonSummaryIndex | None = None
    ) -> "PersonSearchIndex":
        """The haystacks are formed on the first search, not here."""
        return cls(_source=(data, summaries or PersonSummaryIndex.build(data)))

    @staticmethod
    def _make_entries(
        data: ProjectData, summaries: PersonSummaryIndex
    ) -> list[tuple[str, PersonSearchResult]]:
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
        return entries

    def search(self, text: str, limit: int = MAX_RESULTS) -> list[PersonSearchResult]:
        """Up to ``limit`` (max 50) matches in name order; fewer than two
        characters gives no results."""
        query = (text or "").strip().lower()
        if len(query) < MIN_QUERY_LENGTH:
            return []
        limit = min(limit, MAX_RESULTS)
        results: list[PersonSearchResult] = []
        redirected = self._retired_hit(query)
        if redirected is not None:
            results.append(redirected)
        for haystack, result in self._entries:
            if len(results) >= limit:
                break
            if query in haystack:
                if redirected is not None and result.person_id == redirected.person_id:
                    continue
                results.append(result)
        return results

    def _retired_hit(self, query: str) -> PersonSearchResult | None:
        """Survivor for a query equal to a retired id; None for cycles,
        ambiguous ids or a missing survivor."""
        retired_id = self._retired.get(query)
        if retired_id is None or self._resolver is None:
            return None
        survivor = self._resolver.resolve(retired_id)
        if survivor is None or survivor == retired_id:
            return None
        for _haystack, result in self._entries:
            if result.person_id == survivor:
                return replace(result, retired_label=self._labels[retired_id])
        return None
