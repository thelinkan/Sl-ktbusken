"""Offscreen tests for the Person_Comparison_Window (requirements 9, 10, 11, 18.13)."""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import DateValue, Event, Participant, SourceRef
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Source
from slaktbusken.services.comparison_session import LEGEND_TEXT, SELF_COMPARE_MESSAGE
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.comparison_family_view import EMPTY_STATE_TEXT
from slaktbusken.ui.merge.comparison_table import SOURCE_UNAVAILABLE_TEXT
from slaktbusken.ui.merge.person_comparison_window import (
    PersonComparisonWindow,
    open_comparison_window,
)
from slaktbusken.ui.merge.slot_search import NO_PERSON_FOUND


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
        _person("person_2", "Anna", "Svensson"),
        _person("person_3", "Bo", "Svensson"),
        _person("person_4", "Far", "Svensson"),
        _person("person_5", "Mor", "Svensson"),
        _person("person_6", "Cia", "Nilsson"),
    ]
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
    data.sources = [Source(id="source_1", provider="Arkiv", source_type="Kyrkobok", title="Födelsebok")]
    data.events = [
        Event(
            id="event_1",
            type="birth",
            participants=[Participant("person_1", "child")],
            date=DateValue("1850-01-01", "day", [SourceRef("source_1", "good")]),
        ),
        Event(
            id="event_2",
            type="birth",
            participants=[Participant("person_2", "child")],
            date=DateValue("1851-02-02", "day"),
        ),
        Event(
            id="event_3",
            type="death",
            participants=[Participant("person_1", "deceased")],
            date=DateValue("1920-05-05", "day"),
        ),
    ]
    svc._project_data = data
    return svc


@pytest.fixture
def make_window(qapp, service):
    windows = []

    def factory(p1=None, p2=None, **kwargs) -> PersonComparisonWindow:
        win = PersonComparisonWindow(service, p1, p2, **kwargs)
        windows.append(win)
        return win

    yield factory
    for win in windows:
        win.close()


def test_splitter_proportions_35_35_30(make_window):
    win = make_window()
    win.resize(1400, 800)
    win.show()
    QTest.qWait(30)
    sizes = win.splitter.sizes()
    total = sum(sizes)
    shares = [s / total * 100 for s in sizes]
    assert abs(shares[0] - 35) <= 2
    assert abs(shares[1] - 35) <= 2
    assert abs(shares[2] - 30) <= 2


def test_window_is_resizable_and_maximizable(make_window):
    win = make_window()
    assert win.windowTitle() == "Jämför personer"
    assert not win.isModal()
    win.showMaximized()
    assert win.isMaximized()
    win.showNormal()


@pytest.mark.parametrize(
    "p1,p2,expected",
    [
        (None, None, (None, None)),
        ("person_1", None, ("person_1", None)),
        ("person_1", "person_2", ("person_1", "person_2")),
    ],
)
def test_slot_population(make_window, p1, p2, expected):
    win = make_window(p1, p2)
    assert win.slot_persons() == expected
    for view, pid in zip(win.family_views, expected):
        assert view.focal_id == pid
        assert view.is_empty_state() == (pid is None)
    for search, pid in zip(win.search_controls, expected):
        assert search.selected_person_id() == pid


def test_empty_state_and_blank_table(make_window):
    win = make_window()
    assert win.family_views[0].empty_state_text() == EMPTY_STATE_TEXT
    win.show()
    assert win.table.empty_state_visible()
    assert win.table.row_marks() == {}


def test_one_person_leaves_second_column_blank_without_marks(make_window):
    win = make_window("person_1", None)
    assert win.table.row_marks() == {}
    birth = win.table.row_index("birth")
    assert win.table.cell_text(birth, 1) != ""
    assert win.table.cell_text(birth, 2) == ""


def test_focus_person_2_search_with_one_person(make_window):
    win = make_window("person_1", None)
    win.focus_slot_search(1)
    win.show()
    QTest.qWait(10)
    assert win.focusWidget() is win.search_controls[1].line_edit()


def test_open_function_focuses_person_2_for_one_person_and_editor(qapp, service):
    win = open_comparison_window(None, service, "person_1")
    try:
        assert win.slot_persons() == ("person_1", None)
        assert win.focusWidget() is win.search_controls[1].line_edit()
    finally:
        win.close()
    win = open_comparison_window(None, service, "person_1", None, focus_search=True)
    try:
        assert win.focusWidget() is win.search_controls[1].line_edit()
    finally:
        win.close()
    win = open_comparison_window(None, service, "person_1", "person_2", focus_search=False)
    try:
        assert win.slot_persons() == ("person_1", "person_2")
    finally:
        win.close()


def test_open_with_pair_from_register_shows_candidate(make_window, service):
    candidate = service.add_merge_candidate("person_1", "person_2")
    service.set_candidate_assessment(candidate.id, "possible")
    service.add_candidate_comment(candidate.id, "2024-05-01", "Samma präst")
    win = make_window("person_1", "person_2")
    text = win.candidate_text()
    assert "Möjlig" in text or "möjlig" in text.lower()
    assert "Samma präst" in text
    # A different pair shows no carried-over candidate (9.12).
    win.assign_person(1, "person_6")
    assert win.candidate_text() == ""


