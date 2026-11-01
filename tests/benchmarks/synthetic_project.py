"""Deterministic synthetic project generator for the performance benchmarks.

Requirement 32.9 asks for a reproducible, realistic 20,000-person project with
2,000 merge candidates so the 1 s (candidate index) and 2 s (comparison family
views) limits are measured on data that looks like a real family tree and not on
a flat list.

``generate_project(seed, persons, candidates)`` returns a normal
:class:`~slaktbusken.model.project.ProjectData`. Pure Python, no Qt, no I/O, no
files. Two calls with the same arguments give a project whose serialised form is
identical (:func:`project_sha256`).

Determinism: a private ``random.Random(seed)`` is used, but only its ``random()``
method. ``randrange``/``choice``/``shuffle`` changed between Python versions, so
integers, picks, weighted picks and the shuffle are derived here from
``random()``.

Structure (the numbers are those of the design, "Performance design"):

* generations of 25 to 30 years, starting from 120 founder couples (scaled down
  for small ``persons``); children per couple follow a skewed distribution
  (0 to 12, mean about 3.6); about 22 % of married persons have a second
  partnership; about 3 % of the couples in generations that have known
  great-grandparents are second cousins, which creates shared ancestors;
* parentage mix per child: biological 91 %, adoptive 3 %, foster 3 %, step 3 %.
  Adoptive and foster parentage is created as placement events (``adoption``,
  ``foster_home``, sometimes ``foster_home_ended``) with the derived families
  that ``sync_parentage_links`` would build; step children get a ``step`` link to
  the partner who is not their biological parent;
* every person has a birth event with a place from 300 parishes arranged as
  country, county, parish; 80 % have a death event; baptism, burial, marriage
  for couples, 0 to 3 ``flytt`` events, residence facts for 60 %, alternate names
  for 15 %, DNA profiles for 3 %, media items (no files) for 5 %; one research
  case per 100 persons;
* merge candidates: 70 % ``unreviewed``/``possible``, 10 % ``confirmed``, 12 %
  ``rejected``, 8 % disabled; roughly 10 % of the involved persons are hubs that
  appear in up to five candidates; 0 to 6 comments per candidate; 7.5 % of the
  candidates are linked to research cases; one merge history entry per 200
  persons (at most 100) so the grey path is exercised.

Persons that do not descend from a founder couple (married-in spouses, adopted
and foster children) have no biological ancestry, as in real projects.
"""

from __future__ import annotations

import hashlib
from typing import Optional

import random

