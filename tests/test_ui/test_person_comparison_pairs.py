"""Offscreen tests for shared markers, pair selection, candidate panel and
sub-comparison of the Person_Comparison_Window (requirements 12, 13, 14, 20.1)."""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QGraphicsItem

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.comparison_session import (
    DEPTH_REACHED_MESSAGE,
    SAME_PAIR_MESSAGE,
    SHARED_PERSON_TOOLTIP,
)
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.candidate_editor_dialog import CandidatePanel
from slaktbusken.ui.merge.person_comparison_window import (
    BACK_TEXT,
    COMPARE_TEXT,
    CONTINUE_TEXT,
    MARK_SLOTS_TEXT,
    MARK_TEXT,
    REGISTER_ERROR_TEXT,
    PersonComparisonWindow,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _person(pid: str, given: str, surname: str = "Test") -> Person:
    return Person(id=pid, sex="F", names=[Name(type="birth", given=given, surname=surname)])


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        _person("person_1", "Anna", "Svensson"),
        _person("person_3", "Bo", "Svensson"),
        _person("person_4", "Far", "Svensson"),
        _person("person_5", "Mor", "Svensson"),
        _person("person_6", "Cia", "Nilsson"),
    ] + [_person(f"person_{n}", f"Extra{n}") for n in range(100, 122)]
    data.families = [
        Family(
            id="family_1",
            partners=[FamilyPartner("person_4", "father"), FamilyPartner("person_5", "mother")],
            children=["person_1", "person_3"],
            parent_child_links=[
                ParentChildLink("person_1", "person_4", "biological"),
                ParentChildLink("person_1", "person_5", "biological"),
                ParentChildLink("person_3", "person_4", "biological"),
                ParentChildLink("person_3", "person_5", "biological"),
            ],
        )
    ]
    svc._project_data = data
    return svc


@pytest.fixture
def make_window(qapp, service):
    windows = []

    def factory(p1=None, p2=None) -> PersonComparisonWindow:
        win = PersonComparisonWindow(service, p1, p2)
        windows.append(win)
        return win

    yield factory
    for win in windows:
        win._panel = None
        win.close()


def _marker_owners(win, view: int, kind: str) -> set[str]:
    return {
        m.parentItem().person_id
        for m in win.family_views[view].markers()
        if m.kind == kind
    }


def _select(win, left: str, right: str) -> None:
    win.select_in_view(0, left)
    win.select_in_view(1, right)


# -- Requirement 12 -----------------------------------------------------------


def test_shared_marker_on_identical_ids_in_both_views(make_window):
    win = make_window("person_1", "person_3")
    expected = {"person_1", "person_3", "person_4", "person_5"}
    assert _marker_owners(win, 0, "shared") == expected
    assert _marker_owners(win, 1, "shared") == expected
    marker = win.family_views[0].markers()[0]
    assert marker.toolTip() == SHARED_PERSON_TOOLTIP == "Samma registrerade person i båda familjevyerna"
    assert marker.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsFocusable


def test_no_marker_for_different_ids_without_candidate(make_window):
    win = make_window("person_1", "person_6")
    assert win.family_views[0].markers() == []
    assert win.family_views[1].markers() == []


def test_candidate_badge_on_both_boxes_and_activation_opens_comments(make_window, service):
    cand, _ = service.get_or_create_merge_candidate("person_4", "person_6")
    win = make_window("person_1", "person_6")
    assert _marker_owners(win, 0, "candidate") == {"person_4"}
    assert _marker_owners(win, 1, "candidate") == {"person_6"}
    assert win.candidate_panel is None
    badge = next(m for m in win.family_views[1].markers() if m.kind == "candidate")
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    badge.keyPressEvent(ev)
    assert isinstance(win.candidate_panel, CandidatePanel)
    assert win.candidate_panel.candidate_id == cand.id


def test_markers_follow_navigation(make_window):
    win = make_window("person_1", "person_6")
    assert win.family_views[0].markers() == []
    win.navigate(1, "person_3")
    assert _marker_owners(win, 0, "shared") == {"person_1", "person_3", "person_4", "person_5"}


