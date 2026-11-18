"""Re-import of GEDCOM ``RESI`` records (Requirement 22.6 to 22.25).

Example tests for the residence identity of the importer: an unchanged file
creates nothing, reordering and removal change nothing, an inserted or changed
record creates exactly one residence, user edits survive, flytt links stay as
they are and no existing residence is merged or removed by an import.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from slaktbusken.gedcom.importer import GEDCOMImporter, ImportResult
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.persistence.serialization import serialize
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.residence_edit_ops import attach_observations
from slaktbusken.services.validation_service import ValidationService

pytestmark = pytest.mark.mandatory_integrity

_HEAD = "0 HEAD\n1 CHAR UTF-8\n"
_TRLR = "0 TRLR\n"
_SOURCES = "0 @S1@ SOUR\n1 TITL Husförhörslängd A\n0 @S2@ SOUR\n1 TITL Husförhörslängd B\n"


def resi(
    date: str | None = None,
    place: str | None = None,
    sour: tuple[str, ...] = (),
    uid: str | None = None,
    note: str | None = None,
) -> str:
    """One level-1 ``RESI`` record."""
    lines = ["1 RESI"]
    if date:
        lines.append(f"2 DATE {date}")
    if place:
        lines.append(f"2 PLAC {place}")
    for pointer in sour:
        lines.append(f"2 SOUR {pointer}")
    if uid:
        lines.append(f"2 _UID {uid}")
    if note:
        lines.append(f"2 NOTE {note}")
    return "\n".join(lines) + "\n"


def flytt(date: str, place: str) -> str:
    return f"1 EVEN\n2 TYPE Flytt\n2 DATE {date}\n2 PLAC {place}\n"


def gedcom(*records: str, sources: bool = False) -> str:
    """A file with one person ``@I1@`` that carries *records*."""
    text = _HEAD
    if sources:
        text += _SOURCES
    text += "0 @I1@ INDI\n1 NAME Johan /Andersson/\n1 SEX M\n"
    text += "".join(records)
    return text + _TRLR


A = resi("FROM 1 JAN 1850 TO 1 JAN 1860", "Ljusdal")
B = resi("FROM 1 JAN 1860 TO 1 JAN 1870", "Gävle")
C = resi("FROM 1 JAN 1870 TO 1 JAN 1880", "Bollnäs")
D = resi("FROM 1 JAN 1880 TO 1 JAN 1890", "Hudiksvall")


class Env:
    """A project, a translation folder and a GEDCOM file in a temp folder."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.tdir = tmp_path / "translation"
        self.tdir.mkdir()
        self.path = tmp_path / "t.ged"
        self.project = ProjectData(project=ProjectMetadata(title="T"))

    def run(self, text: str) -> ImportResult:
        self.path.write_text(text, encoding="utf-8")
        return GEDCOMImporter(self.project, self.tdir).import_file(self.path)

    def canonical(self) -> dict:
        return serialize(self.project)

    def snapshot(self) -> dict[str, ResidenceFact]:
        return {r.id: copy.deepcopy(r) for r in self.project.residences}

    def translation_bytes(self) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in sorted(self.tdir.iterdir())}


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def _warnings(result: ImportResult) -> str:
    return "\n".join(str(w) for w in result.warnings)


def _by_place(env: Env, name: str) -> ResidenceFact:
    ids = {p.id for p in env.project.places if p.name == name}
    found = [r for r in env.project.residences if r.place_id in ids]
    assert len(found) == 1
    return found[0]


# ---------------------------------------------------------------------------
# Unchanged, reordered, inserted, removed (22.10 to 22.13)
# ---------------------------------------------------------------------------


def test_reimport_resi_file_creates_no_residences(env: Env) -> None:
    first = env.run(gedcom(A, B, C))
    assert first.residences_added == 3
    before = env.canonical()
    again = env.run(gedcom(A, B, C))
    assert again.residences_added == 0
    assert again.residences_claimed == 0
    assert len(env.project.residences) == 3
    assert env.canonical() == before


def test_reimport_resi_reordered_creates_none(env: Env) -> None:
    env.run(gedcom(A, B, C))
    before = env.snapshot()
    result = env.run(gedcom(C, A, B))
    assert result.residences_added == 0
    assert env.snapshot() == before


