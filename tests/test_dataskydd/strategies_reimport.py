"""Generators and helpers for the re-import tests (task 10.7).

A generated file is a :class:`FileSpec`: persons and families, each owning
event records (and, for persons, ``RESI`` records). :func:`render` writes it
as GEDCOM text. Value pools are small on purpose so that identical records,
dateless events with equal type and place, and equal places occur often.

Perturbations of the second import's file are pure functions
(:func:`perturb_file`); perturbations of the project between the imports are
applied by :func:`apply_project_perturbation` through ``residence_edit_ops``
and the project service.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Optional

from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant, SourceRef
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Observation, ResidenceFact
from slaktbusken.services import residence_edit_ops as ops
from slaktbusken.services.residence_coverage import CoverageGap

# ---------------------------------------------------------------------------
# Value pools
# ---------------------------------------------------------------------------

PLACES = (
    "Ljusdal, Gävleborgs län, Sverige",
    "Hudiksvall, Gävleborgs län, Sverige",
    "Bergsjö",
)
PERSON_EVENT_TAGS = ("BIRT", "DEAT", "BAPM", "BURI", "CENS", "EVEN:Flytt", "EVEN:Yrkesbyte")
FAMILY_EVENT_TAGS = ("MARR", "DIV", "EVEN:Samboskap")
EVENT_DATES = (None, "1850", "JAN 1850", "1 JAN 1850", "ABT 1850", "BEF 1860", "BET 1850 AND 1855")
RESI_DATES = (
    None,
    "1850",
    "JAN 1850",
    "1 JAN 1850",
    "FROM 1850 TO 1860",
    "FROM 1850",
    "TO 1860",
    "BET 1850 AND 1855",
    "ABT 1850",
    "BEF 1860",
    "@#DJULIAN@ 1 JAN 1700",
    "ca midsommar 1850",
)
NOTES = (None, "Anteckning A", "Anteckning B")
SOURCES = ("@S1@", "@S2@")


@dataclass
class Rec:
    """One level-1 record of an owner (an event or a ``RESI``)."""

    tag: str                 # "BIRT", "RESI", "EVEN"
    type_name: Optional[str] = None   # TYPE of an EVEN record
    date: Optional[str] = None
    place: Optional[int] = None       # index into PLACES
    adpl: bool = False
    map_coords: bool = False
    note: Optional[str] = None
    sour: Optional[int] = None        # index into SOURCES
    uid: Optional[str] = None

    @property
    def is_residence(self) -> bool:
        return self.tag == "RESI"

    def lines(self) -> list[str]:
        out = [f"1 {self.tag}"]
        if self.type_name is not None:
            out.append(f"2 TYPE {self.type_name}")
        if self.date is not None:
            out.append(f"2 DATE {self.date}")
        if self.place is not None:
            out.append(f"2 PLAC {PLACES[self.place]}")
            if self.adpl:
                parts = [p.strip() for p in PLACES[self.place].split(",")]
                if len(parts) == 3:
                    out += [
                        "3 _ADPL",
                        f"4 _PARISH {parts[0]}",
                        f"4 _COUNTY {parts[1]}",
                        f"4 _COUNTRY {parts[2]}",
                    ]
            if self.map_coords:
                out += ["3 MAP", "4 LATI N61.8", "4 LONG E16.0"]
        if self.note is not None:
            out.append(f"2 NOTE {self.note}")
        if self.sour is not None:
            out.append(f"2 SOUR {SOURCES[self.sour]}")
        if self.uid is not None:
            out.append(f"2 _UID {self.uid}")
        return out


@dataclass
class PersonSpec:
    index: int
    records: list[Rec] = field(default_factory=list)


@dataclass
class FamilySpec:
    husband: int
    wife: int
    records: list[Rec] = field(default_factory=list)


@dataclass
class FileSpec:
    persons: list[PersonSpec]
    families: list[FamilySpec]

    def owners(self) -> list[list[Rec]]:
        return [p.records for p in self.persons] + [f.records for f in self.families]


def render(spec: FileSpec) -> str:
    lines = ["0 HEAD", "1 CHAR UTF-8"]
    for i, source in enumerate(SOURCES, start=1):
        lines += [f"0 {source} SOUR", f"1 TITL Källa {i}"]
    surnames = ("Andersson", "Persson", "Olsson", "Nilsson")
    for person in spec.persons:
        n = person.index
        lines += [
            f"0 @I{n + 1}@ INDI",
            f"1 NAME Fornamn{n} /{surnames[n % len(surnames)]}/",
            "1 SEX M" if n % 2 == 0 else "1 SEX F",
        ]
        for rec in person.records:
            lines += rec.lines()
    for k, fam in enumerate(spec.families, start=1):
        lines += [f"0 @F{k}@ FAM", f"1 HUSB @I{fam.husband + 1}@", f"1 WIFE @I{fam.wife + 1}@"]
        for rec in fam.records:
            lines += rec.lines()
    lines.append("0 TRLR")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _record(draw, tags, residence: bool = False) -> Rec:
    tag = "RESI" if residence else draw(st.sampled_from(tags))
    type_name = None
    if tag.startswith("EVEN:"):
        tag, type_name = "EVEN", tag.split(":", 1)[1]
    dates = RESI_DATES if residence else EVENT_DATES
    place = draw(st.one_of(st.none(), st.integers(0, len(PLACES) - 1)))
    return Rec(
        tag=tag,
        type_name=type_name,
        date=draw(st.sampled_from(dates)),
        place=place,
        adpl=place is not None and draw(st.booleans()),
        map_coords=place is not None and draw(st.booleans()),
        note=draw(st.sampled_from(NOTES)),
        sour=draw(st.one_of(st.none(), st.integers(0, len(SOURCES) - 1))),
        uid="" if draw(st.integers(0, 4)) == 0 else None,   # "" = wants a uid
    )


@st.composite
def _records(draw, tags, residence: bool, max_groups: int) -> list[Rec]:
    out: list[Rec] = []
    for _ in range(draw(st.integers(0, max_groups))):
        rec = draw(_record(tags, residence))
        out.extend(copy.deepcopy(rec) for _ in range(draw(st.sampled_from((1, 1, 2, 3)))))
    return out


@st.composite
def file_specs(
    draw, with_residences: bool = True, with_families: bool = True, rich: bool = False
) -> FileSpec:
    """A generated file. With *rich* the first person always owns two residences
    at one place (so that they can be merged), an event, and a second person
    exists (so that a person merge is possible)."""
    n_persons = draw(st.integers(2 if rich else 1, 4))
    persons = []
    for i in range(n_persons):
        recs = draw(_records(PERSON_EVENT_TAGS, False, 3))
        if with_residences:
            recs += draw(_records(None, True, 3))
        if rich and i == 0:
            recs += [
                Rec("BIRT", date=draw(st.sampled_from(EVENT_DATES))),
                Rec("RESI", date=draw(st.sampled_from(RESI_DATES)), place=0),
                Rec("RESI", date=draw(st.sampled_from(RESI_DATES)), place=0),
            ]
        persons.append(PersonSpec(i, recs))
    families: list[FamilySpec] = []
    if with_families and n_persons >= 2:
        for k in range(draw(st.integers(0, n_persons // 2))):
            families.append(
                FamilySpec(2 * k, 2 * k + 1, draw(_records(FAMILY_EVENT_TAGS, False, 2)))
            )
    spec = FileSpec(persons, families)
    _assign_uids(spec)
    return spec


def _assign_uids(spec: FileSpec) -> None:
    """Give every record that asked for one a uid that is unique in the file."""
    n = 0
    for owner in spec.owners():
        for rec in owner:
            if rec.uid == "":
                n += 1
                rec.uid = f"UID-{n:04d}"


@st.composite
def identical_k(draw, residence: bool) -> tuple[FileSpec, int]:
    """One person with k identical dateless same-type-and-place records."""
    k = draw(st.integers(1, 5))
    if residence:
        rec = Rec("RESI", place=draw(st.one_of(st.none(), st.integers(0, 2))),
                  note=draw(st.sampled_from(NOTES)))
    else:
        rec = Rec(draw(st.sampled_from(("BIRT", "DEAT", "BAPM"))),
                  place=draw(st.one_of(st.none(), st.integers(0, 2))),
                  note=draw(st.sampled_from(NOTES)))
    person = PersonSpec(0, [copy.deepcopy(rec) for _ in range(k)])
    return FileSpec([person], []), k


# ---------------------------------------------------------------------------
# File perturbations
# ---------------------------------------------------------------------------

FILE_PERTURBATIONS = ("none", "reorder", "remove", "insert", "change")
PROJECT_PERTURBATIONS = (
    "none",
    "edit",
    "residence_merge",
    "residence_split",
    "split_then_merge",
    "split_edit_half",
    "merge_different_records",
    "flytt_link",
    "legacy",
    "person_merge",
)
#: Perturbations after which the Canonical_Form must be equal (Property 16).
CANONICAL_EQUAL = frozenset(
    {"none", "reorder", "remove", "edit", "residence_merge", "residence_split",
     "split_then_merge", "split_edit_half", "merge_different_records", "flytt_link"}
)


def perturb_file(spec: FileSpec, kind: str, rnd: random.Random) -> tuple[FileSpec, Optional[Rec], str]:
    """Return ``(new_spec, touched_record, effective_kind)``.

    The effective kind falls back to ``none`` when the file has no record the
    perturbation could act on.
    """
    new = copy.deepcopy(spec)
    owners = [o for o in new.owners()]
    filled = [o for o in owners if o]
    if kind == "reorder" and filled:
        owner = rnd.choice(filled)
        rnd.shuffle(owner)
        return new, None, "reorder"
    if kind == "remove" and filled:
        owner = rnd.choice(filled)
        owner.pop(rnd.randrange(len(owner)))
        return new, None, "remove"
    if kind == "insert":
        persons = new.persons
        owner_is_person = not new.families or rnd.random() < 0.7
        if owner_is_person:
            owner = rnd.choice(persons).records
            rec = Rec(rnd.choice(("RESI", "BIRT", "EVEN")), note="Infogad post",
                      date=rnd.choice(("1900", None)))
            if rec.tag == "EVEN":
                rec.type_name = "Flytt"
        else:
            owner = rnd.choice(new.families).records
            rec = Rec("MARR", note="Infogad post", date=rnd.choice(("1900", None)))
        owner.insert(rnd.randrange(len(owner) + 1), rec)
        return new, rec, "insert"
    if kind == "change":
        candidates = [r for o in owners for r in o if r.uid is None]
        if candidates:
            rec = rnd.choice(candidates)
            rec.note = "Ändrad post"
            return new, rec, "change"
    return new, None, "none"


# ---------------------------------------------------------------------------
# Project perturbations (through residence_edit_ops)
# ---------------------------------------------------------------------------


def _ids(data: ProjectData) -> IDGenerator:
    used = {r.id for r in data.residences} | {e.id for e in data.events}
    return IDGenerator(used)


def _replace_residences(
    data: ProjectData, old: list[ResidenceFact], new: list[ResidenceFact]
) -> None:
    old_ids = {f.id for f in old}
    at = min(i for i, r in enumerate(data.residences) if r.id in old_ids)
    kept = [r for r in data.residences if r.id not in old_ids]
    data.residences[:] = kept[:at] + new + kept[at:]


def _observation(year: int, source_id: str) -> Observation:
    return Observation(
        source_ref=SourceRef(source_id=source_id, quality="secondary"),
        observed_from=str(year),
        observed_to=str(year + 1),
    )


def split_residence(data: ProjectData, fact: ResidenceFact) -> tuple[ResidenceFact, ResidenceFact]:
    """Add observations on both sides of a gap and split *fact* there."""
    gen = _ids(data)
    source_id = data.sources[0].id if data.sources else "source_1"
    with_obs = ops.attach_observations(fact, [_observation(1800, source_id), _observation(1850, source_id)])
    gap = CoverageGap(fact.id, 1802, 1849, "", True)
    first, second = ops.split_at_gap(
        with_obs, gap, (gen.generate("residence"), gen.generate("residence"))
    )
    _replace_residences(data, [fact], [first, second])
    return first, second


def merge_residences(
    data: ProjectData, a: ResidenceFact, b: ResidenceFact
) -> ResidenceFact:
    new_id = _ids(data).generate("residence")
    merged, _warning = ops.merge(a, b, new_id)
    _replace_residences(data, [a, b], [merged])
    return merged


def _mergeable_pairs(data: ProjectData) -> list[tuple[ResidenceFact, ResidenceFact]]:
    pairs = []
    for i, a in enumerate(data.residences):
        for b in data.residences[i + 1:]:
            if a.person_id == b.person_id and a.place_id == b.place_id:
                pairs.append((a, b))
    return pairs


def _first_hash(fact: ResidenceFact) -> Optional[str]:
    return fact.origins[0].record_hash if fact.origins else None


def apply_project_perturbation(
    world, kind: str, rnd: random.Random
) -> str:
    """Apply *kind* to ``world.data``; return the effective kind (``none`` if impossible)."""
    data = world.data
    if kind == "edit":
        edited = False
        for event in data.events[:2]:
            event.date = DateValue(value="1999-09-09", precision="day")
            edited = True
        for fact in data.residences[:2]:
            fact.role_in_household = "Inhysing"
            fact.notes = "Egen anteckning"
            edited = True
        return "edit" if edited else "none"
    if kind in ("residence_split", "split_then_merge", "split_edit_half"):
        if not data.residences:
            return "none"
        fact = rnd.choice(data.residences)
        first, second = split_residence(data, fact)
        if kind == "split_then_merge":
            merge_residences(data, first, second)
        elif kind == "split_edit_half":
            second.role_in_household = "Dräng"
            second.notes = "Redigerad efter delning"
        return kind
    if kind in ("residence_merge", "merge_different_records"):
        pairs = _mergeable_pairs(data)
        if kind == "merge_different_records":
            pairs = [p for p in pairs if _first_hash(p[0]) != _first_hash(p[1])]
        if not pairs:
            return "none"
        a, b = rnd.choice(pairs)
        merge_residences(data, a, b)
        return kind
    if kind == "flytt_link":
        by_person: dict[str, list[ResidenceFact]] = {}
        for fact in data.residences:
            by_person.setdefault(fact.person_id, []).append(fact)
        people = [p for p, facts in by_person.items() if len(facts) >= 2]
        if not people:
            return "none"
        pid = rnd.choice(people)
        a, b = by_person[pid][0], by_person[pid][1]
        flytt = next(
            (e for e in data.events
             if e.type == "flytt" and any(p.person_id == pid for p in e.participants)),
            None,
        )
        if flytt is None:
            flytt = Event(
                id=_ids(data).generate("event"),
                type="flytt",
                participants=[Participant(person_id=pid, role="subject")],
                date=DateValue(value="1855", precision="year"),
            )
            data.events.append(flytt)
        a.end.event_id = flytt.id
        b.start.event_id = flytt.id
        return kind
    if kind == "legacy":
        for event in data.events:
            event.origin = None
        for fact in data.residences:
            fact.origins = []
        return kind
    return "none"

