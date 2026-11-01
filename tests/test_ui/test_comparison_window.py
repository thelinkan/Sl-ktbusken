"""Widget tests for the Person_Comparison_Window (task 7.8 and 7.16).

Covers layout, slot search results, Shared_Person markers, the pair action
area, entry-point enablement, diagram lookup equivalence and siblings in the
comparison family views. Requirements 10.1, 12.1, 8.4, 8.5, 10.5.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.comparison_session import SHARED_PERSON_TOOLTIP
from slaktbusken.services.diagram_lookup import DiagramLookup
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.context_menu_builder import ContextMenuBuilder
from slaktbusken.ui.merge.comparison_markers import (
    CandidateAssessmentBadge,
    SharedPersonMarker,
)
from slaktbusken.ui.merge.person_comparison_window import (
    COMPARE_TEXT,
    CONTINUE_TEXT,
    MARK_TEXT,
    NO_PAIR_TEXT,
    PersonComparisonWindow,
)

COMPARE_MENU = "Jämför personer..."
MARK_MENU = "Markera som sammanslagningskandidater"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _person(pid: str, given: str, surname: str = "Test") -> Person:
    return Person(id=pid, sex="F", names=[Name(type="birth", given=given, surname=surname)])


def _link(child: str, parent: str) -> ParentChildLink:
    return ParentChildLink(child, parent, "biological")


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
        _person("person_7", "Dan", "Svensson"),
    ]
    # person_1, person_3 and person_7 are siblings; person_2 shares the father.
    data.families = [
        Family(
            id="family_1",
            partners=[FamilyPartner("person_4", "father"), FamilyPartner("person_5", "mother")],
            children=["person_1", "person_3", "person_7"],
            parent_child_links=[
                _link(c, p)
                for c in ("person_1", "person_3", "person_7")
                for p in ("person_4", "person_5")
            ],
        ),
        Family(
            id="family_2",
            partners=[FamilyPartner("person_4", "father"), FamilyPartner("person_6", "mother")],
            children=["person_2"],
            parent_child_links=[_link("person_2", "person_4"), _link("person_2", "person_6")],
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


# ---------------------------------------------------------------- layout (10.1)


def test_layout_has_two_slots_with_search_view_and_one_table(make_window):
    win = make_window()
    win.resize(1400, 800)
    win.show()
    QTest.qWait(30)
    assert win.splitter.count() == 3
    assert len(win.search_controls) == 2
    assert len(win.family_views) == 2
    assert win.splitter.widget(2) is win.table
    # each Slot_Search_Control sits in the same pane as its family view, above it
    for i in (0, 1):
        pane = win.splitter.widget(i)
        assert win.search_controls[i].parent() is pane
        assert win.family_views[i].parent() is pane
        assert win.search_controls[i].y() < win.family_views[i].y()
    sizes = win.splitter.sizes()
    assert all(s > 0 for s in sizes)


# ------------------------------------------------------------ slot search results


def test_slot_search_results_and_selection(make_window):
    win = make_window("person_1", None)
    control = win.search_controls[1]
    results = control.search("anna")
    assert [r.person_id for r in results] == ["person_1", "person_2"]
    assert control.choose("person_2")
    assert win.slot_persons() == ("person_1", "person_2")
    assert win.family_views[1].focal_id == "person_2"


# ------------------------------------------------------- shared badge (12.1)


def test_shared_marker_on_same_id_in_both_views(make_window):
    # person_1 and person_2 both show person_4 (their father) as a relative.
    win = make_window("person_1", "person_2")
    for view in win.family_views:
        assert "person_4" in view.visible_person_ids()
        shared = [m for m in view.markers() if isinstance(m, SharedPersonMarker)]
        assert shared, "shared person must be marked in each view"
        assert all(m.tooltip_text == SHARED_PERSON_TOOLTIP for m in shared)
        marked_boxes = {m.parentItem().person_id for m in shared}
        assert marked_boxes == {"person_4"}


def test_no_shared_marker_when_views_show_disjoint_persons(make_window, service):
    service.data.persons.append(_person("person_8", "Eva", "Ek"))
    win = make_window("person_1", "person_8")
    assert win.family_views[0].visible_person_ids().isdisjoint(
        win.family_views[1].visible_person_ids()
    )
    for view in win.family_views:
        assert not [m for m in view.markers() if isinstance(m, SharedPersonMarker)]


def test_candidate_badge_shown_for_saved_candidate(make_window, service):
    candidate = service.add_merge_candidate("person_1", "person_2")
    service.set_candidate_assessment(candidate.id, "possible")
    win = make_window("person_1", "person_2")
    badges = [
        m
        for v in win.family_views
        for m in v.markers()
        if isinstance(m, CandidateAssessmentBadge)
    ]
    assert len(badges) == 2
    # the shared marker and the badge are different marker kinds
    assert not isinstance(badges[0], SharedPersonMarker)


# ------------------------------------------------------------ action area (13.x)


def test_action_area_disabled_until_one_person_selected_per_view(make_window):
    win = make_window("person_1", "person_2")
    assert win.pair_text() == NO_PAIR_TEXT
    assert not win.mark_button.isEnabled()
    assert not win.compare_button.isEnabled()
    assert win.mark_button.text() == MARK_TEXT
    assert win.compare_button.text() == COMPARE_TEXT

    win.select_in_view(0, "person_3")
    assert not win.mark_button.isEnabled()
    win.select_in_view(1, "person_6")
    assert win.mark_button.isEnabled()
    assert win.compare_button.isEnabled()
    assert "person_3" in win.pair_text() and "person_6" in win.pair_text()


def test_action_area_continue_button(make_window):
    win = make_window("person_1", None)
    assert win.continue_button.text() == CONTINUE_TEXT
    assert not win.continue_button.isEnabled()
    win.assign_person(1, "person_2")
    assert win.continue_button.isEnabled()
    seen = []
    win.continue_to_merge_requested.connect(lambda a, b: seen.append((a, b)))
    win.continue_button.click()
    assert seen == [("person_1", "person_2")]


# ------------------------------------------------- entry-point enablement (8.4, 8.5)


@pytest.mark.parametrize(
    "count, compare, mark",
    [(0, False, False), (1, True, False), (2, True, True), (3, False, False)],
)
def test_entry_point_enablement_by_selection_size(qapp, count, compare, mark):
    ids = [f"person_{i}" for i in range(1, count + 1)]
    menu = ContextMenuBuilder().build_person_menu("person_1", None, QWidget(), selected_ids=ids)
    entries = {a.text(): a for a in menu.actions() if a.text() in (COMPARE_MENU, MARK_MENU)}
    assert entries[COMPARE_MENU].isEnabled() is compare
    assert entries[MARK_MENU].isEnabled() is mark


# -------------------------------------------------- diagram lookup equivalence


def test_family_views_use_equivalent_lookup_to_fresh_build(make_window, service):
    win = make_window("person_1", "person_2")
    lookup = win.last_lookup
    assert lookup is not None
    assert win.family_views[0].lookup is win.family_views[1].lookup is lookup
    assert lookup.matches(service.data)
    fresh = DiagramLookup.build(service.data)
    for pid in ("person_1", "person_2", "person_3", "person_4"):
        assert lookup.siblings_of(pid) == fresh.siblings_of(pid)


# ------------------------------------------------------- siblings (7.16, R5)


def test_sibling_row_shows_both_siblings_and_ids_are_visible(make_window):
    win = make_window("person_1", None)
    view = win.family_views[0]
    ids = view.visible_person_ids()
    assert {"person_1", "person_3", "person_7"} <= ids
    # three boxes in the sibling row: the focal person and its two siblings
    sibling_boxes = [b for b in view.person_boxes() if b.person_id in {"person_1", "person_3", "person_7"}]
    assert len(sibling_boxes) == 3
    assert len({round(b.sceneBoundingRect().top()) for b in sibling_boxes}) == 1


def test_sibling_ids_take_part_in_shared_markers(make_window):
    # person_3 is a sibling of person_1; show person_3 as slot 2 focal person so
    # that person_1/person_3/person_7 appear in both views.
    win = make_window("person_1", "person_3")
    for view in win.family_views:
        marked = {
            m.parentItem().person_id for m in view.markers() if isinstance(m, SharedPersonMarker)
        }
        assert {"person_7"} <= marked


def test_sibling_shared_markers_cover_every_sibling_in_both_views(make_window):
    # person_1 and person_3 are siblings, so both views draw all three children.
    win = make_window("person_1", "person_3")
    for view in win.family_views:
        marked = {
            m.parentItem().person_id for m in view.markers() if isinstance(m, SharedPersonMarker)
        }
        assert {"person_1", "person_3", "person_7"} <= marked


def test_no_siblings_means_only_focal_person_in_sibling_row(make_window):
    # person_2 is the only child of family_2 (first and only parent family).
    win = make_window("person_2", None)
    ids = win.family_views[0].visible_person_ids()
    assert "person_2" in ids
    assert not ids & {"person_1", "person_3", "person_7"}


def test_half_sibling_is_not_drawn_in_sibling_row(make_window):
    # person_2 shares only the father with person_1; siblings come from the
    # first parent family, so the half-sibling is not drawn in either view.
    win = make_window("person_1", None)
    assert "person_2" not in win.family_views[0].visible_person_ids()
    win = make_window("person_2", None)
    assert "person_1" not in win.family_views[0].visible_person_ids()