def test_reimport_resi_inserted_record_creates_one(env: Env) -> None:
    env.run(gedcom(A, C))
    before = env.snapshot()
    result = env.run(gedcom(A, B, C))
    assert result.residences_added == 1
    assert len(env.project.residences) == 3
    for rid, fact in before.items():
        assert next(r for r in env.project.residences if r.id == rid) == fact
    new = [r for r in env.project.residences if r.id not in before]
    assert len(new) == 1 and len(new[0].origins) == 1


def test_reimport_resi_removed_record_keeps_residence(env: Env) -> None:
    env.run(gedcom(A, B, C))
    before = env.snapshot()
    result = env.run(gedcom(A, C))
    assert result.residences_added == 0
    assert env.snapshot() == before


def test_reimport_resi_identical_records_pair_by_count(env: Env) -> None:
    first = env.run(gedcom(A, A))
    assert first.residences_added == 2
    assert sorted(r.origins[0].instance for r in env.project.residences) == [0, 1]
    # k = 3 identical records against m = 2 groups: max(k - m, 0) = 1 new.
    second = env.run(gedcom(A, A, A))
    assert second.residences_added == 1
    assert len(env.project.residences) == 3
    assert sorted(r.origins[0].instance for r in env.project.residences) == [0, 1, 2]
    # k = 1 against m = 3 groups: nothing is created or changed.
    before = env.snapshot()
    third = env.run(gedcom(A))
    assert third.residences_added == 0
    assert env.snapshot() == before


# ---------------------------------------------------------------------------
# Changed records (22.8, 22.9, 22.19)
# ---------------------------------------------------------------------------


def test_reimport_resi_changed_record_creates_new_with_notice(env: Env) -> None:
    env.run(gedcom(A, B))
    before = env.snapshot()
    changed = resi("FROM 1 JAN 1861 TO 1 JAN 1870", "Gävle")
    result = env.run(gedcom(A, changed))
    assert result.residences_added == 1
    assert len(env.project.residences) == 3
    for rid, fact in before.items():
        assert next(r for r in env.project.residences if r.id == rid) == fact
    text = _warnings(result)
    assert "Ett nytt boende" in text
    assert "Befintliga boenden som inte kopplades" in text


def test_reimport_resi_uid_changed_record_reports_without_modifying(env: Env) -> None:
    env.run(gedcom(resi("FROM 1 JAN 1850 TO 1 JAN 1860", "Ljusdal", uid="UID-1"), B))
    before = env.snapshot()
    changed = resi("FROM 1 JAN 1851 TO 1 JAN 1861", "Ljusdal", uid="UID-1")
    result = env.run(gedcom(changed, B))
    assert result.residences_added == 0
    assert env.snapshot() == before
    assert "samma _UID" in _warnings(result)


# ---------------------------------------------------------------------------
# Edits made in the application (22.15, 22.19)
# ---------------------------------------------------------------------------


def _replace_in_project(env: Env, fact: ResidenceFact) -> None:
    for i, existing in enumerate(env.project.residences):
        if existing.id == fact.id:
            env.project.residences[i] = fact
            return
    raise AssertionError("residence not found")


def test_reimport_after_user_edit_leaves_residence_unchanged(env: Env) -> None:
    env.run(gedcom(A, B, flytt("1 JAN 1860", "Gävle")))
    env.project.places.append(Place(id="place_user", type="unknown", name="Användarplats"))
    target = _by_place(env, "Ljusdal")
    edited = replace(
        target,
        place_id="place_user",
        start=Endpoint(earliest="1845", latest="1850", precision="year"),
        end=Endpoint(
            earliest="1860", latest="1861", precision="year",
            event_id=env.project.events[-1].id, note="Flyttade",
        ),
        role_in_household="Dräng",
        notes="Egen anteckning",
    )
    _replace_in_project(env, edited)
    before = env.canonical()
    events_before = len(env.project.events)
    result = env.run(gedcom(A, B, flytt("1 JAN 1860", "Gävle")))
    assert result.residences_added == 0
    assert len(env.project.residences) == 2
    assert next(r for r in env.project.residences if r.id == target.id) == edited
    assert len(env.project.events) == events_before
    assert env.canonical() == before


