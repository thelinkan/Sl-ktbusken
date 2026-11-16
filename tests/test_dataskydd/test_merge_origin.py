"""A person merge keeps every event and residence origin (task 10.6).

Property 23: A merge preserves every event and residence origin.

**Validates: Requirements 19.9, 19.10, 19.11, 22.20, 22.21, 22.26**

The tests import a small GEDCOM file into a real project, merge two persons
through the real planner and MergeEngine, and import again. Helpers live in
this file.
"""
from __future__ import annotations

import importlib
import pkgutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

import slaktbusken.model as model_pkg
from slaktbusken.gedcom.importer import GEDCOMImporter
from slaktbusken.model.record_origin import RecordOrigin
from slaktbusken.persistence import translation_io
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_planner import (
    MergeDecisions,
    apply_change_set,
    build_plan,
)
from slaktbusken.services.person_reference_index import (
    INVENTORY_BY_KEY,
    RULE_HISTORICAL,
    find_unlisted_person_reference_fields,
)
from slaktbusken.services.project_service import ProjectService

pytestmark = pytest.mark.mandatory_integrity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURE = """\
0 HEAD
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
1 BIRT
2 DATE 15 MAR 1850
1 DEAT
2 DATE 2 FEB 1920
1 RESI
2 DATE FROM 1880 TO 1890
2 PLAC Almby
0 @I2@ INDI
1 NAME Johan /Andersson/
1 SEX M
1 BIRT
2 DATE 15 MAR 1850
2 PLAC Orebro
1 BURI
2 DATE 5 FEB 1920
1 RESI
2 DATE FROM 1891 TO 1900
2 PLAC Glanshammar
0 TRLR
"""


def _origin_state(items) -> dict[str, list[tuple]]:
    """Object id to its origins, as comparable tuples."""
    out: dict[str, list[tuple]] = {}
    for obj in items:
        if hasattr(obj, "origins"):
            origins = list(obj.origins)
        else:
            origins = [obj.origin] if obj.origin is not None else []
        out[obj.id] = [_tuple(o) for o in origins]
    return out


def _tuple(o: RecordOrigin) -> tuple:
    return (
        o.owner_kind, o.owner_id, o.owner_xref, o.tag_key, o.index,
        o.record_hash, o.uid, o.instance,
    )


class _World:
    """A real project with a GEDCOM file and the two persons to merge."""

    def __init__(self, root: Path, text: str = _FIXTURE) -> None:
        self.svc = ProjectService()
        self.svc.create_project("T", root)
        self.tdir = self.svc.project_path.parent / "translation"
        self.tdir.mkdir(exist_ok=True)
        self.ged = root / "t.ged"
        self.ged.write_text(text, encoding="utf-8")
        self.importer().import_file(self.ged)
        self.svc._dirty = True
        self.svc.save_project()
        by_xref = {m.gedcom_id: m for m in translation_io.read_all(self.tdir).persons}
        self.survivor = by_xref["@I1@"].app_id
        self.retired = by_xref["@I2@"].app_id

    def importer(self) -> GEDCOMImporter:
        return GEDCOMImporter(self.svc.data, self.tdir)

    def plan(self):
        translation = translation_io.read_all(self.tdir)
        decisions = MergeDecisions(
            self.survivor, self.retired,
            survivor_id=self.survivor, survivor_confirmed=True,
        )
        plan = build_plan(
            self.svc.data, translation, decisions, self.svc.content_revision
        )
        assert plan.can_execute, [c.message for c in plan.blocking]
        return plan

    def merge(self) -> None:
        outcome = MergeEngine(self.svc, None).execute(self.plan())
        assert outcome.success, outcome.message

    def events(self) -> dict[str, list[tuple]]:
        return _origin_state(self.svc.data.events)

    def residences(self) -> dict[str, list[tuple]]:
        return _origin_state(self.svc.data.residences)


@pytest.fixture
def world(tmp_path: Path) -> _World:
    w = _World(tmp_path)
    assert w.events() and w.residences()
    return w