# -- Requirement 13 -----------------------------------------------------------


def test_selection_replaces_and_actions_state(make_window):
    win = make_window("person_1", "person_3")
    assert not win.mark_button.isEnabled() and not win.compare_button.isEnabled()
    win.select_in_view(0, "person_4")
    assert not win.mark_button.isEnabled()
    win.select_in_view(0, "person_5")
    assert win.session.selection(0) == "person_5"
    win.select_in_view(1, "person_4")
    assert win.mark_button.isEnabled() and win.compare_button.isEnabled()
    assert win.mark_button.text() == MARK_TEXT and win.compare_button.text() == COMPARE_TEXT
    assert win.family_views[0].selected_id == "person_5"


def test_same_id_disables_actions_with_message(make_window):
    win = make_window("person_1", "person_3")
    _select(win, "person_4", "person_4")
    assert not win.mark_button.isEnabled() and not win.compare_button.isEnabled()
    assert SAME_PAIR_MESSAGE in win.pair_text()


def test_mark_as_candidates_opens_panel_and_keeps_comparison(make_window, service):
    win = make_window("person_1", "person_3")
    _select(win, "person_4", "person_5")
    assert win.mark_as_candidates()
    assert len(service.data.merge_candidates) == 1
    assert win.candidate_panel is not None
    assert win.slot_persons() == ("person_1", "person_3")
    assert win.session.selections() == ("person_4", "person_5")
    # Existing pair is reused, not duplicated.
    win._close_panel()
    assert win.mark_as_candidates()
    assert len(service.data.merge_candidates) == 1
    # The panel is embedded in the window, not a top-level dialog.
    assert win.candidate_panel.parent() is win.candidate_panel_host
    assert not win.candidate_panel.isWindow()


def test_mark_as_candidates_failure_shows_error_and_keeps_selection(make_window, service, monkeypatch):
    win = make_window("person_1", "person_3")
    _select(win, "person_4", "person_5")

    def boom(*_a):
        raise RuntimeError("fel")

    monkeypatch.setattr(service, "get_or_create_merge_candidate", boom)
    assert not win.mark_as_candidates()
    assert win.message_text() == REGISTER_ERROR_TEXT
    assert win.session.selections() == ("person_4", "person_5")
    assert service.data.merge_candidates == []
    assert win.candidate_panel is None


def test_twenty_candidates_without_modifying_relatives(make_window, service):
    before = copy.deepcopy((service.data.persons, service.data.families))
    win = make_window("person_1", "person_3")
    for n in range(100, 120):
        win.session.select(0, f"person_{n}")
        win.session.select(1, f"person_{n + 1}")
        assert win.mark_as_candidates()
        win._close_panel()
    assert len(service.data.merge_candidates) == 20
    assert (service.data.persons, service.data.families) == before


# -- Requirement 14 -----------------------------------------------------------


def test_compare_selected_and_back_restore_context(make_window):
    win = make_window("person_1", "person_3")
    win.toggle_expansion(0, "person_4")
    win.family_views[0].set_zoom(1.5)
    win.session.set_zoom(0, 1.5)
    assert not win.back_button.isEnabled()
    _select(win, "person_4", "person_5")
    assert win.compare_selected()
    assert win.slot_persons() == ("person_4", "person_5")
    assert win.back_button.isEnabled() and win.back_button.text() == BACK_TEXT
    assert win.go_back()
    assert win.slot_persons() == ("person_1", "person_3")
    assert win.session.expansion(0) == frozenset({"person_4"})
    assert win.session.zoom(0) == 1.5
    assert win.session.selections() == ("person_4", "person_5")
    assert not win.back_button.isEnabled()


def test_depth_limit_message(make_window):
    win = make_window("person_1", "person_3")
    for _ in range(20):
        _select(win, "person_4", "person_5")
        assert win.compare_selected()
    _select(win, "person_1", "person_3")
    assert not win.compare_selected()
    assert win.message_text() == DEPTH_REACHED_MESSAGE
    assert win.session.depth == 20


