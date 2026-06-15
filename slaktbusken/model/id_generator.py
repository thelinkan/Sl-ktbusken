"""Stable, unique, type-prefixed ID generation for domain entities."""

from __future__ import annotations

import re


class IDGenerator:
    """Generates stable, unique, type-prefixed IDs.

    IDs follow the pattern ``<prefix><n>`` where ``<prefix>`` is determined by
    the entity type and ``<n>`` is a monotonically increasing numeric suffix
    that is unique per prefix. Once an ID has been generated (or registered as
    used) it is never reused, even after the corresponding entity is deleted,
    because the per-prefix counter is derived from the high-water mark of all
    known suffixes rather than from the current set size.
    """

    _PREFIXES = {
        'person': 'person_', 'family': 'family_', 'event': 'event_',
        'place': 'place_', 'source': 'source_', 'media': 'media_',
        'dna_company': 'dna_company_', 'dna_profile': 'dna_profile_',
        'dna_match': 'dna_match_', 'dna_segment': 'dna_segment_',
        'dna_cluster': 'dna_cluster_', 'dna_triangulation': 'dna_triangulation_',
        'repository': 'repo_', 'research_note': 'note_',
    }

    def __init__(self, existing_ids: set[str]) -> None:
        self._used_ids: set[str] = set(existing_ids)

    def _prefix_for(self, entity_type: str) -> str:
        try:
            return self._PREFIXES[entity_type]
        except KeyError as exc:
            raise ValueError(f"Unknown entity type: {entity_type!r}") from exc

    def _high_water_mark(self, prefix: str) -> int:
        """Return the largest numeric suffix already used for ``prefix``."""
        # Match the prefix followed by digits to the end of the string. Other
        # prefixes that are substrings (e.g. ``dna_company_`` vs ``company_``)
        # are not a concern because we anchor on the exact prefix.
        pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
        highest = 0
        for used in self._used_ids:
            match = pattern.match(used)
            if match:
                highest = max(highest, int(match.group(1)))
        return highest

    def generate(self, entity_type: str, hint: str = '') -> str:
        """Generate the next unique ID for ``entity_type``.

        The ``hint`` argument is accepted for API compatibility but does not
        affect the generated identifier; IDs remain purely numeric per type.
        """
        prefix = self._prefix_for(entity_type)
        next_suffix = self._high_water_mark(prefix) + 1
        new_id = f"{prefix}{next_suffix}"
        # Defensive: in case of unexpected collisions, advance until free.
        while new_id in self._used_ids:
            next_suffix += 1
            new_id = f"{prefix}{next_suffix}"
        self._used_ids.add(new_id)
        return new_id

    def register(self, entity_id: str) -> None:
        """Register an externally-known used ID so it is never reused."""
        self._used_ids.add(entity_id)

    def register_many(self, entity_ids: set[str]) -> None:
        """Register a collection of externally-known used IDs."""
        self._used_ids.update(entity_ids)

    @property
    def used_ids(self) -> set[str]:
        """A copy of the set of all used IDs."""
        return set(self._used_ids)
