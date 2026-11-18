"""Redirect resolution over Merge_History (Qt-free, no I/O).

Maps a retired person id to the person it was finally merged into. History
entries are never modified. A cycle or an ambiguous retired id makes every
affected id resolve to no person and is reported by ``cycles()`` and
``ambiguous_ids()``.
"""

from __future__ import annotations

import re

from slaktbusken.model.merge_candidate import MergeHistoryEntry


def _id_suffix(entry_id: str) -> int:
    """Numeric suffix of ``merge_<n>``; 0 when there is none."""
    match = re.search(r"(\d+)$", entry_id or "")
    return int(match.group(1)) if match else 0


def _sort_key(entry: MergeHistoryEntry) -> tuple[str, int, str]:
    return (entry.merge_date or "", _id_suffix(entry.id), entry.id or "")


class RedirectResolver:
    """Resolves retired person ids over a list of ``MergeHistoryEntry``."""

    def __init__(self, history: list[MergeHistoryEntry]) -> None:
        self._entries: list[MergeHistoryEntry] = sorted(history, key=_sort_key)
        self._map: dict[str, str] = {}
        self._ambiguous: set[str] = set()
        for entry in self._entries:
            retired = entry.merged_person_id
            if retired in self._map or retired in self._ambiguous:
                self._ambiguous.add(retired)
                continue
            self._map[retired] = entry.surviving_person_id
        self._cache: dict[str, str | None] = {}
        self._cycles: list[list[str]] = self._find_cycles()

    def _find_cycles(self) -> list[list[str]]:
        cycles: list[list[str]] = []
        done: set[str] = set()
        for start in self._map:
            if start in done:
                continue
            path: list[str] = []
            index: dict[str, int] = {}
            x = start
            while x in self._map and x not in done and x not in self._ambiguous:
                if x in index:
                    cycles.append(path[index[x]:])
                    break
                index[x] = len(path)
                path.append(x)
                x = self._map[x]
            done.update(path)
        return cycles

    def resolve(self, person_id: str) -> str | None:
        """Final surviving id; the id itself if not retired; None on cycle/ambiguity."""
        if person_id in self._cache:
            return self._cache[person_id]
        seen: set[str] = set()
        x = person_id
        result: str | None
        while True:
            if x in self._ambiguous:
                result = None
                break
            if x not in self._map:
                result = x
                break
            if x in seen:
                result = None
                break
            seen.add(x)
            x = self._map[x]
        self._cache[person_id] = result
        return result

    def is_retired(self, person_id: str) -> bool:
        return person_id in self._map or person_id in self._ambiguous

    def merged_into(self, survivor_id: str) -> list[MergeHistoryEntry]:
        """Entries whose resolved survivor is ``survivor_id``, by date then sequence."""
        return [
            e for e in self._entries
            if self.resolve(e.surviving_person_id) == survivor_id
            and not (e.merged_person_id in self._ambiguous)
            and self.resolve(e.merged_person_id) == survivor_id
        ]

    def cycles(self) -> list[list[str]]:
        """Each detected cycle as a list of retired ids."""
        return [list(c) for c in self._cycles]

    def ambiguous_ids(self) -> list[str]:
        """Retired ids that occur in more than one entry."""
        return sorted(self._ambiguous)
