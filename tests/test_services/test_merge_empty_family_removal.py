"""Opt-in removal of empty duplicate families during a merge (Requirement 23.14 to 23.16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from slaktbusken.model.family import FamilyPartner
from slaktbusken.model.media import Annotation, LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import ResearchCase, ResearchEntityLink, ResearchHypothesis
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.persistence.translation_io import FamilyMapping, TranslationData
from slaktbusken.services import merge_planner as mp
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_planner import EmptyFamilyOffer, MergeDecisions, build_plan
from slaktbusken.services.merge_planner_families import is_empty_family, referenced_family_ids
from slaktbusken.services.merge_rules import name_identity
from slaktbusken.services.project_service import ProjectService
from tests.test_services.test_merge_family_integrity import (
    _bio,
    _fam,
    _final,
    _foster_couples_data,
    _person,
    _plan_pair,
)

REMOVED_TEXT = "Familjen F27 är tom och tas bort; F25 behålls."
SUMMARY_LINE = "Tomma dubblettfamiljer borttagna: {n}"


def _plan(data, survivor, retired, remove=(), translation=None):
    return build_plan(
        data, translation,
        MergeDecisions(
            survivor, retired, survivor_id=survivor, survivor_confirmed=True,
            remove_empty_family_ids=tuple(remove),
        ),
    )


def _user_scenario():
    """Foster parents merged in turn; ready for the second merge (r1 <- r2)."""
    data = _foster_couples_data()
    first = _plan_pair(data, "l1", "l2")
    assert first.can_execute
    return _final(data, first)


def _dups(plan):
    return [c for c in plan.warnings if c.code == "duplicate_family"]


def _summary_line(plan):
    (entry,) = plan.change_set.added["merge_history"]
    return [x for x in entry.summary_lines if x.startswith("Tomma dubblettfamiljer")]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def test_user_scenario_offers_only_the_empty_family():
    plan = _plan(_user_scenario(), "r1", "r2")
    assert plan.can_execute
    assert plan.empty_family_offers == (EmptyFamilyOffer("F27", "F25", "Rutger Berg, Lena Berg"),)
    assert plan.removed_empty_family_ids == ()


def test_unchecked_keeps_the_family_and_the_old_warning():
    data = _user_scenario()
    plan = _plan(data, "r1", "r2")
    (warning,) = _dups(plan)
    assert set(warning.subjects) == {"F25", "F27"}
    assert "De behålls som separata familjer." in warning.message
    assert {f.id for f in _final(data, plan).families} == {"F25", "F27", "F28"}
    assert _summary_line(plan) == [SUMMARY_LINE.format(n=0)]


def test_checked_removes_only_the_empty_family_and_keeps_placement_family():
    data = _user_scenario()
    plan = _plan(data, "r1", "r2", remove=["F27"])
    assert plan.can_execute and not plan.blocking
    assert plan.removed_empty_family_ids == ("F27",)
    (warning,) = _dups(plan)
    assert warning.message == REMOVED_TEXT
    assert set(warning.subjects) == {"F25", "F27"}

    final = _final(data, plan)
    assert {f.id for f in final.families} == {"F25", "F28"}
    assert plan.preview.family_count == 2
    assert "F27" in plan.preview.removed_family_ids
    assert "F27" not in plan.preview.changed_family_ids
    assert mp.compute_ledger(final).differences(plan.ledger_after_expected) == {}
    assert _summary_line(plan) == [SUMMARY_LINE.format(n=1)]
    item = next(i for i in plan.items if i.category == "families" and i.item_id == "F27")
    assert item.disposition is mp.Disposition.EXCLUDED


def test_planning_with_removal_does_not_touch_the_project():
    data = _user_scenario()
    before = [f.id for f in data.families]
    _plan(data, "r1", "r2", remove=["F27"])
    assert [f.id for f in data.families] == before


def test_placement_family_is_never_offered_and_cannot_be_removed():
    data = _user_scenario()
    plan = _plan(data, "r1", "r2", remove=["F28"])
    assert all(o.family_id != "F28" for o in plan.empty_family_offers)
    assert [c.code for c in plan.blocking] == ["stale_family_removal"]
    assert not plan.can_execute


def test_both_empty_offers_one_checkbox_for_the_later_family():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("x", "Eva", sex="F")],
        families=[_fam("F1", ["p1", "x"], []), _fam("F2", ["x", "p2"], [])],
    )
    plan = _plan(data, "p1", "p2")
    assert [(o.family_id, o.kept_family_id) for o in plan.empty_family_offers] == [("F2", "F1")]
    removed = _plan(data, "p1", "p2", remove=["F2"])
    assert {f.id for f in _final(data, removed).families} == {"F1"}


def test_three_equivalent_families_are_each_offered_once():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("x", "Eva", sex="F"), _person("c", "Ola")],
        families=[
            _fam("F1", ["p1", "x"], []), _fam("F2", ["x", "p2"], []),
            _fam("F3", ["x", "p1"], []),
        ],
    )
    plan = _plan(data, "p1", "p2")
    offered = [o.family_id for o in plan.empty_family_offers]
    assert sorted(offered) == ["F2", "F3"] and len(set(offered)) == len(offered)
    assert {o.kept_family_id for o in plan.empty_family_offers} == {"F1"}
    both = _plan(data, "p1", "p2", remove=["F2", "F3"])
    assert {f.id for f in _final(data, both).families} == {"F1"}


def test_empty_family_is_removed_in_favour_of_a_nonempty_one_even_if_listed_first():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("x", "Eva", sex="F"), _person("c", "Ola")],
        families=[
            _fam("F1", ["p1", "x"], []),
            _fam("F2", ["x", "p2"], ["c"], [_bio("c", "x"), _bio("c", "p2")]),
        ],
    )
    plan = _plan(data, "p1", "p2")
    assert [(o.family_id, o.kept_family_id) for o in plan.empty_family_offers] == [("F1", "F2")]


def test_nonempty_pair_has_only_the_warning():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("x", "Eva", sex="F"),
                 _person("c1", "Ola"), _person("c2", "Lisa")],
        families=[
            _fam("F1", ["p1", "x"], ["c1"], [_bio("c1", "p1"), _bio("c1", "x")]),
            _fam("F2", ["x", "p2"], ["c2"], [_bio("c2", "x"), _bio("c2", "p2")]),
        ],
    )
    plan = _plan(data, "p1", "p2")
    assert len(_dups(plan)) == 1
    assert plan.empty_family_offers == ()


def test_partners_with_different_roles_are_not_offered():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("x", "Eva", sex="F")],
        families=[_fam("F1", ["p1", "x"], []), _fam("F2", ["x", "p2"], [])],
    )
    data.families[1].partners = [FamilyPartner("x", "mother"), FamilyPartner("p2", "father")]
    plan = _plan(data, "p1", "p2")
    assert len(_dups(plan)) == 1 and plan.empty_family_offers == ()


def _media_link(data):
    data.media.append(MediaItem(
        id="m1", type="image", file="a.jpg", title="Bild",
        linked_entities=[LinkedEntity("family", "F27")],
    ))


def _media_annotation(data):
    data.media.append(MediaItem(
        id="m1", type="image", file="a.jpg", title="Bild",
        annotations=[Annotation(0.1, 0.1, 0.2, 0.2, "family", "F27")],
    ))


def _note_link(data):
    data.research_notes.append(
        ResearchNote("note_1", "Not", "text", [LinkedEntity("family", "F27")])
    )


def _case_link(data):
    data.research_cases.append(
        ResearchCase("case_1", "Fall", primary_entity_ref=ResearchEntityLink("family", "F27"))
    )


def _hypothesis_link(data):
    data.research_hypotheses.append(
        ResearchHypothesis("hyp_1", "case_1", linked_entities=[ResearchEntityLink("family", "F27")])
    )

@pytest.mark.parametrize("add_reference", [_media_link, _media_annotation, _note_link, _case_link, _hypothesis_link])
def test_family_referenced_elsewhere_is_not_empty(add_reference):
    data = _user_scenario()
    add_reference(data)
    assert "F27" in referenced_family_ids(data)
    plan = _plan(data, "r1", "r2")
    assert plan.empty_family_offers == ()
    assert len(_dups(plan)) == 1
    blocked = _plan(data, "r1", "r2", remove=["F27"])
    assert [c.code for c in blocked.blocking] == ["stale_family_removal"]


def test_family_with_translation_mapping_is_not_empty():
    data = _user_scenario()
    translation = TranslationData(families=[FamilyMapping("@F27@", "F27")])
    plan = _plan(data, "r1", "r2", translation=translation)
    assert plan.empty_family_offers == ()


def test_is_empty_family_definition():
    fam = _fam("F", ["a", "b"], [])
    assert is_empty_family(fam, set())
    assert not is_empty_family(fam, {"F"})
    assert not is_empty_family(_fam("F", ["a"], ["c"]), set())
    assert not is_empty_family(_fam("F", ["a"], [], [_bio("c", "a")]), set())
    assert not is_empty_family(_fam("F", ["a"], [], event_ids=["E1"]), set())


# ---------------------------------------------------------------------------
# Stale decisions and decision semantics
# ---------------------------------------------------------------------------


def test_stale_decision_when_family_is_no_longer_empty_blocks_the_plan():
    data = _user_scenario()
    next(f for f in data.families if f.id == "F27").children = ["k"]
    plan = _plan(data, "r1", "r2", remove=["F27"])
    (conflict,) = plan.blocking
    assert conflict.code == "stale_family_removal" and conflict.subjects == ("F27",)
    assert "F27" in conflict.message
    assert not plan.can_execute


def test_unknown_family_id_is_a_stale_decision():
    plan = _plan(_user_scenario(), "r1", "r2", remove=["F999"])
    assert [c.code for c in plan.blocking] == ["stale_family_removal"]


def test_decisions_normalise_equal_and_hash_equal():
    a = MergeDecisions("p1", "p2", remove_empty_family_ids=["F2", "F1", "F2"])
    b = MergeDecisions("p1", "p2", remove_empty_family_ids=("F1", "F2"))
    assert a.remove_empty_family_ids == ("F1", "F2")
    assert a == b and hash(a) == hash(b)
    assert hash(a) != hash(MergeDecisions("p1", "p2"))
    assert MergeDecisions("p1", "p2").remove_empty_family_ids == ()


def test_fingerprint_covers_the_family_to_remove():
    data = _user_scenario()
    plan = _plan(data, "r1", "r2", remove=["F27"])
    index = mp.pri.PersonReferenceIndex.build(data, ("r1", "r2"), None)
    assert plan.fingerprint == mp.compute_fingerprint(data, ("r1", "r2"), index, None, ("F27",))
    next(f for f in data.families if f.id == "F27").children = ["k"]
    index = mp.pri.PersonReferenceIndex.build(data, ("r1", "r2"), None)
    assert plan.fingerprint != mp.compute_fingerprint(data, ("r1", "r2"), index, None, ("F27",))


# ---------------------------------------------------------------------------
# Engine: the removal is committed and persisted
# ---------------------------------------------------------------------------


def _person_named(pid):
    return Person(id=pid, sex="F", names=[Name("birth", "Anna", "Berg")])


def _engine_service(root: Path) -> ProjectService:
    svc = ProjectService()
    svc.create_project("Test", root)
    svc.data.persons.extend([
        _person_named("person_1"), _person_named("person_2"), _person_named("person_3"),
        _person_named("person_4"),
    ])
    svc.data.families.extend([
        _fam("family_1", ["person_1", "person_3"], ["person_4"],
             [_bio("person_4", "person_1"), _bio("person_4", "person_3")]),
        _fam("family_2", ["person_3", "person_2"], []),
    ])
    svc._dirty = True
    svc.save_project()
    return svc


def _engine_merge(svc, remove):
    survivor = next(p for p in svc.data.persons if p.id == "person_1")
    decisions = MergeDecisions(
        "person_1", "person_2", survivor_id="person_1", survivor_confirmed=True,
        primary_name=name_identity(survivor.names[0]), remove_empty_family_ids=tuple(remove),
    )
    plan = build_plan(svc.data, None, decisions, svc.content_revision)
    assert plan.can_execute, ([c.message for c in plan.blocking], plan.unresolved)
    outcome = MergeEngine(svc, None).execute(plan)
    assert outcome.success, outcome.message
    return plan


def test_engine_commits_the_removal_and_records_the_history_line(tmp_path):
    svc = _engine_service(tmp_path)
    plan = _engine_merge(svc, ["family_2"])
    assert plan.removed_empty_family_ids == ("family_2",)
    assert [f.id for f in svc.data.families] == ["family_1"]
    (entry,) = svc.data.merge_history
    assert SUMMARY_LINE.format(n=1) in entry.summary_lines

    reopened = ProjectService()
    reopened.open_project(svc.project_path)
    assert [f.id for f in reopened.data.families] == ["family_1"]
    assert SUMMARY_LINE.format(n=1) in reopened.data.merge_history[0].summary_lines


def test_engine_keeps_the_family_when_unchecked(tmp_path):
    svc = _engine_service(tmp_path)
    _engine_merge(svc, [])
    assert [f.id for f in svc.data.families] == ["family_1", "family_2"]
    assert SUMMARY_LINE.format(n=0) in svc.data.merge_history[0].summary_lines
