"""Property 21: Exclusive indicator hit targets.

**Validates: Requirements 17.7, 18.6, 18.10**
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from hypothesis import given, settings, strategies as st
from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsSceneMouseEvent,
    QStyleOptionViewItem,
)

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.services.research_index import ResearchCaseCounts
from slaktbusken.ui import person_list_panel as plp
from slaktbusken.ui import research_gateway
from slaktbusken.ui.merge import merge_gateway
from slaktbusken.ui.person_list_panel import ResearchColumnDelegate
from slaktbusken.ui.widgets import person_box as pb


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


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


# ---------------------------------------------------------------------------
# Person list delegate
# ---------------------------------------------------------------------------

CELL = st.builds(
    QRect,
    st.integers(0, 50),
    st.integers(0, 50),
    st.integers(1, 300),
    st.integers(1, 60),
)


@settings(max_examples=30, deadline=None)
@given(
    cell=CELL,
    text_width=st.integers(0, 400),
    has_research=st.booleans(),
    has_candidate=st.booleans(),
)
def test_list_rectangles_never_overlap(qapp, cell, text_width, has_research, has_candidate):
    research, candidate = ResearchColumnDelegate.hit_rectangles(
        cell, text_width, has_research, has_candidate
    )
    if research.isNull() or candidate.isNull():
        return
    assert not research.intersects(candidate)
    for x in range(cell.left(), cell.right() + 1):
        for y in (cell.top(), cell.center().y(), cell.bottom()):
            p = QRect(x, y, 1, 1).topLeft()
            assert not (research.contains(p) and candidate.contains(p))


@settings(max_examples=30, deadline=None)
@given(
    cell=CELL,
    text=st.text(alphabet="0123456789/", max_size=8),
    has_research=st.booleans(),
    has_candidate=st.booleans(),
    fx=st.floats(0, 1),
    fy=st.floats(0, 1),
)
def test_list_click_routes_to_at_most_one_action(
    qapp, cell, text, has_research, has_candidate, fx, fy
):
    delegate = ResearchColumnDelegate()
    research_clicks, candidate_clicks = [], []
    delegate.research_indicator_clicked.connect(research_clicks.append)
    delegate.candidate_indicator_clicked.connect(lambda pid, kind: candidate_clicks.append(pid))

    model = QStandardItemModel(1, 1)
    item = QStandardItem(text)
    item.setData("p1", plp._ROLE_CELL_PERSON_ID)
    if has_research:
        item.setData("#F39C12", plp._ROLE_RESEARCH_COLOR)
    if has_candidate:
        item.setData(plp.CANDIDATE_BLUE, plp._ROLE_CANDIDATE_COLOUR)
    model.setItem(0, 0, item)
    index = model.index(0, 0)

    option = QStyleOptionViewItem()
    option.rect = cell
    pos = QPointF(
        cell.left() + fx * (cell.width() - 1), cell.top() + fy * (cell.height() - 1)
    )
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    delegate.editorEvent(event, model, option, index)
    assert len(research_clicks) + len(candidate_clicks) <= 1


# ---------------------------------------------------------------------------
# Diagram person box
# ---------------------------------------------------------------------------


def _box(research_on, counts, candidate_on, colour, kind, with_state):
    cfg = PersonBoxConfig(research=research_on, merge_candidates=candidate_on)
    display = {"name": "P", "research_counts": ResearchCaseCounts(*counts)}
    if with_state:
        display["candidate_state"] = {"colour": colour, "kind": kind, "tooltip": lambda: ["x"]}
    return pb.PersonBoxItem("p1", display, cfg)


def _press(item, pos: QPointF) -> None:
    event = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.Type.GraphicsSceneMousePress)
    event.setButton(Qt.MouseButton.LeftButton)
    event.setPos(pos)
    item.mousePressEvent(event)


@settings(max_examples=30, deadline=None)
@given(
    research_on=st.booleans(),
    counts=st.tuples(st.integers(0, 5), st.integers(0, 5)).map(lambda t: (min(t), max(t))),
    candidate_on=st.booleans(),
    colour=st.sampled_from(sorted(pb.CANDIDATE_COLOURS)),
    kind=st.sampled_from(["candidates", "history"]),
    with_state=st.booleans(),
    fx=st.floats(0, 1),
    fy=st.floats(0, 1),
)
def test_box_click_triggers_at_most_one_action(
    qapp, research_on, counts, candidate_on, colour, kind, with_state, fx, fy
):
    merge, research = _FakeMerge(), _FakeResearch()
    merge_gateway.set_merge_gateway(merge)
    research_gateway.set_research_gateway(research)
    try:
        box = _box(research_on, counts, candidate_on, colour, kind, with_state)
        ind_r = box._research_indicator()
        ind_c = box._candidate_indicator()
        if ind_r is not None and ind_c is not None:
            hit_r = box._research_hit_rect(ind_r[0])
            hit_c = box._candidate_hit_rect()
            assert not hit_c.intersects(hit_r)
            assert not ind_c[0].intersects(ind_r[0])

        rect = box.boundingRect()
        pos = QPointF(rect.x() + fx * rect.width(), rect.y() + fy * rect.height())
        _press(box, pos)
        assert len(merge.calls) + len(research.calls) <= 1

        # Clicking the centre of each indicator triggers only its own action.
        if ind_c is not None:
            merge.calls.clear()
            research.calls.clear()
            _press(box, ind_c[0].center())
            assert len(merge.calls) == 1 and research.calls == []
        if ind_r is not None:
            merge.calls.clear()
            research.calls.clear()
            _press(box, ind_r[0].center())
            assert len(research.calls) == 1 and merge.calls == []
    finally:
        merge_gateway.set_merge_gateway(None)
        research_gateway.set_research_gateway(None)
