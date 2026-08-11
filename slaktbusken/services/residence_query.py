"""Residence_Query_Service — who lived where, computed from stored facts.

`residents_of_place` answers "who was resident at place P during year Y" by
reading stored Residence_Facts only. Nothing is inferred, nothing is clamped to
the person's lifespan, and nothing is mutated: an unbounded Possible_Span keeps
matching every queried year until the user narrows it through the inference
action (Requirements 8.1–8.6, 8.9, 15.9).

Household composition is derived here and nowhere else; the Residence_Model
defines no household entity (Requirement 8.8).

Matching, labelling and the day algebra all funnel through
:mod:`slaktbusken.model.date_span` and :mod:`slaktbusken.model.residence`, and
the rendered interval comes from the Residence_Formatter in
:mod:`slaktbusken.ui.swedish_locale`, which is the single source of the Swedish
wording (Requirement 11.7).

A Residence_Fact matches a queried year when its Possible_Span shares at least
one day with that year. This is the reading that keeps criteria 8.1 through 8.4
consistent with one another: criterion 8.4 labels an entry for "every queried
year overlapping its Possible_Span by at least one day", and criterion 8.2 calls
a year overlapping the Certain_Core "säker" — a core overlap that whole-year
containment of the Possible_Span would sometimes exclude, as it does for a fact
starting exactly 1840-06-01. For bounds stored at year precision, which is the
common case, sharing a day and containing the whole year coincide.

Pure module: no Qt, no I/O, no mutation of the Project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from slaktbusken.model.date_span import OpenSpan, overlaps, year_span
from slaktbusken.model.person import Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import ResidenceFact, certain_core, possible_span
from slaktbusken.ui.swedish_locale import format_residence_interval


#: Descendant places are included down to this many levels below the queried
#: place (Requirement 8.6).
MAX_DESCENDANT_LEVELS = 10

#: The two labels a matching entry can carry (Requirements 8.2, 8.3, 8.4).
LABEL_CERTAIN = "säker"
LABEL_POSSIBLE = "möjlig"

#: The marker shown for an entry whose Possible_Span is unbounded in both
#: directions (Requirement 8.9).
UNDATED_MARKER = "odaterat"

# Swedish alphabetical order places å, ä and ö after z, in that order, which the
# code point order does not (it gives ä before å). Translating them to the three
# code points just past "z" restores the Swedish order for a plain comparison.
_SWEDISH_LETTER_ORDER = str.maketrans(
    {
        "å": chr(ord("z") + 1),
        "ä": chr(ord("z") + 2),
        "ö": chr(ord("z") + 3),
    }
)


@dataclass
class ResidentEntry:
    """One matching Residence_Fact, as the residents query reports it."""

    person_id: str
    person_display: str
    residence_id: str
    place_id: str
    place_display: str
    interval_display: str
    label: str                              # "säker" | "möjlig"
    role_in_household: str = ""             # "" when empty, never omitted
    undated: bool = False                   # the "odaterat" marker
    place_chain: list[str] = field(default_factory=list)


def swedish_sort_key(text: str) -> str:
    """A sort key giving Swedish alphabetical order for display names.

    Comparison is case-insensitive and places å, ä and ö after z, in that order,
    which is the Swedish alphabet rather than the code point order that would
    give ä before å.
    """
    return text.casefold().translate(_SWEDISH_LETTER_ORDER)


def residents_of_place(
    data: ProjectData, place_id: str, year: int
) -> list[ResidentEntry]:
    """The residents of *place_id* and its descendant places during *year*.

    Returns one entry per Residence_Fact in the place subtree whose Possible_Span
    shares at least one day with *year*; two facts of the same person yield two
    entries and are never merged (Requirement 8.1). An entry is labelled "säker"
    when *year* overlaps the fact's Certain_Core by at least one day and "möjlig"
    when it overlaps only the Possible_Span or when the core is empty
    (Requirements 8.2–8.4). A Possible_Span unbounded in both directions matches
    every year, is labelled "möjlig" with ``undated=True`` and sorts after every
    bounded entry (Requirement 8.9); no clamping to the person's lifespan is
    applied (Requirement 15.9).

    Entries are ordered by label with "säker" first, then the undated entries
    last, then by place display name in Swedish alphabetical order, then by
    person display name, then by ascending Residence_Fact ``id``
    (Requirements 8.1, 8.9).

    *data* and every Residence_Fact it holds are left unchanged.
    """
    places_by_id = {place.id: place for place in data.places}
    persons_by_id = {person.id: person for person in data.persons}
    children_by_parent = _children_index(data.places)
    facts_by_place = _residences_index(data.residences)

    queried_year = year_span(year)
    # The Possible_Span, the Certain_Core and the rendered interval depend on the
    # four stored bounds and nothing else, so facts sharing a bound quadruple —
    # the common case among the many facts matching one queried year — share the
    # derivation as well (Requirement 8.11).
    person_displays: dict[str, str] = {}
    spans: dict[tuple, OpenSpan] = {}
    matched: dict[tuple, tuple[str, str]] = {}
    entries: list[ResidentEntry] = []

    for subtree_place_id, place_chain in _walk_subtree(
        place_id, children_by_parent, places_by_id
    ):
        place_display = place_chain[-1]
        for fact in facts_by_place.get(subtree_place_id, ()):
            bounds = (
                fact.start.earliest,
                fact.start.latest,
                fact.end.earliest,
                fact.end.latest,
            )
            span = spans.get(bounds)
            if span is None:
                span = possible_span(fact)
                spans[bounds] = span
            if not span.overlaps_year(year):
                continue
            label_and_interval = matched.get(bounds)
            if label_and_interval is None:
                core = certain_core(fact)
                label_and_interval = (
                    LABEL_CERTAIN
                    if core is not None and overlaps(core, queried_year)
                    else LABEL_POSSIBLE,
                    format_residence_interval(fact.start, fact.end),
                )
                matched[bounds] = label_and_interval
            label, interval_display = label_and_interval
            person_display = person_displays.get(fact.person_id)
            if person_display is None:
                person_display = _person_display(
                    persons_by_id.get(fact.person_id), fact.person_id
                )
                person_displays[fact.person_id] = person_display
            entries.append(
                ResidentEntry(
                    person_id=fact.person_id,
                    person_display=person_display,
                    residence_id=fact.id,
                    place_id=fact.place_id,
                    place_display=place_display,
                    interval_display=interval_display,
                    label=label,
                    role_in_household=fact.role_in_household,
                    undated=span.is_unbounded_both(),
                    place_chain=list(place_chain),
                )
            )

    entries.sort(key=_sort_key_factory())
    return entries


# ---------------------------------------------------------------------------
# Indexes and the subtree walk
# ---------------------------------------------------------------------------


def _children_index(places: list[Place]) -> dict[str, list[str]]:
    """A ``parent_place_id → child place ids`` index, built once per query."""
    children: dict[str, list[str]] = {}
    for place in places:
        parent_id = place.parent_place_id
        if parent_id:
            children.setdefault(parent_id, []).append(place.id)
    return children


def _residences_index(residences: list[ResidenceFact]) -> dict[str, list[ResidenceFact]]:
    """A ``place_id → Residence_Facts`` index, built once per query.

    With this index the query touches only the facts of the matched subtree
    rather than scanning every fact per place (Requirement 8.11).
    """
    by_place: dict[str, list[ResidenceFact]] = {}
    for fact in residences:
        by_place.setdefault(fact.place_id, []).append(fact)
    return by_place


def _walk_subtree(
    root_place_id: str,
    children_by_parent: dict[str, list[str]],
    places_by_id: dict[str, Place],
) -> list[tuple[str, list[str]]]:
    """The queried place and its descendants, each with its chain of place names.

    The walk is breadth-first and stops at :data:`MAX_DESCENDANT_LEVELS` levels
    below the queried place. Each place is visited at most once, so a circular
    `parent_place_id` chain terminates (Requirement 8.6). The chain of every
    result runs from the queried place down to that place.
    """
    root_display = _place_display(places_by_id.get(root_place_id), root_place_id)
    found: list[tuple[str, list[str]]] = []
    visited: set[str] = {root_place_id}
    level: list[tuple[str, list[str]]] = [(root_place_id, [root_display])]

    for depth in range(MAX_DESCENDANT_LEVELS + 1):
        found.extend(level)
        if depth == MAX_DESCENDANT_LEVELS:
            break
        next_level: list[tuple[str, list[str]]] = []
        for parent_id, chain in level:
            for child_id in children_by_parent.get(parent_id, ()):
                if child_id in visited:
                    continue
                visited.add(child_id)
                child_display = _place_display(places_by_id.get(child_id), child_id)
                next_level.append((child_id, chain + [child_display]))
        if not next_level:
            break
        level = next_level

    return found


# ---------------------------------------------------------------------------
# Displays and ordering
# ---------------------------------------------------------------------------


def _place_display(place: Optional[Place], place_id: str) -> str:
    """The display name of *place*, falling back to the stored identifier.

    An unresolved `place_id` is kept as stored rather than discarded
    (Requirement 13.7), so the query still reports the fact.
    """
    if place is None:
        return place_id
    return place.name


def _person_display(person: Optional[Person], person_id: str) -> str:
    """The display name of *person*: given plus surname of the first name entry.

    Falls back to the stored identifier when the person does not resolve or
    carries no usable name, so an unresolved reference is still reported.
    """
    if person is None or not person.names:
        return person_id
    name = person.names[0]
    display = f"{name.given} {name.surname}".strip()
    return display or person_id


def _sort_key_factory():
    """A sort key function for the ordering of Requirements 8.1 and 8.9.

    Swedish keys are memoised across the entries, since a place or person display
    repeats over the many facts of one household.
    """
    keys: dict[str, str] = {}

    def swedish(text: str) -> str:
        key = keys.get(text)
        if key is None:
            key = swedish_sort_key(text)
            keys[text] = key
        return key

    def sort_key(entry: ResidentEntry) -> tuple:
        return (
            0 if entry.label == LABEL_CERTAIN else 1,
            1 if entry.undated else 0,
            swedish(entry.place_display),
            swedish(entry.person_display),
            entry.residence_id,
        )

    return sort_key