# ---------------------------------------------------------------------------
# Planner and engine keep event origins (19.9, 19.10)
# ---------------------------------------------------------------------------


def test_merge_preserves_event_origin_planner(world: _World) -> None:
    before = world.events()
    view = apply_change_set(world.svc.data, world.plan().change_set)
    assert _origin_state(view.events) == before
    assert any(o[0][1] == world.retired for o in before.values() if o)


def test_merge_preserves_event_origin_engine(world: _World) -> None:
    before = world.events()
    world.merge()
    assert world.events() == before
    reloaded = ProjectService()
    reloaded.open_project(world.svc.project_path)
    assert _origin_state(reloaded.data.events) == before


# ---------------------------------------------------------------------------
# Planner and engine keep residence origins (22.21)
# ---------------------------------------------------------------------------


def test_residence_merge_origin_planner(world: _World) -> None:
    before = world.residences()
    view = apply_change_set(world.svc.data, world.plan().change_set)
    assert _origin_state(view.residences) == before
    # The retired person's residence moved to the survivor; its origin stayed.
    moved = [r for r in view.residences if r.origins and r.origins[0].owner_id == world.retired]
    assert moved and all(r.person_id == world.survivor for r in moved)


def test_residence_merge_origin_engine(world: _World) -> None:
    before = world.residences()
    world.merge()
    assert world.residences() == before
    moved = [
        r for r in world.svc.data.residences
        if r.origins and r.origins[0].owner_id == world.retired
    ]
    assert moved and all(r.person_id == world.survivor for r in moved)


# ---------------------------------------------------------------------------
# Inventory rows (19.11, 22.20)
# ---------------------------------------------------------------------------


def _model_dataclasses() -> list[type]:
    from dataclasses import is_dataclass

    classes: dict[str, type] = {}
    for info in pkgutil.iter_modules(model_pkg.__path__):
        module = importlib.import_module(f"{model_pkg.__name__}.{info.name}")
        for obj in vars(module).values():
            if isinstance(obj, type) and is_dataclass(obj) and obj.__module__ == module.__name__:
                classes[f"{obj.__module__}.{obj.__qualname__}"] = obj
    return list(classes.values())


def _row(key: str):
    return INVENTORY_BY_KEY[key]


def test_event_origin_in_person_reference_inventory() -> None:
    row = _row("event.origin")
    assert row.rule == RULE_HISTORICAL
    assert row.handler is None
    assert find_unlisted_person_reference_fields(_model_dataclasses()) == []


def test_residence_origin_in_person_reference_inventory() -> None:
    row = _row("residence.origins")
    assert row.rule == RULE_HISTORICAL
    assert row.handler is None
    assert find_unlisted_person_reference_fields(_model_dataclasses()) == []


# ---------------------------------------------------------------------------
# Re-import after a merge (19.11, 22.26)
# ---------------------------------------------------------------------------


def test_merged_identity_record_creates_no_events(world: _World) -> None:
    world.merge()
    events, origins = len(world.svc.data.events), world.events()
    result = world.importer().import_file(world.ged)
    assert result.events_added == 0
    assert result.events_claimed == 0
    assert [m.xref for m in result.merged_identity_matches] == ["@I2@"]
    assert len(world.svc.data.events) == events
    assert world.events() == origins


def test_survivor_record_matches_only_own_origin_events(world: _World) -> None:
    world.merge()
    retired_before = {
        e.id: _tuple(e.origin)
        for e in world.svc.data.events
        if e.origin is not None and e.origin.owner_id == world.retired
    }
    assert retired_before
    # The survivor's birth record changes. Its own birth event is the only
    # event it may match; the retired person's birth event is never touched.
    changed = _FIXTURE.replace("15 MAR 1850\n1 DEAT", "16 MAR 1850\n1 DEAT")
    world.ged.write_text(changed, encoding="utf-8")
    result = world.importer().import_file(world.ged)
    assert result.events_added == 1
    retired_after = {
        e.id: _tuple(e.origin)
        for e in world.svc.data.events
        if e.origin is not None and e.origin.owner_id == world.retired
    }
    assert retired_after == retired_before
    retired_birth = [
        e for e in world.svc.data.events
        if e.id in retired_before and e.type == "birth"
    ]
    assert len(retired_birth) == 1
    assert retired_birth[0].date.value == "1850-03-15"