def test_reimport_after_user_edited_observations_leaves_residence_unchanged(env: Env) -> None:
    record = resi("FROM 1 JAN 1850 TO 1 JAN 1860", "Ljusdal", sour=("@S1@",))
    first = env.run(gedcom(record, sources=True))
    assert first.residences_added == 1
    fact = env.project.residences[0]
    assert len(fact.observations) == 1
    # The user adds observed years and a second observation.
    fact.observations[0].observed_from = "1851"
    fact.observations[0].observed_to = "1853"
    extra = Observation(
        source_ref=SourceRef(source_id="source_other", quality="primary"),
        observed_from="1855",
        observed_to="1858",
    )
    edited = attach_observations(fact, [extra])
    _replace_in_project(env, edited)
    before = env.canonical()
    result = env.run(gedcom(record, sources=True))
    assert result.residences_added == 0
    assert env.project.residences == [edited]
    assert env.canonical() == before


def test_reimport_resi_sour_change_creates_new_residence(env: Env) -> None:
    env.run(gedcom(resi("FROM 1 JAN 1850 TO 1 JAN 1860", "Ljusdal", sour=("@S1@",)), sources=True))
    before = env.snapshot()
    other = resi("FROM 1 JAN 1850 TO 1 JAN 1860", "Ljusdal", sour=("@S2@",))
    result = env.run(gedcom(other, sources=True))
    assert result.residences_added == 1
    assert len(env.project.residences) == 2
    for rid, fact in before.items():
        assert next(r for r in env.project.residences if r.id == rid) == fact
    new = next(r for r in env.project.residences if r.id not in before)
    old_source = next(iter(before.values())).observations[0].source_ref.source_id
    assert new.observations[0].source_ref.source_id != old_source


def test_deleted_imported_residence_reappears_known_limitation(env: Env) -> None:
    """Known limitation 2 (Requirement 22.17)."""
    env.run(gedcom(A, B))
    deleted = _by_place(env, "Ljusdal")
    env.project.residences.remove(deleted)
    result = env.run(gedcom(A, B))
    assert result.residences_added == 1
    assert len(env.project.residences) == 2
    again = _by_place(env, "Ljusdal")
    assert again.id != deleted.id


# ---------------------------------------------------------------------------
# Unchanged records write nothing (22.7)
# ---------------------------------------------------------------------------