def test_swap_including_empty_slot(make_window):
    win = make_window("person_1", "person_2")
    win.swap_button.click()
    assert win.slot_persons() == ("person_2", "person_1")
    assert win.family_views[0].focal_id == "person_2"
    assert win.search_controls[0].selected_person_id() == "person_2"

    one = make_window("person_1", None)
    one.swap()
    assert one.slot_persons() == (None, "person_1")
    assert one.family_views[0].is_empty_state()
    assert not one.family_views[1].is_empty_state()


def test_self_compare_is_rejected_with_message(make_window):
    win = make_window("person_1", "person_2")
    assert win.assign_person(1, "person_1") is False
    assert win.message_text() == SELF_COMPARE_MESSAGE == "En person kan inte jämföras med sig själv."
    assert win.slot_persons() == ("person_1", "person_2")
    assert win.search_controls[1].selected_person_id() == "person_2"
    assert win.assign_person(1, "person_6") is True
    assert win.message_text() == ""


def test_slot_search_lists_distinguishable_results_and_places_person(make_window):
    win = make_window("person_1", None)
    control = win.search_controls[1]
    results = control.search("anna")
    ids = [r.person_id for r in results]
    assert ids == ["person_1", "person_2"]
    texts = control.row_texts()
    assert len(set(texts)) == 2
    assert "[person_2]" in texts[1] and "1851-02-02" in texts[1]
    assert control.search("a") == []
    assert control.search("finnsinte") == []
    assert control.row_texts() == [NO_PERSON_FOUND]
    assert win.slot_persons() == ("person_1", None)
    control.search("cia")
    assert control.choose("person_6")
    assert win.slot_persons() == ("person_1", "person_6")


def test_table_marks_differs_and_missing(make_window):
    win = make_window("person_1", "person_2")
    table = win.table
    birth = table.row_index("birth")
    death = table.row_index("death")
    name = table.row_index("name")
    assert table.row_mark(birth) == "Avviker"
    assert table.row_mark(death) == "Saknas"
    assert table.cell_text(death, 2) == "Saknas"
    assert table.row_mark(name) == ""
    assert table.legend_text().endswith(LEGEND_TEXT)
    assert table.table.horizontalHeaderItem(3).toolTip() == LEGEND_TEXT


def test_source_opening_and_unavailable_source(make_window):
    win = make_window("person_1", "person_2")
    table = win.table
    assert table.open_source("source_1") is True
    assert table.error_text() == ""
    assert table.open_source("source_missing") is False
    assert table.error_text() == SOURCE_UNAVAILABLE_TEXT
    assert table.row_mark(table.row_index("birth")) == "Avviker"


def test_family_view_shows_parents_partners_children_and_siblings(make_window, service):
    service.data.families.append(
        Family(
            id="family_2",
            partners=[FamilyPartner("person_1", "mother"), FamilyPartner("person_6", "father")],
            children=["person_2"],
            parent_child_links=[ParentChildLink("person_2", "person_1", "biological")],
        )
    )
    win = make_window("person_1", None)
    ids = win.family_views[0].visible_person_ids()
    assert {"person_1", "person_3", "person_4", "person_5", "person_6", "person_2"} <= ids


def test_views_are_independent_and_slot_person_unchanged(make_window):
    win = make_window("person_1", "person_2")
    left, right = win.family_views
    win.navigate(0, "person_3")
    assert left.focal_id == "person_3"
    assert right.focal_id == "person_2"
    assert win.slot_persons() == ("person_1", "person_2")
    left.graphics_view.set_zoom(2.0)
    assert win.session.zoom(0) == pytest.approx(2.0)
    assert right.zoom_factor == pytest.approx(1.0)
    win.toggle_expansion(0, "person_4")
    assert win.session.expansion(0) == frozenset({"person_4"})
    assert win.session.expansion(1) == frozenset()
    assert "person_4" in left.visible_person_ids()
    win.select_in_view(1, "person_2")
    assert win.session.selection(0) is None
    assert "person_2" in win.selected_label_text(1)


def test_views_share_one_render_scoped_lookup(make_window):
    win = make_window("person_1", "person_2")
    assert win.last_lookup is not None
    assert win.family_views[0].lookup is win.family_views[1].lookup is win.last_lookup


def test_deleting_slot_person_clears_slot_and_keeps_other(make_window, service):
    win = make_window("person_1", "person_2")
    win.navigate(0, "person_3")
    service.data.persons = [p for p in service.data.persons if p.id != "person_1"]
    service.notify_merge_changed()
    QTest.qWait(200)
    assert win.slot_persons() == (None, "person_2")
    assert win.family_views[0].is_empty_state()
    assert win.family_views[1].focal_id == "person_2"
    assert win.table.row_marks() == {}


