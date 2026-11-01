"""Planning of sources, media, DNA, research and other references (task 11.3, Req 22)."""

from __future__ import annotations

import copy

from slaktbusken.model.dna import DnaCluster, DnaMatch, DnaProfile
from slaktbusken.model.media import Annotation, LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_case import ResearchCase, ResearchEntityLink
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.services import merge_planner as mp
from slaktbusken.services import person_reference_index as pri
from slaktbusken.services.merge_planner import MergeDecisions, build_plan


def _person(pid, **kw):
    return Person(id=pid, sex="M", names=[Name("birth", "Anna", "Berg")], **kw)


def _media(mid, links=(), mentioned=(), annotations=()):
    return MediaItem(
        id=mid, type="image", file=f"{mid}.jpg", title=mid,
        linked_entities=[LinkedEntity("person", p, r) for p, r in links],
        mentioned_person_ids=list(mentioned),
        annotations=[Annotation(0.1 * i, 0, 0.1, 0.1, "person", p) for i, p in enumerate(annotations)],
    )


def _data(persons=None, **kw):
    persons = persons or [_person("p1"), _person("p2")]
    return ProjectData(persons=persons, **kw)


def _plan(data, **choices):
    choices.setdefault("survivor_id", "p1")
    choices.setdefault("survivor_confirmed", True)
    return build_plan(data, None, MergeDecisions("p1", "p2", **choices))


def _items(plan, category):
    return {i.item_id: i for i in plan.items if i.category == category}


def test_module_is_registered_and_handlers_shrink():
    from slaktbusken.services import merge_planner_refs as refs

    for slot, func in (
        ("media_sources", refs.plan_media_sources), ("dna", refs.plan_dna),
        ("research", refs.plan_research), ("other_refs", refs.plan_other_refs),
    ):
        assert func in mp.registered_steps(slot)
    missing = {loc.key for loc in pri.missing_handlers()}
    assert not missing & {
        "media.linked_entities", "media.mentioned_person_ids", "media.annotations",
        "research_note.linked_entities", "research_case.entities",
        "research_hypothesis.entities", "dna_profile.person", "dna_profile.admin_person",
        "dna_cluster.person_ids", "project.main_person_id",
        "project.connection_overrides", "person.profile_media_id",
    }


def test_media_links_collapse_with_first_non_empty_role():
    data = _data(media=[
        _media("m1", links=[("p1", ""), ("p2", "mor"), ("p2", "syster")],
               mentioned=["p2", "x", "p1"]),
    ])
    plan = _plan(data)
    m = plan.change_set.replaced["media"]["m1"]
    assert [(le.entity_id, le.role) for le in m.linked_entities] == [("p1", "mor")]
    assert m.mentioned_person_ids == ["p1", "x"]
    assert _items(plan, "media")["m1"].disposition is mp.Disposition.COMBINED
    assert plan.ledger_before["media_person_links"] - plan.ledger_after_expected["media_person_links"] == 3


def test_annotations_rewritten_kept_separate_with_warning():
    data = _data(media=[_media("m1", annotations=["p1", "p2", "x"])])
    plan = _plan(data)
    m = plan.change_set.replaced["media"]["m1"]
    assert [a.entity_id for a in m.annotations] == ["p1", "p1", "x"]
    assert any(c.code == "annotation_same_person" and not c.is_blocking for c in plan.conflicts)
    assert plan.ledger_after_expected["annotations"] == plan.ledger_before["annotations"]


def test_profile_media_choice_links_unchosen_photo_to_survivor():
    data = _data(
        persons=[_person("p1", profile_media_id="m1"), _person("p2", profile_media_id="m2")],
        media=[_media("m1", links=[("x", "")]), _media("m2", links=[("x", "")])],
    )
    unresolved = _plan(data)
    assert [u.key for u in unresolved.unresolved] == ["profile_media_id"]
    plan = _plan(data, profile_media_id="m1")
    assert not plan.unresolved
    other = plan.change_set.replaced["media"]["m2"]
    assert LinkedEntity("person", "p1", "") in other.linked_entities
    assert "m1" not in plan.change_set.replaced.get("media", {})
    assert plan.ledger_after_expected["media_person_links"] == plan.ledger_before["media_person_links"] + 1


