"""Hypothesis strategies for the GEDCOM round-trip properties.

Every strategy produces data that passes ``ValidationService`` (the one
exception is the opt-in ``free_roles`` flag, see below), so a failing property
points at the exporter or importer and not at an invalid input.

Strategy map (design "Properties"):

========================  =============================================
Strategy                  Properties
========================  =============================================
``free_text``             2 (notes, titles, roles, citation notes)
``name_lists``            3
``partner_projects``      4, 5
``parentage_projects``    6
``event_projects``        1, 7, 17
``citation_projects``     8
``residence_projects``    9, 10
``source_projects``       11
``projects``              1, 13, 15, 16 (whole project)
========================  =============================================

Persons keep a fixed shape of ids (``person_N`` and so on). Places, sources
and the repository come from ``synthetic.py`` so both modules share one
valid environment.

``make/maka`` is a valid partner role (``validate_family``) and is in the
default role pool. ``free_roles=True`` adds the literal texts ``make`` and
``maka``, which ``validate_family`` does not accept; use it only for tests
that do not validate.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Optional

from hypothesis import strategies as st

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import (
    Kalltyp,
    Leverantor,
    Repository,
    RepositoryRef,
    Source,
    StructuredReference,
)

from tests.test_gedcom_roundtrip import synthetic as syn

SEXES = ("M", "F", "U", "X")
NAME_TYPES = ("birth", "married", "alias", "adopted", "other")
VALID_PARTNER_ROLES = (
    "father", "mother", "husband", "wife", "partner", "make/maka",
)
FREE_PARTNER_ROLES = VALID_PARTNER_ROLES + ("make", "maka")
PARENTAGE_TYPES = ("biological", "legal", "adoptive", "foster", "step", "donation")

INDIVIDUAL_EVENT_TYPES = (
    "birth", "baptism", "death", "burial", "confirmation", "will", "blessing",
    "first_communion", "census", "custom_individual_event",
)
FAMILY_EVENT_TYPES = (
    "marriage", "divorce", "engagement", "divorce_filed", "custom_family_event",
)
PARTICIPANT_ROLES = ("subject", "godfather", "witness", "förälder")

_PLACE_IDS = (syn.PLACE_LJUSDAL, syn.PLACE_GAVLE, syn.PLACE_BOLLNAS, syn.PLACE_CHURCH)
_SOURCE_IDS = (syn.SOURCE_HFL, syn.SOURCE_DOP, syn.SOURCE_DB, syn.SOURCE_NEWS,
               syn.SOURCE_OTHER)


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

# No surrogates, controls (the line break is added back), or line and
# paragraph separators that str.splitlines would treat as breaks.
_TEXT_CHARS = st.characters(
    exclude_categories=("Cs", "Cc", "Zl", "Zp"), include_characters="\n@ åäöÅÄÖé",
)


def free_text(min_size: int = 0, max_size: int = 300) -> st.SearchStrategy[str]:
    """Free text: line breaks, leading and trailing spaces, ``@``, non-ASCII."""
    return st.text(_TEXT_CHARS, min_size=min_size, max_size=max_size)


def long_free_text() -> st.SearchStrategy[str]:
    """Text of 190 to 700 characters, so that CONC splitting is exercised."""
    return st.text(_TEXT_CHARS, min_size=190, max_size=700)


def text_value() -> st.SearchStrategy[str]:
    """Mostly short text, sometimes long enough for CONC."""
    return st.one_of(free_text(max_size=60), free_text(max_size=60),
                     free_text(max_size=300), long_free_text())


_NAME_ALPHABET = st.characters(
    categories=("Lu", "Ll"), include_characters="åäöÅÄÖéü-",
)


def simple_name() -> st.SearchStrategy[str]:
    """A name part without spaces at the ends, ``/`` or ``@``; 1 to 20 letters."""
    return st.text(_NAME_ALPHABET, min_size=1, max_size=20).filter(
        lambda s: s == s.strip() and not s.startswith("-"))


def aspect_text() -> st.SearchStrategy[str]:
    return st.text(_NAME_ALPHABET, min_size=1, max_size=12)


def short_text() -> st.SearchStrategy[str]:
    return st.text(_NAME_ALPHABET, min_size=1, max_size=15)


# ---------------------------------------------------------------------------
# Dates, citations
# ---------------------------------------------------------------------------


@st.composite
def iso_dates(draw, min_year: int = 1600, max_year: int = 2000) -> str:
    """A real ISO date (``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``), Gregorian."""
    year = draw(st.integers(min_year, max_year))
    level = draw(st.sampled_from(("year", "month", "day")))
    if level == "year":
        return f"{year:04d}"
    month = draw(st.integers(1, 12))
    if level == "month":
        return f"{year:04d}-{month:02d}"
    day = draw(st.integers(1, 28))
    return f"{year:04d}-{month:02d}-{day:02d}"


@st.composite
def date_values(draw, source_refs: Optional[list[SourceRef]] = None) -> DateValue:
    """A valid ``DateValue`` of any qualifier except the Julian calendar."""
    refs = list(source_refs or [])
    qualifier = draw(st.sampled_from((
        "exact", "exact", "exact", "about", "estimated", "calculated", "before",
        "after", "between", "from_to", "from", "to", "interpreted", "unparsed",
    )))
    if qualifier == "unparsed":
        text = draw(st.text(_NAME_ALPHABET, min_size=1, max_size=20)) + " 1900"
        return DateValue(value="", precision="approximate", qualifier="unparsed",
                         original_text=text, source_refs=refs)
    value = draw(iso_dates())
    if qualifier == "exact":
        precision = {4: "year", 7: "month", 10: "day"}[len(value)]
        return DateValue(value=value, precision=precision, source_refs=refs)
    kw: dict = {}
    if qualifier in ("between", "from_to"):
        second = draw(iso_dates())
        # Sorted by first day, so the end never lies before the start.
        value, kw["value_to"] = sorted((value, second), key=syn_span)
    if qualifier == "interpreted":
        kw["original_text"] = "INT " + value
    return DateValue(value=value, precision="approximate", qualifier=qualifier,
                     source_refs=refs, **kw)


def syn_span(iso: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """First and last day of an ISO date as tuples, for ordering two dates."""
    parts = [int(p) for p in iso.split("-")]
    y = parts[0]
    if len(parts) == 1:
        return (y, 1, 1), (y, 12, 31)
    m = parts[1]
    if len(parts) == 2:
        return (y, m, 1), (y, m, 31)
    return (y, m, parts[2]), (y, m, parts[2])


@st.composite
def source_refs(draw, max_size: int = 3) -> list[SourceRef]:
    """Citations with any quality, a note and aspects."""
    n = draw(st.integers(0, max_size))
    refs = []
    for _ in range(n):
        refs.append(SourceRef(
            source_id=draw(st.sampled_from(_SOURCE_IDS)),
            quality=draw(st.sampled_from(syn.QUALITIES)),
            note=draw(st.one_of(st.just(""), free_text(max_size=80))),
            aspects=draw(st.lists(aspect_text(), max_size=3)),
        ))
    return refs


# ---------------------------------------------------------------------------
# Project builder
# ---------------------------------------------------------------------------


@dataclass
class _Builder:
    persons: list[Person] = field(default_factory=list)
    families: list[Family] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    residences: list[ResidenceFact] = field(default_factory=list)
    sources: Optional[list[Source]] = None
    repositories: Optional[list[Repository]] = None
    leverantorer: list[Leverantor] = field(default_factory=list)
    kalltyper: list[Kalltyp] = field(default_factory=list)
    _counters: dict = field(default_factory=lambda: {
        "person": itertools.count(1), "family": itertools.count(1),
        "event": itertools.count(1), "residence": itertools.count(1),
    })

    def new_id(self, kind: str) -> str:
        return f"{kind}_{next(self._counters[kind])}"

    def person_ids(self) -> list[str]:
        return [p.id for p in self.persons]

    def build(self) -> ProjectData:
        sources, leverantorer, kalltyper = syn.build_sources()
        repositories = syn.build_repositories()
        if self.sources is not None:
            sources = self.sources
            leverantorer, kalltyper = self.leverantorer, self.kalltyper
            repositories = self.repositories or []
        main = self.persons[0].id if self.persons else None
        return ProjectData(
            project=ProjectMetadata(title="Genererat projekt", main_person_id=main),
            persons=self.persons, families=self.families, events=self.events,
            residences=self.residences, places=syn.build_places(),
            sources=sources, repositories=repositories,
            leverantorer=leverantorer, kalltyper=kalltyper,
        )


@st.composite
def name_lists(draw, min_size: int = 1, max_size: int = 5) -> list[Name]:
    """Names of any type in any order (Property 3). Types may repeat."""
    n = draw(st.integers(min_size, max_size))
    return [Name(type=draw(st.sampled_from(NAME_TYPES)), given=draw(simple_name()),
                 surname=draw(simple_name())) for _ in range(n)]


def _add_person(draw, b: _Builder, *, sex: Optional[str] = None,
                names: bool = True, texts: bool = True) -> str:
    pid = b.new_id("person")
    name_list = draw(name_lists(1, 3)) if names else [
        Name("birth", draw(simple_name()), draw(simple_name()))]
    kw = {}
    if texts:
        kw["notes"] = draw(text_value())
        kw["title"] = draw(st.one_of(st.none(), free_text(min_size=1, max_size=40)
                                     .filter(lambda s: "\n" not in s)))
        kw["occupation"] = draw(st.one_of(st.none(), free_text(min_size=1, max_size=40)
                                          .filter(lambda s: "\n" not in s)))
    b.persons.append(Person(
        id=pid, sex=sex or draw(st.sampled_from(SEXES)), names=name_list, **kw))
    return pid


def _add_family(draw, b: _Builder, *, n_partners: Optional[int] = None,
                free_roles: bool = False, children: int = 0,
                parentage: bool = False) -> Family:
    count = n_partners if n_partners is not None else draw(st.integers(1, 2))
    pids = [_add_person(draw, b, texts=False) for _ in range(count)]
    # Any list order: a permutation of the partner ids.
    order = draw(st.permutations(pids))
    roles = FREE_PARTNER_ROLES if free_roles else VALID_PARTNER_ROLES
    partners = [FamilyPartner(pid, draw(st.sampled_from(roles))) for pid in order]
    kids = [_add_person(draw, b, texts=False) for _ in range(children)]
    links: list[ParentChildLink] = []
    if parentage:
        # One link per child and partner (a biological link is never written,
        # so a missing link and a biological link read the same after import),
        # plus an optional link without parent for an unknown donor.
        #
        # Known importer behaviour (reported, pinned by xfail tests in
        # test_families_roundtrip.py): a foster or adoptive child makes the
        # post-import parentage sync rewrite the whole imported family (other
        # children, other links and partner roles are dropped). Generated
        # families therefore either hold one child with a uniform foster or
        # adoptive type, or any number of children with other types.
        derived = bool(kids) and draw(st.booleans())
        if derived:
            kids = kids[:1]
            ptype = draw(st.sampled_from(("foster", "adoptive")))
            links = [ParentChildLink(kids[0], pid, ptype) for pid in pids]
        else:
            others = tuple(t for t in PARENTAGE_TYPES
                           if t not in ("foster", "adoptive"))
            for kid in kids:
                for pid in pids:
                    links.append(ParentChildLink(
                        kid, pid, draw(st.sampled_from(others))))
                if draw(st.booleans()):
                    links.append(ParentChildLink(kid, None, "unknown_donor"))
    fam = Family(id=b.new_id("family"), partners=partners, children=kids,
                 parent_child_links=links)
    b.families.append(fam)
    return fam


@st.composite
def _place_ref(draw, with_citations: bool) -> PlaceRef:
    refs = draw(source_refs(2)) if with_citations else []
    return PlaceRef(draw(st.sampled_from(_PLACE_IDS)), refs)


def _add_event(draw, b: _Builder, type_: str, people: list[tuple[str, str]], *,
               citations: bool, from_place: bool = False) -> Event:
    date = draw(st.one_of(st.none(), date_values(
        draw(source_refs(2)) if citations else None)))
    place = draw(st.one_of(st.none(), _place_ref(citations)))
    event = Event(
        id=b.new_id("event"), type=type_,
        participants=[Participant(p, r) for p, r in people],
        date=date, place=place,
        source_refs=draw(source_refs(2)) if citations else [],
    )
    if type_ in ("custom_individual_event", "custom_family_event"):
        event.custom_type_name = draw(simple_name())
    # K56: the cause is written as CAUS on every event type that has one.
    event.cause_of_death = draw(st.one_of(st.none(), simple_name()))
    if from_place:
        event.from_place = draw(_place_ref(citations))
    b.events.append(event)
    return event


def _add_individual_events(draw, b: _Builder, citations: bool) -> None:
    pids = b.person_ids()
    for _ in range(draw(st.integers(0, 6))):
        type_ = draw(st.sampled_from(INDIVIDUAL_EVENT_TYPES + ("flytt",)))
        owner = draw(st.sampled_from(pids))
        people = [(owner, "subject")]
        if len(pids) > 1 and draw(st.booleans()):
            other = draw(st.sampled_from([p for p in pids if p != owner]))
            people.append((other, draw(st.sampled_from(PARTICIPANT_ROLES))))
        _add_event(draw, b, type_, people, citations=citations,
                   from_place=(type_ == "flytt"))


def _add_family_events(draw, b: _Builder, fam: Family, citations: bool) -> None:
    """Family events: listed, orphan with a unique match, or neither."""
    spouses = [(p.person_id, "spouse") for p in fam.partners]
    for _ in range(draw(st.integers(0, 3))):
        type_ = draw(st.sampled_from(FAMILY_EVENT_TYPES))
        event = _add_event(draw, b, type_, spouses, citations=citations)
        if draw(st.booleans()):
            fam.event_ids.append(event.id)  # listed; otherwise an orphan


def _add_fallback_marriages(draw, b: _Builder, citations: bool) -> None:
    """Couples without a family: Individual_Fallback, equal date and place."""
    n = draw(st.integers(1, 3))
    shared = draw(st.one_of(st.none(), date_values()))
    shared_place = draw(st.sampled_from(_PLACE_IDS))
    for _ in range(n):
        a = _add_person(draw, b, texts=False)
        c = _add_person(draw, b, texts=False)
        event = _add_event(draw, b, "marriage", [(a, "spouse"), (c, "spouse")],
                           citations=citations)
        if shared is not None:  # equal date and place, different participants
            event.date = DateValue(**{**shared.__dict__, "source_refs": []})
            event.place = PlaceRef(shared_place)


# ---------------------------------------------------------------------------
# Residences
# ---------------------------------------------------------------------------


@st.composite
def _endpoint(draw, event_ids: list[str]) -> Endpoint:
    """An endpoint: empty, one-sided, exact or a window."""
    kind = draw(st.sampled_from(("empty", "earliest", "latest", "exact", "window")))
    year = draw(st.integers(1700, 1990))
    kw: dict = {}
    if kind == "earliest":
        kw["earliest"] = f"{year:04d}"
    elif kind == "latest":
        kw["latest"] = f"{year:04d}-{draw(st.integers(1, 12)):02d}"
    elif kind == "exact":
        day = f"{year:04d}-{draw(st.integers(1, 12)):02d}-{draw(st.integers(1, 28)):02d}"
        kw["earliest"] = kw["latest"] = day
    elif kind == "window":
        kw["earliest"] = f"{year:04d}"
        kw["latest"] = f"{year + draw(st.integers(0, 3)):04d}"
    if kind != "empty":
        kw["precision"] = draw(st.sampled_from(
            (None, "day", "month", "year", "approximate")))
    if draw(st.booleans()):
        kw["note"] = draw(free_text(max_size=100))
    if event_ids and draw(st.booleans()):
        kw["event_id"] = draw(st.sampled_from(event_ids))
    return Endpoint(**kw)


@st.composite
def _observation(draw) -> Observation:
    a = draw(st.integers(1700, 1990))
    kind = draw(st.sampled_from(("range", "from", "to", "none")))
    bounds = {"range": (f"{a:04d}", f"{a + draw(st.integers(0, 5)):04d}"),
              "from": (f"{a:04d}", ""), "to": ("", f"{a:04d}"), "none": ("", "")}
    ref = SourceRef(
        source_id=draw(st.sampled_from(_SOURCE_IDS)),
        quality=draw(st.sampled_from(syn.QUALITIES)),
        note=draw(st.one_of(st.just(""), free_text(max_size=60))),
        aspects=draw(st.lists(aspect_text(), max_size=2)),
    )
    return Observation(ref, bounds[kind][0], bounds[kind][1],
                       draw(st.one_of(st.just(""), free_text(max_size=60))))


def _add_residences(draw, b: _Builder) -> None:
    flytt_ids = [e.id for e in b.events if e.type == "flytt"]
    pids = b.person_ids()
    for _ in range(draw(st.integers(1, 3))):
        b.residences.append(ResidenceFact(
            id=b.new_id("residence"), person_id=draw(st.sampled_from(pids)),
            place_id=draw(st.sampled_from(_PLACE_IDS)),
            start=draw(_endpoint(flytt_ids)), end=draw(_endpoint(flytt_ids)),
            role_in_household=draw(st.one_of(
                st.just(""), free_text(max_size=40).map(str.strip)
                .filter(lambda s: "\n" not in s))),
            observations=draw(st.lists(_observation(), max_size=3)),
            notes=draw(text_value()),
        ))


def _fix_residence_order(b: _Builder) -> None:
    """Drop bounds that make a residence invalid (inverted endpoints)."""
    for r in b.residences:
        if r.end.latest and r.start.earliest and r.end.latest < r.start.earliest:
            r.end = Endpoint()


# ---------------------------------------------------------------------------
# Public strategies
# ---------------------------------------------------------------------------


@st.composite
def person_projects(draw) -> ProjectData:
    """Persons only: names of any type and order, notes, title, occupation."""
    b = _Builder()
    for _ in range(draw(st.integers(1, 4))):
        _add_person(draw, b)
    return b.build()


@st.composite
def partner_projects(draw, free_roles: bool = False) -> ProjectData:
    """One family with one or two partners of any sex, role and order."""
    b = _Builder()
    _add_family(draw, b, free_roles=free_roles)
    return b.build()


@st.composite
def parentage_projects(draw) -> ProjectData:
    """One family with children and links of any parentage type."""
    b = _Builder()
    _add_family(draw, b, n_partners=draw(st.integers(1, 2)),
                children=draw(st.integers(1, 3)), parentage=True)
    return b.build()


@st.composite
def event_projects(draw, citations: bool = False) -> ProjectData:
    """Events of every exportable type, family events listed or orphaned."""
    b = _Builder()
    for _ in range(draw(st.integers(0, 2))):
        fam = _add_family(draw, b, n_partners=2)
        _add_family_events(draw, b, fam, citations)
    if draw(st.booleans()):
        _add_fallback_marriages(draw, b, citations)
    if not b.persons:
        _add_person(draw, b)
    _add_individual_events(draw, b, citations)
    return b.build()


@st.composite
def citation_projects(draw) -> ProjectData:
    """Events with citations in the contexts event, date, place and from_place."""
    return draw(event_projects(citations=True))


@st.composite
def residence_projects(draw) -> ProjectData:
    """Persons, flytt events that endpoints can link to, and residences."""
    b = _Builder()
    for _ in range(draw(st.integers(1, 3))):
        _add_person(draw, b)
    for _ in range(draw(st.integers(0, 2))):
        owner = draw(st.sampled_from(b.person_ids()))
        _add_event(draw, b, "flytt", [(owner, "subject")], citations=True,
                   from_place=True)
    _add_residences(draw, b)
    _fix_residence_order(b)
    return b.build()


_REFERENCE_FIELDS = {
    "church_book": ("parish", "county_code", "series", "volume", "years", "image",
                    "page"),
    "database": ("database_name", "record_id"),
    "death_notice": ("newspaper", "publication_date", "page"),
    "newspaper": ("newspaper", "date", "page", "article_title"),
}
_SOURCE_TYPES = ("church_book", "database", "death_notice", "newspaper",
                 "photograph", "census", "other")


@st.composite
def structured_references(draw, source_type: str) -> StructuredReference:
    """Field values of type string, integer or null, only allowed fields."""
    names = _REFERENCE_FIELDS.get(source_type, ())
    chosen = draw(st.lists(st.sampled_from(names), unique=True, max_size=len(names))
                  ) if names else []
    values = st.one_of(st.none(), st.integers(0, 9999),
                       st.text(_NAME_ALPHABET, min_size=1, max_size=12))
    return StructuredReference(fields={n: draw(values) for n in chosen})


@st.composite
def source_projects(draw) -> ProjectData:
    """Sources with type, provider, reference fields, Leverantör, Källtyp and
    repository references with call numbers; repositories are shared."""
    b = _Builder()
    _add_person(draw, b)
    repos = [Repository(
        id=f"repo_{i}", name=draw(simple_name()) + " arkiv",
        type=draw(st.sampled_from(("archive", "library", "museum"))),
        address=draw(st.one_of(st.none(), free_text(min_size=1, max_size=60))),
        phone=draw(st.lists(short_text(), max_size=2)),
        email=draw(st.lists(short_text(), max_size=2)),
        web=draw(st.lists(short_text(), max_size=2)),
        notes=draw(free_text(max_size=80)),
        external_ids=draw(st.lists(short_text(), max_size=2)),
    ) for i in range(1, draw(st.integers(1, 2)) + 1)]
    b.repositories = repos
    b.leverantorer = [Leverantor(id="lev_1", name="Leverantör", comment="")]
    b.kalltyper = [Kalltyp(id="kalltyp_1", leverantor_id="lev_1", name="Källtyp")]
    sources = []
    for i in range(1, draw(st.integers(1, 4)) + 1):
        stype = draw(st.sampled_from(_SOURCE_TYPES))
        with_lev = draw(st.booleans())
        refs = [RepositoryRef(
            repository_id=draw(st.sampled_from(repos)).id,
            call_number=draw(free_text(max_size=30)),
            source_type=draw(st.one_of(st.just(""), short_text())),
            image_number=draw(st.one_of(st.none(), st.integers(0, 999))),
            page_number=draw(st.one_of(st.none(), st.integers(0, 999))),
            media_type=draw(st.one_of(st.just(""), short_text())),
            media_name=draw(st.one_of(st.just(""), short_text())),
            notes=draw(free_text(max_size=60)),
        ) for _ in range(draw(st.integers(0, 2)))]
        sources.append(Source(
            id=f"source_{i}", provider=draw(st.one_of(st.just(""), short_text())),
            source_type=stype, title=draw(simple_name()) + f" {i}",
            reference_text=draw(free_text(max_size=60).filter(lambda s: "\n" not in s)),
            structured_reference=draw(structured_references(stype)),
            repository_refs=refs,
            leverantor_id="lev_1" if with_lev else "",
            kalltyp_id="kalltyp_1" if with_lev else "",
        ))
    b.sources = sources
    return b.build()


@st.composite
def projects(draw, free_roles: bool = False) -> ProjectData:
    """A whole project: persons, families, events, citations and residences.

    Places, sources and the repository are the fixed ones of ``synthetic``.
    """
    b = _Builder()
    for _ in range(draw(st.integers(1, 3))):
        _add_person(draw, b)
    fam = _add_family(draw, b, free_roles=free_roles,
                      children=draw(st.integers(0, 2)), parentage=True)
    _add_family_events(draw, b, fam, True)
    if draw(st.booleans()):
        _add_fallback_marriages(draw, b, True)
    _add_individual_events(draw, b, True)
    _add_residences(draw, b)
    _fix_residence_order(b)
    return b.build()
