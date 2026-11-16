"""Generators and helpers for the Origin_Group regression tests (task 10.9).

A generated file is a list of persons whose ``RESI`` (and optional dateless
event) records come from small value pools, so identical records and records
with a ``_UID`` occur often. :func:`apply_step` applies one generated step
(split, merge, edit, save and reopen, none) through ``residence_edit_ops`` and
the project service. The module is self-contained: it does not import the
harness of the other re-import tests.
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from hypothesis import strategies as st

from slaktbusken.gedcom.importer import ImportResult
from slaktbusken.model.event import Event, SourceRef
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Observation, ResidenceFact
from slaktbusken.persistence.serialization import serialize
from slaktbusken.services import residence_edit_ops as ops
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.residence_coverage import CoverageGap
from slaktbusken.services.validation_service import ValidationService

PLACES = ("Ljusdal, Gävleborgs län, Sverige", "Bergsjö")
RESI_DATES = (None, "1850", "FROM 1850 TO 1860", "BET 1850 AND 1855", "ABT 1870")
NOTES = (None, "Anteckning A", "Anteckning B")
STEP_KINDS = ("split", "merge", "edit", "reopen", "none")

#: Markers of the two review notices that an ambiguous or unmatched record writes.
AMBIGUITY_MARKERS = ("inte kunde kopplas", "Granska och ta bort")


# ---------------------------------------------------------------------------
# World: a real project on disk and the import service
# ---------------------------------------------------------------------------


class World:
    def __init__(self, root: Path) -> None:
        self.ps = ProjectService()
        self.ps.create_project("Projekt", root)
        self.folder = self.ps.project_path.parent
        self.service = ImportService(ValidationService(), ReportService())
        self._n = 0

    @classmethod
    def from_project_file(cls, project_file: Path) -> "World":
        self = cls.__new__(cls)
        self.ps = ProjectService()
        self.ps.open_project(project_file)
        self.folder = project_file.parent
        self.service = ImportService(ValidationService(), ReportService())
        self._n = 0
        return self

    @property
    def data(self) -> ProjectData:
        return self.ps.data

    def run(self, text: str) -> ImportResult:
        self._n += 1
        path = self.folder / f"import_{self._n}.ged"
        path.write_text(text, encoding="utf-8")
        return self.service.run(self.ps.data, path, self.folder, self.ps)

    def save_and_reopen(self) -> None:
        self.ps.save_project()
        path = self.ps.project_path
        self.ps = ProjectService()
        self.ps.open_project(path)


# ---------------------------------------------------------------------------
# File specs
# ---------------------------------------------------------------------------


@dataclass
class Rec:
    tag: str                          # "RESI" or "BAPM"
    date: Optional[str] = None
    place: Optional[int] = None
    note: Optional[str] = None
    uid: Optional[str] = None         # "" = wants a uid

    def lines(self) -> list[str]:
        out = [f"1 {self.tag}"]
        if self.date is not None:
            out.append(f"2 DATE {self.date}")
        if self.place is not None:
            out.append(f"2 PLAC {PLACES[self.place]}")
        if self.note is not None:
            out.append(f"2 NOTE {self.note}")
        if self.uid:
            out.append(f"2 _UID {self.uid}")
        return out


@dataclass
class FileSpec:
    persons: list[list[Rec]] = field(default_factory=list)


def render(spec: FileSpec) -> str:
    lines = ["0 HEAD", "1 CHAR UTF-8"]
    for n, records in enumerate(spec.persons, start=1):
        lines += [f"0 @I{n}@ INDI", f"1 NAME Fornamn{n} /Testsson/", "1 SEX M"]
        for rec in records:
            lines += rec.lines()
    lines.append("0 TRLR")
    return "\n".join(lines) + "\n"


@st.composite
def _record(draw, tag: str) -> Rec:
    return Rec(
        tag=tag,
        date=draw(st.sampled_from(RESI_DATES if tag == "RESI" else (None, "1850"))),
        place=draw(st.one_of(st.none(), st.integers(0, len(PLACES) - 1))),
        note=draw(st.sampled_from(NOTES)),
        uid="" if draw(st.integers(0, 4)) == 0 else None,
    )


@st.composite
def file_specs(draw, with_events: bool = False) -> FileSpec:
    """One to three persons, each with up to three groups of one to three
    identical ``RESI`` records (and, with *with_events*, dateless ``BAPM``)."""
    persons: list[list[Rec]] = []
    for _ in range(draw(st.integers(1, 3))):
        records: list[Rec] = []
        for _ in range(draw(st.integers(1, 3))):
            rec = draw(_record("RESI"))
            records += [copy.deepcopy(rec) for _ in range(draw(st.sampled_from((1, 1, 2, 3))))]
        if with_events:
            rec = draw(_record("BAPM"))
            records += [copy.deepcopy(rec) for _ in range(draw(st.integers(1, 2)))]
        persons.append(records)
    spec = FileSpec(persons)
    n = 0
    for records in persons:
        for rec in records:
            if rec.uid == "":
                n += 1
                rec.uid = f"UID-{n:04d}"
    return spec


#: A step is (kind, a, b); a and b pick the residences by position.
steps = st.tuples(st.sampled_from(STEP_KINDS), st.integers(0, 50), st.integers(0, 50))


# ---------------------------------------------------------------------------
# Operations through residence_edit_ops and the project service
# ---------------------------------------------------------------------------


def _ids(data: ProjectData) -> IDGenerator:
    return IDGenerator({r.id for r in data.residences} | {e.id for e in data.events})


def _replace(data: ProjectData, old: list[ResidenceFact], new: list[ResidenceFact]) -> None:
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


def split_residence(
    data: ProjectData, fact: ResidenceFact, base: int = 1800
) -> tuple[ResidenceFact, ResidenceFact]:
    """Add observations on both sides of a gap and split *fact* there."""
    gen = _ids(data)
    source_id = data.sources[0].id if data.sources else "source_1"
    with_obs = ops.attach_observations(
        fact, [_observation(base, source_id), _observation(base + 50, source_id)]
    )
    gap = CoverageGap(fact.id, base + 2, base + 49, "", True)
    first, second = ops.split_at_gap(
        with_obs, gap, (gen.generate("residence"), gen.generate("residence"))
    )
    _replace(data, [fact], [first, second])
    return first, second


def merge_residences(data: ProjectData, a: ResidenceFact, b: ResidenceFact) -> ResidenceFact:
    merged, _warning = ops.merge(a, b, _ids(data).generate("residence"))
    _replace(data, [a, b], [merged])
    return merged


def apply_step(world: World, step: tuple[str, int, int], n: int) -> str:
    """Apply one step; return the effective kind (``none`` when impossible)."""
    kind, a, b = step
    data = world.data
    if kind == "split" and data.residences:
        fact = data.residences[a % len(data.residences)]
        try:
            split_residence(data, fact, base=1700 + 3 * (n % 40))
        except ops.ResidenceSplitError:
            return "none"
        world.ps.mark_changed("split")
        return "split"
    if kind == "merge":
        pairs = [
            (x, y)
            for i, x in enumerate(data.residences)
            for y in data.residences[i + 1:]
            if x.person_id == y.person_id and x.place_id == y.place_id
        ]
        if not pairs:
            return "none"
        x, y = pairs[a % len(pairs)]
        try:
            merge_residences(data, x, y)
        except ops.ResidenceMergeError:
            return "none"
        world.ps.mark_changed("merge")
        return "merge"
    if kind == "edit" and data.residences:
        fact = data.residences[a % len(data.residences)]
        fact.role_in_household = f"Roll {b}"
        fact.notes = f"Egen anteckning {b}"
        world.ps.mark_changed("edit")
        return "edit"
    if kind == "reopen":
        world.save_and_reopen()
        return "reopen"
    return "none"


def duplicate_event_origin(world: World, pick: int) -> bool:
    """Copy the origin of one imported event to a new event of the same owner
    (what a manual edit of the project file can do). False when no event exists."""
    data = world.data
    originals = [e for e in data.events if e.origin is not None]
    if not originals:
        return False
    source = originals[pick % len(originals)]
    copy_ = dataclasses.replace(
        copy.deepcopy(source), id=_ids(data).generate("event"), origin=copy.deepcopy(source.origin)
    )
    data.events.append(copy_)
    world.ps.mark_changed("duplicate event origin")
    return True


# ---------------------------------------------------------------------------
# Observations of the project before and after the re-import
# ---------------------------------------------------------------------------


def group_counts(data: ProjectData) -> dict[tuple[str, str], int]:
    """Number of Origin_Groups per (tag key, record hash), for residences and events."""
    keys: set[tuple] = set()
    for fact in data.residences:
        for o in fact.origins:
            keys.add(("residence", o.owner_kind, o.owner_id, o.tag_key, o.record_hash, o.instance, o.uid))
    for ev in data.events:
        o = ev.origin
        if o is not None:
            keys.add(("event", o.owner_kind, o.owner_id, o.tag_key, o.record_hash, o.instance, o.uid))
    counts: dict[tuple[str, str], int] = {}
    for key in keys:
        counts[(key[0] + ":" + key[3], key[4])] = counts.get((key[0] + ":" + key[3], key[4]), 0) + 1
    return counts


@dataclass
class Snapshot:
    residences: dict[str, ResidenceFact]
    events: dict[str, Event]
    canonical: dict
    groups: dict

    @classmethod
    def of(cls, data: ProjectData) -> "Snapshot":
        return cls(
            residences={r.id: copy.deepcopy(r) for r in data.residences},
            events={e.id: copy.deepcopy(e) for e in data.events},
            canonical=serialize(data),
            groups=group_counts(data),
        )


def assert_import_changes_nothing(world: World, text: str, before: Optional[Snapshot] = None) -> None:
    """Re-import *text*; nothing is created, deleted or modified."""
    before = before or Snapshot.of(world.data)
    result = world.run(text)
    data = world.data
    assert result.residences_added == 0 and result.events_added == 0
    assert set(before.residences) == {r.id for r in data.residences}, "residence set changed"
    assert set(before.events) == {e.id for e in data.events}, "event set changed"
    for r in data.residences:
        assert r == before.residences[r.id], f"residence {r.id} was modified"
    for e in data.events:
        assert e == before.events[e.id], f"event {e.id} was modified"
    assert serialize(data) == before.canonical, "Canonical_Form changed"
    assert group_counts(data) == before.groups, "Origin_Group count changed"
    notices = [w for w in result.warnings if any(m in str(w) for m in AMBIGUITY_MARKERS)]
    assert not notices, f"ambiguity notice in the Import_Log: {notices}"
