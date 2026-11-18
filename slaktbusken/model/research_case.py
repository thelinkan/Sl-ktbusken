"""Research case data containers and pure helpers.

A ResearchCase is a research question that may concern zero or more project
entities. It owns ResearchHypotheses (proposed explanations, each with dated
HypothesisComments) and ResearchActions (planned or completed research work).

Research is descriptive: nothing in this module touches a genealogical fact.
This module is pure: no Qt and no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from slaktbusken.model.event import SourceRef

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "person",
        "family",
        "event",
        "place",
        "source",
        "media",
        "dna_match",
        "dna_cluster",
    }
)
"""Internal entity keys a research link may target."""

VALID_RESEARCH_STATUSES: tuple[str, ...] = ("open", "in_progress", "on_hold", "closed")
VALID_RESEARCH_PRIORITIES: tuple[str, ...] = ("low", "normal", "high")
VALID_HYPOTHESIS_ASSESSMENTS: tuple[str, ...] = (
    "unassessed",
    "possible",
    "strong_support",
    "confirmed",
    "rejected",
)


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def normalize_completed_date(value: Optional[str]) -> Optional[str]:
    """Normalize a completion date so an empty value never means "completed".

    ``None``, an empty string, and a whitespace-only string all become ``None``
    (a pending action). Any other string is returned trimmed.
    """
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def is_valid_calendar_date(value: Optional[str]) -> bool:
    """Return True for a non-empty ÅÅÅÅ, ÅÅÅÅ-MM or ÅÅÅÅ-MM-DD that is a real date.

    ``parse_date_value`` alone only range-checks month 1-12 and day 1-31, so it
    accepts "2026-02-30". It is therefore composed with
    ``is_valid_swedish_calendar``, which checks days-in-month and leap years.
    Year and month precision are valid; day precision is never required.
    """
    if value is None or not value.strip():
        return False

    # Imported lazily: ``slaktbusken.services`` imports the delete service,
    # which imports the model, so a module-level import would be circular.
    from slaktbusken.model.event import DateValue
    from slaktbusken.services.checks.date_utils import (
        is_valid_swedish_calendar,
        parse_date_value,
    )

    parsed = parse_date_value(DateValue(value=value.strip(), precision="exact"))
    if parsed is None:
        return False
    return is_valid_swedish_calendar(parsed)


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@dataclass
class ResearchEntityLink:
    """A reference from research data to a project entity.

    Mirrors ``model.media.LinkedEntity``. ``role`` is a free-text relationship
    descriptor (for example "candidate"); empty when unused. No display text
    is stored: names are resolved from the referenced entity at render time.
    """

    entity_type: str
    entity_id: str
    role: str = ""


@dataclass
class HypothesisComment:
    """A dated free-text observation about a hypothesis."""

    id: str
    date: str = ""
    text: str = ""


@dataclass
class ResearchHypothesis:
    """A proposed explanation belonging to one research case."""

    id: str
    research_case_id: str
    statement: str = ""
    assessment: str = "unassessed"
    reasoning: str = ""
    linked_entities: list[ResearchEntityLink] = field(default_factory=list)
    comments: list[HypothesisComment] = field(default_factory=list)


@dataclass
class ResearchAction:
    """Planned or completed research work belonging to one research case.

    ``completed_date`` is ``None`` for a pending action. An empty string is
    never stored: it is normalized to ``None`` on construction.
    """

    id: str
    research_case_id: str
    title: str = ""
    text: str = ""
    completed_date: Optional[str] = None
    sort_order: int = 0
    source_refs: list[SourceRef] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.completed_date = normalize_completed_date(self.completed_date)


@dataclass
class ResearchCase:
    """A research question that may concern zero or more project entities."""

    id: str
    title: str = ""
    description: str = ""
    status: str = "open"
    priority: str = "normal"
    conclusion: str = ""
    primary_entity_ref: Optional[ResearchEntityLink] = None
    linked_entities: list[ResearchEntityLink] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def is_pending(action: ResearchAction) -> bool:
    """Return True when the action has no completion date."""
    return action.completed_date is None


def case_entity_links(case: ResearchCase) -> list[ResearchEntityLink]:
    """Return the case's links: the primary one first, then ``linked_entities``.

    Returns a new list; the case is left unchanged.
    """
    links: list[ResearchEntityLink] = []
    if case.primary_entity_ref is not None:
        links.append(case.primary_entity_ref)
    links.extend(case.linked_entities)
    return links


def count_links_for_entity(
    case: ResearchCase, entity_type: str, entity_id: str
) -> int:
    """Count how many of the case's links point at one entity.

    A count above one means the case links the same entity more than once.
    """
    return sum(
        1
        for link in case_entity_links(case)
        if link.entity_type == entity_type and link.entity_id == entity_id
    )
