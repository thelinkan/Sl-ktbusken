"""Property 9: A failed candidate edit leaves the stored state unchanged.

A candidate edit that fails validation, names an unknown person/candidate/case
or raises during the operation (including creation of a research case with two
links) leaves the stored candidates (deep-equal), the id high-water marks, the
research cases, the dirty flag and the revision counters as they were.

**Validates: Requirements 3.9, 6.4, 13.7**
"""

from __future__ import annotations

import copy
from unittest import mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.merge_candidate import CANDIDATE_ASSESSMENTS
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_case import ResearchCase
from slaktbusken.services import merge_candidate_service as mcs
from slaktbusken.services.project_service import ProjectService, ValidationError

_TEXT = st.text(alphabet="abcABCåäö", min_size=1, max_size=8)


@st.composite
def _setup(draw):
    data = ProjectData(
        project=ProjectMetadata(title="T"),
        persons=[
            Person(id=f"P{i}", sex="U", names=[Name(type="birth", given="A", surname="B")])
            for i in range(3)
        ],
        research_cases=[ResearchCase(id="research_case_1", title="Befintligt")],
    )
    svc = ProjectService()
    svc._project_data = data
    pairs = draw(st.lists(st.sampled_from([("P0", "P1"), ("P1", "P2"), ("P0", "P2")]),
                          min_size=1, max_size=3, unique=True))
    for a, b in pairs:
        cand = svc.add_merge_candidate(a, b)
        svc.set_candidate_assessment(cand.id, draw(st.sampled_from(CANDIDATE_ASSESSMENTS)))
        svc.set_candidate_enabled(cand.id, draw(st.booleans()))
        for text in draw(st.lists(_TEXT, max_size=3)):
            svc.add_candidate_comment(cand.id, "", text)
    # Start from a clean, counted state.
    svc._dirty_value = False
    return svc


def _state(svc: ProjectService) -> dict:
    d = svc.data
    return {
        "candidates": copy.deepcopy(d.merge_candidates),
        "marks": dict(d.id_high_water_marks),
        "cases": copy.deepcopy(d.research_cases),
        "dirty": svc.is_dirty,
        "revision": svc.revision,
        "content_revision": svc.content_revision,
        "clean_content_revision": svc.clean_content_revision,
    }


def _boom(*_a, **_k):
    raise RuntimeError("injected")


_FAIL_VALIDATION = lambda *a, **k: ["fel"]  # noqa: E731

# (label, operation, patches) where patches map a mcs attribute to a replacement.
_OPS = [
    ("self_pair", lambda s, c: s.add_merge_candidate("P0", "P0"), {}),
    ("unknown_person", lambda s, c: s.add_merge_candidate("P0", "nobody"), {}),
    ("duplicate_pair", lambda s, c: s.add_merge_candidate(c.person_1_id, c.person_2_id), {}),
    ("bad_assessment", lambda s, c: s.set_candidate_assessment(c.id, "bogus"), {}),
    ("unknown_case", lambda s, c: s.set_candidate_research_case(c.id, "nope"), {}),
    ("unknown_cand", lambda s, c: s.set_candidate_enabled("nope", True), {}),
    ("unknown_cand_case", lambda s, c: s.create_research_case_for_candidate("nope"), {}),
    ("empty_comment", lambda s, c: s.add_candidate_comment(c.id, "", "   "), {}),
    ("bad_date", lambda s, c: s.add_candidate_comment(c.id, "xx", "text"), {}),
    ("unknown_comment", lambda s, c: s.update_candidate_comment(c.id, "nope", "", "t"), {}),
    ("inj_assess", lambda s, c: s.set_candidate_assessment(c.id, "confirmed"),
     {"validate_merge_candidate": _FAIL_VALIDATION}),
    ("inj_assess_raise", lambda s, c: s.set_candidate_enabled(c.id, False),
     {"validate_merge_candidate": _boom}),
    ("inj_comment", lambda s, c: s.add_candidate_comment(c.id, "", "ny"),
     {"validate_merge_candidate_comment": _FAIL_VALIDATION}),
    ("inj_create", lambda s, c: s.add_merge_candidate("P0", "nobody2"),
     {"validate_merge_candidate": _FAIL_VALIDATION}),
    ("inj_case_validation", lambda s, c: s.create_research_case_for_candidate(c.id),
     {"validate_research_case": _FAIL_VALIDATION}),
    ("inj_case_candidate_validation", lambda s, c: s.create_research_case_for_candidate(c.id),
     {"validate_merge_candidate": _FAIL_VALIDATION}),
    ("inj_case_raise", lambda s, c: s.create_research_case_for_candidate(c.id),
     {"validate_merge_candidate": _boom}),
    ("inj_case_idgen_raise", lambda s, c: s.create_research_case_for_candidate(c.id),
     {"ResearchIdGenerator": _boom}),
]


@settings(settings.get_profile("sbk"))
@given(_setup(), st.sampled_from(range(len(_OPS))), st.data())
def test_failed_candidate_edit_leaves_state_unchanged(svc, op_index, draw) -> None:
    _label, op, patches = _OPS[op_index]
    cands = svc.data.merge_candidates
    cand = cands[draw.draw(st.integers(0, len(cands) - 1))]
    if _label == "unknown_comment" and not cand.comments:
        svc.add_candidate_comment(cand.id, "", "x")
        svc._dirty_value = False
    before = _state(svc)

    managers = [mock.patch.object(mcs, name, fn) for name, fn in patches.items()]
    for m in managers:
        m.start()
    try:
        with pytest.raises((ValidationError, KeyError, RuntimeError)):
            op(svc, cand)
    finally:
        for m in managers:
            m.stop()

    assert _state(svc) == before
