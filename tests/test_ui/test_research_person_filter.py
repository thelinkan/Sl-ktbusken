"""Property 50: Research overview person filter (task 9.14).

Pure tests, no Qt.

**Validates: Requirements 17.6, 17.8, 17.15, 17.16, 18.14**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
)
from slaktbusken.services.research_index import ResearchIndex
from slaktbusken.ui.research_overview import (
    CaseFilter,
    build_overview_case_rows,
    build_overview_hypothesis_rows,
    build_person_scope,
    build_todo_rows,
)

PERSON_IDS = ["person_1", "person_2", "person_3"]
# "person_ghost" does not exist in the project; a link to it involves nobody.
LINK_TARGETS = PERSON_IDS + ["person_ghost"]
CASE_IDS = [f"case_{i}" for i in range(5)]


def _link(kind: str, entity_id: str) -> ResearchEntityLink:
    return ResearchEntityLink(kind, entity_id)


links = st.lists(
    st.builds(
        _link,
        st.sampled_from(["person", "person", "family"]),
        st.sampled_from(LINK_TARGETS),
    ),
    max_size=3,
)


@st.composite
def projects(draw) -> ProjectData:
    data = ProjectData()
    data.persons = [
        Person(id=pid, sex="M", names=[Name(type="birth", given=pid, surname="T")])
        for pid in PERSON_IDS
    ]
    for case_id in CASE_IDS[: draw(st.integers(0, len(CASE_IDS)))]:
        primary = draw(st.one_of(st.none(), st.builds(_link, st.just("person"), st.sampled_from(LINK_TARGETS))))
        data.research_cases.append(
            ResearchCase(
                id=case_id,
                title=case_id,
                status=draw(st.sampled_from(["open", "in_progress", "on_hold", "closed"])),
                primary_entity_ref=primary,
                linked_entities=draw(links),
            )
        )
    case_pool = CASE_IDS + ["case_missing"]
    for i in range(draw(st.integers(0, 8))):
        data.research_actions.append(
            ResearchAction(
                id=f"action_{i}",
                research_case_id=draw(st.sampled_from(case_pool)),
                completed_date=draw(st.sampled_from([None, "2026-01-01"])),
                sort_order=draw(st.integers(0, 3)),
            )
        )
    for i in range(draw(st.integers(0, 8))):
        data.research_hypotheses.append(
            ResearchHypothesis(
                id=f"hyp_{i}",
                research_case_id=draw(st.sampled_from(case_pool)),
                linked_entities=draw(links),
            )
        )
    return data


def _involved_case_ids(data: ProjectData, pid: str) -> set[str]:
    """Independent definition: the case links the person (primary or linked)."""
    result = set()
    for case in data.research_cases:
        refs = list(case.linked_entities)
        if case.primary_entity_ref is not None:
            refs.append(case.primary_entity_ref)
        if any(r.entity_type == "person" and r.entity_id == pid for r in refs):
            result.add(case.id)
    return result


@given(projects(), st.sampled_from(PERSON_IDS))
def test_person_scope_rows_match_brute_force(data: ProjectData, pid: str) -> None:
    scope = build_person_scope(ResearchIndex(data), pid)
    case_ids = _involved_case_ids(data, pid)
    existing_cases = {c.id for c in data.research_cases}

    # Cases: closed ones included, project order.
    case_rows = build_overview_case_rows(data, person_scope=scope)
    assert [r.case_id for r in case_rows] == [
        c.id for c in data.research_cases if c.id in case_ids
    ]

    # To-do: pending actions of those cases, closed cases included.
    expected_todo = {
        a.id
        for a in data.research_actions
        if a.completed_date is None and a.research_case_id in case_ids
    }
    todo_rows = build_todo_rows(data, person_scope=scope)
    assert {r.action_id for r in todo_rows} == expected_todo
    assert len(todo_rows) == len(expected_todo)

    # Hypotheses: of those cases, or naming the person; owner case must exist.
    expected_hyp = {
        h.id
        for h in data.research_hypotheses
        if h.research_case_id in existing_cases
        and (
            h.research_case_id in case_ids
            or any(l.entity_type == "person" and l.entity_id == pid for l in h.linked_entities)
        )
    }
    hyp_rows = build_overview_hypothesis_rows(data, person_scope=scope)
    assert {r.hypothesis_id for r in hyp_rows} == expected_hyp
    assert len(hyp_rows) == len(expected_hyp)


@given(projects(), st.sampled_from(PERSON_IDS))
def test_case_rows_equal_index_and_indicator_total(data: ProjectData, pid: str) -> None:
    index = ResearchIndex(data)
    scope = build_person_scope(index, pid)
    rows = build_overview_case_rows(data, person_scope=scope)
    assert {r.case_id for r in rows} == {c.id for c in index.cases_for_entity("person", pid)}
    assert len(rows) == index.counts_for_entity("person", pid).total


@given(projects())
def test_none_scope_returns_pre_feature_rows(data: ProjectData) -> None:
    open_ids = [c.id for c in data.research_cases if c.status != "closed"]
    assert [r.case_id for r in build_overview_case_rows(data, None, None)] == open_ids
    assert [r.case_id for r in build_overview_case_rows(data)] == open_ids
    assert [r.case_id for r in build_overview_case_rows(data, CaseFilter(include_closed=True))] == [
        c.id for c in data.research_cases
    ]

    status = {c.id: c.status for c in data.research_cases}
    pending = [
        a.id
        for a in data.research_actions
        if a.completed_date is None and a.research_case_id in status
        and status[a.research_case_id] != "closed"
    ]
    assert {r.action_id for r in build_todo_rows(data, person_scope=None)} == set(pending)

    assert {r.hypothesis_id for r in build_overview_hypothesis_rows(data, person_scope=None)} == {
        h.id for h in data.research_hypotheses if h.research_case_id in status
    }


# ---------------------------------------------------------------------------
# Widget tests (task 9.15)
#
# **Validates: Requirements 17.8, 17.15, 17.16, 18.14**
# ---------------------------------------------------------------------------

import os  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QGraphicsSceneMouseEvent,
    QStyleOptionViewItem,
)

from slaktbusken.model.merge_candidate import MergeCandidate  # noqa: E402
from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService  # noqa: E402
from slaktbusken.persistence.settings_io import PersonBoxConfig  # noqa: E402
from slaktbusken.services.research_index import ResearchCaseCounts  # noqa: E402
from slaktbusken.ui import research_gateway  # noqa: E402
from slaktbusken.ui.merge import merge_gateway  # noqa: E402
from slaktbusken.ui.person_list_panel import (  # noqa: E402
    _RESEARCH_COLUMN,
    _ROLE_CANDIDATE_COLOUR,
    _ROLE_CANDIDATE_KIND,
    _ROLE_RESEARCH_COLOR,
    PersonListPanel,
)
from slaktbusken.ui.research_overview import (  # noqa: E402
    STATUS_ALL,
    STATUS_NOT_CLOSED,
    ResearchOverview,
)
from slaktbusken.ui.widgets import person_box as pb  # noqa: E402
from slaktbusken.ui.widgets import research_marker as rm  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _widget_data() -> ProjectData:
    data = ProjectData()
    data.persons = [
        Person(id="p1", sex="M", names=[Name(type="birth", given="Anna", surname="Test")]),
        Person(id="p2", sex="M", names=[Name(type="birth", given="Bo", surname="Test")]),
        Person(id="p3", sex="M", names=[Name(type="birth", given="Cecilia", surname="Test")]),
    ]
    link = ResearchEntityLink
    data.research_cases = [
        ResearchCase(id="c1", title="Annas ärende", status="open", primary_entity_ref=link("person", "p1")),
        ResearchCase(id="c2", title="Bos ärende", status="in_progress", primary_entity_ref=link("person", "p2")),
        ResearchCase(id="c3", title="Annas stängda", status="closed", linked_entities=[link("person", "p1")]),
        ResearchCase(id="c4", title="Bos stängda", status="closed", linked_entities=[link("person", "p2")]),
    ]
    data.research_actions = [
        ResearchAction(id="a1", research_case_id="c1"),
        ResearchAction(id="a2", research_case_id="c2"),
    ]
    data.research_hypotheses = [
        ResearchHypothesis(id="h1", research_case_id="c1"),
        ResearchHypothesis(id="h2", research_case_id="c2"),
    ]
    return data


def _snapshot(window: ResearchOverview) -> dict:
    return {
        "cases": [r.case_id for r in window.case_rows()],
        "todo": [r.action_id for r in window.todo_rows()],
        "hyp": [r.hypothesis_id for r in window.hypothesis_rows()],
        "case_table": window._cases_table.rowCount(),
        "todo_table": window._todo_table.rowCount(),
        "hyp_table": window._hyp_table.rowCount(),
        "status": window._status_filter.currentData(),
        "banner_hidden": window._banner.isHidden(),
        "person": window.person_filter(),
        "mode": window.mode(),
    }


@pytest.fixture
def overview(qapp):
    window = ResearchOverview(_widget_data())
    yield window
    window.close()


def test_banner_shows_name_and_id(overview) -> None:
    assert overview._banner.isHidden()
    overview.set_person_filter("p1")
    assert not overview._banner.isHidden()
    assert overview._banner_label.text() == "Filtrerat på person: Anna Test (p1)"
    assert overview._show_all_button.text() == "Visa alla"
    assert overview._show_all_button.accessibleName() == "Visa alla"
    assert overview._show_all_button.focusPolicy() != Qt.FocusPolicy.NoFocus
    assert [r.case_id for r in overview.case_rows()] == ["c1", "c3"]
    assert overview._cases_table.rowCount() == 2
    assert overview._todo_table.rowCount() == 1
    assert overview._hyp_table.rowCount() == 1


def test_visa_alla_restores_tables_and_previous_status_choice(overview) -> None:
    overview._status_filter.setCurrentIndex(overview._status_filter.findData("in_progress"))
    before = _snapshot(overview)
    assert before["cases"] == ["c2"]

    overview.set_person_filter("p1")
    assert overview._status_filter.currentData() == STATUS_ALL
    assert not overview._banner.isHidden()

    overview._show_all_button.click()
    after = _snapshot(overview)
    assert after == before
    assert overview._status_filter.currentData() == "in_progress"
    assert overview._banner.isHidden()


def test_visa_alla_restores_default_status_and_all_rows(overview) -> None:
    before = _snapshot(overview)
    overview.set_person_filter("p2")
    overview.set_person_filter(None)
    assert _snapshot(overview) == before


def test_missing_person_shows_empty_state(overview) -> None:
    overview.set_person_filter("person_gone")
    assert not overview._banner.isHidden()
    assert overview._banner_label.text() == "Okänd person (person_gone)"
    assert overview._cases_table.rowCount() == 0
    assert overview._todo_table.rowCount() == 0
    assert overview._hyp_table.rowCount() == 0


def test_person_deleted_while_filtered_shows_empty_state(overview) -> None:
    data = overview._data
    overview.set_person_filter("p3")
    assert overview._banner_label.text() == "Filtrerat på person: Cecilia Test (p3)"
    data.persons = [p for p in data.persons if p.id != "p3"]
    overview.refresh()
    assert overview.person_filter() == "p3"
    assert overview._banner_label.text() == "Okänd person (p3)"
    assert overview._cases_table.rowCount() == 0
    assert overview._todo_table.rowCount() == 0
    assert overview._hyp_table.rowCount() == 0


def test_research_change_keeps_filter(overview) -> None:
    data = overview._data
    overview.set_person_filter("p1")
    data.research_cases.append(
        ResearchCase(
            id="c5",
            title="Nytt",
            status="open",
            primary_entity_ref=ResearchEntityLink("person", "p1"),
        )
    )
    data.research_cases.append(
        ResearchCase(
            id="c6",
            title="Annan",
            status="open",
            primary_entity_ref=ResearchEntityLink("person", "p2"),
        )
    )
    overview.refresh()
    assert overview.person_filter() == "p1"
    assert not overview._banner.isHidden()
    assert [r.case_id for r in overview.case_rows()] == ["c1", "c3", "c5"]
    assert overview._cases_table.rowCount() == 3
    assert overview._status_filter.currentData() == STATUS_ALL


def test_person_filter_independent_of_entity_filter(overview) -> None:
    overview.set_person_filter("p1")
    overview._entity_filter = ("person", "p2")
    overview.set_person_filter(None)
    assert overview._entity_filter == ("person", "p2")


def test_unfiltered_overview_unchanged_by_construction_paths(qapp) -> None:
    # Every pre-feature caller builds the window without a filter: no banner,
    # all open cases, all pending actions and hypotheses.
    for mode in ("cases", "todo", "hypotheses"):
        window = ResearchOverview(_widget_data(), mode)
        try:
            snap = _snapshot(window)
            assert snap["person"] is None and snap["banner_hidden"]
            assert snap["mode"] == mode
            assert snap["status"] == STATUS_NOT_CLOSED
            assert snap["cases"] == ["c1", "c2"]
            assert snap["todo"] == ["a1", "a2"]
            assert snap["hyp"] == ["h1", "h2"]
            assert (snap["case_table"], snap["todo_table"], snap["hyp_table"]) == (2, 2, 2)
        finally:
            window.close()


# --- click routing ---------------------------------------------------------


class _FakeResearch:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def show_research_for_entity(self, entity_type, entity_id, person_filter=None) -> None:
        self.calls.append((entity_type, entity_id, person_filter))


class _FakeMerge:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def open_register(self, person_id=None) -> None:
        self.calls.append(("register", person_id))

    def open_history(self, person_id=None) -> None:
        self.calls.append(("history", person_id))


@pytest.fixture
def gateways():
    research, merge = _FakeResearch(), _FakeMerge()
    research_gateway.set_research_gateway(research)
    merge_gateway.set_merge_gateway(merge)
    yield research, merge
    research_gateway.set_research_gateway(None)
    merge_gateway.set_merge_gateway(None)


def _release(pos: QPointF) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_person_list_research_glyph_passes_person_filter_candidate_does_not(
    qapp, tmp_path, gateways
) -> None:
    research, merge = gateways
    data = _widget_data()
    data.merge_candidates = [
        MergeCandidate(id="m1", person_1_id="p1", person_2_id="p3", assessment="possible")
    ]
    service = AppSettingsService()
    service.SETTINGS_PATH = tmp_path / "app_settings.json"
    service._settings = AppSettings()
    project_service = SimpleNamespace(
        data=data, project_path=None, add_merge_listener=lambda fn: (lambda: None)
    )
    panel = PersonListPanel(SimpleNamespace(app_settings_service=service, project_service=project_service))
    panel.refresh()

    tree = panel._tree_widget
    item = next(
        tree.topLevelItem(r)
        for r in range(tree.topLevelItemCount())
        if tree.topLevelItem(r).data(0, Qt.ItemDataRole.UserRole) == "p1"
    )
    item.setData(_RESEARCH_COLUMN, _ROLE_RESEARCH_COLOR, "#F39C12")
    item.setText(_RESEARCH_COLUMN, "1/2")
    option = QStyleOptionViewItem()
    option.initFrom(tree.viewport())
    option.rect = QRect(0, 0, 200, 24)
    index = tree.indexFromItem(item, _RESEARCH_COLUMN)
    delegate = panel._research_delegate
    research_rect, candidate_rect = delegate._rects_for(option, index)
    assert not research_rect.isNull() and not candidate_rect.isNull()
    assert item.data(_RESEARCH_COLUMN, _ROLE_CANDIDATE_COLOUR) is not None
    assert item.data(_RESEARCH_COLUMN, _ROLE_CANDIDATE_KIND) == "candidates"

    # Candidate glyph: merge gateway only, research gateway untouched.
    assert delegate.editorEvent(_release(QPointF(candidate_rect.center())), tree.model(), option, index)
    assert research.calls == []
    assert merge.calls == [("register", "p1")]

    # Research glyph: research gateway with person_filter.
    assert delegate.editorEvent(_release(QPointF(research_rect.center())), tree.model(), option, index)
    assert research.calls == [("person", "p1", "p1")]
    assert merge.calls == [("register", "p1")]


def test_diagram_box_research_glyph_passes_person_filter_candidate_does_not(
    qapp, gateways
) -> None:
    research, merge = gateways
    data = _widget_data()
    data.merge_candidates = [
        MergeCandidate(id="m1", person_1_id="p1", person_2_id="p3", assessment="possible")
    ]
    rm.begin_diagram_render(data, True, True)
    box = pb.PersonBoxItem(
        "p1",
        {
            "name": "p1",
            "research_counts": ResearchCaseCounts(1, 1),
            "candidate_state": rm.diagram_candidate_state("p1"),
        },
        PersonBoxConfig(research=True, merge_candidates=True),
    )

    def press(pos: QPointF) -> None:
        event = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.Type.GraphicsSceneMousePress)
        event.setButton(Qt.MouseButton.LeftButton)
        event.setPos(pos)
        box.mousePressEvent(event)

    press(box._candidate_indicator()[0].center())
    assert research.calls == []
    assert merge.calls == [("register", "p1")]

    press(box._research_indicator()[0].center())
    assert research.calls == [("person", "p1", "p1")]