def test_reimport_resi_merged_identity_record_creates_none(world: _World) -> None:
    world.merge()
    residences, origins = len(world.svc.data.residences), world.residences()
    result = world.importer().import_file(world.ged)
    assert result.residences_added == 0
    assert result.residences_claimed == 0
    assert len(world.svc.data.residences) == residences
    assert world.residences() == origins


def test_reimport_resi_after_person_merge_considers_only_survivor_origins(
    world: _World,
) -> None:
    world.merge()
    retired_before = {
        r.id: (_tuple(r.origins[0]), r.person_id, r.place_id)
        for r in world.svc.data.residences
        if r.origins and r.origins[0].owner_id == world.retired
    }
    assert retired_before
    count = len(world.svc.data.residences)
    changed = _FIXTURE.replace("FROM 1880 TO 1890", "FROM 1881 TO 1890")
    world.ged.write_text(changed, encoding="utf-8")
    result = world.importer().import_file(world.ged)
    assert result.residences_added == 1
    assert len(world.svc.data.residences) == count + 1
    retired_after = {
        r.id: (_tuple(r.origins[0]), r.person_id, r.place_id)
        for r in world.svc.data.residences
        if r.origins and r.origins[0].owner_id == world.retired
    }
    assert retired_after == retired_before


# ---------------------------------------------------------------------------
# Property 23
# ---------------------------------------------------------------------------

_EVENT_TAGS = ("BIRT", "DEAT", "BURI", "BAPM")
_PLACES = ("Almby", "Glanshammar", "Orebro", "Kumla")


@st.composite
def _projects(draw) -> str:
    """A GEDCOM file with two persons of small, varied event and RESI sets."""
    lines = ["0 HEAD", "1 CHAR UTF-8"]
    for xref in ("@I1@", "@I2@"):
        lines += [f"0 {xref} INDI", "1 NAME Johan /Andersson/", "1 SEX M"]
        tags = draw(st.lists(st.sampled_from(_EVENT_TAGS), unique=True, max_size=3))
        for tag in tags:
            year = draw(st.integers(1800, 1900))
            lines += [f"1 {tag}", f"2 DATE {year}"]
        for _ in range(draw(st.integers(0, 2))):
            start = draw(st.integers(1800, 1890))
            place = draw(st.sampled_from(_PLACES))
            lines += ["1 RESI", f"2 DATE FROM {start} TO {start + 5}", f"2 PLAC {place}"]
    lines.append("0 TRLR")
    return "\n".join(lines) + "\n"


@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(text=_projects())
def test_dp_property_23_merge_preserves_event_and_residence_origins(text: str) -> None:
    """**Validates: Requirements 19.9, 19.10, 22.21, 22.26**"""
    with tempfile.TemporaryDirectory() as tmp:
        w = _World(Path(tmp), text)
        events, residences = w.events(), w.residences()
        survivor_events = {
            i for i, o in events.items() if o and o[0][1] == w.survivor
        }
        survivor_residences = {
            i for i, o in residences.items() if o and o[0][1] == w.survivor
        }

        w.merge()

        assert w.events() == events
        assert w.residences() == residences

        # A later import of the same file reads only the survivor's origins
        # (plus its origin-less legacy objects, of which there are none).
        result = w.importer().import_file(w.ged)
        assert result.events_added == 0 and result.residences_added == 0
        assert result.events_claimed == 0 and result.residences_claimed == 0
        assert w.events() == events
        assert w.residences() == residences
        assert {i for i, o in w.events().items() if o and o[0][1] == w.survivor} == survivor_events
        assert {
            i for i, o in w.residences().items() if o and o[0][1] == w.survivor
        } == survivor_residences
