"""Candidate redirect, collision and identity planning (task 11.5, Req 29, 30.1, 30.10)."""

from __future__ import annotations

import itertools
import random

import pytest

from slaktbusken.model.merge_candidate import (
    CANDIDATE_ASSESSMENTS,
    MergeCandidate,
    MergeCandidateComment,
    assessment_label,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.translation_io import (
    IdentityAlias,
    PersonMapping,
    TranslationData,
)
from slaktbusken.services import merge_planner as mp
from slaktbusken.services import person_reference_index as pri
from slaktbusken.services.merge_candidate_redirect import plan_candidate_changes
from slaktbusken.services.merge_planner import MergeDecisions, build_plan

DATE = "2024-05-01"


def _counter():
    n = itertools.count(100)
    return lambda: f"cc_{next(n)}"


def _cand(cid, a, b, assessment="unreviewed", enabled=True, case=None, comments=()):
    return MergeCandidate(
        id=cid, person_1_id=a, person_2_id=b, assessment=assessment, enabled=enabled,
        research_case_id=case,
        comments=[MergeCandidateComment(i, d, t) for i, d, t in comments],
    )


def _run(cands, survivor="A", retired="B"):
    return plan_candidate_changes(cands, survivor, retired, DATE, _counter())


def _active(res, cid):
    return next(c for c in res.active if c.id == cid)


# ---------------------------------------------------------------------------
# Redirect and archive
# ---------------------------------------------------------------------------


def test_direct_candidate_archived_in_full():
    direct = _cand("mc_1", "A", "B", "confirmed", False, "rc_1",
                   [("c1", "2020-01-01", "x"), ("c2", "2020-01-02", "y")])
    res = _run([direct])
    assert res.active == []
    (arch,) = res.archived
    assert (arch.id, arch.assessment, arch.enabled, arch.research_case_id, arch.role) == (
        "mc_1", "confirmed", False, "rc_1", "direct")
    assert [(c.id, c.date, c.text) for c in arch.comments] == [
        ("c1", "2020-01-01", "x"), ("c2", "2020-01-02", "y")]


def test_direct_candidate_archived_regardless_of_slot_order():
    assert _run([_cand("mc_1", "B", "A")]).archived[0].role == "direct"


def test_redirect_b_c_to_a_c_keeps_everything_but_adds_one_comment():
    orig = _cand("mc_2", "B", "C", "possible", True, "rc_9", [("c1", "2020-01-01", "x")])
    res = _run([orig])
    assert res.redirected == ["mc_2"] and res.archived == []
    new = _active(res, "mc_2")
    assert (new.person_1_id, new.person_2_id) == ("A", "C")
    assert (new.assessment, new.enabled, new.research_case_id) == ("possible", True, "rc_9")
    assert [(c.id, c.date, c.text) for c in new.comments] == [
        ("c1", "2020-01-01", "x"),
        ("cc_100", DATE,
         "Omdirigerad vid sammanslagning av B in i A. Ursprunglig bedömning: Möjlig dubblett."),
    ]
    assert orig.person_1_id == "B" and len(orig.comments) == 1  # input untouched


def test_redirect_in_second_slot_keeps_slot():
    new = _active(_run([_cand("mc_2", "C", "B")]), "mc_2")
    assert (new.person_1_id, new.person_2_id) == ("C", "A")


@pytest.mark.parametrize(
    "assessment,enabled,expected",
    [
        ("confirmed", True, ("possible", True)),
        ("confirmed", False, ("possible", False)),
        ("possible", True, ("possible", True)),
        ("unreviewed", False, ("unreviewed", False)),
        ("rejected", True, ("rejected", True)),
        ("rejected", False, ("rejected", False)),
    ],
)
def test_redirect_changes_only_confirmed(assessment, enabled, expected):
    new = _active(_run([_cand("mc_2", "B", "C", assessment, enabled)]), "mc_2")
    assert (new.assessment, new.enabled) == expected
    assert len(new.comments) == 1
    assert assessment_label(assessment) in new.comments[0].text


def test_self_candidate_after_redirect_archived():
    res = _run([_cand("mc_3", "B", "B", "possible")])
    assert res.active == [] and res.archived[0].role == "self_after_redirect"


def test_unrelated_candidates_unchanged_and_no_reference_to_retired():
    res = _run([
        _cand("mc_1", "A", "B"), _cand("mc_2", "B", "C"), _cand("mc_3", "D", "E", "rejected"),
        _cand("mc_4", "A", "C"),
    ])
    for c in res.active:
        assert "B" not in (c.person_1_id, c.person_2_id)
    assert _active(res, "mc_3").comments == []
    assert {c.id for c in res.active} | {a.id for a in res.archived} == {
        "mc_1", "mc_2", "mc_3", "mc_4"}


# ---------------------------------------------------------------------------
# Collision
# ---------------------------------------------------------------------------


def _collide(e_assess, c_assess, e_enabled=True, c_enabled=True, e_case=None, c_case=None):
    e = _cand("mc_1", "A", "C", e_assess, e_enabled, e_case,
              [("e1", "2020-01-01", "ex1"), ("e2", "2020-01-02", "ex2")])
    c = _cand("mc_2", "B", "C", c_assess, c_enabled, c_case, [("r1", "2021-01-01", "re1")])
    return _run([e, c]), e, c


@pytest.mark.parametrize("e_assess", CANDIDATE_ASSESSMENTS)
@pytest.mark.parametrize("c_assess", CANDIDATE_ASSESSMENTS)
def test_collision_assessment_table(e_assess, c_assess):
    res, e, c = _collide(e_assess, c_assess)
    survivor = _active(res, "mc_1")
    eff_c = "possible" if c_assess == "confirmed" else c_assess
    equal = eff_c == e_assess
    assert survivor.assessment == (e_assess if equal else "unreviewed")
    assert [x.id for x in survivor.comments[:3]] == ["e1", "e2", "r1"]
    redirect_text = survivor.comments[3].text
    assert redirect_text == (
        f"Omdirigerad vid sammanslagning av B in i A. "
        f"Ursprunglig bedömning: {assessment_label(c_assess)}."
    )
    if equal:
        assert len(survivor.comments) == 4
    else:
        assert len(survivor.comments) == 5
        text = survivor.comments[4].text
        assert text == (
            f"Sammanslagning av B in i A: bedömningarna {assessment_label(e_assess)} (mc_1) "
            f"och {assessment_label(c_assess)} (mc_2) stämde inte överens. "
            "Bedömningen återställd till Ej granskad."
        )
        assert survivor.comments[4].date == DATE
    (arch,) = res.archived
    assert (arch.id, arch.role, arch.assessment) == ("mc_2", "collision", c_assess)
    assert [x.id for x in arch.comments] == ["r1"]
    assert res.collided == ["mc_2"]
    assert all(x.id != "mc_2" for x in res.active)


@pytest.mark.parametrize("e_enabled", [True, False])
@pytest.mark.parametrize("c_enabled", [True, False])
def test_collision_enabled_combinations(e_enabled, c_enabled):
    res, _, _ = _collide("possible", "possible", e_enabled, c_enabled)
    survivor = _active(res, "mc_1")
    assert survivor.enabled is e_enabled
    assert res.archived[0].enabled is c_enabled
    if e_enabled == c_enabled:
        assert len(survivor.comments) == 4
    else:
        assert len(survivor.comments) == 5
        text = survivor.comments[4].text
        assert text.startswith("Sammanslagning av B in i A: kandidaterna mc_1 och mc_2 skilde sig åt.")
        ja = lambda v: "ja" if v else "nej"
        assert f"Aktiv: mc_1 {ja(e_enabled)}, mc_2 {ja(c_enabled)}." in text


@pytest.mark.parametrize(
    "e_case,c_case,kept,commented",
    [
        (None, None, None, False),
        ("rc_1", "rc_1", "rc_1", False),
        ("rc_1", None, "rc_1", True),
        (None, "rc_2", "rc_2", True),
        ("rc_1", "rc_2", "rc_1", True),
        ("", "rc_2", "rc_2", True),
    ],
)
def test_collision_research_case_combinations(e_case, c_case, kept, commented):
    res, _, _ = _collide("possible", "possible", e_case=e_case, c_case=c_case)
    survivor = _active(res, "mc_1")
    assert survivor.research_case_id == kept
    assert res.archived[0].research_case_id == c_case
    assert (len(survivor.comments) == 5) is commented
    if commented:
        text = survivor.comments[4].text
        shown_e = e_case or "inget"
        shown_c = c_case or "inget"
        assert f"Forskningsärende: mc_1 {shown_e}, mc_2 {shown_c}." in text


def test_collision_single_explanatory_comment_for_all_differences():
    res, _, _ = _collide("possible", "rejected", True, False, "rc_1", "rc_2")
    comments = _active(res, "mc_1").comments
    assert len(comments) == 5
    text = comments[4].text
    assert "bedömningarna" in text and "Aktiv:" in text and "Forskningsärende:" in text


def test_collision_independent_of_storage_order():
    cands = [
        _cand("mc_1", "A", "C", "possible", True, None, [("e1", "2020-01-01", "x")]),
        _cand("mc_2", "B", "C", "rejected", False, "rc_1", [("r1", "2021-01-01", "y")]),
        _cand("mc_3", "C", "B", "confirmed", True, "rc_2"),
        _cand("mc_4", "A", "B", "possible"),
        _cand("mc_5", "B", "D", "confirmed"),
        _cand("mc_6", "D", "A", "unreviewed"),
    ]
    baseline = _run(cands)
    rng = random.Random(7)
    for _ in range(10):
        shuffled = cands[:]
        rng.shuffle(shuffled)
        res = _run(shuffled)
        key = lambda r: (
            sorted((c.id, c.person_1_id, c.person_2_id, c.assessment, c.enabled,
                    c.research_case_id, [(x.id, x.date, x.text) for x in c.comments])
                   for c in r.active),
            sorted((a.id, a.role, a.assessment, a.enabled, a.research_case_id) for a in r.archived),
        )
        assert key(res) == key(baseline)


def test_two_redirects_to_same_other_collide_in_id_order():
    res = _run([_cand("mc_2", "B", "C", "possible"), _cand("mc_3", "C", "B", "possible")])
    assert res.redirected == ["mc_2"] and res.collided == ["mc_3"]
    survivor = _active(res, "mc_2")
    assert survivor.assessment == "possible" and len(survivor.comments) == 2


# ---------------------------------------------------------------------------
# Planner integration
# ---------------------------------------------------------------------------


def _person(pid):
    return Person(id=pid, sex="M", names=[Name("birth", "Anna", pid)])


def _plan(data, translation=None):
    return build_plan(
        data, translation,
        MergeDecisions("p1", "p2", survivor_id="p1", survivor_confirmed=True),
    )


def test_registered_and_inventory_complete():
    assert mp.registered_steps("candidates") and mp.registered_steps("identity")
    assert pri.missing_handlers() == []


def test_plan_candidates_history_entry_and_change_set():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("p3")],
        merge_candidates=[
            _cand("merge_candidate_1", "p1", "p2", "confirmed", True, None,
                  [("merge_candidate_comment_1", "2020-01-01", "k")]),
            _cand("merge_candidate_2", "p2", "p3", "confirmed"),
        ],
    )
    plan = _plan(data)
    cs = plan.change_set
    assert cs.removed["merge_candidates"] == {"merge_candidate_1"}
    redirected = cs.replaced["merge_candidates"]["merge_candidate_2"]
    assert (redirected.person_1_id, redirected.assessment) == ("p1", "possible")
    (entry,) = cs.added["merge_history"]
    assert (entry.surviving_person_id, entry.merged_person_id) == ("p1", "p2")
    assert entry.merge_candidate_id == "merge_candidate_1"
    assert [a.id for a in entry.archived_candidates] == ["merge_candidate_1"]
    assert entry.archived_candidates[0].comments[0].text == "k"
    assert plan.candidate_ops.redirected == ("merge_candidate_2",)
    assert plan.candidate_ops.archived == ("merge_candidate_1",)
    # Planning is read-only.
    assert [c.person_1_id for c in data.merge_candidates] == ["p1", "p2"]
    assert data.merge_history == [] and data.id_high_water_marks == {}
    new = mp.apply_change_set(data, cs)
    assert all("p2" not in (c.person_1_id, c.person_2_id) for c in new.merge_candidates)
    assert new.merge_history[0].id.startswith("merge_history_") or new.merge_history[0].id
    assert plan.ledger_after_expected["candidates"] == len(new.merge_candidates)
    assert plan.ledger_after_expected["candidate_comments"] == sum(
        len(c.comments) for c in new.merge_candidates)


