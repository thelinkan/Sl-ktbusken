"""Research index: reverse lookups over the research collections.

Which cases link to this person? How many of them are still open? Which actions
cited this source? Answering those by scanning every case each time a person row
or a diagram box is drawn would be too slow, so ``ResearchIndex`` builds the
reverse maps once from ``ProjectData`` and answers each lookup from a dictionary.

It follows the pattern of ``foster_sync._ProjectIndex`` and
``person_check_engine.CheckContext``: built on demand from the authoritative
data, read-only, never stored or cached by the caller across changes. Build a
new one after any change; an index that outlives a change is stale.

Two rules shape what the lookups return:

- A link counts only while the entity it names still exists. A link kept after
  its target was deleted contributes to no indicator, count or list.
- Hypotheses that name an entity are indexed separately from the cases that
  link it, so they never enter an indicator count.

This module is pure: no Qt and no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    ResearchAction,
    ResearchCase,
    ResearchHypothesis,
    case_entity_links,
    is_pending,
)

EntityKey = tuple[str, str]
"""An entity as ``(entity_type, entity_id)``."""


@dataclass(frozen=True)
class ResearchCaseCounts:
    """How many research cases link an entity.

    Attributes:
        non_closed: Cases whose status is not ``closed``.
        total: All cases, closed or not.
    """

    non_closed: int
    total: int


class ResearchIndex:
    """Read-only reverse lookups over a project's research data.

    Args:
        data: The project to index.
    """

    def __init__(self, data: ProjectData) -> None:
        existing = self._existing_entities(data)

        self._cases: dict[str, ResearchCase] = {case.id: case for case in data.research_cases}

        self._cases_by_entity: dict[EntityKey, list[ResearchCase]] = {}
        for case in data.research_cases:
            # A case that links one entity several times still counts once.
            seen: set[EntityKey] = set()
            for link in case_entity_links(case):
                key = (link.entity_type, link.entity_id)
                if key in seen or key not in existing:
                    continue
                seen.add(key)
                self._cases_by_entity.setdefault(key, []).append(case)

        self._counts_by_entity: dict[EntityKey, ResearchCaseCounts] = {
            key: ResearchCaseCounts(
                non_closed=sum(1 for case in cases if case.status != "closed"),
                total=len(cases),
            )
            for key, cases in self._cases_by_entity.items()
        }

        self._hypotheses_by_case: dict[str, list[ResearchHypothesis]] = {}
        self._hypotheses_by_entity: dict[EntityKey, list[tuple[ResearchHypothesis, ResearchCase]]] = {}
        for hypothesis in data.research_hypotheses:
            self._hypotheses_by_case.setdefault(hypothesis.research_case_id, []).append(hypothesis)

            owner = self._cases.get(hypothesis.research_case_id)
            if owner is None:
                continue  # a hypothesis whose case is gone has no case to pair with
            seen_keys: set[EntityKey] = set()
            for link in hypothesis.linked_entities:
                key = (link.entity_type, link.entity_id)
                if key in seen_keys or key not in existing:
                    continue
                seen_keys.add(key)
                self._hypotheses_by_entity.setdefault(key, []).append((hypothesis, owner))

        self._actions_by_case: dict[str, list[ResearchAction]] = {}
        self._actions_by_source: dict[str, list[ResearchAction]] = {}
        self._pending_by_case: dict[str, int] = {}
        for action in data.research_actions:
            self._actions_by_case.setdefault(action.research_case_id, []).append(action)
            if is_pending(action):
                self._pending_by_case[action.research_case_id] = (
                    self._pending_by_case.get(action.research_case_id, 0) + 1
                )
            # An action that cites one source twice is listed once for it.
            for source_id in {ref.source_id for ref in action.source_refs}:
                self._actions_by_source.setdefault(source_id, []).append(action)

    @staticmethod
    def _existing_entities(data: ProjectData) -> set[EntityKey]:
        """Return every ``(entity_type, entity_id)`` a research link may name that exists."""
        existing: set[EntityKey] = set()
        existing.update(("person", x.id) for x in data.persons)
        existing.update(("family", x.id) for x in data.families)
        existing.update(("event", x.id) for x in data.events)
        existing.update(("place", x.id) for x in data.places)
        existing.update(("source", x.id) for x in data.sources)
        existing.update(("media", x.id) for x in data.media)
        existing.update(("dna_match", x.id) for x in data.dna_matches)
        existing.update(("dna_cluster", x.id) for x in data.dna_clusters)
        return existing

    # ------------------------------------------------------------------
    # Cases
    # ------------------------------------------------------------------

    def case(self, case_id: str) -> ResearchCase | None:
        """Return the case with this id, or ``None``."""
        return self._cases.get(case_id)

    def cases_for_entity(self, entity_type: str, entity_id: str) -> list[ResearchCase]:
        """Return the cases that directly link an entity, each exactly once.

        A case counts whether the entity is its primary link, one of its linked
        entities, or both. Only existing entities have cases; a link kept after
        its target was deleted contributes nothing. Cases come in project order.
        """
        return list(self._cases_by_entity.get((entity_type, entity_id), ()))

    def counts_for_entity(self, entity_type: str, entity_id: str) -> ResearchCaseCounts:
        """Return how many cases directly link an entity, and how many are not closed."""
        return self._counts_by_entity.get((entity_type, entity_id), ResearchCaseCounts(0, 0))

    # ------------------------------------------------------------------
    # Hypotheses
    # ------------------------------------------------------------------

    def hypotheses_for_case(self, case_id: str) -> list[ResearchHypothesis]:
        """Return the hypotheses belonging to a case, in project order."""
        return list(self._hypotheses_by_case.get(case_id, ()))

    def hypotheses_for_entity(
        self, entity_type: str, entity_id: str
    ) -> list[tuple[ResearchHypothesis, ResearchCase]]:
        """Return the hypotheses that name an entity, each with its owning case.

        This is how an entity editor shows "Förekommer i hypoteser". It is kept
        apart from :meth:`cases_for_entity`: a hypothesis that names a person
        does not make its case one of that person's directly linked cases, and
        never affects an indicator count.
        """
        return list(self._hypotheses_by_entity.get((entity_type, entity_id), ()))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def actions_for_case(self, case_id: str) -> list[ResearchAction]:
        """Return the actions belonging to a case, in project order."""
        return list(self._actions_by_case.get(case_id, ()))

    def actions_for_source(self, source_id: str) -> list[ResearchAction]:
        """Return every action that cites a source, across all cases.

        The owning case need not link the source. An action that cites the same
        source more than once is listed once.
        """
        return list(self._actions_by_source.get(source_id, ()))

    def pending_action_count(self, case_id: str) -> int:
        """Return how many of a case's actions have no completion date."""
        return self._pending_by_case.get(case_id, 0)