def test_dna_profiles_kept_separate_and_reassigned_with_warning():
    data = _data(
        dna_profiles=[
            DnaProfile("d1", "p1", "c1", "autosomal", kit_id="K1"),
            DnaProfile("d2", "p2", "c1", "autosomal", kit_id="K1", admin_person_id="p2"),
        ],
        dna_clusters=[DnaCluster("k1", "Grupp", person_ids=["a", "p2", "b", "p1"])],
        dna_matches=[DnaMatch("mt1", "d1", "d2")],
    )
    plan = _plan(data)
    prof = plan.change_set.replaced["dna_profiles"]["d2"]
    assert (prof.person_id, prof.admin_person_id) == ("p1", "p1")
    assert plan.ledger_after_expected["dna_profiles"] == 2
    assert plan.change_set.replaced["dna_clusters"]["k1"].person_ids == ["a", "p1", "b"]
    codes = {c.code for c in plan.warnings}
    assert {"dna_duplicate_profile", "dna_match_same_person"} <= codes
    assert _items(plan, "dna_summary")["dna_matches"].detail == "Antal: 1"


def test_research_rewired_notes_collapsed_and_counts_reported():
    link = lambda pid: ResearchEntityLink("person", pid)  # noqa: E731
    data = _data(
        research_cases=[ResearchCase("rc1", primary_entity_ref=link("p2"),
                                     linked_entities=[link("p1"), link("p2")])],
        research_notes=[ResearchNote("rn1", "t", "x", [LinkedEntity("person", "p2"),
                                                       LinkedEntity("person", "p1", "r")])],
    )
    plan = _plan(data)
    case = plan.change_set.replaced["research_cases"]["rc1"]
    assert case.primary_entity_ref.entity_id == "p1"
    assert "p2" not in [le.entity_id for le in case.linked_entities]
    assert plan.research.links_collapsed >= 1 and plan.research.links_rewired >= 1
    note = plan.change_set.replaced["research_notes"]["rn1"]
    assert [(le.entity_id, le.role) for le in note.linked_entities] == [("p1", "r")]


def test_research_failure_aborts_plan(monkeypatch):
    data = _data(research_cases=[ResearchCase("rc1", linked_entities=[ResearchEntityLink("person", "p2")])])

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(mp, "rewire_entity_merge", boom)
    try:
        _plan(data)
    except mp.MergePlanError as exc:
        assert str(exc) == mp.RESEARCH_REWIRE_FAILED_MESSAGE
    else:
        raise AssertionError("expected MergePlanError")


def test_main_person_moves_to_survivor():
    data = _data()
    data.project = ProjectMetadata(title="", main_person_id="p2")
    plan = _plan(data)
    assert plan.change_set.scalars["main_person_id"] == "p1"
    untouched = _plan(_data())
    assert "main_person_id" not in untouched.change_set.scalars


def test_connection_override_cases():
    only_retired = _data()
    only_retired.connection_overrides = {"p2": "foster"}
    assert _plan(only_retired).change_set.scalars["connection_overrides"] == {"p1": "foster"}

    both = _data()
    both.connection_overrides = {"p1": "biological", "p2": "foster"}
    plan = _plan(both)
    assert [u.key for u in plan.unresolved] == ["connection_override"]
    chosen = _plan(both, connection_override="foster")
    assert not chosen.unresolved
    assert chosen.change_set.scalars["connection_overrides"] == {"p1": "foster"}

    equal = _data()
    equal.connection_overrides = {"p1": "foster", "p2": "foster"}
    plan = _plan(equal)
    assert not plan.unresolved
    assert plan.change_set.scalars["connection_overrides"] == {"p1": "foster"}


def test_reference_summary_lists_every_preserve_and_historical_row():
    plan = _plan(_data())
    rows = _items(plan, "references")
    expected = {
        loc.key for loc in pri.PERSON_REFERENCE_INVENTORY
        if loc.rule in (pri.RULE_PRESERVE_SEPARATELY, pri.RULE_HISTORICAL)
    }
    assert set(rows) == expected
    assert "Regel S" in rows["family.event_ids"].detail


def test_source_refs_item_present_and_planning_does_not_mutate():
    data = _data(
        media=[_media("m1", links=[("p1", ""), ("p2", "mor")], annotations=["p1", "p2"])],
        dna_profiles=[DnaProfile("d2", "p2", "c1", "autosomal", admin_person_id="p2")],
        dna_clusters=[DnaCluster("k1", "G", person_ids=["p2", "p1"])],
        research_cases=[ResearchCase("rc1", linked_entities=[ResearchEntityLink("person", "p2")])],
        research_notes=[ResearchNote("rn1", "t", "x", [LinkedEntity("person", "p2")])],
        connection_overrides={"p2": "foster"},
    )
    data.project = ProjectMetadata(title="", main_person_id="p2")
    before = copy.deepcopy(data)
    plan = _plan(data)
    assert data == before
    assert _items(plan, "source_refs")["all"].disposition is mp.Disposition.PRESERVED
    assert plan.ledger_after_expected["dna_profiles"] == plan.ledger_before["dna_profiles"]
    assert plan.ledger_after_expected["source_refs"] == plan.ledger_before["source_refs"]
