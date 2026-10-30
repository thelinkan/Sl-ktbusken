"""Shared Hypothesis strategies for the research-cases tests.

Every research property test draws its input from this module, so the edge cases
the design calls out are exercised everywhere rather than per test file:

- empty cases, and cases with no linked entities at all,
- a primary link only, linked entities only, both, and the same entity linked
  more than once (including the primary link repeated in ``linked_entities``),
- several hypotheses on one case with conflicting assessments,
- pending and completed actions, with real calendar dates of year, month and day
  precision, and with blank completion dates that must normalize to ``None``,
- impossible and malformed dates for the validators to reject,
- text lengths at 0, 1, ``limit - 1``, ``limit`` and ``limit + 1`` for the
  200, 1000 and 10000 character limits,
- absent versus empty-string fields,
- references that do not resolve (when no id pool is given).

The public strategies are composable: each takes optional identifier pools and
shape selectors so a test can either sample the whole space or pin down the one
case it is about.

    valid_dates()         -> str, a real ÅÅÅÅ / ÅÅÅÅ-MM / ÅÅÅÅ-MM-DD date
    entity_links()        -> ResearchEntityLink
    hypothesis_comments() -> HypothesisComment
    hypotheses()          -> ResearchHypothesis
    actions()             -> ResearchAction
    research_cases()      -> ResearchCase
    consistent_projects() -> ProjectData whose research entities all resolve

Pure test support: no Qt, no I/O.
"""

from __future__ import annotations

import calendar
from typing import Optional, Sequence

from hypothesis import strategies as st
from hypothesis.strategies import DrawFn, SearchStrategy

from slaktbusken.model.dna import DnaCluster, DnaMatch
from slaktbusken.model.event import Event, Participant, SourceRef
from slaktbusken.model.family import Family
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_case import (
    SUPPORTED_ENTITY_TYPES,
    VALID_HYPOTHESIS_ASSESSMENTS,
    VALID_RESEARCH_PRIORITIES,
    VALID_RESEARCH_STATUSES,
    HypothesisComment,
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
)
from slaktbusken.model.source import Source


# ---------------------------------------------------------------------------
# Constants — the boundaries the generators deliberately hit
# ---------------------------------------------------------------------------

TITLE_MAX_LENGTH = 200            # ResearchCase.title, ResearchAction.title
STATEMENT_MAX_LENGTH = 1000       # ResearchHypothesis.statement
LONG_TEXT_MAX_LENGTH = 10000      # descriptions, conclusions, reasoning, texts

#: Years the date strategy draws from. 1760 keeps clear of the 1753 Swedish
#: calendar transition so every drawn date is valid under both calendars.
MIN_DATE_YEAR = 1760
MAX_DATE_YEAR = 2100

#: Shaped like an ISO date but naming a day that does not exist.
IMPOSSIBLE_DATES: tuple[str, ...] = (
    "2026-02-30",
    "2026-02-29",
    "2025-02-29",
    "1900-02-29",
    "2026-04-31",
    "2026-13-01",
    "2026-00-10",
    "2026-06-00",
    "2026-06-32",
    "1753-02-20",
)

#: Not ISO-shaped at all.
MALFORMED_DATES: tuple[str, ...] = (
    "26-05-01",
    "2026-5-1",
    "abc",
    "2026/05/01",
    "2026-05-01T10:00",
    "20260501",
    "2026-",
)

#: Blank completion dates; ``ResearchAction`` normalizes each of these to ``None``.
BLANK_DATES: tuple[str, ...] = ("", " ", "   ", "\t", "\n ")

#: Entity types a link may name that research does not support.
UNKNOWN_ENTITY_TYPES: tuple[str, ...] = ("residence", "repository", "note", "")

INVALID_STATUSES: tuple[str, ...] = ("", "Open", "done", "avslutad", "pending")
INVALID_PRIORITIES: tuple[str, ...] = ("", "urgent", "Hög", "medium")
INVALID_ASSESSMENTS: tuple[str, ...] = ("", "likely", "Möjlig", "proven")

#: How a generated case links entities. ``duplicate_links`` repeats one entity,
#: either as the primary link and again in ``linked_entities`` or twice there.
LINK_SHAPES: tuple[str, ...] = (
    "none",
    "primary_only",
    "linked_only",
    "primary_and_linked",
    "duplicate_links",
)