def test_plan_identity_moves_mappings_and_rewrites_aliases():
    translation = TranslationData(
        persons=[PersonMapping("@I1@", "p1", "f1"), PersonMapping("@I2@", "p2", "f2"),
                 PersonMapping("@I3@", "p2", None)],
        person_aliases=[IdentityAlias("@I9@", "f9", "p2", "merge_history_0"),
                        IdentityAlias("@I8@", "f8", "p1", "merge_history_0")],
    )
    data = ProjectData(persons=[_person("p1"), _person("p2")])
    plan = _plan(data, translation)
    ops = plan.identity_ops
    assert ops.mappings_moved == ("@I2@", "@I3@")
    assert [(a.gedcom_id, a.fingerprint, a.person_id) for a in ops.new_aliases] == [
        ("@I2@", "f2", "p1"), ("@I3@", None, "p1")]
    (entry,) = plan.change_set.added["merge_history"]
    assert all(a.merge_id == entry.id for a in ops.new_aliases)
    assert [(m.gedcom_id, m.fingerprint) for m in entry.identity_mappings] == [
        ("@I2@", "f2"), ("@I3@", None)]
    assert ops.aliases_rewritten == ("@I9@",)
    assert [(a.person_id, a.merge_id) for a in ops.rewritten_aliases] == [("p1", "merge_history_0")]
    # Translation data is untouched by planning.
    assert [m.app_id for m in translation.persons] == ["p1", "p2", "p2"]
    assert translation.person_aliases[0].person_id == "p2"
