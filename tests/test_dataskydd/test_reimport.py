"""Repeated GEDCOM import of events and residences (Requirements 10 and 22).

Property 16 and Property 17 of the data-integrity-0-3-0 design plus the
example tests of Requirement 10.16. Every test imports through
``ImportService.run`` into a real project on disk, so the second import reads
the Pending_Translation or the saved translation files exactly as the
application does.

**Validates: Requirements 10.1 to 10.15, 22.10 to 22.15**
"""

from __future__ import annotations

import copy
import dataclasses
import random
import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from slaktbusken.gedcom.importer import ImportResult
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.serialization import serialize
from slaktbusken.persistence.translation_io import (
    PersonMapping,
    PlaceMapping,
    SourceMapping,
    TranslationData,
    read_all,
    write_all,
)
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService
from tests.test_dataskydd import strategies_reimport as sr
from tests.test_dataskydd.strategies_reimport import FileSpec

pytestmark = pytest.mark.mandatory_integrity

FIXTURE_V0_4 = Path(__file__).resolve().parents[1] / "fixtures" / "project_v0_4.json.gz"

_PROPERTY_SETTINGS = dict(
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class World:
    """A real project on disk and the service that imports into it."""

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

    def run_spec(self, spec: FileSpec) -> ImportResult:
        return self.run(sr.render(spec))

    def save(self) -> None:
        self.ps.save_project()

    def save_and_reopen(self) -> None:
        self.ps.save_project()
        path = self.ps.project_path
        self.ps = ProjectService()
        self.ps.open_project(path)

    def merge_persons(self) -> bool:
        """Merge the persons imported from ``@I2@`` into ``@I1@``; False when refused."""
        self.save()
        translation = read_all(self.folder / "translation")
        by_xref = {m.gedcom_id: m.app_id for m in translation.persons}
        if "@I1@" not in by_xref or "@I2@" not in by_xref:
            return False
        survivor, retired = by_xref["@I1@"], by_xref["@I2@"]
        kept = next(p for p in self.data.persons if p.id == survivor)
        name = kept.names[0]
        decisions = MergeDecisions(
            survivor,
            retired,
            survivor_id=survivor,
            survivor_confirmed=True,
            sex=kept.sex,
            primary_name=(name.given, name.surname, name.type, getattr(name, "event_id", None)),
        )
        plan = build_plan(self.data, translation, decisions, self.ps.content_revision)
        if not plan.can_execute:
            return False
        return MergeEngine(self.ps, None).execute(plan).success


@dataclasses.dataclass
class Snapshot:
    events: dict
    residences: dict
    family_event_ids: dict
    canonical: dict

    @classmethod
    def of(cls, data: ProjectData) -> "Snapshot":
        return cls(
            events={e.id: copy.deepcopy(e) for e in data.events},
            residences={r.id: copy.deepcopy(r) for r in data.residences},
            family_event_ids={f.id: list(f.event_ids) for f in data.families},
            canonical=serialize(data),
        )


def assert_nothing_lost_or_rewritten(
    before: Snapshot, data: ProjectData, legacy: bool = False
) -> None:
    """Sets only grow; every earlier object is equal to itself afterwards.

    With *legacy* the only allowed difference is an origin added to an object
    that had none.
    """
    after_events = {e.id: e for e in data.events}
    after_res = {r.id: r for r in data.residences}
    assert set(before.events) <= set(after_events), "an event was removed"
    assert set(before.residences) <= set(after_res), "a residence was removed"
    for event_id, old in before.events.items():
        new = after_events[event_id]
        if legacy and old.origin is None:
            new = dataclasses.replace(new, origin=None)
        assert new == old, f"event {event_id} was rewritten"
    for res_id, old in before.residences.items():
        new = after_res[res_id]
        if legacy and not old.origins:
            new = dataclasses.replace(new, origins=[])
        assert new == old, f"residence {res_id} was rewritten"
    families = {f.id: f for f in data.families}
    for family_id, ids in before.family_event_ids.items():
        assert set(ids) <= set(families[family_id].event_ids), "Family.event_ids lost an id"


def ged(*lines: str) -> str:
    """A GEDCOM file with sources @S1@ and @S2@ and the given body lines."""
    head = ["0 HEAD", "1 CHAR UTF-8"]
    for i in (1, 2):
        head += [f"0 @S{i}@ SOUR", f"1 TITL Källa {i}"]
    return "\n".join(head + list(lines) + ["0 TRLR"]) + "\n"


def person(n: int = 1, *body: str) -> list[str]:
    return [f"0 @I{n}@ INDI", f"1 NAME Fornamn{n} /Testsson/", "1 SEX M", *body]


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def _with_world(fn):
    """Run ``fn(world)`` in a fresh project directory (for property tests)."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        return fn(World(Path(tmp)))


# ---------------------------------------------------------------------------
# Property 16
# ---------------------------------------------------------------------------

_PERTURBATIONS = (
    ["none"]
    + [f"file:{k}" for k in sr.FILE_PERTURBATIONS if k != "none"]
    + [f"project:{k}" for k in sr.PROJECT_PERTURBATIONS if k != "none"]
)


def _run_property_16(
    world: World, spec: FileSpec, perturbation: str, reopen: bool, rnd: random.Random
) -> None:
    world.run_spec(spec)
    first = Snapshot.of(world.data)

    scope, _, name = perturbation.partition(":")
    second_spec, touched, effective = spec, None, "none"
    merged_persons = False
    if scope == "file":
        second_spec, touched, effective = sr.perturb_file(spec, name, rnd)
    elif scope == "project":
        if name == "person_merge":
            if len(spec.persons) >= 2 and world.merge_persons():
                effective, merged_persons = name, True
        else:
            effective = sr.apply_project_perturbation(world, name, rnd)
    if reopen:
        world.save_and_reopen()

    event(f"effective: {effective}")
    before = Snapshot.of(world.data)
    result = world.run_spec(second_spec)
    data = world.data

    assert_nothing_lost_or_rewritten(before, data, legacy=effective == "legacy")
    assert_nothing_lost_or_rewritten(
        dataclasses.replace(before, events={}, residences={}), data
    )

    new_events = len(data.events) - len(before.events)
    new_residences = len(data.residences) - len(before.residences)
    if effective in sr.CANONICAL_EQUAL:
        assert serialize(data) == before.canonical, "Canonical_Form changed"
        assert (new_events, new_residences) == (0, 0)
    if effective == "insert":
        expected = (0, 1) if touched.is_residence else (1, 0)
        assert (new_events, new_residences) == expected
    if effective == "change":
        expected = (0, 1) if touched.is_residence else (1, 0)
        assert (new_events, new_residences) == expected
        assert any("Granska och ta bort det som är inaktuellt" in w for w in result.warnings)
    if merged_persons:
        # A Merged_Identity_Record creates no event and no residence.
        assert (new_events, new_residences) == (0, 0)
    if effective == "legacy":
        # Every object that was re-imported exactly is claimed; none is removed.
        assert len(data.events) >= len(first.events)


@pytest.mark.parametrize("reopen", [False, True], ids=["same_session", "save_and_reopen"])
@pytest.mark.parametrize("perturbation", _PERTURBATIONS)
@settings(max_examples=20, **_PROPERTY_SETTINGS)
@given(spec=sr.file_specs(rich=True), rnd=st.randoms(use_true_random=False))
def test_dp_property_16_repeated_import_is_stable(spec, rnd, perturbation, reopen) -> None:
    """Feature: data-integrity-0-3-0, Property 16: Repeated import is stable and
    never removes, merges, duplicates or silently rewrites events and residences.

    **Validates: Requirements 10.2, 10.4, 10.5, 10.6, 10.7, 10.9, 10.10, 10.14,
    10.15, 19.8, 22.7, 22.10, 22.11, 22.12, 22.13, 22.15, 22.20, 22.21, 22.23,
    22.24, 22.25, 22.27, 22.28, 22.29, 22.32**
    """
    _with_world(lambda w: _run_property_16(w, spec, perturbation, reopen, rnd))


# ---------------------------------------------------------------------------
# Property 17
# ---------------------------------------------------------------------------


@settings(max_examples=40, **_PROPERTY_SETTINGS)
@given(case=sr.identical_k(residence=False), later_imports=st.integers(1, 3))
def test_dp_property_17_dateless_events_stay_distinct(case, later_imports) -> None:
    """Feature: data-integrity-0-3-0, Property 17: Dateless events and identical
    residence records stay distinct.

    **Validates: Requirements 10.1, 10.3, 22.14, 22.28**
    """
    spec, k = case

    def body(world: World) -> None:
        assert world.run_spec(spec).events_added == k
        assert len(world.data.events) == k
        before = Snapshot.of(world.data)
        for _ in range(later_imports):
            assert world.run_spec(spec).events_added == 0
        assert Snapshot.of(world.data).events == before.events

    _with_world(body)


@settings(max_examples=40, **_PROPERTY_SETTINGS)
@given(
    case=sr.identical_k(residence=True),
    later_imports=st.integers(1, 2),
    split_one=st.booleans(),
    rnd=st.randoms(use_true_random=False),
)
def test_dp_property_17_identical_residence_records_stay_distinct(
    case, later_imports, split_one, rnd
) -> None:
    """Property 17 for residences, also after one of the k residences was split.

    **Validates: Requirements 22.14, 22.28**
    """
    spec, k = case

    def body(world: World) -> None:
        assert world.run_spec(spec).residences_added == k
        assert len(world.data.residences) == k
        if split_one:
            sr.split_residence(world.data, rnd.choice(world.data.residences))
        expected = len(world.data.residences)
        before = Snapshot.of(world.data)
        for _ in range(later_imports):
            assert world.run_spec(spec).residences_added == 0
        assert len(world.data.residences) == expected
        assert_nothing_lost_or_rewritten(before, world.data)
        assert serialize(world.data) == before.canonical

    _with_world(body)


# ---------------------------------------------------------------------------
# Example tests (Requirement 10.16)
# ---------------------------------------------------------------------------

THREE_DATELESS = ged(
    *person(
        1,
        "1 EVEN", "2 TYPE Flytt", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
        "1 EVEN", "2 TYPE Flytt", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
        "1 EVEN", "2 TYPE Flytt", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
    )
)

FULL = ged(
    *person(
        1,
        "1 BIRT", "2 DATE 1 JAN 1850", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
        "1 DEAT", "2 DATE 5 MAR 1920",
        "1 RESI", "2 DATE FROM 1850 TO 1860", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
    ),
    *person(2, "1 BIRT", "2 DATE 3 FEB 1852"),
    "0 @F1@ FAM", "1 HUSB @I1@", "1 WIFE @I2@",
    "1 MARR", "2 DATE 15 MAY 1875", "1 DIV", "2 DATE 1 JAN 1890",
)


def test_dateless_same_type_place_events_stay_distinct(world: World) -> None:
    """B10: three dateless events of equal type and place were collapsed to one."""
    first = world.run(THREE_DATELESS)
    assert first.events_added == 3
    flytt = [e for e in world.data.events if e.type == "flytt"]
    assert len(flytt) == 3
    assert len({e.origin.instance for e in flytt}) == 3  # distinct Origin_Keys
    again = world.run(THREE_DATELESS)
    assert again.events_added == 0
    assert [e.id for e in world.data.events] == [e.id for e in flytt]
    # Family events with the same type and place stay distinct too.
    fam = ged(
        *person(1), *person(2), "0 @F1@ FAM", "1 HUSB @I1@", "1 WIFE @I2@",
        "1 MARR", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
        "1 MARR", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
    )
    w2 = World(world.folder.parent / "fam")
    assert w2.run(fam).events_added == 2
    assert w2.run(fam).events_added == 0


def test_b10_reproduction_second_import_never_merges_or_drops(world: World) -> None:
    """Headless B10: events equal in (type, place) used to be skipped as already present."""
    world.run(ged(*person(1, "1 EVEN", "2 TYPE Flytt", "2 PLAC Ljusdal, Gävleborgs län, Sverige")))
    assert len(world.data.events) == 1
    # A second, different dateless record with the same type and place.
    result = world.run(
        ged(*person(
            1,
            "1 EVEN", "2 TYPE Flytt", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
            "1 EVEN", "2 TYPE Flytt", "2 PLAC Ljusdal, Gävleborgs län, Sverige", "2 NOTE Andra flytten",
        ))
    )
    assert result.events_added == 1
    assert len(world.data.events) == 2
    # And with the file in the other order nothing happens.
    result = world.run(
        ged(*person(
            1,
            "1 EVEN", "2 TYPE Flytt", "2 PLAC Ljusdal, Gävleborgs län, Sverige", "2 NOTE Andra flytten",
            "1 EVEN", "2 TYPE Flytt", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
        ))
    )
    assert result.events_added == 0
    assert len(world.data.events) == 2


def test_reimport_identical_file_creates_no_events(world: World) -> None:
    first = world.run(FULL)
    assert first.events_added == 5 and first.residences_added == 1
    family_before = [list(f.event_ids) for f in world.data.families]
    world.save()
    before = Snapshot.of(world.data)
    again = world.run(FULL)
    assert (again.events_added, again.residences_added) == (0, 0)
    assert (again.events_claimed, again.residences_claimed) == (0, 0)
    assert Snapshot.of(world.data).events == before.events
    assert [list(f.event_ids) for f in world.data.families] == family_before
    assert serialize(world.data) == before.canonical
    assert not world.ps.is_dirty  # nothing adopted


@settings(max_examples=40, **_PROPERTY_SETTINGS)
@given(spec=sr.file_specs(with_residences=False))
def test_reimport_is_idempotent_property(spec) -> None:
    """Includes the whole-project post-steps of the importer (importer.py post-steps)."""

    def body(world: World) -> None:
        world.run_spec(spec)
        after_first = serialize(world.data)
        result = world.run_spec(spec)
        assert result.events_added == 0
        assert serialize(world.data) == after_first
        world.run_spec(spec)
        assert serialize(world.data) == after_first

    _with_world(body)


@settings(max_examples=40, **_PROPERTY_SETTINGS)
@given(spec=sr.file_specs(with_residences=True))
def test_reimport_is_idempotent_with_resi_property(spec) -> None:
    def body(world: World) -> None:
        world.run_spec(spec)
        after_first = serialize(world.data)
        result = world.run_spec(spec)
        assert (result.events_added, result.residences_added) == (0, 0)
        assert serialize(world.data) == after_first
        world.save_and_reopen()
        result = world.run_spec(spec)
        assert (result.events_added, result.residences_added) == (0, 0)
        assert serialize(world.data) == after_first

    _with_world(body)


def test_reimport_reordered_records_creates_no_events(world: World) -> None:
    records = [
        ["1 BIRT", "2 DATE 1 JAN 1850"],
        ["1 BAPM", "2 DATE 5 JAN 1850", "2 NOTE Dop"],
        ["1 EVEN", "2 TYPE Flytt"],
        ["1 EVEN", "2 TYPE Flytt", "2 NOTE Igen"],
        ["1 RESI", "2 DATE FROM 1850 TO 1860"],
        ["1 RESI", "2 DATE FROM 1860 TO 1870"],
    ]

    def file(order) -> str:
        return ged(*person(1, *[line for i in order for line in records[i]]))

    world.run(file(range(6)))
    before = Snapshot.of(world.data)
    result = world.run(file([5, 3, 1, 0, 4, 2]))
    assert (result.events_added, result.residences_added) == (0, 0)
    assert serialize(world.data) == before.canonical


def test_reimport_inserted_record_creates_one_event(world: World) -> None:
    base = ["1 BIRT", "2 DATE 1 JAN 1850", "1 DEAT", "2 DATE 1 JAN 1920"]
    world.run(ged(*person(1, *base)))
    before = Snapshot.of(world.data)
    result = world.run(
        ged(*person(1, "1 BURI", "2 DATE 5 JAN 1920", *base[:2], "1 EVEN", "2 TYPE Flytt", *base[2:]))
    )
    assert result.events_added == 2
    assert_nothing_lost_or_rewritten(before, world.data)
    result = world.run(ged(*person(1, *base, "1 BURI", "2 DATE 5 JAN 1920")))
    assert result.events_added == 0
    # Exactly one inserted record: one new event.
    world2 = World(world.folder.parent / "w2")
    world2.run(ged(*person(1, *base)))
    before2 = Snapshot.of(world2.data)
    result = world2.run(ged(*person(1, "1 BURI", "2 DATE 5 JAN 1920", *base)))
    assert result.events_added == 1
    assert len(world2.data.events) == len(before2.events) + 1
    assert_nothing_lost_or_rewritten(before2, world2.data)


def test_reimport_removed_record_keeps_event(world: World) -> None:
    world.run(FULL)
    before = Snapshot.of(world.data)
    reduced = ged(*person(1, "1 BIRT", "2 DATE 1 JAN 1850", "2 PLAC Ljusdal, Gävleborgs län, Sverige"))
    result = world.run(reduced)
    assert (result.events_added, result.residences_added) == (0, 0)
    assert Snapshot.of(world.data).events == before.events
    assert Snapshot.of(world.data).residences == before.residences
    assert any("hittades inte i GEDCOM-filen" in w for w in result.warnings)


def test_reimport_identical_records_pair_by_count(world: World) -> None:
    def file(k: int) -> str:
        return ged(*person(1, *(["1 BIRT", "2 PLAC Ljusdal, Gävleborgs län, Sverige"] * k)))

    assert world.run(file(3)).events_added == 3
    before = Snapshot.of(world.data)
    assert world.run(file(2)).events_added == 0       # min(2, 3) unchanged, none new
    assert Snapshot.of(world.data).events == before.events
    assert world.run(file(5)).events_added == 2       # max(5 - 3, 0) new
    assert len(world.data.events) == 5
    assert world.run(file(5)).events_added == 0


def test_reimport_after_user_edit_leaves_event_unchanged(world: World) -> None:
    world.run(ged(*person(1, "1 BIRT", "2 DATE 1 JAN 1850", "2 PLAC Ljusdal, Gävleborgs län, Sverige")))
    event = world.data.events[0]
    event.date = DateValue(value="1850-01-02", precision="day")
    event.place = PlaceRef(place_id=world.data.places[-1].id)
    event.participants.append(Participant(person_id="person_x", role="witness"))
    edited = copy.deepcopy(event)
    result = world.run(ged(*person(1, "1 BIRT", "2 DATE 1 JAN 1850", "2 PLAC Ljusdal, Gävleborgs län, Sverige")))
    assert result.events_added == 0
    assert world.data.events == [edited]


def test_reimport_changed_record_creates_new_with_notice(world: World) -> None:
    world.run(ged(*person(1, "1 BIRT", "2 DATE 1 JAN 1850")))
    old = copy.deepcopy(world.data.events[0])
    result = world.run(ged(*person(1, "1 BIRT", "2 DATE 2 JAN 1850")))
    assert result.events_added == 1
    assert world.data.events[0] == old
    new = world.data.events[1]
    notices = [w for w in result.warnings if "inte kunde kopplas" in w]
    assert len(notices) == 1
    assert new.id in notices[0] and old.id in notices[0]
    assert "Granska och ta bort det som är inaktuellt" in notices[0]


def test_reimport_uid_match_changed_record_reports_without_modifying(world: World) -> None:
    world.run(ged(*person(1, "1 BIRT", "2 DATE 1 JAN 1850", "2 _UID ABC-1")))
    old = copy.deepcopy(world.data.events[0])
    result = world.run(ged(*person(1, "1 BIRT", "2 DATE 2 JAN 1850", "2 _UID ABC-1")))
    assert result.events_added == 0
    assert world.data.events == [old]
    assert sum("samma _UID" in w for w in result.warnings) == 1


def test_reimport_never_removes_existing_events(world: World) -> None:
    world.run(FULL)
    user_event = Event(
        id="event_user",
        type="occupation",
        participants=[Participant(person_id=world.data.persons[0].id, role="subject")],
    )
    world.data.events.append(user_event)
    before = Snapshot.of(world.data)
    for text in (
        ged(*person(1)),                          # every record removed
        ged(*person(1, "1 BIRT", "2 DATE 9 JAN 1800")),   # only a different record
        ged(),                                    # no persons at all
        FULL,
    ):
        world.run(text)
        assert_nothing_lost_or_rewritten(before, world.data)


def test_reimport_family_events_preserved(world: World) -> None:
    world.run(FULL)
    family = world.data.families[0]
    ids = list(family.event_ids)
    assert len(ids) == 2
    before = Snapshot.of(world.data)
    result = world.run(FULL)
    assert result.events_added == 0
    assert world.data.families[0].event_ids == ids
    assert Snapshot.of(world.data).events == before.events


def test_family_event_ids_never_dropped(world: World) -> None:
    world.run(FULL)
    family = world.data.families[0]
    user_event = Event(
        id="event_user_fam", type="engagement",
        participants=[Participant(person_id=p.person_id, role="spouse") for p in family.partners],
    )
    world.data.events.append(user_event)
    family.event_ids.append(user_event.id)
    old_ids = list(family.event_ids)
    before = Snapshot.of(world.data)
    # DIV removed, MARR changed, a new family event added.
    changed = ged(
        *person(1), *person(2),
        "0 @F1@ FAM", "1 HUSB @I1@", "1 WIFE @I2@",
        "1 MARR", "2 DATE 16 MAY 1875", "1 ENGA", "2 DATE 1 JAN 1874",
    )
    result = world.run(changed)
    assert result.events_added == 2
    new_ids = world.data.families[0].event_ids
    assert new_ids[: len(old_ids)] == old_ids
    assert len(new_ids) == len(old_ids) + 2
    assert_nothing_lost_or_rewritten(before, world.data)


def test_deleted_imported_event_reappears_known_limitation(world: World) -> None:
    """Known limitation 1 (Requirement 10.13)."""
    text = ged(*person(1, "1 BIRT", "2 DATE 1 JAN 1850"))
    world.run(text)
    deleted = world.data.events.pop()
    result = world.run(text)
    assert result.events_added == 1
    assert len(world.data.events) == 1
    assert world.data.events[0].id != "" and world.data.events[0].type == deleted.type
    assert world.data.events[0].origin.record_hash == deleted.origin.record_hash


def test_ambiguous_event_creates_new_with_review_notice(world: World) -> None:
    dates = [f"{d} JAN 1850" for d in range(1, 8)]
    world.run(ged(*person(1, *[l for d in dates for l in ("1 BAPM", f"2 DATE {d}")])))
    assert len(world.data.events) == 7
    before = Snapshot.of(world.data)
    result = world.run(ged(*person(1, "1 BAPM", "2 DATE 20 JAN 1850")))
    assert result.events_added == 1
    assert_nothing_lost_or_rewritten(before, world.data)
    notice = next(w for w in result.warnings if "inte kunde kopplas" in w)
    new_id = world.data.events[-1].id
    assert new_id in notice
    assert sum(e.id in notice for e in world.data.events[:7]) == 5   # at most five named
    assert "och 2 till" in notice


def _strip_origins(world: World) -> None:
    for event in world.data.events:
        event.origin = None
    for fact in world.data.residences:
        fact.origins = []


LEGACY_FILE = ged(
    *person(
        1,
        "1 BIRT", "2 DATE 1 JAN 1850", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
        "1 DEAT", "2 DATE 5 MAR 1920",
    ),
    *person(2, "1 BIRT", "2 DATE 3 FEB 1852"),
    "0 @F1@ FAM", "1 HUSB @I1@", "1 WIFE @I2@", "1 MARR", "2 DATE 15 MAY 1875",
)


def test_legacy_event_claim_reported_in_import_log(world: World) -> None:
    world.run(LEGACY_FILE)
    n = len(world.data.events)
    assert n == 4
    _strip_origins(world)
    before = Snapshot.of(world.data)
    result = world.run(LEGACY_FILE)
    assert result.events_added == 0
    assert result.events_claimed == n
    notice = f"{n} befintliga händelser kopplades till GEDCOM-posterna och fick ursprungsmärkning."
    assert sum(notice in w for w in result.warnings) == 1
    assert_nothing_lost_or_rewritten(before, world.data, legacy=True)
    assert all(e.origin is not None for e in world.data.events)
    # After the claim a further import changes nothing.
    again = world.run(LEGACY_FILE)
    assert (again.events_added, again.events_claimed) == (0, 0)


def test_legacy_event_claim_marks_project_changed(world: World) -> None:
    world.run(LEGACY_FILE)
    world.save()
    _strip_origins(world)
    assert not world.ps.is_dirty
    revision = world.ps.content_revision
    world.run(LEGACY_FILE)
    assert world.ps.is_dirty
    assert world.ps.content_revision > revision
    # A claim-free import afterwards adopts nothing.
    world.save()
    world.run(LEGACY_FILE)
    assert not world.ps.is_dirty


def test_reimport_after_save_and_reopen_creates_nothing(world: World) -> None:
    world.run(FULL)
    world.save_and_reopen()
    before = Snapshot.of(world.data)
    result = world.run(FULL)
    assert (result.events_added, result.residences_added) == (0, 0)
    assert serialize(world.data) == before.canonical


def test_reimport_keeps_flytt_events_and_links_between_residences(world: World) -> None:
    text = ged(
        *person(
            1,
            "1 EVEN", "2 TYPE Flytt", "2 DATE 1860",
            "1 RESI", "2 DATE FROM 1850 TO 1860", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
            "1 RESI", "2 DATE FROM 1860 TO 1870", "2 PLAC Ljusdal, Gävleborgs län, Sverige",
        )
    )
    world.run(text)
    flytt = next(e for e in world.data.events if e.type == "flytt")
    a, b = world.data.residences
    a.end.event_id = flytt.id
    b.start.event_id = flytt.id
    before = Snapshot.of(world.data)
    result = world.run(text)
    assert (result.events_added, result.residences_added) == (0, 0)
    assert serialize(world.data) == before.canonical
    assert world.data.residences[0].end.event_id == flytt.id


def test_reimport_after_person_merge_creates_nothing_for_the_retired_record(
    world: World,
) -> None:
    text = ged(
        "0 @I1@ INDI", "1 NAME Johan /Andersson/", "1 SEX M",
        "1 BIRT", "2 DATE 15 MAR 1850", "1 RESI", "2 DATE FROM 1850 TO 1860",
        "2 PLAC Ljusdal, Gävleborgs län, Sverige",
        "0 @I2@ INDI", "1 NAME Johan /Andersson/", "1 SEX M",
        "1 BIRT", "2 DATE 15 MAR 1850", "1 RESI", "2 DATE FROM 1850 TO 1860",
        "2 PLAC Ljusdal, Gävleborgs län, Sverige",
    )
    world.run(text)
    assert world.merge_persons()
    assert len(world.data.persons) == 1
    before = Snapshot.of(world.data)
    result = world.run(text)
    assert (result.events_added, result.residences_added) == (0, 0)
    assert_nothing_lost_or_rewritten(before, world.data)


# ---------------------------------------------------------------------------
# Re-import of a legacy (pre-0.5) project
# ---------------------------------------------------------------------------


def test_reimport_of_legacy_v0_4_project(tmp_path: Path) -> None:
    """The v0.4 fixture has imported events and residences without any origin.

    A GEDCOM file for its persons is imported into it. Nothing existing is
    removed or rewritten except an origin on an event that matches exactly.
    """
    project_file = tmp_path / "projekt.json.gz"
    shutil.copy2(FIXTURE_V0_4, project_file)
    (tmp_path / "translation").mkdir()
    write_all(
        TranslationData(
            persons=[PersonMapping(f"@I{i}@", f"person_{i}") for i in (1, 2, 3)],
            places=[
                PlaceMapping("Backa", "place_2", "Backa"),
                PlaceMapping("Dala", "place_3", "Dala"),
            ],
            sources=[SourceMapping("@S1@", "source_1")],
        ),
        tmp_path / "translation",
    )
    world = World.from_project_file(project_file)
    assert all(e.origin is None for e in world.data.events)
    assert all(not r.origins for r in world.data.residences)
    # The fixture roles are synthetic; the pre-0.5 importer wrote "subject".
    # Make one event look exactly like an importer-made one.
    next(e for e in world.data.events if e.id == "event_5").participants[0].role = "subject"
    text = "\n".join([
        "0 HEAD", "1 CHAR UTF-8", "0 @S1@ SOUR", "1 TITL Källa",
        "0 @I1@ INDI", "1 NAME Förnamn1 /Testsson/", "1 SEX M",
        "1 DEAT", "2 DATE 1910",
        "1 EVEN", "2 TYPE Flytt", "2 DATE 1 MAY 1875", "2 PLAC Dala",
        "1 RESI", "2 DATE FROM 1850 TO 1875", "2 PLAC Backa",
        "0 @I2@ INDI", "1 NAME Förnamn2 /Testsson/", "1 SEX F",
        "1 CENS",
        "0 @I3@ INDI", "1 NAME Förnamn3 /Testsson/", "1 SEX M",
        "1 BAPM", "2 DATE 10 JAN 1852", "2 PLAC Backa",
        "0 TRLR",
    ]) + "\n"
    before = Snapshot.of(world.data)
    persons_before = [p.id for p in world.data.persons]

    result = world.run(text)

    assert [p.id for p in world.data.persons] == persons_before
    assert_nothing_lost_or_rewritten(before, world.data, legacy=True)
    # Exact legacy matches got an origin, nothing else changed.
    claimed = [e for e in world.data.events if e.id in before.events and e.origin is not None]
    assert len(claimed) == result.events_claimed
    assert {e.id for e in claimed} == {"event_5"}      # the only exact content match
    # Residences of the fixture carry flytt links or observations, so the plain
    # RESI record matches none of them and gets a residence of its own.
    assert result.residences_claimed == 0
    assert result.residences_added == 1
    assert any("inte kunde kopplas till ett befintligt boende" in w for w in result.warnings)
    # A second import of the same file is stable.
    after_first = serialize(world.data)
    again = world.run(text)
    assert (again.events_added, again.events_claimed) == (0, 0)
    assert (again.residences_added, again.residences_claimed) == (0, 0)
    assert serialize(world.data) == after_first
    # Save and reopen: the origins are persisted and the next import is stable.
    world.save_and_reopen()
    third = world.run(text)
    assert (third.events_added, third.residences_added) == (0, 0)
    assert serialize(world.data) == after_first

