"""Shared rules for the research indicator shown next to an entity.

The person list, the diagram person boxes and the other entity views all show
whether an entity has research. They share these rules, so a case being closed or
reopened changes every view the same way.

The indicator is based only on research cases that link the entity directly. It
says nothing about whether the facts are verified, which is why a closed case is
grey and never green: closing a case does not make its conclusion true.

    no linked cases                -> no indicator
    linked cases, all closed       -> grey
    at least one case not closed   -> orange

This module is pure: no Qt and no I/O. It decides state, text and colour; the
widgets decide how to draw them.
"""

from __future__ import annotations

from slaktbusken.services.research_index import ResearchCaseCounts

STATE_NONE = "none"
STATE_GREY = "grey"
STATE_ORANGE = "orange"

#: Indicator colours. There is deliberately no green.
INDICATOR_COLORS: dict[str, str] = {
    STATE_GREY: "#9E9E9E",
    STATE_ORANGE: "#F39C12",
}


def indicator_state(counts: ResearchCaseCounts) -> str:
    """Return ``"none"``, ``"grey"`` or ``"orange"`` for an entity's case counts."""
    if counts.total <= 0:
        return STATE_NONE
    if counts.non_closed > 0:
        return STATE_ORANGE
    return STATE_GREY


def indicator_color(state: str) -> str | None:
    """Return the colour for an indicator state, or ``None`` when nothing is drawn."""
    return INDICATOR_COLORS.get(state)


def indicator_tooltip(counts: ResearchCaseCounts) -> str:
    """Return the tooltip for an indicator, or an empty string when there is none.

    "öppna" counts every case that is not closed, that is open, in progress and
    on hold. For example "3 forskningsärenden, varav 2 öppna". A single case
    reads "1 forskningsärende, varav 1 öppet" (or "varav 0 öppna").
    """
    if counts.total <= 0:
        return ""
    if counts.total == 1:
        cases = "1 forskningsärende"
        open_text = "1 öppet" if counts.non_closed == 1 else "0 öppna"
    else:
        cases = f"{counts.total} forskningsärenden"
        open_text = f"{counts.non_closed} öppna"
    return f"{cases}, varav {open_text}"


def format_research_counts(counts: ResearchCaseCounts) -> str:
    """Return the person-list cell text "{open}/{total}", empty when there are no cases."""
    if counts.total <= 0:
        return ""
    return f"{counts.non_closed}/{counts.total}"


def research_sort_key(counts: ResearchCaseCounts) -> tuple[int, int]:
    """Return the sort key for the "Forskningsärenden" column.

    Primarily the number of cases that are not closed, secondarily the total.
    """
    return (counts.non_closed, counts.total)
