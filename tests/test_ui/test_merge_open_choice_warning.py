"""A warning with an open choice shows "Varning" in red (preview list and Familj section)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.ui.merge.merge_pages import SECTION_DEFS, SectionPage
from slaktbusken.ui.merge.merge_preview import (
    CHOICE_OPEN_ROLE,
    CHOICE_REQUIRED_SUFFIX,
    ChoiceWarningDelegate,
    MergePreviewWidget,
)
from tests.test_services.test_merge_family_integrity import _final, _foster_couples_data, _plan_pair
from tests.test_ui.test_merge_empty_family_checkbox import (
    _confirm_survivor,
    _family_page,
    _service,
    _wizard,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _flagged(list_widget):
    return [
        list_widget.item(i).text()
        for i in range(list_widget.count())
        if list_widget.item(i).data(CHOICE_OPEN_ROLE)
    ]


def _warning_texts(list_widget):
    return [
        list_widget.item(i).text()
        for i in range(list_widget.count())
        if "Varning" in list_widget.item(i).text()
    ]


def _foster_plan(remove=()):
    data = _foster_couples_data()
    first = _plan_pair(data, "l1", "l2")
    data = _final(data, first)
    return build_plan(
        data, None,
        MergeDecisions("r1", "r2", survivor_id="r1", survivor_confirmed=True,
                       remove_empty_family_ids=tuple(remove)),
    )


def _family_section():
    spec = next(s for s in SECTION_DEFS if s[0] == "families")
    return SectionPage(spec[0], spec[1], spec[2], spec[3])


def test_foster_scenario_marks_duplicate_warning_in_preview_and_family_section(qapp):
    preview = MergePreviewWidget(lambda pid: pid)
    page = _family_section()
    for remove, expect_open in (((), True), (("F27",), False)):
        plan = _foster_plan(remove)
        preview.set_plan(plan)
        page.show_plan(plan, [], {}, frozenset(remove))
        for widget in (preview.problem_list, page.problems_list):
            texts = _warning_texts(widget)
            assert any("F25" in t and "F27" in t for t in texts)
            if expect_open:
                (flagged,) = _flagged(widget)
                assert "F25" in flagged and "F27" in flagged
                assert isinstance(widget.itemDelegate(), ChoiceWarningDelegate)
                item = next(
                    widget.item(i) for i in range(widget.count())
                    if widget.item(i).data(CHOICE_OPEN_ROLE)
                )
                assert item.text().startswith("⚠ Varning:")
                accessible = item.data(Qt.ItemDataRole.AccessibleTextRole)
                assert accessible == item.text() + CHOICE_REQUIRED_SUFFIX
            else:
                assert _flagged(widget) == []


def test_other_warnings_are_never_marked(qapp):
    plan = _foster_plan()
    preview = MergePreviewWidget(lambda pid: pid)
    preview.set_plan(plan)
    others = [c for c in plan.warnings if c.code != "duplicate_family"]
    open_count = len(_flagged(preview.problem_list))
    assert open_count == len([c for c in plan.warnings if c.code == "duplicate_family"])
    assert preview.problem_list.count() >= open_count + len(others)
    assert preview.can_execute() or not plan.can_execute  # warnings never block


def test_wizard_marks_warning_until_checkbox_is_checked(qapp):
    wiz = _wizard(_service(second_family_has_child=False))
    _confirm_survivor(wiz)
    page = _family_page(wiz)
    assert len(_flagged(page.problems_list)) == 1
    assert len(_flagged(wiz.preview.problem_list)) == 1
    assert wiz.preview.execute_button.isEnabled() == wiz.preview.can_execute()

    page.removal_checkbox("family_2").setChecked(True)
    assert _flagged(_family_page(wiz).problems_list) == []
    assert _flagged(wiz.preview.problem_list) == []
    assert _warning_texts(wiz.preview.problem_list)  # still shown, just not red

    _family_page(wiz).removal_checkbox("family_2").setChecked(False)
    assert len(_flagged(_family_page(wiz).problems_list)) == 1


def test_delegate_paints_red_varning_word(qapp):
    preview = MergePreviewWidget(lambda pid: pid)
    preview.set_plan(_foster_plan())
    preview.resize(700, 400)
    preview.show()
    image = preview.problem_list.viewport().grab().toImage()
    reds = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if (c := image.pixelColor(x, y)).red() > 150 and c.green() < 90 and c.blue() < 90
    )
    assert reds > 0


def test_tooltip_depends_on_where_the_open_choice_is_shown(qapp):
    plan = _foster_plan()
    preview = MergePreviewWidget(lambda pid: pid)
    page = _family_section()
    preview.set_plan(plan)
    page.show_plan(plan, [], {}, frozenset())

    def tooltips(widget):
        return [
            widget.item(i).toolTip()
            for i in range(widget.count())
            if widget.item(i).data(CHOICE_OPEN_ROLE)
        ]

    preview_tips = tooltips(preview.problem_list)
    assert preview_tips == ["Det finns ett val att göra i avsnittet Familj."]
    assert tooltips(page.problems_list) == ["Det finns ett val att göra i det här avsnittet."]
    item = next(
        preview.problem_list.item(i) for i in range(preview.problem_list.count())
        if preview.problem_list.item(i).data(CHOICE_OPEN_ROLE)
    )
    assert "det här avsnittet" not in item.data(Qt.ItemDataRole.AccessibleTextRole)
