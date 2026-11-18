"""The comparison views always show the candidate indicator icon.

The Candidate_Assessment label ("badge") is gone from the comparison window.
Instead the usual Candidate_Indicator (the two-person icon drawn by
``PersonBoxItem``) is shown on every box in both comparison family views,
regardless of ``PersonBoxConfig.merge_candidates`` (which still controls the
normal diagrams). Box sizes in the comparison views equal the normal size.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QGraphicsScene

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.comparison_markers import SharedPersonMarker
from slaktbusken.ui.merge.person_comparison_window import PersonComparisonWindow
from slaktbusken.ui.views.family_view import FamilyView
from slaktbusken.ui.widgets.person_box import (
    _BOX_HEIGHT_MIN,
    _BOX_WIDTH,
    _LINE_HEIGHT,
    _PADDING,
    PersonBoxItem,
)
from slaktbusken.ui.widgets.research_marker import begin_diagram_render


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _person(pid: str, given: str) -> Person:
    return Person(id=pid, sex="F", names=[Name(type="birth", given=given, surname="Svensson")])


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [_person("person_1", "Anna"), _person("person_2", "Anna"), _person("person_3", "Bo")]
    svc._project_data = data
    return svc


def _window(service, config=None) -> PersonComparisonWindow:
    return PersonComparisonWindow(service, "person_1", "person_2", person_box_config=config)


def _boxes(win: PersonComparisonWindow, person_id: str) -> list[PersonBoxItem]:
    return [b for v in win.family_views for b in v.person_boxes() if b.person_id == person_id]


def test_indicator_shown_although_diagram_setting_is_off(qapp, service):
    candidate = service.add_merge_candidate("person_1", "person_2")
    service.set_candidate_assessment(candidate.id, "possible")
    config = PersonBoxConfig(merge_candidates=False)
    win = _window(service, config)
    try:
        for pid in ("person_1", "person_2"):
            boxes = _boxes(win, pid)
            assert boxes
            for box in boxes:
                indicator = box._candidate_indicator()
                assert indicator is not None
                assert indicator[1] == "orange"
        # The shared panel config is never mutated.
        assert config.merge_candidates is False
    finally:
        win.close()


def test_person_without_candidates_has_no_indicator(qapp, service):
    service.add_merge_candidate("person_1", "person_2")
    service.data.persons.append(_person("person_9", "Cia"))
    win = PersonComparisonWindow(
        service, "person_1", "person_9", person_box_config=PersonBoxConfig(merge_candidates=False)
    )
    try:
        assert win.family_views[1].person_boxes()
        for box in win.family_views[1].person_boxes():
            assert box._candidate_indicator() is None
    finally:
        win.close()


def test_no_badge_item_for_saved_candidate(qapp, service):
    candidate = service.add_merge_candidate("person_1", "person_2")
    service.set_candidate_assessment(candidate.id, "confirmed")
    win = _window(service)
    try:
        for view in win.family_views:
            for marker in view.markers():
                assert isinstance(marker, SharedPersonMarker)
            for item in view.scene.items():
                assert type(item).__name__ != "CandidateAssessmentBadge"
        assert not hasattr(win, "open_candidate_comments")
    finally:
        win.close()


def test_main_family_view_still_obeys_its_setting(qapp, service):
    service.add_merge_candidate("person_1", "person_2")
    data = service.data
    config = PersonBoxConfig(merge_candidates=False)
    begin_diagram_render(data, False, False)
    scene = QGraphicsScene()
    FamilyView().render(scene, data, "person_1", config)
    boxes = [i for i in scene.items() if isinstance(i, PersonBoxItem)]
    assert boxes
    assert all(b._candidate_indicator() is None for b in boxes)


def test_comparison_boxes_have_the_normal_height(qapp, service):
    candidate = service.add_merge_candidate("person_1", "person_2")
    service.set_candidate_assessment(candidate.id, "possible")
    win = _window(service)
    try:
        boxes = [b for v in win.family_views for b in v.person_boxes()]
        assert boxes
        for box in boxes:
            expected = max(_BOX_HEIGHT_MIN, len(box._lines) * _LINE_HEIGHT + 2 * _PADDING)
            assert box.box_height == expected
            assert box.boundingRect().height() == expected + 2
    finally:
        win.close()


def test_shared_marker_does_not_overlap_the_indicators(qapp, service):
    candidate = service.add_merge_candidate("person_1", "person_2")
    service.set_candidate_assessment(candidate.id, "possible")
    win = _window(service)
    try:
        added = win.family_views[0].add_shared_marker("person_1", "x")
        added += win.family_views[1].add_shared_marker("person_2", "x")
        assert len(added) == 2
        for box in (b for v in win.family_views for b in v.person_boxes()):
            hit = box._candidate_hit_rect()
            for child in box.childItems():
                if isinstance(child, SharedPersonMarker):
                    rect = child.mapRectToParent(child.boundingRect())
                    assert rect.right() <= _BOX_WIDTH - 18.0  # left of the gender icon
                    if hit is not None:
                        assert not rect.intersects(hit)
    finally:
        win.close()