def test_residence_unchanged_writes_nothing_and_resolves_no_place(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = gedcom(
        resi("FROM 1 JAN 1850 TO 1 JAN 1860", "Ljusdal, Gävleborgs län, Sverige"), B
    )
    env.run(text)
    before = env.canonical()
    translation = env.translation_bytes()
    places = [copy.deepcopy(p) for p in env.project.places]
    calls: list[str] = []
    original_resolve = GEDCOMImporter._resolve_residence_place
    original_add = GEDCOMImporter._add_residence

    def spy_resolve(self, *args, **kwargs):
        calls.append("resolve")
        return original_resolve(self, *args, **kwargs)

    def spy_add(self, *args, **kwargs):
        calls.append("add")
        return original_add(self, *args, **kwargs)

    monkeypatch.setattr(GEDCOMImporter, "_resolve_residence_place", spy_resolve)
    monkeypatch.setattr(GEDCOMImporter, "_add_residence", spy_add)
    result = env.run(text)
    assert calls == []
    assert result.residences_added == 0 and result.places_added == 0
    assert env.project.places == places
    assert env.canonical() == before
    assert env.translation_bytes() == translation


# ---------------------------------------------------------------------------
# Flytt events and Endpoint links (22.23, 22.24)
# ---------------------------------------------------------------------------


def _link_with_flytt(env: Env, earlier: ResidenceFact, later: ResidenceFact) -> Event:
    event = Event(
        id="event_flytt_user",
        type="flytt",
        participants=[Participant(person_id=earlier.person_id, role="subject")],
        date=DateValue(value="1860-01-01", precision="day"),
        place=PlaceRef(place_id=later.place_id),
        from_place=PlaceRef(place_id=earlier.place_id),
    )
    env.project.events.append(event)
    _replace_in_project(
        env, replace(earlier, end=replace(earlier.end, event_id=event.id))
    )
    _replace_in_project(
        env, replace(later, start=replace(later.start, event_id=event.id))
    )
    return event


def test_import_creates_no_flytt_event_from_residence(env: Env) -> None:
    result = env.run(gedcom(A, B, C))
    assert result.residences_added == 3
    assert [e for e in env.project.events if e.type == "flytt"] == []
    for fact in env.project.residences:
        assert fact.start.event_id is None and fact.end.event_id is None


def test_reimport_keeps_flytt_links_between_residences(env: Env) -> None:
    env.run(gedcom(A, B))
    event = _link_with_flytt(env, _by_place(env, "Ljusdal"), _by_place(env, "Gävle"))
    before = env.snapshot()
    events_before = copy.deepcopy(env.project.events)
    for text in (gedcom(A, B), gedcom(B, A), gedcom(A)):
        env.run(text)
        assert env.snapshot() == before
        assert env.project.events == events_before
    assert _by_place(env, "Ljusdal").end.event_id == event.id
    assert _by_place(env, "Gävle").start.event_id == event.id


def test_reimport_keeps_flytt_event_count_with_resi(env: Env) -> None:
    text = gedcom(A, B, flytt("1 JAN 1860", "Gävle"))
    env.run(text)
    flytt_ids = sorted(e.id for e in env.project.events if e.type == "flytt")
    assert len(flytt_ids) == 1
    for _ in range(2):
        env.run(text)
        assert sorted(e.id for e in env.project.events if e.type == "flytt") == flytt_ids
        assert len(env.project.residences) == 2


def test_flytt_event_edited_in_app_not_duplicated_by_reimport(env: Env) -> None:
    text = gedcom(A, B, flytt("1 JAN 1860", "Gävle"))
    env.run(text)
    event = next(e for e in env.project.events if e.type == "flytt")
    event.date = DateValue(value="1860-06-15", precision="day")
    event.place = PlaceRef(place_id="place_user")
    edited = copy.deepcopy(event)
    count = len(env.project.events)
    result = env.run(text)
    assert result.events_added == 0
    assert len(env.project.events) == count
    assert next(e for e in env.project.events if e.id == event.id) == edited


# ---------------------------------------------------------------------------
# No merge, removal or rewrite by import (22.25)
# ---------------------------------------------------------------------------


def test_no_residence_is_merged_or_removed_by_import(env: Env) -> None:
    env.run(gedcom(A, A))
    # Two adjacent residences at one place that the user could merge, a
    # residence made by the user and a legacy duplicate pair.
    user = ResidenceFact(
        id="residence_user",
        person_id=env.project.residences[0].person_id,
        place_id=env.project.residences[0].place_id,
        start=Endpoint(earliest="1860", latest="1860"),
        end=Endpoint(earliest="1865", latest="1865"),
    )
    legacy = [
        replace(user, id="residence_legacy_1", start=Endpoint(earliest="1890", latest="1890")),
        replace(user, id="residence_legacy_2", start=Endpoint(earliest="1890", latest="1890")),
    ]
    env.project.residences.extend([user, *legacy])
    order = [r.id for r in env.project.residences]
    before = env.snapshot()
    result = env.run(gedcom(A, A, B, C, D))
    assert result.residences_added == 3
    assert [r.id for r in env.project.residences[: len(order)]] == order
    for rid, fact in before.items():
        assert next(r for r in env.project.residences if r.id == rid) == fact


# ---------------------------------------------------------------------------
# Save, reopen and import again (22.32)
# ---------------------------------------------------------------------------


def test_residence_save_reopen_reimport_creates_none(tmp_path: Path) -> None:
    ged = tmp_path / "t.ged"
    ged.write_text(gedcom(A, A, B, sources=False), encoding="utf-8")
    service = ImportService(ValidationService())
    ps = ProjectService()
    ps.create_project("Test", tmp_path / "work")
    project_folder = ps.project_path.parent

    first = service.run(ps.data, ged, project_folder, ps)
    assert first.residences_added == 3
    ps.save_project()
    saved = serialize(ps.data)
    origin_keys = sorted(
        (o.record_hash, o.instance) for r in ps.data.residences for o in r.origins
    )

    reopened = ProjectService()
    reopened.open_project(ps.project_path)
    assert serialize(reopened.data) == saved
    again = service.run(reopened.data, ged, project_folder, reopened)
    assert again.residences_added == 0
    assert again.residences_claimed == 0
    assert len(reopened.data.residences) == 3
    assert serialize(reopened.data) == saved
    assert sorted(
        (o.record_hash, o.instance) for r in reopened.data.residences for o in r.origins
    ) == origin_keys