from slaktbusken.model.dna import DnaCompany, DnaMatch, DnaProfile
from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.merge_candidate import (
    ArchivedCandidate,
    MergeCandidate,
    MergeCandidateComment,
    MergedIdentityMapping,
    MergeHistoryEntry,
    pair_key,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import CustomFieldDef, Place, RegionLevel
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_case import ResearchCase, ResearchEntityLink
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source, StructuredReference

DEFAULT_SEED = 20240607
DEFAULT_PERSONS = 20000
DEFAULT_CANDIDATES = 2000

_COUNTY_COUNT = 24
_PARISH_COUNT = 300

_CHILD_COUNT_WEIGHTS = (
    0.10, 0.13, 0.15, 0.15, 0.13, 0.11, 0.08, 0.06, 0.04, 0.02, 0.015, 0.0075, 0.0075,
)
_FLYTT_COUNT_WEIGHTS = (0.4, 0.3, 0.2, 0.1)

_MALE_NAMES = (
    "Anders", "Johan", "Erik", "Lars", "Per", "Olof", "Nils", "Carl", "Jonas", "Mats",
    "Hans", "Peter", "Magnus", "Gustaf", "Anton", "Sven", "Karl", "Jöns", "Daniel",
    "Mårten", "Axel", "Fredrik", "Bengt", "Pehr", "Jakob", "Samuel", "Isak", "Elof",
    "August", "Emil", "Oskar", "Gösta", "Henrik", "Ola", "Nicklas", "Abraham",
    "Ture", "Knut", "Ingvar", "Stig",
)
_FEMALE_NAMES = (
    "Anna", "Maria", "Brita", "Kajsa", "Karin", "Margareta", "Ingeborg", "Lisa",
    "Elisabeth", "Sara", "Christina", "Johanna", "Ingrid", "Greta", "Cajsa", "Eva",
    "Märta", "Emma", "Hilda", "Ulrika", "Lena", "Stina", "Sofia", "Gunilla", "Elin",
    "Hedvig", "Helena", "Anna-Lisa", "Amanda", "Selma", "Beata", "Malin", "Agneta",
    "Disa", "Frida", "Ester", "Signe", "Alma", "Britta", "Ebba",
)
_SURNAMES = (
    "Andersson", "Johansson", "Eriksson", "Larsson", "Persson", "Olsson", "Nilsson",
    "Svensson", "Karlsson", "Jonsson", "Hansson", "Pettersson", "Magnusson", "Gustafsson",
    "Mattsson", "Jakobsson", "Danielsson", "Bengtsson", "Sandberg", "Lindqvist",
    "Berg", "Lund", "Ek", "Holm", "Strand", "Nordin", "Forsberg", "Lindström", "Dahl",
    "Sjöberg", "Wikström", "Åkesson", "Ström", "Björk", "Hedlund", "Engström", "Öberg",
    "Norberg", "Blom", "Falk", "Gren", "Hellström", "Isaksson", "Kron", "Lindgren",
    "Malm", "Nyman", "Palm", "Rydén", "Sundin", "Törnqvist", "Wall", "Åberg", "Östlund",
    "Backman", "Carlén", "Edström", "Fors", "Granath", "Hägg",
)
_OCCUPATIONS = (
    "Bonde", "Dräng", "Piga", "Hemmansägare", "Skräddare", "Smed", "Soldat", "Torpare",
    "Skomakare", "Lärare", "Snickare", "Fiskare", "Handlande", "Husmor",
)
_ALIAS_GIVEN = ("Lasse", "Pelle", "Nisse", "Kalle", "Stina", "Lotta", "Greta", "Kersti")


class _Rec:
    """Mutable build state for one person."""

    __slots__ = (
        "pid", "sex", "given", "surname", "by", "place", "parents", "coupled",
        "last_child", "person",
    )

    def __init__(self, pid, sex, given, surname, by, place, parents, person):
        self.pid = pid
        self.sex = sex
        self.given = given
        self.surname = surname
        self.by = by
        self.place = place
        self.parents = parents
        self.coupled = False
        self.last_child = 0
        self.person = person


class _Couple:
    """A partnership with its family record."""

    __slots__ = ("family", "h", "w", "year", "home", "second")

    def __init__(self, family, h, w, year, home, second):
        self.family = family
        self.h = h
        self.w = w
        self.year = year
        self.home = home
        self.second = second


class _Builder:
    def __init__(self, seed: int, persons: int, candidates: int) -> None:
        self._rng = random.Random(seed)
        self.target = persons
        self.cand_target = candidates
        self._counters: dict[str, int] = {}
        self.recs: list[_Rec] = []
        self.by_id: dict[str, _Rec] = {}
        self.families: list[Family] = []
        self.events: list[Event] = []
        self.places: list[Place] = []
        self.parish_ids: list[str] = []
        self.sources: list[Source] = []
        self.cousin_couples = 0

    # -- randomness derived from random() only --------------------------------

    def u(self) -> float:
        return self._rng.random()

    def rint(self, lo: int, hi: int) -> int:
        """Inclusive integer in ``[lo, hi]``."""
        return lo + int(self.u() * (hi - lo + 1))

    def pick(self, seq):
        return seq[int(self.u() * len(seq))]

    def skew_pick(self, seq):
        """Pick favouring the front of ``seq`` (common names repeat often)."""
        x = self.u()
        return seq[int(x * x * len(seq))]

    def weighted(self, weights) -> int:
        total = sum(weights)
        x = self.u() * total
        acc = 0.0
        for index, weight in enumerate(weights):
            acc += weight
            if x < acc:
                return index
        return len(weights) - 1

    def shuffle(self, items: list) -> None:
        for i in range(len(items) - 1, 0, -1):
            j = int(self.u() * (i + 1))
            items[i], items[j] = items[j], items[i]

    def next_id(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"{prefix}{n}"

    # -- reference data -------------------------------------------------------

    def build_places(self) -> None:
        country_id = self.next_id("place_")
        self.places.append(
            Place(
                id=country_id,
                type="country",
                name="Sverige",
                region_levels=[
                    RegionLevel(
                        key="lan",
                        label="Län",
                        order=1,
                        custom_fields=[CustomFieldDef(key="code", label="Länsbokstav")],
                    ),
                    RegionLevel(key="socken", label="Socken", order=2),
                ],
            )
        )
        county_ids = []
        for i in range(_COUNTY_COUNT):
            cid = self.next_id("place_")
            county_ids.append(cid)
            self.places.append(
                Place(id=cid, type="lan", name=f"Testlän {i + 1}", parent_place_id=country_id)
            )
        per_county = _PARISH_COUNT // _COUNTY_COUNT + 1
        for i in range(_PARISH_COUNT):
            pid = self.next_id("place_")
            self.parish_ids.append(pid)
            self.places.append(
                Place(
                    id=pid,
                    type="socken",
                    name=f"Testsocken {i + 1}",
                    parent_place_id=county_ids[min(i // per_county, _COUNTY_COUNT - 1)],
                )
            )

    def build_sources(self) -> None:
        count = max(5, self.target // 130)
        for i in range(count):
            self.sources.append(
                Source(
                    id=self.next_id("source_"),
                    provider="Syntetisk",
                    source_type="church_book",
                    title=f"Kyrkobok {i + 1}",
                    structured_reference=StructuredReference(
                        fields={
                            "parish": f"Testsocken {i % _PARISH_COUNT + 1}",
                            "series": "C",
                            "volume": str(i % 9 + 1),
                            "years": "1700-1900",
                        }
                    ),
                )
            )

    def source_ref(self, place_index: int) -> SourceRef:
        source = self.sources[place_index % len(self.sources)]
        return SourceRef(source_id=source.id, quality="high" if self.u() < 0.7 else "medium")

    def nearby(self, place_index: int) -> int:
        return (place_index + self.rint(-4, 4)) % _PARISH_COUNT

    # -- people ---------------------------------------------------------------

    def full(self) -> bool:
        return len(self.recs) >= self.target

    def new_person(self, sex, surname, birth_year, place, parents) -> Optional[_Rec]:
        if self.full():
            return None
        given = self.skew_pick(_MALE_NAMES if sex == "M" else _FEMALE_NAMES)
        if surname is None:
            surname = self.skew_pick(_SURNAMES)
        pid = self.next_id("person_")
        person = Person(
            id=pid,
            sex=sex,
            names=[Name(type="birth", given=given, surname=surname)],
            occupation=self.pick(_OCCUPATIONS) if self.u() < 0.6 else None,
        )
        rec = _Rec(pid, sex, given, surname, birth_year, place, parents, person)
        self.recs.append(rec)
        self.by_id[pid] = rec
        return rec

    def outsider(self, sex: str, ref_year: int, ref_place: int) -> Optional[_Rec]:
        return self.new_person(
            sex, None, ref_year + self.rint(-4, 4), self.nearby(ref_place), []
        )

    def make_couple(self, a: _Rec, b: _Rec, year: int, second: bool = False) -> _Couple:
        h, w = (a, b) if a.sex == "M" else (b, a)
        home = h.place if self.u() < 0.6 else w.place
        marriage_id = self.next_id("event_")
        self.events.append(
            Event(
                id=marriage_id,
                type="marriage",
                participants=[
                    Participant(person_id=h.pid, role="husband"),
                    Participant(person_id=w.pid, role="wife"),
                ],
                date=self.date(year),
                place=PlaceRef(place_id=self.parish_ids[home]),
            )
        )
        family = Family(
            id=self.next_id("family_"),
            partners=[
                FamilyPartner(person_id=h.pid, role="father"),
                FamilyPartner(person_id=w.pid, role="mother"),
            ],
            children=[],
            event_ids=[marriage_id],
        )
        self.families.append(family)
        if w.surname != h.surname and self.u() < 0.6:
            w.person.names.append(
                Name(type="married", given=w.given, surname=h.surname, event_id=marriage_id)
            )
        h.coupled = True
        w.coupled = True
        return _Couple(family, h, w, year, home, second)

    def date(self, year: int, refs: Optional[list] = None) -> DateValue:
        return DateValue(
            value=f"{year:04d}-{self.rint(1, 12):02d}-{self.rint(1, 28):02d}",
            precision="day",
            source_refs=refs or [],
        )

    # -- families and children ------------------------------------------------

    def produce_children(self, couple: _Couple, pool: list[_Rec], couples: list[_Couple]) -> None:
        count = self.weighted(_CHILD_COUNT_WEIGHTS)
        if couple.second:
            count = min(count, 5)
        year = couple.year + self.rint(1, 2)
        for _ in range(count):
            if self.full():
                break
            kind_roll = self.u()
            if kind_roll < 0.91:
                kind = "biological"
            elif kind_roll < 0.94:
                kind = "adoptive"
            elif kind_roll < 0.97:
                kind = "foster"
            else:
                kind = "step"
            place = couple.home if self.u() < 0.85 else self.nearby(couple.home)
            sex = "M" if self.u() < 0.5 else "F"
            h, w = couple.h, couple.w
            if kind in ("adoptive", "foster"):
                parents: list[str] = []
            else:
                parents = [h.pid, w.pid]
            child = self.new_person(sex, h.surname, year, place, parents)
            if child is None:
                break
            pool.append(child)
            for parent in (h, w):
                parent.last_child = max(parent.last_child, year)
            if kind == "biological":
                self.link_family(couple.family, child, [(h, "biological"), (w, "biological")])
            elif kind == "step":
                bio, step = (w, h) if self.u() < 0.8 else (h, w)
                self.link_family(couple.family, child, [(bio, "biological"), (step, "step")])
            else:
                self.add_placement(couple, child, kind, year)
            year += self.rint(1, 3)

        if not couple.second:
            for partner in (couple.h, couple.w):
                if self.u() < 0.22:
                    self.second_partnership(couple, partner, couples)

    def link_family(self, family: Family, child: _Rec, parents) -> None:
        family.children.append(child.pid)
        for parent, parentage in parents:
            family.parent_child_links.append(
                ParentChildLink(child_id=child.pid, parent_id=parent.pid, parentage_type=parentage)
            )

    def second_partnership(self, couple: _Couple, partner: _Rec, couples: list[_Couple]) -> None:
        sex = "F" if partner.sex == "M" else "M"
        spouse = self.outsider(sex, partner.by, partner.place)
        if spouse is None:
            return
        year = couple.year + self.rint(12, 22)
        couples.append(self.make_couple(partner, spouse, year, second=True))

    def add_placement(self, couple: _Couple, child: _Rec, kind: str, child_year: int) -> None:
        """Placement event plus the derived family ``sync_parentage_links`` builds."""
        adoptive = kind == "adoptive"
        start_type = "adoption" if adoptive else "foster_home"
        child_role = "adopterad" if adoptive else "fosterbarn"
        parent_role = "adoptivförälder" if adoptive else "fosterförälder"
        parentage = "adoptive" if adoptive else "foster"
        parents = [couple.h, couple.w] if self.u() < 0.85 else [couple.w]
        participants = [Participant(person_id=child.pid, role=child_role)]
        participants += [Participant(person_id=p.pid, role=parent_role) for p in parents]
        start_year = child_year + (self.rint(1, 8) if adoptive else self.rint(0, 5))
        start_id = self.next_id("event_")
        self.events.append(
            Event(
                id=start_id,
                type=start_type,
                participants=participants,
                date=self.date(start_year),
                place=PlaceRef(place_id=self.parish_ids[couple.home]),
            )
        )
        event_ids = [start_id]
        if not adoptive and self.u() < 0.4:
            end_id = self.next_id("event_")
            self.events.append(
                Event(
                    id=end_id,
                    type="foster_home_ended",
                    participants=[Participant(person_id=child.pid, role=child_role)]
                    + [Participant(person_id=p.pid, role=parent_role) for p in parents],
                    date=self.date(start_year + self.rint(2, 12)),
                )
            )
            event_ids.append(end_id)
        self.families.append(
            Family(
                id=self.next_id("family_"),
                partners=[
                    FamilyPartner(person_id=p.pid, role="father" if p.sex == "M" else "mother")
                    for p in parents
                ],
                children=[child.pid],
                parent_child_links=[
                    ParentChildLink(child_id=child.pid, parent_id=p.pid, parentage_type=parentage)
                    for p in parents
                ],
                event_ids=event_ids,
            )
        )
        child.parents = [p.pid for p in parents]

    # -- pairing of the next generation ---------------------------------------

    def ancestor_levels(self, rec: _Rec):
        levels = []
        current = {rec.pid}
        for _ in range(3):
            nxt = set()
            for pid in current:
                nxt.update(self.by_id[pid].parents)
            levels.append(nxt)
            current = nxt
        return levels

    def pair(self, pool: list[_Rec]) -> list[_Couple]:
        order = list(pool)
        self.shuffle(order)
        couples: list[_Couple] = []
        cousin_index: Optional[dict[str, list[_Rec]]] = None
        for c in order:
            if c.coupled or self.u() >= 0.85:
                continue
            spouse = None
            if self.u() < 0.03:
                if cousin_index is None:
                    cousin_index = {}
                    for rec in pool:
                        for gp in self.ancestor_levels(rec)[2]:
                            cousin_index.setdefault(gp, []).append(rec)
                spouse = self.second_cousin(c, cousin_index)
                if spouse is not None:
                    self.cousin_couples += 1
            if spouse is None:
                spouse = self.outsider("F" if c.sex == "M" else "M", c.by, c.place)
            if spouse is None:
                continue
            year = max(c.by, spouse.by) + self.rint(21, 29)
            couples.append(self.make_couple(c, spouse, year))
        return couples

    def second_cousin(self, c: _Rec, index: dict[str, list[_Rec]]) -> Optional[_Rec]:
        a1, a2, a3 = self.ancestor_levels(c)
        if not a3:
            return None
        seen: set[str] = set()
        candidates: list[_Rec] = []
        for gp in sorted(a3):
            for other in index.get(gp, ()):
                if other.pid in seen:
                    continue
                seen.add(other.pid)
                if other is c or other.coupled or other.sex == c.sex:
                    continue
                b1, b2, _ = self.ancestor_levels(other)
                if a1 & b1 or a2 & b2:
                    continue
                candidates.append(other)
        return self.pick(candidates) if candidates else None

    # -- whole tree -----------------------------------------------------------

    def build_tree(self) -> None:
        founders = max(1, min(120, self.target // 166))
        couples: list[_Couple] = []
        for _ in range(founders):
            year = self.rint(1715, 1730)
            place = self.rint(0, _PARISH_COUNT - 1)
            h = self.new_person("M", None, year - self.rint(22, 30), place, [])
            w = self.new_person("F", None, year - self.rint(20, 28), self.nearby(place), []) if h else None
            if h is None or w is None:
                break
            couples.append(self.make_couple(h, w, year))
        while not self.full():
            pool: list[_Rec] = []
            i = 0
            while i < len(couples):  # second partnerships are appended while we go
                self.produce_children(couples[i], pool, couples)
                i += 1
            if pool:
                couples = self.pair(pool)
                if couples:
                    continue
            # The line died out before the budget was reached: start new founders.
            couples = []
            year = max((r.by for r in self.recs), default=1750) + self.rint(5, 20)
            place = self.rint(0, _PARISH_COUNT - 1)
            h = self.new_person("M", None, year - 25, place, [])
            w = self.new_person("F", None, year - 23, self.nearby(place), []) if h else None
            if h is not None and w is not None:
                couples.append(self.make_couple(h, w, year))

    # -- events and the rest of the per-person data ---------------------------

    def person_data(self) -> tuple[list, list, list, list, list]:
        residences: list[ResidenceFact] = []
        media: list[MediaItem] = []
        profiles: list[DnaProfile] = []
        companies = [
            DnaCompany(id=self.next_id("dna_company_"), name=name)
            for name in ("TestDNA A", "TestDNA B", "TestDNA C")
        ]
        for rec in self.recs:
            pid = rec.pid
            by = rec.by
            place_ref = PlaceRef(place_id=self.parish_ids[rec.place])
            refs = [self.source_ref(rec.place)] if self.u() < 0.5 else []
            self.events.append(
                Event(
                    id=self.next_id("event_"),
                    type="birth",
                    participants=[Participant(person_id=pid, role="principal")],
                    date=self.date(by, refs),
                    place=place_ref,
                )
            )
            if self.u() < 0.95:
                self.events.append(
                    Event(
                        id=self.next_id("event_"),
                        type="baptism",
                        participants=[Participant(person_id=pid, role="principal")],
                        date=self.date(by),
                        place=place_ref,
                    )
                )
            death_year = None
            if self.u() < 0.8:
                age = self.rint(0, 5) if self.u() < 0.1 else self.rint(30, 89)
                death_year = min(max(by + age, rec.last_child + 1), 2022)
                death_year = max(death_year, by)
                self.events.append(
                    Event(
                        id=self.next_id("event_"),
                        type="death",
                        participants=[Participant(person_id=pid, role="principal")],
                        date=self.date(death_year),
                        place=place_ref,
                    )
                )
                if self.u() < 0.9:
                    self.events.append(
                        Event(
                            id=self.next_id("event_"),
                            type="burial",
                            participants=[Participant(person_id=pid, role="principal")],
                            date=self.date(death_year),
                            place=place_ref,
                        )
                    )
            end_year = death_year if death_year is not None else by + self.rint(40, 80)
            current = rec.place
            for _ in range(self.weighted(_FLYTT_COUNT_WEIGHTS)):
                destination = self.nearby(current)
                if destination == current:
                    destination = (current + 1) % _PARISH_COUNT
                move_year = min(max(by + self.rint(16, 60), by), max(end_year, by))
                self.events.append(
                    Event(
                        id=self.next_id("event_"),
                        type="flytt",
                        participants=[Participant(person_id=pid, role="principal")],
                        date=self.date(move_year),
                        place=PlaceRef(place_id=self.parish_ids[destination]),
                        from_place=PlaceRef(place_id=self.parish_ids[current]),
                    )
                )
                current = destination
            if self.u() < 0.6:
                start = by + self.rint(0, 3)
                fact = ResidenceFact(
                    id=self.next_id("residence_"),
                    person_id=pid,
                    place_id=self.parish_ids[current],
                    start=Endpoint(earliest=str(start), latest=str(start + self.rint(0, 3)), precision="year"),
                    end=Endpoint(earliest=str(end_year - 1), latest=str(end_year), precision="year"),
                )
                if self.u() < 0.4:
                    fact.observations.append(
                        Observation(
                            source_ref=self.source_ref(current),
                            observed_from=str(start + 1),
                            observed_to=str(start + 2),
                        )
                    )
                residences.append(fact)
            if self.u() < 0.15:
                rec.person.names.append(
                    Name(type="alias", given=self.pick(_ALIAS_GIVEN), surname=rec.surname)
                )
            if self.u() < 0.03:
                profiles.append(
                    DnaProfile(
                        id=self.next_id("dna_profile_"),
                        person_id=pid,
                        company_id=self.pick(companies).id,
                        test_type=self.pick(("autosomal", "y-dna", "mtdna", "combined")),
                        kit_name=f"Kit {len(profiles) + 1}",
                    )
                )
            if self.u() < 0.05:
                n = len(media) + 1
                media.append(
                    MediaItem(
                        id=self.next_id("media_"),
                        type="photo",
                        file=f"media/synthetic_{n}.jpg",
                        title=f"Foto {n}",
                        linked_entities=[LinkedEntity(entity_type="person", entity_id=pid)],
                    )
                )
        matches: list[DnaMatch] = []
        for i in range(len(profiles) // 2):
            a = profiles[self.rint(0, len(profiles) - 1)]
            b = profiles[self.rint(0, len(profiles) - 1)]
            if a.id == b.id:
                continue
            matches.append(
                DnaMatch(
                    id=self.next_id("dna_match_"),
                    profile1_id=a.id,
                    profile2_id=b.id,
                    shared_cm=float(self.rint(20, 1800)),
                    segment_count=self.rint(1, 30),
                )
            )
        return residences, media, companies, profiles, matches

    # -- research, candidates, merge history ----------------------------------

    def build_candidates(self):
        n = self.cand_target
        buckets: dict[tuple[str, str], list[_Rec]] = {}
        for rec in self.recs:
            buckets.setdefault((rec.sex, rec.given), []).append(rec)

        hubs: list[_Rec] = []
        if n:
            hub_ids: set[str] = set()
            for _ in range(max(1, round(0.1 * 2 * n))):
                rec = self.pick(self.recs)
                if rec.pid not in hub_ids:
                    hub_ids.add(rec.pid)
                    hubs.append(rec)

        appear: dict[str, int] = {}
        seen: set[tuple[str, str]] = set()
        pairs: list[tuple[str, str]] = []
        attempts = 0
        while len(pairs) < n and attempts < n * 60 + 200:
            attempts += 1
            a = self.pick(hubs) if hubs and self.u() < 0.5 else self.pick(self.recs)
            if appear.get(a.pid, 0) >= 5:
                continue
            bucket = buckets[(a.sex, a.given)]
            if len(bucket) < 2:
                continue
            b = self.pick(bucket)
            if b is a or appear.get(b.pid, 0) >= 5 or abs(a.by - b.by) > 15:
                continue
            if b.pid in a.parents or a.pid in b.parents:
                continue
            key = pair_key(a.pid, b.pid)
            if key in seen:
                continue
            seen.add(key)
            appear[a.pid] = appear.get(a.pid, 0) + 1
            appear[b.pid] = appear.get(b.pid, 0) + 1
            pairs.append(key)

        count = len(pairs)
        n_unreviewed = round(0.35 * count)
        n_possible = round(0.35 * count)
        n_confirmed = round(0.10 * count)
        n_rejected = round(0.12 * count)
        kinds = (
            ["unreviewed"] * n_unreviewed
            + ["possible"] * n_possible
            + ["confirmed"] * n_confirmed
            + ["rejected"] * n_rejected
        )
        kinds += ["disabled"] * (count - len(kinds))
        kinds = kinds[:count]
        self.shuffle(kinds)

        n_cases = max(1, round(0.01 * self.target))
        cases = [
            ResearchCase(
                id=self.next_id("case_"),
                title=f"Forskningsfråga {i + 1}",
                status=self.pick(("open", "in_progress", "on_hold", "closed")),
                priority=self.pick(("low", "normal", "high")),
                primary_entity_ref=ResearchEntityLink("person", self.pick(self.recs).pid),
            )
            for i in range(n_cases)
        ]
        linked = min(round(0.075 * count), n_cases)
        order = list(range(count))
        self.shuffle(order)
        case_for: dict[int, ResearchCase] = {idx: cases[j] for j, idx in enumerate(order[:linked])}

        candidates: list[MergeCandidate] = []
        for i, (p1, p2) in enumerate(pairs):
            kind = kinds[i]
            enabled = kind != "disabled"
            assessment = kind if enabled else self.pick(("unreviewed", "possible"))
            comments = [
                MergeCandidateComment(
                    id=self.next_id("mergecomment_"),
                    date=f"{self.rint(2015, 2024)}-{self.rint(1, 12):02d}-{self.rint(1, 28):02d}",
                    text=f"Kommentar {j + 1}",
                )
                for j in range(self.rint(0, 6))
            ]
            case = case_for.get(i)
            if case is not None:
                case.primary_entity_ref = ResearchEntityLink("person", p1)
                case.linked_entities = [
                    ResearchEntityLink("person", p1, "candidate"),
                    ResearchEntityLink("person", p2, "candidate"),
                ]
            candidates.append(
                MergeCandidate(
                    id=self.next_id("mergecand_"),
                    person_1_id=p1,
                    person_2_id=p2,
                    assessment=assessment,
                    enabled=enabled,
                    research_case_id=case.id if case is not None else None,
                    comments=comments,
                )
            )
        return candidates, cases

    def build_history(self, candidates: list[MergeCandidate]) -> list[MergeHistoryEntry]:
        total = min(100, max(1, self.target // 200)) if self.target >= 200 else 0
        history: list[MergeHistoryEntry] = []
        for i in range(total):
            survivor = self.pick(self.recs)
            archived = []
            mappings = []
            if self.u() < 0.3:
                archived.append(
                    ArchivedCandidate(
                        id=self.next_id("mergecand_"),
                        person_1_id=survivor.pid,
                        person_2_id=f"person_{self.target + 1 + i}",
                        assessment="confirmed",
                        enabled=True,
                    )
                )
            if self.u() < 0.3:
                mappings.append(MergedIdentityMapping(gedcom_id=f"@I{900000 + i}@"))
            history.append(
                MergeHistoryEntry(
                    id=self.next_id("merge_"),
                    surviving_person_id=survivor.pid,
                    merged_person_id=f"person_{self.target + 1 + i}",
                    merged_person_name=f"{self.pick(_MALE_NAMES)} {self.pick(_SURNAMES)}",
                    merged_person_lifespan=f"{survivor.by}-{survivor.by + 60}",
                    merge_date=f"{self.rint(2018, 2024)}-{self.rint(1, 12):02d}-{self.rint(1, 28):02d}",
                    archived_candidates=archived,
                    identity_mappings=mappings,
                )
            )
        return history

    def build(self) -> ProjectData:
        self.build_places()
        self.build_sources()
        self.build_tree()
        residences, media, companies, profiles, matches = self.person_data()
        candidates, cases = self.build_candidates()
        history = self.build_history(candidates)
        return ProjectData(
            project=ProjectMetadata(
                title="Syntetiskt benchmarkprojekt",
                main_person_id=self.recs[0].pid,
            ),
            persons=[r.person for r in self.recs],
            families=self.families,
            events=self.events,
            residences=residences,
            places=self.places,
            sources=self.sources,
            media=media,
            dna_companies=companies,
            dna_profiles=profiles,
            dna_matches=matches,
            research_cases=cases,
            merge_candidates=candidates,
            merge_history=history,
        )


def generate_project(
    seed: int = DEFAULT_SEED,
    persons: int = DEFAULT_PERSONS,
    candidates: int = DEFAULT_CANDIDATES,
) -> ProjectData:
    """Build the deterministic synthetic project.

    ``persons`` is the exact number of persons. ``candidates`` is the exact number
    of merge candidates unless the project is too small to hold that many distinct
    pairs of same-named persons, in which case fewer are produced. The same
    arguments always give the same project.
    """
    if persons < 10:
        raise ValueError("persons must be at least 10")
    if candidates < 0:
        raise ValueError("candidates must not be negative")
    return _Builder(seed, persons, candidates).build()


def serialise_project(project: ProjectData) -> str:
    """The project's JSON text, exactly as it would be saved."""
    from slaktbusken.persistence.serialization import serialize

    return serialize(project)


def project_sha256(project: ProjectData) -> str:
    """SHA-256 of the serialised project, to detect generator drift."""
    return hashlib.sha256(serialise_project(project).encode("utf-8")).hexdigest()


def couples_sharing_ancestors(project: ProjectData, max_depth: int = 6) -> int:
    """Number of partner pairs in a family that share an ancestor (pedigree collapse)."""
    parents: dict[str, list[str]] = {}
    for family in project.families:
        for link in family.parent_child_links:
            if link.parent_id is not None:
                parents.setdefault(link.child_id, []).append(link.parent_id)

    def ancestors(pid: str) -> set[str]:
        found: set[str] = set()
        frontier = {pid}
        for _ in range(max_depth):
            frontier = {p for c in frontier for p in parents.get(c, ())}
            found |= frontier
        return found

    count = 0
    for family in project.families:
        if len(family.partners) == 2 and family.event_ids:
            a, b = family.partners[0].person_id, family.partners[1].person_id
            if ancestors(a) & ancestors(b):
                count += 1
    return count
