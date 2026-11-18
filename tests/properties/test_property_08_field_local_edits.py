"""Property 8: Assessment, enabled and comment edits change only their own field.

**Validates: Requirements 3.6, 4.5, 5.1**
"""

from __future__ import annotations

from dataclasses import asdict

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.merge_candidate import CANDIDATE_ASSESSMENTS
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services import merge_candidate_service as svc

_TEXT = st.text(alphabet="abcABCåäö", min_size=1, max_size=8)
_DATES = st.sampled_from(["", "2020", "2021-05", "2019-12-31"])
_COMMENT = st.tuples(_DATES, _TEXT)


@st.composite
def _setup(draw):
    data = ProjectData(
        project=ProjectMetadata(title="T"),
        persons=[
            Person(id=f"P{i}", sex="U", names=[Name(type="birth", given="A", surname="B")])
            for i in range(2)
        ],
    )
    cand = svc.create_candidate(data, "P0", "P1")
    svc.set_assessment(data, cand.id, draw(st.sampled_from(CANDIDATE_ASSESSMENTS)))
    svc.set_enabled(data, cand.id, draw(st.booleans()))
    for date, text in draw(st.lists(_COMMENT, max_size=5)):
        svc.add_comment(data, cand.id, date, text)
    return data, cand.id


def _snap(data: ProjectData, cid: str) -> dict:
    return asdict(next(c for c in data.merge_candidates if c.id == cid))


def _others(snap: dict, *skip: str) -> dict:
    return {k: v for k, v in snap.items() if k not in skip}


@settings(settings.get_profile("sbk"))
@given(_setup(), st.sampled_from(CANDIDATE_ASSESSMENTS))
def test_assessment_change_keeps_everything_else(setup, new_value) -> None:
    data, cid = setup
    before = _snap(data, cid)
    svc.set_assessment(data, cid, new_value)
    after = _snap(data, cid)
    assert after["assessment"] == new_value
    assert _others(after, "assessment") == _others(before, "assessment")
    assert after["comments"] == before["comments"]


@settings(settings.get_profile("sbk"))
@given(_setup(), st.booleans())
def test_enabled_change_keeps_everything_else(setup, flag) -> None:
    data, cid = setup
    before = _snap(data, cid)
    svc.set_enabled(data, cid, flag)
    after = _snap(data, cid)
    assert after["enabled"] == flag
    assert _others(after, "enabled") == _others(before, "enabled")


@settings(settings.get_profile("sbk"))
@given(_setup(), _COMMENT)
def test_add_comment_keeps_assessment_and_existing_comments(setup, comment) -> None:
    data, cid = setup
    before = _snap(data, cid)
    added = svc.add_comment(data, cid, *comment)
    after = _snap(data, cid)
    assert _others(after, "comments") == _others(before, "comments")
    assert after["comments"][:-1] == before["comments"]
    assert after["comments"][-1]["id"] == added.id
    assert (after["comments"][-1]["date"], after["comments"][-1]["text"]) == comment


@settings(settings.get_profile("sbk"))
@given(_setup(), _COMMENT, st.data())
def test_update_comment_changes_only_that_comment(setup, comment, draw) -> None:
    data, cid = setup
    if not _snap(data, cid)["comments"]:
        svc.add_comment(data, cid, "", "x")
    before = _snap(data, cid)
    idx = draw.draw(st.integers(0, len(before["comments"]) - 1))
    target = before["comments"][idx]["id"]
    svc.update_comment(data, cid, target, *comment)
    after = _snap(data, cid)
    assert _others(after, "comments") == _others(before, "comments")
    assert [c["id"] for c in after["comments"]] == [c["id"] for c in before["comments"]]
    for j, (b, a) in enumerate(zip(before["comments"], after["comments"])):
        if j == idx:
            assert (a["date"], a["text"]) == comment
        else:
            assert a == b