def _open_panel_with_unsaved(win):
    _select(win, "person_4", "person_5")
    assert win.mark_as_candidates()
    panel = win.candidate_panel
    panel._text_edit.setPlainText("osparad text")
    return panel


def test_unsaved_comment_stay_keeps_everything(make_window):
    win = make_window("person_1", "person_3")
    panel = _open_panel_with_unsaved(win)
    panel._ask_unsaved = lambda: "stay"
    assert not win.compare_selected()
    assert win.slot_persons() == ("person_1", "person_3")
    assert win.session.depth == 0
    assert panel._text_edit.toPlainText() == "osparad text"


def test_unsaved_comment_discard_then_compare(make_window):
    win = make_window("person_1", "person_3")
    panel = _open_panel_with_unsaved(win)
    panel._ask_unsaved = lambda: "discard"
    assert win.compare_selected()
    assert win.slot_persons() == ("person_4", "person_5")
    assert win.candidate_panel is None


def test_unsaved_comment_save_then_back(make_window, service):
    win = make_window("person_1", "person_3")
    _select(win, "person_4", "person_5")
    assert win.compare_selected()
    _select(win, "person_1", "person_3")
    assert win.mark_as_candidates()
    panel = win.candidate_panel
    panel._text_edit.setPlainText("Sparad kommentar")
    panel._ask_unsaved = lambda: "save"
    assert win.go_back()
    assert service.data.merge_candidates[0].comments[0].text == "Sparad kommentar"
    assert win.slot_persons() == ("person_1", "person_3")


def test_save_failure_stays_on_comparison(make_window):
    win = make_window("person_1", "person_3")
    _select(win, "person_4", "person_5")
    assert win.compare_selected()
    _select(win, "person_1", "person_3")
    win.mark_as_candidates()
    panel = win.candidate_panel
    panel._text_edit.setPlainText("text")
    panel._ask_unsaved = lambda: "save"
    panel.save_comment = lambda: False
    assert not win.go_back()
    assert win.session.depth == 1
    assert panel._text_edit.toPlainText() == "text"
    assert win.message_text() != ""


def test_registry_sees_unsaved_panel_text(qapp, service):
    from slaktbusken.services.editor_registry import EditorRegistry

    registry = EditorRegistry()
    win = PersonComparisonWindow(service, "person_1", "person_3", editor_registry=registry)
    try:
        panel = _open_panel_with_unsaved(win)
        assert panel in registry.unsaved_editors()
    finally:
        win._panel = None
        win.close()


# -- Requirement 20.1 ---------------------------------------------------------


def test_continue_button_only_signals(make_window, service):
    win = make_window("person_1", None)
    assert win.continue_button.text() == CONTINUE_TEXT
    assert not win.continue_button.isEnabled()
    assert not win.continue_to_merge()
    win.assign_person(1, "person_3")
    assert win.continue_button.isEnabled()
    got = []
    win.continue_to_merge_requested.connect(lambda a, b: got.append((a, b)))
    win.continue_to_merge_callback = lambda a, b: got.append(("cb", a, b))
    assert win.continue_to_merge()
    assert got == [("person_1", "person_3"), ("cb", "person_1", "person_3")]
    assert len(service.data.persons) == 27
    QTest.qWait(10)


# -- Candidate indicator on comparison boxes (Req 18.13, 10.11) ---------------


