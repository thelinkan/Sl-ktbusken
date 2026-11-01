"""Property 22: Editor section visibility.

**Validates: Requirements 16.1, 16.8**
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hypothesis import given, settings, strategies as st
from PySide6.QtWidgets import QApplication

from slaktbusken.model.merge_candidate import MergeCandidate
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.merge.candidate_section import CandidatesSection

_app = QApplication.instance() or QApplication([])

PIDS = [f"person_{i}" for i in range(5)]
PAIRS = [(a, b) for i, a in enumerate(PIDS) for b in PIDS[i + 1 :]]
ASSESSMENTS = ["unreviewed", "rejected", "likely", "possible"]


@st.composite
def _candidates(draw):
    pairs = draw(st.lists(st.sampled_from(PAIRS), unique=True, max_size=len(PAIRS)))
    out = []
    for n, (a, b) in enumerate(pairs):
        if draw(st.booleans()):
            a, b = b, a
        out.append(
            MergeCandidate(
                id=f"mc_{n}",
                person_1_id=a,
                person_2_id=b,
                assessment=draw(st.sampled_from(ASSESSMENTS)),
                enabled=draw(st.booleans()),
            )
        )
    return out


@settings(max_examples=25, deadline=None)
@given(_candidates(), st.sampled_from(PIDS), st.booleans())
def test_property_22_editor_section_visibility(candidates, pid, historical):
    data = ProjectData()
    data.persons = [
        Person(id=p, sex="M", names=[Name(type="birth", given=p, surname="X")])
        for p in PIDS
    ]
    data.merge_candidates = candidates

    section = CandidatesSection(data, lambda: pid)
    section.set_show_historical(historical)

    mine = [c for c in candidates if pid in (c.person_1_id, c.person_2_id)]
    expected = {
        c.id
        for c in mine
        if historical or (c.assessment != "rejected" and c.enabled)
    }
    shown = section.candidate_ids()
    assert len(shown) == len(set(shown))
    assert set(shown) == expected

    # Toggling back and forth only depends on the project collection.
    section.set_show_historical(not historical)
    section.set_show_historical(historical)
    assert set(section.candidate_ids()) == expected
    section.deleteLater()
