"""Shared Hypothesis strategies for the residence-periods property tests.

Every residence property test draws its input from this module, so the edge cases
the design calls out are exercised everywhere rather than per test file:

- whitespace-only bounds, empty strings and ``None`` (Requirement 2.1),
- length boundaries at 100 characters (``role_in_household``), 1000 characters
  (``Endpoint.note`` and ``Observation.page_note``) and 5000 characters
  (``ResidenceFact.notes``),
- 100 Observations on one fact,
- inverted bounds, empty Certain_Cores and Possible_Spans unbounded in one or
  both directions,
- one-sided Observation spans (only ``observed_from`` or only ``observed_to``),
- years outside the plausible 1500–2100 range,
- circular place-parent chains.

The five public strategies are composable: each takes optional identifier pools
and shape selectors so a test can either sample the whole space or pin down the
one case it is about.

    iso_values()          → Optional[str], the three ISO precisions plus absent,
                            padded and malformed values
    endpoints()           → Endpoint, over all five classifications
    observations()        → Observation, over every span shape
    residence_facts()     → ResidenceFact, over every core/span shape
    consistent_projects() → ProjectData whose residences reference existing
                            persons, places, sources and events

Pure test support: no Qt, no I/O.
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Sequence

from hypothesis import strategies as st
from hypothesis.strategies import DrawFn, SearchStrategy

from slaktbusken.model.date_span import expand_iso, precision_of, year_of
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import (
    Endpoint,
    EndpointKind,
    Observation,
    ResidenceFact,
)
from slaktbusken.model.source import Source, StructuredReference


# ---------------------------------------------------------------------------
# Constants — the boundaries the generators deliberately hit
# ---------------------------------------------------------------------------

#: The plausible year range residence validation accepts (Requirement 4.12).
MIN_PLAUSIBLE_YEAR = 1500
MAX_PLAUSIBLE_YEAR = 2100

ROLE_MAX_LENGTH = 100           # role_in_household, after trimming
NOTE_MAX_LENGTH = 1000          # Endpoint.note and Observation.page_note
FACT_NOTES_MAX_LENGTH = 5000    # ResidenceFact.notes
MANY_OBSERVATIONS = 100         # the documented "many Observations" case

#: Values that count as absent for an Endpoint bound (Requirement 2.1).
ABSENT_ISO_VALUES: tuple[Optional[str], ...] = (None, "", " ", "   ", "\t", "\n ")

#: Values that count as absent for an Observation bound, which is a plain ``str``.
ABSENT_YEAR_VALUES: tuple[str, ...] = ("", " ", "   ", "\t")

#: Present but malformed ISO values — no day interval, so the validator reports them.
MALFORMED_ISO_VALUES: tuple[str, ...] = (
    "184",
    "18400",
    "1840-",
    "1840-13",
    "1840-00",
    "1840-06-32",
    "1840-02-30",   # day does not exist in that month
    "1841-02-29",   # not a leap year
    "1840/06/15",
    "1840-6-1",
    "1840-06-15T12:00",
    "ca 1840",
    "okänt",
)

#: Four-digit years outside 1500–2100.
OUT_OF_RANGE_YEARS: tuple[str, ...] = ("0001", "1000", "1499", "2101", "2999", "9999")

#: Present but malformed Observation bounds — only the bare ÅÅÅÅ form is a year.
MALFORMED_YEAR_VALUES: tuple[str, ...] = (
    "18ab",
    "184",
    "18400",
    "1840-06",
    "1840-06-15",
    "ca 1840",
    "okänt",
)

#: ``Endpoint.precision`` is descriptive only, so unknown values belong in the space.
PRECISION_VALUES: tuple[Optional[str], ...] = (
    "day",
    "month",
    "year",
    "approximate",
    None,
    "cirka",
    "unknown",
)

SOURCE_QUALITY_VALUES: tuple[str, ...] = ("primary", "secondary", "questionable")

#: The residence source aspects registered by task 5.2.
RESIDENCE_SOURCE_ASPECTS: tuple[str, ...] = (
    "place",
    "period",
    "household_role",
    "household_members",
)

_PLACE_TYPES: tuple[str, ...] = ("country", "county", "parish", "village", "farm", "ort")

_GIVEN_NAMES: tuple[str, ...] = ("Anders", "Brita", "Erik", "Karin", "Olof", "Märta")
_SURNAMES: tuple[str, ...] = ("Andersson", "Persdotter", "Ek", "Öberg", "Lund")
_PLACE_NAMES: tuple[str, ...] = ("Ed", "Ljusdal", "Norrgården", "Åby", "Östansjö")
_PARISH_SERIES: tuple[str, ...] = ("AI", "AII", "AIIa", "CI", "B", "C")

#: Individual event types an Endpoint may link to, including ``flytt`` (task 5.1).
_EVENT_TYPES: tuple[str, ...] = (
    "birth",
    "death",
    "census",
    "emigration",
    "immigration",
    "flytt",
)

# Letters and digits up to Latin Extended-B, which covers å/ä/ö.
_TEXT_CHARS = st.one_of(
    st.characters(categories=("Ll", "Lu", "Nd"), max_codepoint=0x24F),
    st.sampled_from(list(" -'åäöÅÄÖ")),
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _identifiers(prefix: str) -> SearchStrategy[str]:
    """Generate identifiers of the project's ``{prefix}_{n}`` form."""
    return st.integers(min_value=1, max_value=99).map(lambda n: f"{prefix}_{n}")


