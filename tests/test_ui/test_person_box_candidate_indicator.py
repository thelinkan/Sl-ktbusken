"""Offscreen tests for the candidate indicator on diagram person boxes (Req 18)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
)

from slaktbusken.model.merge_candidate import MergeCandidate, MergeHistoryEntry
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.services import candidate_index as ci
from slaktbusken.services.research_index import ResearchCaseCounts
from slaktbusken.ui.merge import merge_gateway
from slaktbusken.ui import research_gateway
from slaktbusken.ui.widgets import person_box as pb
from slaktbusken.ui.widgets import research_marker as rm


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _person(pid: str) -> Person:
    return Person(id=pid, sex="U", names=[Name(type="birth", given=pid, surname="Test")])


def _data() -> ProjectData:
    data = ProjectData()
    data.persons = [_person(f"p{i}") for i in range(1, 6)]
    data.merge_candidates = [
        MergeCandidate(id="c1", person_1_id="p1", person_2_id="p2", assessment="confirmed"),
        MergeCandidate(id="c2", person_1_id="p3", person_2_id="p4", assessment="possible"),
    ]
    data.merge_history = [
        MergeHistoryEntry(
            id="h1",
            surviving_person_id="p5",
            merged_person_id="gone",
            merged_person_name="Gone",
            merged_person_lifespan="",
            merge_date="2024-01-01",
        )
    ]
    return data


def _box(person_id="p1", config=None, counts=(0, 0)):
    cfg = config or PersonBoxConfig(research=True, merge_candidates=True)
    display = {
        "name": person_id,
        "research_counts": ResearchCaseCounts(*counts),
        "candidate_state": rm.diagram_candidate_state(person_id),
    }
    return pb.PersonBoxItem(person_id, display, cfg)


def _press(item, pos: QPointF) -> None:
    event = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.Type.GraphicsSceneMousePress)
    event.setButton(Qt.MouseButton.LeftButton)
    event.setPos(pos)
    item.mousePressEvent(event)


class _FakeMerge:
    def __init__(self):
        self.calls = []

    def open_register(self, person_id=None):
        self.calls.append(("register", person_id))

    def open_history(self, person_id=None):
        self.calls.append(("history", person_id))


class _FakeResearch:
    def __init__(self):
        self.calls = []

    def show_research_for_entity(self, entity_type, entity_id, person_filter=None):
        self.calls.append((entity_type, entity_id, person_filter))


@pytest.fixture
def gateways():
    merge, research = _FakeMerge(), _FakeResearch()
    merge_gateway.set_merge_gateway(merge)
    research_gateway.set_research_gateway(research)
    yield merge, research
    merge_gateway.set_merge_gateway(None)
    research_gateway.set_research_gateway(None)


def test_colour_mapping(qapp):
    rm.begin_diagram_render(_data(), True, True)
    assert rm.diagram_candidate_state("p1")["colour"] == ci.BLUE
    assert rm.diagram_candidate_state("p3")["colour"] == ci.ORANGE
    grey = rm.diagram_candidate_state("p5")
    assert grey["colour"] == ci.GREY and grey["kind"] == "history"
    assert rm.diagram_candidate_state("unrelated") is None
    assert rm.diagram_candidate_state("p1")["kind"] == "candidates"
    assert _box("p1")._candidate_indicator()[1] == ci.BLUE


def test_setting_off_builds_no_index_and_draws_nothing(qapp, monkeypatch):
    built = []
    real = ci.CandidateIndex.build.__func__
    monkeypatch.setattr(
        ci.CandidateIndex, "build", classmethod(lambda cls, d: built.append(1) or real(cls, d))
    )
    rm.begin_diagram_render(_data(), True, False)
    assert built == [] and rm._diagram_candidate_index is None
    assert rm.diagram_candidate_state("p1") is None
    assert _box("p1")._candidate_indicator() is None

    # Enabled: exactly one index per render, however many boxes ask.
    rm.begin_diagram_render(_data(), True, True)
    for pid in ("p1", "p2", "p3"):
        rm.diagram_candidate_state(pid)
    assert built == [1]

    # Index exists but the box config disables the indicator.
    off = PersonBoxConfig(merge_candidates=False)
    assert _box("p1", config=off)._candidate_indicator() is None


def test_no_overlap_and_box_size_unchanged(qapp):
    rm.begin_diagram_render(_data(), True, True)
    with_candidate = _box("p1", counts=(1, 1))
    research_rect = with_candidate._research_indicator()[0]
    cand_rect = with_candidate._candidate_indicator()[0]
    assert not cand_rect.intersects(research_rect)
    assert cand_rect.right() < research_rect.left()
    assert cand_rect.y() == research_rect.y()
    assert not with_candidate._candidate_hit_rect().intersects(
        with_candidate._research_hit_rect(research_rect)
    )

    rm.begin_diagram_render(_data(), True, False)
    plain = _box("p1", counts=(1, 1))
    assert plain.boundingRect() == with_candidate.boundingRect()
    assert plain.box_height == with_candidate.box_height
    assert plain._lines == with_candidate._lines


def test_click_routing(qapp, gateways):
    merge, research = gateways
    rm.begin_diagram_render(_data(), True, True)

    box = _box("p1", counts=(1, 1))
    _press(box, box._candidate_indicator()[0].center())
    assert merge.calls == [("register", "p1")] and research.calls == []

    _press(box, box._research_indicator()[0].center())
    assert research.calls == [("person", "p1", "p1")]
    assert merge.calls == [("register", "p1")]

    grey = _box("p5")
    _press(grey, grey._candidate_indicator()[0].center())
    assert merge.calls[-1] == ("history", "p5")


def test_tooltip_uses_own_500ms_timer(qapp):
    rm.begin_diagram_render(_data(), True, True)
    box = _box("p1")
    event = QGraphicsSceneHoverEvent(QGraphicsSceneHoverEvent.Type.GraphicsSceneHoverMove)
    event.setPos(box._candidate_indicator()[0].center())
    box.hoverMoveEvent(event)
    assert pb.CANDIDATE_TOOLTIP_DELAY_MS == 500
    assert box._candidate_timer.interval() == 500 and box._candidate_timer.isActive()
    assert "dublett" in box._candidate_tooltip_text().lower()
    box.hoverLeaveEvent(event)
    assert not box._candidate_timer.isActive()