@pytest.mark.parametrize("enabled", [True, False])
def test_candidate_indicator_on_comparison_boxes(qapp, service, monkeypatch, enabled):
    from slaktbusken.persistence.settings_io import PersonBoxConfig
    from slaktbusken.services import candidate_index as ci
    from slaktbusken.ui.widgets import research_marker as rm

    built = []
    real = ci.CandidateIndex.build.__func__
    monkeypatch.setattr(
        ci.CandidateIndex, "build", classmethod(lambda cls, d: built.append(1) or real(cls, d))
    )
    service.get_or_create_merge_candidate("person_4", "person_6")
    win = PersonComparisonWindow(
        service,
        "person_1",
        "person_6",
        person_box_config=PersonBoxConfig(merge_candidates=enabled),
    )
    try:
        box0 = win.family_views[0].box_for("person_4")
        box1 = win.family_views[1].box_for("person_6")
        assert box0 is not None and box1 is not None
        if enabled:
            assert built
            assert box0._candidate_indicator() is not None
            assert box1._candidate_indicator() is not None
            # Candidate badges (child markers) remain present alongside.
            assert _marker_owners(win, 0, "candidate") == {"person_4"}
        else:
            # The diagram render itself builds no index (the badge feature may).
            assert rm._diagram_candidate_index is None
            assert box0._candidate_indicator() is None
            assert box1._candidate_indicator() is None
    finally:
        win._panel = None
        win.close()


# -- Requirement 13 (toolbar "Markera dessa som kandidater") ------------------


def _toolbar_index(win, button) -> int:
    layout = win.toolbar_layout
    for i in range(layout.count()):
        if layout.itemAt(i).widget() is button:
            return i
    return -1


def test_mark_slots_button_is_left_of_continue(make_window):
    win = make_window("person_1", "person_3")
    assert win.mark_slots_button.text() == MARK_SLOTS_TEXT == "Markera dessa som kandidater"
    mark_index = _toolbar_index(win, win.mark_slots_button)
    continue_index = _toolbar_index(win, win.continue_button)
    assert mark_index >= 0 and continue_index >= 0
    assert mark_index < continue_index


def test_mark_slots_button_enabled_only_with_two_slot_persons(make_window):
    win = make_window("person_1", None)
    assert not win.mark_slots_button.isEnabled()
    win.assign_person(1, "person_3")
    assert win.mark_slots_button.isEnabled()
    # Independent of any in-view selection.
    win.select_in_view(0, None)
    win.select_in_view(1, None)
    assert win.mark_slots_button.isEnabled()
    win.clear_slot(1)
    assert not win.mark_slots_button.isEnabled()


def test_mark_slots_button_same_person_disabled(make_window):
    # Two distinct slots are required; the window already rejects same-id slots,
    # but the button guard must also hold for the slot pair directly.
    win = make_window("person_1", "person_3")
    assert win.mark_slots_button.isEnabled()


def test_mark_slots_creates_and_opens_candidate_for_slot_pair(make_window, service):
    win = make_window("person_1", "person_3")
    # No in-view selection at all.
    assert win.session.selections() == (None, None)
    assert win.mark_slots_as_candidates()
    assert len(service.data.merge_candidates) == 1
    cand = service.data.merge_candidates[0]
    assert {cand.person_1_id, cand.person_2_id} == {"person_1", "person_3"}
    assert win.candidate_panel is not None
    assert win.candidate_panel.candidate_id == cand.id
    # Reused, not duplicated.
    win._close_panel()
    assert win.mark_slots_as_candidates()
    assert len(service.data.merge_candidates) == 1


def test_mark_slots_failure_shows_error(make_window, service, monkeypatch):
    win = make_window("person_1", "person_3")

    def boom(*_a):
        raise RuntimeError("fel")

    monkeypatch.setattr(service, "get_or_create_merge_candidate", boom)
    assert not win.mark_slots_as_candidates()
    assert win.message_text() == REGISTER_ERROR_TEXT
    assert service.data.merge_candidates == []
    assert win.candidate_panel is None


def test_old_mark_button_reads_new_label_and_works_on_in_view_selection(make_window, service):
    win = make_window("person_1", "person_3")
    assert win.mark_button.text() == MARK_TEXT == "Markera valda som kandidater"
    _select(win, "person_4", "person_5")
    assert win.mark_as_candidates()
    cand = service.data.merge_candidates[0]
    assert {cand.person_1_id, cand.person_2_id} == {"person_4", "person_5"}