def _well_formed_iso(
    min_year: int = MIN_PLAUSIBLE_YEAR,
    max_year: int = MAX_PLAUSIBLE_YEAR,
    precisions: Sequence[str] = ("year", "month", "day"),
) -> SearchStrategy[str]:
    """Generate valid ISO values in the requested precisions and year range."""
    branches: list[SearchStrategy[str]] = []
    if "year" in precisions:
        branches.append(
            st.integers(min_value=min_year, max_value=max_year).map(lambda y: f"{y:04d}")
        )
    if "month" in precisions:
        branches.append(
            st.builds(
                lambda y, m: f"{y:04d}-{m:02d}",
                st.integers(min_value=min_year, max_value=max_year),
                st.integers(min_value=1, max_value=12),
            )
        )
    if "day" in precisions:
        branches.append(
            st.dates(
                min_value=date(max(min_year, 1), 1, 1),
                max_value=date(max_year, 12, 31),
            ).map(lambda d: d.isoformat())
        )
    if not branches:
        raise ValueError(f"no known precision in {precisions!r}")
    return st.one_of(*branches)


@st.composite
def _bounded_texts(
    draw: DrawFn,
    limit: int,
    *,
    include_over_limit: bool = True,
    include_whitespace_only: bool = True,
) -> str:
    """Generate text that hits the interesting lengths around *limit*.

    The lengths 0, 1, ``limit - 1``, ``limit`` and ``limit + 1`` are all
    reachable, so a test can find the exact boundary case it needs. Roughly one
    value in ten is whitespace-only, which trims to empty.
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


def _pool_or_generated(
    draw: DrawFn,
    pool: Optional[Sequence[str]],
    prefix: str,
    *,
    empty_pool_value: str = "",
) -> str:
    """Pick an identifier from *pool*, or generate one when no pool is given.

    ``None`` means "no pool" and yields a freely generated identifier, which may
    dangle. An empty pool means "nothing to reference" and yields
    *empty_pool_value*, keeping generated projects referentially consistent.
    """
    if pool is None:
        return draw(_identifiers(prefix))
    if not pool:
        return empty_pool_value
    return draw(st.sampled_from(list(pool)))


# ---------------------------------------------------------------------------
# iso_values
# ---------------------------------------------------------------------------


def iso_values(
    *,
    min_year: int = MIN_PLAUSIBLE_YEAR,
    max_year: int = MAX_PLAUSIBLE_YEAR,
    precisions: Sequence[str] = ("year", "month", "day"),
    include_absent: bool = True,
    include_malformed: bool = True,
    include_padded: bool = True,
) -> SearchStrategy[Optional[str]]:
    """Generate an Endpoint bound value.

    The space covers the three ISO precisions ÅÅÅÅ, ÅÅÅÅ-MM and ÅÅÅÅ-MM-DD, and
    unless switched off also the absent values (``None``, empty, whitespace-only),
    values padded with surrounding whitespace, and present-but-malformed values.
    Well-formed values are weighted higher so callers get usable dates most of
    the time.

    Pass ``include_absent=False, include_malformed=False`` for a strategy of
    values that always denote a day interval.
    """
    well_formed = _well_formed_iso(min_year, max_year, precisions)
    branches: list[SearchStrategy[Optional[str]]] = [well_formed, well_formed]
    if include_padded:
        branches.append(well_formed.map(lambda value: f"  {value}\t"))
    if include_absent:
        branches.append(st.sampled_from(ABSENT_ISO_VALUES))
    if include_malformed:
        branches.append(st.sampled_from(MALFORMED_ISO_VALUES))
    return st.one_of(*branches)


def year_values(
    *,
    min_year: int = MIN_PLAUSIBLE_YEAR,
    max_year: int = MAX_PLAUSIBLE_YEAR,
) -> SearchStrategy[str]:
    """Generate a bare four-digit year in the given range, as stored."""
    return st.integers(min_value=min_year, max_value=max_year).map(lambda y: f"{y:04d}")


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------

#: The generated Endpoint shapes. ``malformed`` keeps both bounds present with at
#: least one malformed value, so it classifies as a WINDOW.
ENDPOINT_SHAPES: tuple[str, ...] = (
    "unknown",
    "open_latest",
    "open_earliest",
    "exact",
    "window",
    "inverted_window",
    "malformed",
)

_SHAPES_BY_KIND: dict[EndpointKind, tuple[str, ...]] = {
    EndpointKind.UNKNOWN: ("unknown",),
    EndpointKind.OPEN_LATEST: ("open_latest",),
    EndpointKind.OPEN_EARLIEST: ("open_earliest",),
    EndpointKind.EXACT: ("exact",),
    EndpointKind.WINDOW: ("window", "inverted_window", "malformed"),
}


@st.composite
def endpoints(
    draw: DrawFn,
    *,
    kind: Optional[EndpointKind] = None,
    shape: Optional[str] = None,
    event_ids: Optional[Sequence[str]] = None,
    min_year: int = MIN_PLAUSIBLE_YEAR,
    max_year: int = MAX_PLAUSIBLE_YEAR,
    include_notes: bool = True,
) -> Endpoint:
    """Generate an :class:`Endpoint` over all five classifications.

    Pass *kind* to pin the classification, or *shape* to pin the exact generated
    form (see :data:`ENDPOINT_SHAPES`). Absent bounds are drawn from
    :data:`ABSENT_ISO_VALUES`, so whitespace-only bounds occur throughout.
    ``precision`` is drawn from :data:`PRECISION_VALUES`, including unknown
    values, because it must never affect any outcome.

    *event_ids* is a pool for ``event_id``: ``None`` generates a possibly
    dangling identifier, an empty pool leaves ``event_id`` absent.
    """
    if shape is None:
        candidates = ENDPOINT_SHAPES if kind is None else _SHAPES_BY_KIND[kind]
        shape = draw(st.sampled_from(candidates))

    iso = _well_formed_iso(min_year, max_year)
    absent = st.sampled_from(ABSENT_ISO_VALUES)

    earliest: Optional[str]
    latest: Optional[str]

    if shape == "unknown":
        earliest = draw(absent)
        latest = draw(absent)
    elif shape == "open_latest":
        earliest = draw(absent)
        latest = draw(iso)
    elif shape == "open_earliest":
        earliest = draw(iso)
        latest = draw(absent)
    elif shape == "exact":
        value = draw(iso)
        earliest = value
        # A padded copy denotes the same day interval, so this is still EXACT.
        latest = draw(st.sampled_from([value, f" {value} "]))
    elif shape == "window":
        earliest = draw(iso)
        latest = draw(iso)
        if expand_iso(earliest) == expand_iso(latest):
            # Nudge to a different day interval at a different precision.
            year = year_of(earliest)
            latest = f"{year:04d}" if len(earliest) > 4 else f"{year:04d}-06-15"
    elif shape == "inverted_window":
        low = draw(st.integers(min_value=min_year, max_value=max_year - 1))
        high = draw(st.integers(min_value=low + 1, max_value=max_year))
        earliest = f"{high:04d}"
        latest = f"{low:04d}"
    elif shape == "malformed":
        malformed = draw(st.sampled_from(MALFORMED_ISO_VALUES))
        if draw(st.booleans()):
            earliest, latest = malformed, draw(iso)
        else:
            earliest, latest = draw(iso), malformed
    else:
        raise ValueError(f"unknown endpoint shape {shape!r}")

    if event_ids is None:
        event_id = draw(st.none() | _identifiers("event"))
    elif event_ids:
        event_id = draw(st.none() | st.sampled_from(list(event_ids)))
    else:
        event_id = None

    note = draw(st.none() | _bounded_texts(NOTE_MAX_LENGTH)) if include_notes else None

    return Endpoint(
        earliest=earliest,
        latest=latest,
        precision=draw(st.sampled_from(PRECISION_VALUES)),
        event_id=event_id,
        note=note,
    )


# ---------------------------------------------------------------------------
# observations
# ---------------------------------------------------------------------------

#: The generated Observation span shapes.
OBSERVATION_SHAPES: tuple[str, ...] = (
    "ordered",
    "one_sided_from",
    "one_sided_to",
    "absent",
    "inverted",
    "out_of_range",
    "malformed",
)


@st.composite
def observations(
    draw: DrawFn,
    *,
    source_ids: Optional[Sequence[str]] = None,
    shape: Optional[str] = None,
    min_year: int = MIN_PLAUSIBLE_YEAR,
    max_year: int = MAX_PLAUSIBLE_YEAR,
    include_page_notes: bool = True,
) -> Observation:
    """Generate an :class:`Observation` over every span shape.

    The shapes cover an ordered year pair, the two one-sided spans, both bounds
    absent, an inverted pair, years outside 1500–2100 and malformed bounds (see
    :data:`OBSERVATION_SHAPES`). *source_ids* is a pool for
    ``source_ref.source_id``: ``None`` generates a possibly dangling identifier,
    an empty pool yields a blank reference.
    """
    if shape is None:
        shape = draw(st.sampled_from(OBSERVATION_SHAPES))

    years = st.integers(min_value=min_year, max_value=max_year)
    absent = st.sampled_from(ABSENT_YEAR_VALUES)

    if shape == "ordered":
        first = draw(years)
        last = draw(st.integers(min_value=first, max_value=max_year))
        observed_from, observed_to = f"{first:04d}", f"{last:04d}"
    elif shape == "one_sided_from":
        observed_from, observed_to = f"{draw(years):04d}", draw(absent)
    elif shape == "one_sided_to":
        observed_from, observed_to = draw(absent), f"{draw(years):04d}"
    elif shape == "absent":
        observed_from, observed_to = draw(absent), draw(absent)
    elif shape == "inverted":
        low = draw(st.integers(min_value=min_year, max_value=max_year - 1))
        high = draw(st.integers(min_value=low + 1, max_value=max_year))
        observed_from, observed_to = f"{high:04d}", f"{low:04d}"
    elif shape == "out_of_range":
        out_of_range = st.sampled_from(OUT_OF_RANGE_YEARS)
        in_range = years.map(lambda y: f"{y:04d}")
        observed_from = draw(st.one_of(out_of_range, in_range))
        observed_to = draw(st.one_of(out_of_range, in_range))
    elif shape == "malformed":
        malformed = st.sampled_from(MALFORMED_YEAR_VALUES)
        if draw(st.booleans()):
            observed_from = draw(malformed)
            observed_to = draw(st.one_of(years.map(lambda y: f"{y:04d}"), absent))
        else:
            observed_from = draw(st.one_of(years.map(lambda y: f"{y:04d}"), absent))
            observed_to = draw(malformed)
    else:
        raise ValueError(f"unknown observation shape {shape!r}")

    source_id = _pool_or_generated(draw, source_ids, "source")
    source_ref = SourceRef(
        source_id=source_id,
        quality=draw(st.sampled_from(SOURCE_QUALITY_VALUES)),
        note=draw(st.just("") | _bounded_texts(NOTE_MAX_LENGTH)),
        aspects=draw(
            st.lists(
                st.sampled_from(RESIDENCE_SOURCE_ASPECTS),
                min_size=0,
                max_size=len(RESIDENCE_SOURCE_ASPECTS),
                unique=True,
            )
        ),
    )

    page_note = draw(_bounded_texts(NOTE_MAX_LENGTH)) if include_page_notes else ""

    return Observation(
        source_ref=source_ref,
        observed_from=observed_from,
        observed_to=observed_to,
        page_note=page_note,
    )


# ---------------------------------------------------------------------------
# residence_facts
# ---------------------------------------------------------------------------

#: The generated core/span shapes of a Residence_Fact.
FACT_SHAPES: tuple[str, ...] = (
    "free",         # two independently drawn Endpoints, any classification
    "ordered",      # four increasing years, so the Certain_Core is non-empty
    "empty_core",   # start.latest after end.earliest, so the core is empty
    "unbounded",    # both Endpoints unknown, so the Possible_Span is unbounded
    "open_start",   # unknown start, so the span is unbounded backwards
    "open_end",     # unknown end, so the span is unbounded forwards
)


@st.composite
def _decorated_endpoint(
    draw: DrawFn,
    earliest: Optional[str],
    latest: Optional[str],
    event_ids: Optional[Sequence[str]],
) -> Endpoint:
    """Wrap given bounds in an Endpoint with generated descriptive fields."""
    if event_ids is None:
        event_id = draw(st.none() | _identifiers("event"))
    elif event_ids:
        event_id = draw(st.none() | st.sampled_from(list(event_ids)))
    else:
        event_id = None
    return Endpoint(
        earliest=earliest,
        latest=latest,
        precision=draw(st.sampled_from(PRECISION_VALUES)),
        event_id=event_id,
        note=draw(st.none() | _bounded_texts(NOTE_MAX_LENGTH)),
    )


@st.composite
def residence_facts(
    draw: DrawFn,
    *,
    residence_id: Optional[str] = None,
    person_ids: Optional[Sequence[str]] = None,
    place_ids: Optional[Sequence[str]] = None,
    source_ids: Optional[Sequence[str]] = None,
    event_ids: Optional[Sequence[str]] = None,
    shape: Optional[str] = None,
    observation_count: Optional[int] = None,
    max_observations: int = 4,
    include_many_observations: bool = True,
    include_blank_references: bool = True,
    min_year: int = MIN_PLAUSIBLE_YEAR,
    max_year: int = MAX_PLAUSIBLE_YEAR,
) -> ResidenceFact:
    """Generate a :class:`ResidenceFact`.

    *shape* pins the relation between the two Endpoints (see :data:`FACT_SHAPES`)
    so a test can ask for a non-empty core, an empty core or an unbounded span
    directly; left open, all shapes occur. ``role_in_household`` and ``notes``
    hit their 100- and 5000-character boundaries, and roughly one fact in ten
    carries :data:`MANY_OBSERVATIONS` Observations unless
    ``include_many_observations=False`` or *observation_count* says otherwise.

    The identifier pools work like elsewhere in this module: ``None`` generates a
    possibly dangling identifier, an empty pool yields a blank one. With
    *include_blank_references* the ``person_id`` and ``place_id`` are sometimes
    blank or whitespace-only, which the validator treats specially.
    """
    if shape is None:
        shape = draw(st.sampled_from(FACT_SHAPES))

    fact_id = residence_id if residence_id is not None else draw(_identifiers("residence"))

    person_id = _pool_or_generated(draw, person_ids, "person")
    place_id = _pool_or_generated(draw, place_ids, "place")
    if include_blank_references and draw(st.integers(min_value=0, max_value=9)) == 0:
        blank = draw(st.sampled_from(["", "   "]))
        if draw(st.booleans()):
            person_id = blank
        else:
            place_id = blank

    unknown = st.sampled_from(ABSENT_ISO_VALUES)

    if shape == "free":
        start = draw(endpoints(event_ids=event_ids, min_year=min_year, max_year=max_year))
        end = draw(endpoints(event_ids=event_ids, min_year=min_year, max_year=max_year))
    elif shape == "ordered":
        # Four strictly increasing years, so the last day of start.latest falls on
        # or before the first day of end.earliest and the core is non-empty.
        bounds = sorted(
            draw(
                st.lists(
                    st.integers(min_value=min_year, max_value=max_year),
                    min_size=4,
                    max_size=4,
                    unique=True,
                )
            )
        )
        start = draw(
            _decorated_endpoint(f"{bounds[0]:04d}", f"{bounds[1]:04d}", event_ids)
        )
        end = draw(_decorated_endpoint(f"{bounds[2]:04d}", f"{bounds[3]:04d}", event_ids))
    elif shape == "empty_core":
        low = draw(st.integers(min_value=min_year, max_value=max_year - 1))
        high = draw(st.integers(min_value=low + 1, max_value=max_year))
        # start.latest ends after end.earliest begins → the core is empty.
        start = draw(_decorated_endpoint(f"{low:04d}", f"{high:04d}", event_ids))
        end = draw(_decorated_endpoint(f"{low:04d}", f"{high:04d}", event_ids))
    elif shape == "unbounded":
        start = draw(_decorated_endpoint(draw(unknown), draw(unknown), event_ids))
        end = draw(_decorated_endpoint(draw(unknown), draw(unknown), event_ids))
    elif shape == "open_start":
        start = draw(_decorated_endpoint(draw(unknown), draw(unknown), event_ids))
        end = draw(
            endpoints(
                kind=draw(
                    st.sampled_from(
                        [EndpointKind.EXACT, EndpointKind.WINDOW, EndpointKind.OPEN_EARLIEST]
                    )
                ),
                event_ids=event_ids,
                min_year=min_year,
                max_year=max_year,
            )
        )
    elif shape == "open_end":
        start = draw(
            endpoints(
                kind=draw(
                    st.sampled_from(
                        [EndpointKind.EXACT, EndpointKind.WINDOW, EndpointKind.OPEN_LATEST]
                    )
                ),
                event_ids=event_ids,
                min_year=min_year,
                max_year=max_year,
            )
        )
        end = draw(_decorated_endpoint(draw(unknown), draw(unknown), event_ids))
    else:
        raise ValueError(f"unknown fact shape {shape!r}")

    if observation_count is not None:
        count = observation_count
    elif include_many_observations and draw(st.integers(min_value=0, max_value=9)) == 0:
        count = MANY_OBSERVATIONS
    else:
        count = draw(st.integers(min_value=0, max_value=max_observations))

    observation_list = [
        draw(
            observations(
                source_ids=source_ids,
                min_year=min_year,
                max_year=max_year,
            )
        )
        for _ in range(count)
    ]

    return ResidenceFact(
        id=fact_id,
        person_id=person_id,
        place_id=place_id,
        start=start,
        end=end,
        role_in_household=draw(_bounded_texts(ROLE_MAX_LENGTH)),
        observations=observation_list,
        notes=draw(_bounded_texts(FACT_NOTES_MAX_LENGTH)),
    )


# ---------------------------------------------------------------------------
# consistent_projects
# ---------------------------------------------------------------------------


@st.composite
def _church_book_sources(draw: DrawFn, source_id: str, min_year: int, max_year: int) -> Source:
    """Generate a church book Source with the structured fields residences read."""
    first = draw(st.integers(min_value=min_year, max_value=max_year - 5))
    last = draw(st.integers(min_value=first, max_value=min(first + 20, max_year)))
    years = draw(
        st.sampled_from(
            [
                f"{first}-{last}",
                f"{first}\u2013{last}",   # en dash
                f"{first}",
                f"  {first} - {last} ",
                f"{last}-{first}",        # descending, so unparsable
                "odaterad",
                "",
            ]
        )
    )
    parish = draw(st.sampled_from(_PLACE_NAMES))
    series = draw(st.sampled_from(_PARISH_SERIES))
    volume = draw(st.integers(min_value=1, max_value=40))
    return Source(
        id=source_id,
        provider="Arkiv Digital",
        source_type="church_book",
        title=f"{parish} {series}:{volume} ({years})",
        structured_reference=StructuredReference(
            fields={
                "parish": parish,
                "county_code": draw(st.sampled_from(["X", "S", "Y", "AB"])),
                "series": series,
                "volume": str(volume),
                "years": years,
            }
        ),
    )


@st.composite
def consistent_projects(
    draw: DrawFn,
    *,
    min_persons: int = 1,
    max_persons: int = 3,
    min_places: int = 1,
    max_places: int = 3,
    max_sources: int = 2,
    max_events: int = 3,
    min_residences: int = 0,
    max_residences: int = 4,
    include_circular_place_parents: bool = True,
    include_many_observations: bool = False,
    min_year: int = MIN_PLAUSIBLE_YEAR,
    max_year: int = MAX_PLAUSIBLE_YEAR,
) -> ProjectData:
    """Generate a :class:`ProjectData` whose residences reference existing entities.

    Every ``person_id``, ``place_id``, ``source_ref.source_id`` and ``event_id``
    on a generated Residence_Fact resolves inside the returned project, so tests
    of coverage, inference, querying and reporting get referentially sound input.
    Place parents form real chains and, roughly one project in five, a cycle —
    two places naming each other, or a single place naming itself — so every
    hierarchy walk must guard against it.

    The generated facts are passed straight into the declared
    ``ProjectData.residences`` field, in generation order.
    """
    persons = [
        Person(
            id=f"person_{index + 1}",
            sex=draw(st.sampled_from(["M", "F", "X", "U"])),
            names=[
                Name(
                    type="birth",
                    given=draw(st.sampled_from(_GIVEN_NAMES)),
                    surname=draw(st.sampled_from(_SURNAMES)),
                )
            ],
        )
        for index in range(draw(st.integers(min_value=min_persons, max_value=max_persons)))
    ]

    place_count = draw(st.integers(min_value=min_places, max_value=max_places))
    places: list[Place] = []
    for index in range(place_count):
        parent_place_id: Optional[str] = None
        if index > 0 and draw(st.booleans()):
            parent_place_id = f"place_{draw(st.integers(min_value=1, max_value=index))}"
        places.append(
            Place(
                id=f"place_{index + 1}",
                type=draw(st.sampled_from(_PLACE_TYPES)),
                name=draw(st.sampled_from(_PLACE_NAMES)),
                parent_place_id=parent_place_id,
            )
        )
    if include_circular_place_parents and draw(st.integers(min_value=0, max_value=4)) == 0:
        if len(places) >= 2:
            places[0].parent_place_id = places[-1].id
            places[-1].parent_place_id = places[0].id
        else:
            places[0].parent_place_id = places[0].id

    sources = [
        draw(_church_book_sources(f"source_{index + 1}", min_year, max_year))
        for index in range(draw(st.integers(min_value=0, max_value=max_sources)))
    ]

    person_ids = [person.id for person in persons]
    place_ids = [place.id for place in places]
    source_ids = [source.id for source in sources]

    events: list[Event] = []
    for index in range(draw(st.integers(min_value=0, max_value=max_events))):
        value = draw(st.none() | _well_formed_iso(min_year, max_year))
        date_value = (
            None
            if value is None
            else DateValue(value=value, precision=precision_of(value) or "year")
        )
        place_ref = draw(st.none() | st.sampled_from(place_ids).map(lambda pid: PlaceRef(place_id=pid)))
        events.append(
            Event(
                id=f"event_{index + 1}",
                type=draw(st.sampled_from(_EVENT_TYPES)),
                participants=[
                    Participant(person_id=draw(st.sampled_from(person_ids)), role="primary")
                ],
                date=date_value,
                place=place_ref,
            )
        )
    event_ids = [event.id for event in events]

    residences = [
        draw(
            residence_facts(
                residence_id=f"residence_{index + 1}",
                person_ids=person_ids,
                place_ids=place_ids,
                source_ids=source_ids,
                event_ids=event_ids,
                observation_count=0 if not source_ids else None,
                include_many_observations=include_many_observations,
                include_blank_references=False,
                min_year=min_year,
                max_year=max_year,
            )
        )
        for index in range(draw(st.integers(min_value=min_residences, max_value=max_residences)))
    ]

    data = ProjectData(
        project=ProjectMetadata(title=draw(st.sampled_from(["Testprojekt", "Släkten Ek"]))),
        persons=persons,
        places=places,
        sources=sources,
        events=events,
        residences=residences,
    )
    return data
