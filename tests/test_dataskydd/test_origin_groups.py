"""Origin_Groups of residences: split, merge, reopen, edit, legacy (Requirement 22.27 to 22.32).

A residence split copies the origins to both halves, so one Origin_Key sits on
two residences. The matcher counts that as one original GEDCOM record, claims
the whole group and creates nothing. Property 28 drives generated sequences of
splits, merges, edits and reopens between two imports of one file.

**Validates: Requirements 19.13, 22.27, 22.28, 22.29, 22.30, 22.31, 22.32**
"""

from __future__ import annotations

import random
import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from slaktbusken.persistence.serialization import serialize
from slaktbusken.persistence.translation_io import (
    PersonMapping,
    PlaceMapping,
    SourceMapping,
    TranslationData,
    write_all,
)
from tests.test_dataskydd import strategies_origin_groups as sg
from tests.test_dataskydd.strategies_origin_groups import (
    Snapshot,
    World,
    assert_import_changes_nothing,
)

pytestmark = pytest.mark.mandatory_integrity

FIXTURE_V0_4 = Path(__file__).resolve().parents[1] / "fixtures" / "project_v0_4.json.gz"

_PROPERTY_SETTINGS = dict(
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

PLACE = "Ljusdal, Gävleborgs län, Sverige"


def ged(*records: str) -> str:
    """A file with one person ``@I1@`` that carries the given record blocks."""
    return (
        "0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Johan /Andersson/\n1 SEX M\n"
        + "".join(records)
        + "0 TRLR\n"
    )


def resi(date: str, place: str = PLACE, uid: str | None = None) -> str:
    out = f"1 RESI\n2 DATE {date}\n2 PLAC {place}\n"
    return out + (f"2 _UID {uid}\n" if uid else "")


A = resi("FROM 1850 TO 1860")
B = resi("FROM 1860 TO 1870")


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def _with_world(fn):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        return fn(World(Path(tmp)))


# ---------------------------------------------------------------------------
# Property 28
# ---------------------------------------------------------------------------


def _run_sequence(world: World, spec: sg.FileSpec, plan: list, duplicate_event: bool) -> list[str]:
    text = sg.render(spec)
    world.run(text)
    if duplicate_event:
        sg.duplicate_event_origin(world, 0)
    effective = [sg.apply_step(world, step, n) for n, step in enumerate(plan)]
    assert_import_changes_nothing(world, text)
    # A second re-import is just as quiet, also after a save and reopen.
    world.save_and_reopen()
    assert_import_changes_nothing(world, text)
    return effective


@settings(max_examples=40, **_PROPERTY_SETTINGS)
@given(spec=sg.file_specs(), plan=st.lists(sg.steps, max_size=6))
def test_dp_property_28_unchanged_reimport_after_split_and_merge_changes_nothing(
    spec, plan
) -> None:
    """Feature: data-integrity-0-3-0, Property 28: An unchanged re-import after any
    sequence of residence splits and merges creates, deletes and modifies nothing.

    **Validates: Requirements 22.27, 22.28, 22.29, 22.31, 22.32, 19.13**
    """
    effective = _with_world(lambda w: _run_sequence(w, spec, plan, False))
    for kind in set(effective):
        event(f"step: {kind}")


@settings(max_examples=25, **_PROPERTY_SETTINGS)
@given(spec=sg.file_specs(with_events=True), plan=st.lists(sg.steps, max_size=4))
def test_dp_property_28_event_origin_duplicated_on_a_second_event(spec, plan) -> None:
    """Property 28, event variant: an event origin that sits on two events of one
    owner is one Origin_Group and the re-import creates and modifies nothing.

    **Validates: Requirements 19.13, 22.31**
    """
    _with_world(lambda w: _run_sequence(w, spec, plan, True))


def _fixed_plan(seed: int) -> list:
    rnd = random.Random(seed)
    return [
        (rnd.choice(sg.STEP_KINDS), rnd.randrange(51), rnd.randrange(51))
        for _ in range(rnd.randrange(2, 8))
    ]


@pytest.mark.parametrize("seed", range(12))
def test_residence_split_merge_import_sequences_property(tmp_path: Path, seed: int) -> None:
    """Example-level driver of the Property 28 sequence generator with fixed seeds."""
    rnd = random.Random(seed)
    persons = []
    for _ in range(rnd.randrange(1, 3)):
        records: list[sg.Rec] = []
        for _ in range(rnd.randrange(1, 4)):
            rec = sg.Rec(
                "RESI",
                date=rnd.choice(sg.RESI_DATES),
                place=rnd.choice((None, 0, 1)),
                note=rnd.choice(sg.NOTES),
                uid=rnd.choice((None, None, f"UID-{seed}-{len(persons)}-{len(records)}")),
            )
            records += [rec] * rnd.choice((1, 1, 2, 3))
        persons.append(records)
    effective = _run_sequence(World(tmp_path), sg.FileSpec(persons), _fixed_plan(seed), False)
    assert len(effective) >= 2


# ---------------------------------------------------------------------------
# Importer-level examples
# ---------------------------------------------------------------------------


def test_reimport_after_residence_split_creates_no_residence_and_changes_none(
    world: World,
) -> None:
    text = ged(A)
    assert world.run(text).residences_added == 1
    first, second = sg.split_residence(world.data, world.data.residences[0])
    assert first.origins and first.origins == second.origins
    before = Snapshot.of(world.data)
    assert len(before.residences) == 2

    assert_import_changes_nothing(world, text, before)

    assert len(world.data.residences) == 2          # no third residence
    assert world.data.residences[0] == first and world.data.residences[1] == second


def test_reimport_after_split_then_merge_again_creates_none(world: World) -> None:
    text = ged(A)
    world.run(text)
    first, second = sg.split_residence(world.data, world.data.residences[0])
    merged = sg.merge_residences(world.data, first, second)
    assert len(merged.origins) == 1                 # the origin once
    assert len(world.data.residences) == 1

    assert_import_changes_nothing(world, text)
    assert len(world.data.residences) == 1


def test_reimport_after_merge_of_residences_from_different_records_creates_none(
    world: World,
) -> None:
    text = ged(A, B)
    world.run(text)
    a, b = world.data.residences
    assert a.place_id == b.place_id and a.origins != b.origins
    merged = sg.merge_residences(world.data, a, b)
    assert len(merged.origins) == 2                 # both origins
    assert len({o.record_hash for o in merged.origins}) == 2
    before = Snapshot.of(world.data)

    assert_import_changes_nothing(world, text, before)

    assert len(world.data.residences) == 1
    assert world.data.residences[0].origins == merged.origins


def test_reimport_after_split_save_reopen_creates_none(world: World) -> None:
    text = ged(A)
    world.run(text)
    first, second = sg.split_residence(world.data, world.data.residences[0])
    keys = [[(o.instance, o.uid, o.record_hash) for o in f.origins] for f in (first, second)]
    world.save_and_reopen()
    reopened = world.data.residences
    assert [[(o.instance, o.uid, o.record_hash) for o in f.origins] for f in reopened] == keys

    assert_import_changes_nothing(world, text)
    assert len(world.data.residences) == 2


def test_reimport_after_split_and_edit_of_one_half_leaves_both_unchanged(world: World) -> None:
    text = ged(A)
    world.run(text)
    first, second = sg.split_residence(world.data, world.data.residences[0])
    second.role_in_household = "Dräng"
    second.notes = "Redigerad efter delning"
    world.ps.mark_changed("edit")
    before = Snapshot.of(world.data)

    assert_import_changes_nothing(world, text, before)

    assert world.data.residences[1].role_in_household == "Dräng"
    assert world.data.residences[1].notes == "Redigerad efter delning"
    assert world.data.residences[0] == first


def test_identical_resi_records_imported_twice_then_one_split_pairs_by_origin_group(
    world: World,
) -> None:
    two = ged(A, A)
    assert world.run(two).residences_added == 2
    groups = {(o.record_hash, o.instance) for f in world.data.residences for o in f.origins}
    assert len(groups) == 2                          # separate imports: two groups
    sg.split_residence(world.data, world.data.residences[0])
    assert len(world.data.residences) == 3
    assert len({(o.record_hash, o.instance) for f in world.data.residences for o in f.origins}) == 2

    assert_import_changes_nothing(world, two)        # the same two records create nothing
    assert len(world.data.residences) == 3

    before = Snapshot.of(world.data)
    result = world.run(ged(A, A, A))                 # a third identical record
    assert result.residences_added == 1
    assert len(world.data.residences) == 4
    for res_id, old in before.residences.items():
        assert next(r for r in world.data.residences if r.id == res_id) == old
    assert len({(o.record_hash, o.instance) for f in world.data.residences for o in f.origins}) == 3
    assert_import_changes_nothing(world, ged(A, A, A))


def test_legacy_residence_split_before_first_import_is_never_grouped(tmp_path: Path) -> None:
    """A legacy residence has no origin, so its two halves share no Origin_Group.

    Neither half equals the plain incoming record, so neither is claimed: both
    stay unchanged and the record creates one new residence with a notice.
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
    legacy = next(r for r in world.data.residences if r.id == "residence_1")
    first, second = sg.split_residence(world.data, legacy)
    assert first.origins == [] and second.origins == []
    text = (
        "0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Förnamn1 /Testsson/\n1 SEX M\n"
        "1 RESI\n2 DATE FROM 1850 TO 1875\n2 PLAC Backa\n0 TRLR\n"
    )
    before = Snapshot.of(world.data)

    result = world.run(text)

    assert (result.residences_added, result.residences_claimed) == (1, 0)
    assert any("inte kunde kopplas till ett befintligt boende" in str(w) for w in result.warnings)
    after = {r.id: r for r in world.data.residences}
    for res_id, old in before.residences.items():
        assert after[res_id] == old                  # both halves (and all others) unchanged
        assert after[res_id].origins == []
    (new,) = [r for r in world.data.residences if r.id not in before.residences]
    assert len(new.origins) == 1
    # The new residence is a group of its own; a further import creates nothing.
    assert_import_changes_nothing(world, text)
    assert serialize(world.data) != before.canonical