_ROLES: tuple[str, ...] = ("", "candidate", "research_context", "identified_person")
_QUALITIES: tuple[str, ...] = ("primary", "secondary", "questionable")
_GIVEN_NAMES: tuple[str, ...] = ("Anders", "Brita", "Erik", "Karin", "Olof", "Märta")
_SURNAMES: tuple[str, ...] = ("Andersson", "Persdotter", "Ek", "Öberg", "Lund")

#: Letters and digits up to Latin Extended-B, which covers å/ä/ö.
_TEXT_CHARS = st.one_of(
    st.characters(categories=("Ll", "Lu", "Nd"), max_codepoint=0x24F),
    st.sampled_from(list(" -'åäöÅÄÖ")),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _identifiers(prefix: str) -> SearchStrategy[str]:
    """Generate identifiers of the project's ``{prefix}_{n}`` form."""
    return st.integers(min_value=1, max_value=99).map(lambda n: f"{prefix}_{n}")


@st.composite
def bounded_texts(
    draw: DrawFn,
    limit: int,
    *,
    include_over_limit: bool = True,
    include_whitespace_only: bool = True,
) -> str:
    """Generate text that hits the interesting lengths around *limit*.

    The lengths 0, 1, ``limit - 1``, ``limit`` and ``limit + 1`` are all
    reachable, so a test can find the exact boundary case it needs. Roughly one
    value in ten is whitespace-only.
    """
    boundaries = [0, 1, max(limit - 1, 0), limit]
    if include_over_limit:
        boundaries.append(limit + 1)
    length = draw(
        st.one_of(
            st.sampled_from(boundaries),
            st.integers(min_value=0, max_value=min(limit, 40)),
        )
    )
    if length == 0:
        return ""
    if include_whitespace_only and draw(st.integers(min_value=0, max_value=9)) == 0:
        return " " * length
    seed = draw(st.text(alphabet=_TEXT_CHARS, min_size=1, max_size=8))
    if not seed:
        seed = "a"
    return (seed * (length // len(seed) + 1))[:length]


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


@st.composite
def valid_dates(
    draw: DrawFn,
    *,
    min_year: int = MIN_DATE_YEAR,
    max_year: int = MAX_DATE_YEAR,
    precisions: Sequence[str] = ("year", "month", "day"),
) -> str:
    """Generate a real calendar date as ÅÅÅÅ, ÅÅÅÅ-MM or ÅÅÅÅ-MM-DD."""
    year = draw(st.integers(min_value=min_year, max_value=max_year))
    precision = draw(st.sampled_from(list(precisions)))
    if precision == "year":
        return f"{year:04d}"
    month = draw(st.integers(min_value=1, max_value=12))
    if precision == "month":
        return f"{year:04d}-{month:02d}"
    day = draw(st.integers(min_value=1, max_value=calendar.monthrange(year, month)[1]))
    return f"{year:04d}-{month:02d}-{day:02d}"


def invalid_dates() -> SearchStrategy[str]:
    """Generate non-empty dates a validator must reject: impossible or malformed."""
    return st.sampled_from(IMPOSSIBLE_DATES + MALFORMED_DATES)


# ---------------------------------------------------------------------------
# entity_links
# ---------------------------------------------------------------------------


@st.composite
def entity_links(
    draw: DrawFn,
    *,
    entity_types: Optional[Sequence[str]] = None,
    pools: Optional[dict[str, Sequence[str]]] = None,
    include_unknown_types: bool = False,
    include_blank_ids: bool = False,
) -> ResearchEntityLink:
    """Generate a :class:`ResearchEntityLink`.

    Args:
        entity_types: The supported types to draw from (default: all eight).
        pools: Maps an entity type to the ids that exist. When given, only types
            with a non-empty pool are drawn and every id comes from its pool,
            so the link resolves. ``None`` generates free ids that may dangle.
        include_unknown_types: Also draw types research does not support.
        include_blank_ids: Also draw an empty ``entity_id``.
    """
    types = list(entity_types) if entity_types is not None else sorted(SUPPORTED_ENTITY_TYPES)
    if pools is not None:
        types = [t for t in types if pools.get(t)]
        assert types, "entity_links(pools=...) needs at least one non-empty pool"

    entity_type = draw(st.sampled_from(types))
    if include_unknown_types and draw(st.integers(min_value=0, max_value=4)) == 0:
        entity_type = draw(st.sampled_from(list(UNKNOWN_ENTITY_TYPES)))

    if include_blank_ids and draw(st.integers(min_value=0, max_value=4)) == 0:
        entity_id = ""
    elif pools is not None and pools.get(entity_type):
        entity_id = draw(st.sampled_from(list(pools[entity_type])))
    else:
        entity_id = draw(_identifiers(entity_type or "entity"))

    return ResearchEntityLink(
        entity_type=entity_type,
        entity_id=entity_id,
        role=draw(st.sampled_from(_ROLES)),
    )


# ---------------------------------------------------------------------------
# hypothesis_comments
# ---------------------------------------------------------------------------


@st.composite
def hypothesis_comments(
    draw: DrawFn,
    *,
    comment_id: Optional[str] = None,
    include_invalid_dates: bool = False,
    include_over_limit: bool = True,
) -> HypothesisComment:
    """Generate a :class:`HypothesisComment`.

    The date is empty, or a real date of year, month or day precision. With
    *include_invalid_dates* it may also be impossible or malformed.
    """
    date_options: list[SearchStrategy[str]] = [st.just(""), valid_dates()]
    if include_invalid_dates:
        date_options.append(invalid_dates())
    return HypothesisComment(
        id=comment_id if comment_id is not None else draw(_identifiers("hypcomment")),
        date=draw(st.one_of(*date_options)),
        text=draw(bounded_texts(LONG_TEXT_MAX_LENGTH, include_over_limit=include_over_limit)),
    )


# ---------------------------------------------------------------------------
# hypotheses
# ---------------------------------------------------------------------------


@st.composite
def hypotheses(
    draw: DrawFn,
    *,
    hypothesis_id: Optional[str] = None,
    case_id: Optional[str] = None,
    entity_pools: Optional[dict[str, Sequence[str]]] = None,
    max_links: int = 2,
    max_comments: int = 3,
    comment_id_start: int = 1,
    include_invalid_values: bool = False,
    include_over_limit: bool = True,
) -> ResearchHypothesis:
    """Generate a :class:`ResearchHypothesis`.

    Comments are numbered ``hypcomment_{comment_id_start}`` onwards, so a caller
    building several hypotheses can keep comment ids unique across them.
    *include_invalid_values* adds unsupported assessments and bad comment dates.
    """
    assessments = list(VALID_HYPOTHESIS_ASSESSMENTS)
    if include_invalid_values:
        assessments += list(INVALID_ASSESSMENTS)

    link_count = draw(st.integers(min_value=0, max_value=max_links))
    links = [draw(entity_links(pools=entity_pools)) for _ in range(link_count)]

    comment_count = draw(st.integers(min_value=0, max_value=max_comments))
    comments = [
        draw(
            hypothesis_comments(
                comment_id=f"hypcomment_{comment_id_start + offset}",
                include_invalid_dates=include_invalid_values,
                include_over_limit=include_over_limit,
            )
        )
        for offset in range(comment_count)
    ]

    return ResearchHypothesis(
        id=hypothesis_id if hypothesis_id is not None else draw(_identifiers("hypothesis")),
        research_case_id=case_id if case_id is not None else draw(_identifiers("case")),
        statement=draw(bounded_texts(STATEMENT_MAX_LENGTH, include_over_limit=include_over_limit)),
        assessment=draw(st.sampled_from(assessments)),
        reasoning=draw(bounded_texts(LONG_TEXT_MAX_LENGTH, include_over_limit=include_over_limit)),
        linked_entities=links,
        comments=comments,
    )


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------


@st.composite
def actions(
    draw: DrawFn,
    *,
    action_id: Optional[str] = None,
    case_id: Optional[str] = None,
    source_ids: Optional[Sequence[str]] = None,
    max_sources: int = 3,
    pending: Optional[bool] = None,
    include_blank_completed: bool = True,
    include_invalid_values: bool = False,
    include_over_limit: bool = True,
) -> ResearchAction:
    """Generate a :class:`ResearchAction`.

    Args:
        source_ids: Sources that exist. ``None`` generates free ids that may
            dangle; an empty sequence yields no source references.
        pending: ``True`` forces a pending action, ``False`` a completed one,
            ``None`` draws either.
        include_blank_completed: A pending action may be built from a blank
            completion date (``""``, whitespace), which normalizes to ``None``.
        include_invalid_values: A completed action may carry an impossible or
            malformed date.
    """
    if pending is None:
        pending = draw(st.booleans())

    completed_date: Optional[str]
    if pending:
        options: list[SearchStrategy[Optional[str]]] = [st.none()]
        if include_blank_completed:
            options.append(st.sampled_from(BLANK_DATES))
        completed_date = draw(st.one_of(*options))
    else:
        date_options: list[SearchStrategy[str]] = [valid_dates()]
        if include_invalid_values:
            date_options.append(invalid_dates())
        completed_date = draw(st.one_of(*date_options))

    if source_ids is not None and not source_ids:
        source_refs: list[SourceRef] = []
    else:
        source_pool = (
            st.sampled_from(list(source_ids)) if source_ids else _identifiers("source")
        )
        chosen = draw(st.lists(source_pool, max_size=max_sources, unique=True))
        source_refs = [
            SourceRef(source_id=sid, quality=draw(st.sampled_from(_QUALITIES)))
            for sid in chosen
        ]

    return ResearchAction(
        id=action_id if action_id is not None else draw(_identifiers("action")),
        research_case_id=case_id if case_id is not None else draw(_identifiers("case")),
        title=draw(bounded_texts(TITLE_MAX_LENGTH, include_over_limit=include_over_limit)),
        text=draw(bounded_texts(LONG_TEXT_MAX_LENGTH, include_over_limit=include_over_limit)),
        completed_date=completed_date,
        sort_order=draw(st.integers(min_value=0, max_value=20)),
        source_refs=source_refs,
    )


# ---------------------------------------------------------------------------
# research_cases
# ---------------------------------------------------------------------------


@st.composite
def research_cases(
    draw: DrawFn,
    *,
    case_id: Optional[str] = None,
    entity_pools: Optional[dict[str, Sequence[str]]] = None,
    link_shape: Optional[str] = None,
    status: Optional[str] = None,
    include_invalid_values: bool = False,
    include_over_limit: bool = True,
) -> ResearchCase:
    """Generate a :class:`ResearchCase`.

    Args:
        entity_pools: Entities that exist, per type. ``None`` generates free ids
            that may dangle.
        link_shape: One of :data:`LINK_SHAPES`, or ``None`` to draw one.
        status: Pin the status; otherwise drawn from the valid statuses.
        include_invalid_values: Also draw unsupported status and priority values.

    The title may be empty and the conclusion is drawn independently of the
    status, so a closed case may have none and an open case may have one.
    """
    shape = link_shape if link_shape is not None else draw(st.sampled_from(LINK_SHAPES))
    assert shape in LINK_SHAPES, f"unknown link shape {shape!r}"

    statuses = list(VALID_RESEARCH_STATUSES)
    priorities = list(VALID_RESEARCH_PRIORITIES)
    if include_invalid_values:
        statuses += list(INVALID_STATUSES)
        priorities += list(INVALID_PRIORITIES)

    primary: Optional[ResearchEntityLink] = None
    linked: list[ResearchEntityLink] = []

    if shape in ("primary_only", "primary_and_linked", "duplicate_links"):
        primary = draw(entity_links(pools=entity_pools))
    if shape in ("linked_only", "primary_and_linked"):
        count = draw(st.integers(min_value=1, max_value=3))
        linked = [draw(entity_links(pools=entity_pools)) for _ in range(count)]
    if shape == "duplicate_links":
        original = primary
        assert original is not None
        repeated = ResearchEntityLink(
            original.entity_type, original.entity_id, draw(st.sampled_from(_ROLES))
        )
        if draw(st.booleans()):
            linked = [repeated]                       # primary repeated in linked
        else:
            primary = None
            linked = [original, repeated]             # twice in linked

    return ResearchCase(
        id=case_id if case_id is not None else draw(_identifiers("case")),
        title=draw(bounded_texts(TITLE_MAX_LENGTH, include_over_limit=include_over_limit)),
        description=draw(bounded_texts(LONG_TEXT_MAX_LENGTH, include_over_limit=include_over_limit)),
        status=status if status is not None else draw(st.sampled_from(statuses)),
        priority=draw(st.sampled_from(priorities)),
        conclusion=draw(bounded_texts(LONG_TEXT_MAX_LENGTH, include_over_limit=include_over_limit)),
        primary_entity_ref=primary,
        linked_entities=linked,
    )


# ---------------------------------------------------------------------------
# consistent_projects
# ---------------------------------------------------------------------------


@st.composite
def consistent_projects(
    draw: DrawFn,
    *,
    max_cases: int = 4,
    max_hypotheses_per_case: int = 3,
    max_actions_per_case: int = 4,
    max_entities_per_type: int = 3,
    include_over_limit: bool = False,
) -> ProjectData:
    """Generate a :class:`ProjectData` whose research entities all resolve.

    Every entity link points at an entity that exists in the returned project,
    every action names an existing source, and every hypothesis and action names
    an existing case. All ids are unique and of the project's ``prefix_{n}`` form.
    Each of the eight linkable entity types has at least one entity.

    Over-limit text is off by default so the project is also valid; turn it on
    to exercise the length validators.
    """

    def count() -> int:
        return draw(st.integers(min_value=1, max_value=max_entities_per_type))

    person_ids = [f"person_{i + 1}" for i in range(count())]
    persons = [
        Person(
            id=pid,
            sex=draw(st.sampled_from(["M", "F", "X", "U"])),
            names=[
                Name(
                    type="birth",
                    given=draw(st.sampled_from(_GIVEN_NAMES)),
                    surname=draw(st.sampled_from(_SURNAMES)),
                )
            ],
        )
        for pid in person_ids
    ]
    families = [Family(id=f"family_{i + 1}", partners=[], children=[]) for i in range(count())]
    events = [
        Event(
            id=f"event_{i + 1}",
            type="birth",
            participants=[Participant(person_id=person_ids[0], role="subject")],
        )
        for i in range(count())
    ]
    places = [Place(id=f"place_{i + 1}", type="parish", name="Ljusdal") for i in range(count())]
    sources = [
        Source(id=f"source_{i + 1}", provider="Arkiv Digital", source_type="church_book",
               title=f"Volym {i + 1}")
        for i in range(count())
    ]
    media = [
        MediaItem(id=f"media_{i + 1}", type="photo", file=f"media/photos/{i + 1}.jpg",
                  title=f"Foto {i + 1}")
        for i in range(count())
    ]
    dna_matches = [
        DnaMatch(id=f"dna_match_{i + 1}", profile1_id="dna_profile_1", profile2_id="dna_profile_2")
        for i in range(count())
    ]
    dna_clusters = [DnaCluster(id=f"dna_cluster_{i + 1}", name=f"Kluster {i + 1}") for i in range(count())]

    pools: dict[str, list[str]] = {
        "person": person_ids,
        "family": [f.id for f in families],
        "event": [e.id for e in events],
        "place": [p.id for p in places],
        "source": [s.id for s in sources],
        "media": [m.id for m in media],
        "dna_match": [m.id for m in dna_matches],
        "dna_cluster": [c.id for c in dna_clusters],
    }
    source_ids = pools["source"]

    cases: list[ResearchCase] = []
    hypotheses_list: list[ResearchHypothesis] = []
    actions_list: list[ResearchAction] = []
    next_hypothesis = 1
    next_comment = 1
    next_action = 1

    for case_index in range(draw(st.integers(min_value=0, max_value=max_cases))):
        case_id = f"case_{case_index + 1}"
        cases.append(
            draw(research_cases(case_id=case_id, entity_pools=pools,
                                include_over_limit=include_over_limit))
        )

        for _ in range(draw(st.integers(min_value=0, max_value=max_hypotheses_per_case))):
            hypothesis = draw(
                hypotheses(
                    hypothesis_id=f"hypothesis_{next_hypothesis}",
                    case_id=case_id,
                    entity_pools=pools,
                    comment_id_start=next_comment,
                    include_over_limit=include_over_limit,
                )
            )
            next_hypothesis += 1
            next_comment += len(hypothesis.comments)
            hypotheses_list.append(hypothesis)

        for _ in range(draw(st.integers(min_value=0, max_value=max_actions_per_case))):
            actions_list.append(
                draw(
                    actions(
                        action_id=f"action_{next_action}",
                        case_id=case_id,
                        source_ids=source_ids,
                        include_over_limit=include_over_limit,
                    )
                )
            )
            next_action += 1

    return ProjectData(
        project=ProjectMetadata(title=draw(st.sampled_from(["Testprojekt", "Släkten Ek"]))),
        persons=persons,
        families=families,
        events=events,
        places=places,
        sources=sources,
        media=media,
        dna_matches=dna_matches,
        dna_clusters=dna_clusters,
        research_cases=cases,
        research_hypotheses=hypotheses_list,
        research_actions=actions_list,
    )
