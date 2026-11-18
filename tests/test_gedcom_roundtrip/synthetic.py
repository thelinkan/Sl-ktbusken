"""Synthetic project that reproduces the shape of ``MergeTest.json``.

The mandatory round-trip tests must stay meaningful when the fixture files
change, so this module builds the same shapes from code (design "Testing
Strategy", module ``synthetic.py``). Persons are fictive.

Shapes covered (task 1.3):

* a heterosexual family with children, a listed marriage, a divorce and
  married-name links to the marriage event;
* same-sex families ``M``+``M`` and ``F``+``F``;
* a partner with sex ``U`` and a partner with sex ``X``;
* partners with the roles ``make``/``maka`` and ``partner``;
* a one-partner family;
* a foster family (``PEDI foster`` links and a ``foster_home`` placement
  with its paired end event, which exports as ``EVEN Fosterhem`` with
  ``FAMC``);
* an orphan marriage that matches exactly one family, and two orphan
  marriages that match no family and share date and place (Individual
  Fallback);
* citations in every context (event, date, place, from_place) with aspects
  and every quality;
* residences with exact, windowed and one-sided endpoints, endpoint event
  links and observations;
* one repository shared by two sources.

``make`` and ``maka`` are not members of the roles that ``validate_family``
accepts (``father``, ``mother``, ``husband``, ``wife``, ``partner``). The
default project is valid and uses accepted roles. Passing ``free_roles=True``
writes ``make`` and ``maka`` literally, for tests that bypass validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place, RegionLevel
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

# Every quality the exporter must keep: the three QUAY-mapped values and one
# free text that only ``_SLK_QUAL`` can carry.
QUALITIES: tuple[str, ...] = ("primary", "secondary", "tertiary", "osäker")

# Place ids of the fixed hierarchy.
PLACE_EUROPE = "place_1"
PLACE_SWEDEN = "place_2"
PLACE_COUNTY = "place_3"
PLACE_LJUSDAL = "place_4"
PLACE_GAVLE = "place_5"
PLACE_BOLLNAS = "place_6"
PLACE_CHURCH = "place_7"

# Source ids.
SOURCE_HFL = "source_1"
SOURCE_DOP = "source_2"
SOURCE_DB = "source_3"
SOURCE_NEWS = "source_4"
SOURCE_OTHER = "source_5"

REPOSITORY_ID = "repo_1"


def date_value(value: str, qualifier: str = "exact", **kw) -> DateValue:
    """A valid ``DateValue``; the precision follows the length of *value*."""
    if "precision" not in kw:
        if qualifier == "exact":
            kw["precision"] = {4: "year", 7: "month", 10: "day"}[len(value)]
        else:
            kw["precision"] = "approximate"
    return DateValue(value=value, qualifier=qualifier, **kw)


def source_ref(source_id: str, quality: str = "secondary", **kw) -> SourceRef:
    return SourceRef(source_id=source_id, quality=quality, **kw)


def build_places() -> list[Place]:
    """Continent, country with two region levels, county, parishes, church."""
    return [
        Place(id=PLACE_EUROPE, type="continent", name="Europa"),
        Place(
            id=PLACE_SWEDEN, type="country", name="Sverige",
            parent_place_id=PLACE_EUROPE,
            region_levels=[
                RegionLevel(key="lan", label="Län", order=1),
                RegionLevel(key="socken", label="Socken", order=2),
            ],
        ),
        Place(id=PLACE_COUNTY, type="lan", name="Gävleborgs län",
              parent_place_id=PLACE_SWEDEN),
        Place(id=PLACE_LJUSDAL, type="socken", name="Ljusdal",
              parent_place_id=PLACE_COUNTY),
        Place(id=PLACE_GAVLE, type="socken", name="Gävle",
              parent_place_id=PLACE_COUNTY),
        Place(id=PLACE_BOLLNAS, type="socken", name="Bollnäs",
              parent_place_id=PLACE_COUNTY),
        Place(id=PLACE_CHURCH, type="church", name="Ljusdals kyrka",
              parent_place_id=PLACE_LJUSDAL),
    ]


def build_repositories() -> list[Repository]:
    return [
        Repository(
            id=REPOSITORY_ID,
            name="Härnösands landsarkiv",
            type="archive",
            address="Arkivgatan 1, 871 45 Härnösand",
            phone=["0611-000000", "0611-000001"],
            email=["arkiv@example.org"],
            web=["https://example.org/arkiv"],
            notes="Fiktivt arkiv.\nAndra raden.",
            external_ids=["SE/HLA", "Q12345"],
        )
    ]


def build_sources() -> tuple[list[Source], list[Leverantor], list[Kalltyp]]:
    """Five sources; ``source_1`` and ``source_2`` share one repository."""
    leverantorer = [Leverantor(id="lev_1", name="Arkiv Digital", comment="")]
    kalltyper = [
        Kalltyp(id="kalltyp_1", leverantor_id="lev_1", name="Husförhörslängd")
    ]
    sources = [
        Source(
            id=SOURCE_HFL, provider="Arkiv Digital", source_type="church_book",
            title="Ljusdal AI:12 (1840-1850)",
            reference_text="Ljusdal AI:12 (1840-1850) Bild 12",
            structured_reference=StructuredReference(fields={
                "parish": "Ljusdal", "series": "AI", "volume": "12",
                "years": "1840-1850", "image": 12, "page": None,
            }),
            repository_refs=[RepositoryRef(
                repository_id=REPOSITORY_ID, call_number="SE/HLA/1234",
                source_type="mikrofilm", image_number=12, page_number=None,
                media_type="microfilm", media_name="Rulle 7",
                notes="Läsbar.",
            )],
            leverantor_id="lev_1", kalltyp_id="kalltyp_1",
        ),
        Source(
            id=SOURCE_DOP, provider="Arkiv Digital", source_type="church_book",
            title="Ljusdal CI:4 (1845-1855)",
            reference_text="Ljusdal CI:4 (1845-1855) Bild 3",
            structured_reference=StructuredReference(fields={
                "parish": "Ljusdal", "series": "CI", "volume": "4",
                "years": "1845-1855", "image": 3, "page": "17",
            }),
            repository_refs=[RepositoryRef(
                repository_id=REPOSITORY_ID, call_number="SE/HLA/5678",
                media_type="microfilm",
            )],
        ),
        Source(
            id=SOURCE_DB, provider="Sveriges släktforskarförbund",
            source_type="database", title="Sveriges dödbok",
            structured_reference=StructuredReference(fields={
                "database_name": "Sveriges dödbok", "record_id": "42",
            }),
        ),
        Source(
            id=SOURCE_NEWS, provider="", source_type="newspaper",
            title="Ljusdals Tidning 1920-06-25",
            structured_reference=StructuredReference(fields={
                "newspaper": "Ljusdals Tidning", "date": "1920-06-25",
                "page": 3, "article_title": None,
            }),
        ),
        Source(
            id=SOURCE_OTHER, provider="", source_type="other",
            title="Släktbok", reference_text="Egen släktbok",
        ),
    ]
    return sources, leverantorer, kalltyper


@dataclass
class _Ids:
    """Hands out ``prefix_N`` ids in order."""

    counters: dict[str, int] = field(default_factory=dict)

    def next(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}_{n}"


def _person(ids: _Ids, persons: list[Person], sex: str, given: str, surname: str,
            **kw) -> str:
    pid = ids.next("person")
    names = kw.pop("names", None) or [Name("birth", given, surname)]
    persons.append(Person(id=pid, sex=sex, names=names, **kw))
    return pid


def _event(ids: _Ids, events: list[Event], type_: str, people: list[tuple[str, str]],
           date: Optional[DateValue] = None, **kw) -> str:
    eid = ids.next("event")
    events.append(Event(
        id=eid, type=type_,
        participants=[Participant(person_id=p, role=r) for p, r in people],
        date=date, **kw,
    ))
    return eid


def build_synthetic_project(*, free_roles: bool = False) -> ProjectData:
    """Build the synthetic project. See the module docstring for the shapes.

    With ``free_roles=True`` the couple ``Sara``/``Nils`` has the roles
    ``make`` and ``maka``; otherwise both are ``partner``.
    """
    ids = _Ids()
    persons: list[Person] = []
    events: list[Event] = []
    families: list[Family] = []

    sources, leverantorer, kalltyper = build_sources()

    # -- persons -----------------------------------------------------------
    johan = _person(ids, persons, "M", "Johan", "Andersson",
                    title="Fil.Dr", occupation="Lektor",
                    notes="Född i Ljusdal.\nFlyttade 1860.\n@hemma med mellanslag  ")
    anna = _person(ids, persons, "F", "Anna", "Berg", names=[
        Name("birth", "Anna", "Berg"),
        Name("alias", "Anna", "Berg-Andersson"),
    ])
    karl = _person(ids, persons, "M", "Karl", "Andersson")
    erik = _person(ids, persons, "M", "Erik", "Lund")
    olof = _person(ids, persons, "M", "Olof", "Strand")
    maria = _person(ids, persons, "F", "Maria", "Ek")
    eva = _person(ids, persons, "F", "Eva", "Dal")
    kim = _person(ids, persons, "U", "Kim", "Sand")
    lisa = _person(ids, persons, "F", "Lisa", "Sand")
    alex = _person(ids, persons, "X", "Alex", "Vik")
    bo = _person(ids, persons, "M", "Bo", "Vik")
    sara = _person(ids, persons, "F", "Sara", "Holm")
    nils = _person(ids, persons, "M", "Nils", "Holm")
    hugo = _person(ids, persons, "M", "Hugo", "Hed")
    robin = _person(ids, persons, "U", "Robin", "Hed")
    ida = _person(ids, persons, "F", "Ida", "Ahl")
    ivar = _person(ids, persons, "M", "Ivar", "Ahl")
    gustav = _person(ids, persons, "M", "Gustav", "Ljung")
    hilda = _person(ids, persons, "F", "Hilda", "Ljung")
    elin = _person(ids, persons, "F", "Elin", "Nord", names=[
        Name("birth", "Elin", "Nord"), Name("adopted", "Elin", "Ljung"),
        Name("other", "Lina", "Nord"),
    ])
    y1a = _person(ids, persons, "M", "Axel", "Ros")
    y1b = _person(ids, persons, "F", "Britta", "Ros")
    y2a = _person(ids, persons, "M", "Carl", "Fors")
    y2b = _person(ids, persons, "F", "Disa", "Fors")

    # -- events of the heterosexual family --------------------------------
    marriage = _event(
        ids, events, "marriage",
        [(johan, "spouse"), (anna, "spouse")],
        date_value("1848-05-14", source_refs=[
            source_ref(SOURCE_DOP, "primary", note="Vigselbok", aspects=["datum"]),
        ]),
        place=PlaceRef(PLACE_CHURCH, [source_ref(SOURCE_HFL, "tertiary")]),
        source_refs=[source_ref(SOURCE_HFL, "secondary", note="Lysning")],
    )
    divorce = _event(ids, events, "divorce", [(johan, "spouse"), (anna, "spouse")],
                     date_value("1870"))
    # Married name linked to the marriage event.
    next(p for p in persons if p.id == anna).names.append(
        Name("married", "Anna", "Andersson", event_id=marriage))

    birth_karl = _event(
        ids, events, "birth", [(karl, "subject")],
        date_value("1850-03-04", source_refs=[
            source_ref(SOURCE_DOP, "primary", note="s. 4", aspects=["datum", "dag"]),
            source_ref(SOURCE_HFL, "osäker"),
        ]),
        place=PlaceRef(PLACE_LJUSDAL, [source_ref(SOURCE_HFL, "tertiary",
                                                  aspects=["ort"])]),
        source_refs=[source_ref(SOURCE_DOP, "primary", note="födelsepost")],
    )
    _event(ids, events, "birth", [(elin, "subject")], date_value("1852"),
           place=PlaceRef(PLACE_GAVLE))
    _event(ids, events, "baptism", [(karl, "subject"), (erik, "godfather")],
           date_value("1850-03-10"), place=PlaceRef(PLACE_CHURCH))
    _event(ids, events, "death", [(johan, "subject")],
           date_value("1920-06-21", source_refs=[source_ref(SOURCE_NEWS, "secondary")]),
           place=PlaceRef(PLACE_LJUSDAL),
           source_refs=[source_ref(SOURCE_DB, "primary")],
           cause_of_death="Ålderdom")
    _event(ids, events, "burial", [(johan, "subject")], date_value("1920-06-28"))
    _event(ids, events, "confirmation", [(karl, "subject")], date_value("1865"))
    _event(ids, events, "will", [(johan, "subject")], date_value("1915-02"))
    _event(ids, events, "blessing", [(karl, "subject")], date_value("1850"))
    _event(ids, events, "first_communion", [(karl, "subject")], date_value("1864"))
    _event(ids, events, "census", [(johan, "subject")],
           date_value("1851", "about"), source_refs=[source_ref(SOURCE_HFL)])
    _event(ids, events, "custom_individual_event", [(karl, "subject")],
           date_value("1862"), custom_type_name="Skolgång")
    flytt = _event(
        ids, events, "flytt", [(johan, "subject")], date_value("1860-05-01"),
        place=PlaceRef(PLACE_GAVLE, [source_ref(SOURCE_HFL, "secondary")]),
        from_place=PlaceRef(PLACE_LJUSDAL, [source_ref(SOURCE_DOP, "primary")]),
        source_refs=[source_ref(SOURCE_OTHER, "tertiary")],
    )
    flytt_back = _event(
        ids, events, "flytt", [(johan, "subject")], date_value("1872-10"),
        place=PlaceRef(PLACE_LJUSDAL), from_place=PlaceRef(PLACE_GAVLE),
    )

    # -- families ----------------------------------------------------------
    families.append(Family(
        id=ids.next("family"),
        partners=[FamilyPartner(johan, "husband"), FamilyPartner(anna, "wife")],
        children=[karl, elin],
        parent_child_links=[
            ParentChildLink(karl, johan, "biological"),
            ParentChildLink(karl, anna, "biological"),
            ParentChildLink(elin, johan, "biological"),
            ParentChildLink(elin, anna, "biological"),
        ],
        event_ids=[marriage, divorce],
    ))
    engagement_mm = _event(ids, events, "engagement",
                           [(erik, "spouse"), (olof, "spouse")], date_value("1999"))
    families.append(Family(
        id=ids.next("family"),
        partners=[FamilyPartner(erik, "husband"), FamilyPartner(olof, "husband")],
        children=[], event_ids=[engagement_mm],
    ))
    custom_ff = _event(ids, events, "custom_family_event",
                       [(maria, "spouse"), (eva, "spouse")], date_value("2005-08"),
                       custom_type_name="Samboavtal")
    families.append(Family(
        id=ids.next("family"),
        partners=[FamilyPartner(maria, "wife"), FamilyPartner(eva, "wife")],
        children=[], event_ids=[custom_ff],
    ))
    families.append(Family(  # partner of sex U (Kim) next to F (Lisa)
        id=ids.next("family"),
        partners=[FamilyPartner(kim, "partner"), FamilyPartner(lisa, "partner")],
        children=[], event_ids=[],
    ))
    families.append(Family(  # partner of sex X
        id=ids.next("family"),
        partners=[FamilyPartner(alex, "partner"), FamilyPartner(bo, "husband")],
        children=[], event_ids=[],
    ))
    role_a, role_b = ("make", "maka") if free_roles else ("partner", "partner")
    families.append(Family(  # F+M in the order F, M; roles make/maka
        id=ids.next("family"),
        partners=[FamilyPartner(sara, role_a), FamilyPartner(nils, role_b)],
        children=[], event_ids=[],
    ))
    families.append(Family(  # M+U, role partner for both
        id=ids.next("family"),
        partners=[FamilyPartner(hugo, "partner"), FamilyPartner(robin, "partner")],
        children=[], event_ids=[],
    ))
    families.append(Family(  # one partner
        id=ids.next("family"),
        partners=[FamilyPartner(ida, "mother")], children=[], event_ids=[],
    ))
    families.append(Family(  # M, F in list order (Ida also heads a one-partner family)
        id=ids.next("family"),
        partners=[FamilyPartner(ivar, "father"), FamilyPartner(ida, "mother")],
        children=[], event_ids=[],
    ))

    # Orphan marriage that matches exactly one family (Sara + Nils).
    _event(ids, events, "marriage", [(sara, "spouse"), (nils, "spouse")],
           date_value("1901-07-07"), place=PlaceRef(PLACE_BOLLNAS))
    # Two orphan marriages that match no family and share date and place.
    shared_date = "1900-06-15"
    for a, b in ((y1a, y1b), (y2a, y2b)):
        _event(ids, events, "marriage", [(a, "spouse"), (b, "spouse")],
               date_value(shared_date, source_refs=[source_ref(SOURCE_HFL, "primary")]),
               place=PlaceRef(PLACE_LJUSDAL))

    # Foster family: PEDI foster links and a placement with its paired end.
    foster_start = _event(
        ids, events, "foster_home",
        [(elin, "fosterbarn"), (gustav, "fosterförälder"), (hilda, "fosterförälder")],
        date_value("1858-01-01"), place=PlaceRef(PLACE_BOLLNAS),
    )
    foster_end = _event(
        ids, events, "foster_home_ended",
        [(elin, "fosterbarn"), (gustav, "fosterförälder"), (hilda, "fosterförälder")],
        date_value("1866-01-01"),
    )
    families.append(Family(
        id=ids.next("family"),
        partners=[FamilyPartner(gustav, "husband"), FamilyPartner(hilda, "wife")],
        children=[elin],
        parent_child_links=[
            ParentChildLink(elin, gustav, "foster"),
            ParentChildLink(elin, hilda, "foster"),
        ],
        event_ids=[foster_start, foster_end],
    ))

    # -- residences ---------------------------------------------------------
    residences = [
        ResidenceFact(
            id="residence_1", person_id=johan, place_id=PLACE_LJUSDAL,
            start=Endpoint(earliest="1850", latest="1850-06", precision="year",
                           note="Från födseln"),
            end=Endpoint(earliest="1860-04", latest="1860-05-01", precision="month",
                         event_id=flytt),
            role_in_household="Dräng",
            observations=[
                Observation(source_ref(SOURCE_HFL, "primary", note="rad 4",
                                       aspects=["namn", "ålder"]),
                            "1855", "1858", "s. 12"),
                Observation(source_ref(SOURCE_DOP, "osäker"), "1859", "", ""),
            ],
            notes="Egen anteckning.\nAndra raden.",
        ),
        ResidenceFact(
            id="residence_2", person_id=johan, place_id=PLACE_GAVLE,
            start=Endpoint(earliest="1860-04", latest="1860-05-01", precision="month",
                           event_id=flytt),
            end=Endpoint(earliest="1872", latest="1872-10", precision="approximate",
                         event_id=flytt_back),
            observations=[Observation(source_ref(SOURCE_HFL, "tertiary"),
                                      "1865", "1868", "")],
        ),
        ResidenceFact(  # exact endpoint, one-sided end
            id="residence_3", person_id=karl, place_id=PLACE_BOLLNAS,
            start=Endpoint(earliest="1872-10-05", latest="1872-10-05", precision="day"),
            end=Endpoint(),
        ),
        ResidenceFact(  # only a latest bound on the start
            id="residence_4", person_id=anna, place_id=PLACE_LJUSDAL,
            start=Endpoint(latest="1848"),
            end=Endpoint(earliest="1870"),
            role_in_household="Hustru",
        ),
    ]

    return ProjectData(
        project=ProjectMetadata(title="Syntetiskt projekt", main_person_id=johan),
        persons=persons, families=families, events=events,
        residences=residences, places=build_places(),
        sources=sources, repositories=build_repositories(),
        leverantorer=leverantorer, kalltyper=kalltyper,
    )