def test_refresh_after_change_keeps_focus_and_zoom(make_window, service):
    win = make_window("person_1", "person_2")
    win.navigate(1, "person_3")
    win.family_views[1].graphics_view.set_zoom(1.5)
    service.data.persons[1].names[0].given = "Berta"
    service.notify_merge_changed()
    QTest.qWait(200)
    assert win.family_views[1].focal_id == "person_3"
    assert win.family_views[1].zoom_factor == pytest.approx(1.5)
    assert "Berta" in win.table.cell_text(win.table.row_index("name"), 2)


def test_comparison_stage_is_read_only(make_window, service):
    before = copy.deepcopy(service.data)
    revision = service.revision
    win = make_window("person_1", "person_2")
    win.show()
    win.swap()
    win.assign_person(1, "person_6")
    win.assign_person(1, "person_1")
    win.navigate(0, "person_3")
    win.toggle_expansion(0, "person_4")
    win.select_in_view(0, "person_3")
    win.search_controls[1].search("anna")
    win.table.open_source("source_1")
    win.table.open_source("source_missing")
    win.refresh()
    assert service.data == before
    assert service.revision == revision


# --------------------------------------------------------------------------
# Remembered internal state: splitter sizes and per-view zoom (per computer).


def test_comparison_state_store_none_opens_and_closes_cleanly(make_window):
    """A window without a state store works exactly like before."""
    win = make_window("person_1", "person_2")
    win.resize(1400, 800)
    win.show()
    QTest.qWait(30)
    # Default proportions are untouched, no error on close.
    sizes = win.splitter.sizes()
    assert len(sizes) == 3
    assert win.close()


def test_comparison_state_saved_on_close(make_window):
    """Closing writes splitter sizes and both zoom levels under the window key."""
    store: dict[str, dict] = {}
    win = make_window("person_1", "person_2", state_store=lambda: store)
    win.resize(1400, 800)
    win.show()
    QTest.qWait(30)
    win.session.set_zoom(0, 1.5)
    win.session.set_zoom(1, 0.5)
    recorded = list(win.splitter.sizes())
    win.close()

    assert "PersonComparisonWindow" in store
    entry = store["PersonComparisonWindow"]
    assert entry["splitter_sizes"] == recorded
    assert entry["zoom"] == [1.5, 0.5]


def test_comparison_state_restored_on_open(make_window):
    """A new window with a populated store restores splitter sizes and zoom."""
    store: dict[str, dict] = {}
    first = make_window("person_1", "person_2", state_store=lambda: store)
    first.resize(1400, 800)
    first.show()
    QTest.qWait(30)
    first.session.set_zoom(0, 2.0)
    first.session.set_zoom(1, 0.5)
    # Nudge the splitter so the stored sizes differ from the 35/35/30 default.
    total = sum(first.splitter.sizes())
    custom = [int(total * 0.5), int(total * 0.3), 0]
    custom[2] = total - custom[0] - custom[1]
    first.splitter.setSizes(custom)
    saved_sizes = list(first.splitter.sizes())
    first.close()

    second = make_window("person_1", "person_2", state_store=lambda: store)
    second.resize(1400, 800)
    second.show()
    QTest.qWait(30)

    assert second.splitter.sizes() == saved_sizes
    assert second.session.zoom(0) == pytest.approx(2.0)
    assert second.session.zoom(1) == pytest.approx(0.5)
    assert second.family_views[0].zoom_factor == pytest.approx(2.0)
    assert second.family_views[1].zoom_factor == pytest.approx(0.5)


def test_comparison_state_garbage_falls_back_to_defaults(make_window):
    """Mismatched/garbage stored state falls back to 35/35/30 and default zoom."""
    store = {
        "PersonComparisonWindow": {
            "splitter_sizes": ["a", "b", "c"],
            "zoom": ["x", None],
        }
    }
    win = make_window("person_1", "person_2", state_store=lambda: store)
    win.resize(1400, 800)
    win.show()
    QTest.qWait(30)

    sizes = win.splitter.sizes()
    total = sum(sizes)
    shares = [s / total * 100 for s in sizes]
    assert abs(shares[0] - 35) <= 2
    assert abs(shares[1] - 35) <= 2
    assert abs(shares[2] - 30) <= 2
    assert win.session.zoom(0) == pytest.approx(1.0)
    assert win.session.zoom(1) == pytest.approx(1.0)
    assert win.close()


def test_comparison_state_wrong_sum_keeps_default_proportions(make_window):
    """Splitter sizes whose sum is far from the width are ignored."""
    store = {
        "PersonComparisonWindow": {
            "splitter_sizes": [10, 10, 10],
            "zoom": [1.0, 1.0],
        }
    }
    win = make_window("person_1", "person_2", state_store=lambda: store)
    win.resize(1400, 800)
    win.show()
    QTest.qWait(30)

    sizes = win.splitter.sizes()
    total = sum(sizes)
    shares = [s / total * 100 for s in sizes]
    assert abs(shares[0] - 35) <= 2
    assert abs(shares[1] - 35) <= 2
    assert abs(shares[2] - 30) <= 2
    assert win.close()
