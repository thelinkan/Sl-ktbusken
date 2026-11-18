"""The Familj section offers removal of empty duplicate families (Requirement 23.14, 23.16)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.merge_gateway import MergeExecutionResult
from slaktbusken.ui.merge.merge_pages import SECTION_DEFS
from slaktbusken.ui.merge.merge_review_wizard import MergeReviewWizard

FAMILY_PAGE = [s[0] for s in SECTION_DEFS].index("families")
CHECKBOX_TEXT = "Ta bort den tomma dubblettfamiljen family_2 (Eva Berg, Anna Berg)"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Executor:
    def __init__(self) -> None:
        self.plans: list = []

    def execute(self, plan):
        self.plans.append(plan)
        return MergeExecutionResult(True, "")


def _person(pid, given="Anna", sex="F"):
    return Person(id=pid, sex=sex, names=[Name("birth", given, "Berg")])


def _family(fid, partners, children=(), links=()):
    return Family(
        id=fid,
        partners=[FamilyPartner(p, "partner") for p in partners],
        children=list(children),
        parent_child_links=[ParentChildLink(c, p, "biological") for c, p in links],
    )


def _service(second_family_has_child: bool) -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        _person("person_1"), _person("person_2"), _person("person_3", "Eva"),
        _person("person_4", "Ola", "M"), _person("person_5", "Lisa"),
    ]
    data.families = [
        _family("family_1", ["person_3", "person_1"], ["person_4"],
                [("person_4", "person_3"), ("person_4", "person_1")]),
        _family("family_2", ["person_3", "person_2"],
                ["person_5"] if second_family_has_child else [],
                [("person_5", "person_3"), ("person_5", "person_2")]
                if second_family_has_child else []),
    ]
    svc._project_data = data
    return svc


def _wizard(service) -> MergeReviewWizard:
    return MergeReviewWizard(
        service, ["person_1", "person_2"], executor=_Executor(), use_worker=False
    )


def _confirm_survivor(wiz, survivor="person_1") -> None:
    wiz.survivor_page.radios[survivor].setChecked(True)
    wiz.survivor_page.confirm_button.click()


def _family_page(wiz):
    return wiz.section_pages[FAMILY_PAGE]


def test_checkbox_appears_only_in_the_family_section_and_is_unchecked(qapp):
    wiz = _wizard(_service(second_family_has_child=False))
    assert _family_page(wiz).removal_checkbox("family_2") is None  # no survivor yet
    _confirm_survivor(wiz)
    box = _family_page(wiz).removal_checkbox("family_2")
    assert box is not None
    assert box.text() == CHECKBOX_TEXT
    assert not box.isChecked()
    assert _family_page(wiz).removal_checkbox("family_1") is None
    for index, page in enumerate(wiz.section_pages):
        if index != FAMILY_PAGE:
            assert page.removal_checkbox("family_2") is None
    assert wiz.plan.removed_empty_family_ids == ()
    assert wiz.build_decisions().remove_empty_family_ids == ()


def test_toggling_rebuilds_the_plan_with_and_without_the_removal(qapp):
    wiz = _wizard(_service(second_family_has_child=False))
    _confirm_survivor(wiz)
    _family_page(wiz).removal_checkbox("family_2").setChecked(True)
    assert wiz.build_decisions().remove_empty_family_ids == ("family_2",)
    assert wiz.plan.removed_empty_family_ids == ("family_2",)
    assert "family_2" in wiz.plan.preview.removed_family_ids
    texts = [
        _family_page(wiz).problems_list.item(i).text()
        for i in range(_family_page(wiz).problems_list.count())
    ]
    assert any("Familjen family_2 är tom och tas bort; family_1 behålls." in t for t in texts)
    box = _family_page(wiz).removal_checkbox("family_2")
    assert box.isChecked()  # rebuilt checkbox keeps its state

    box.setChecked(False)
    assert wiz.plan.removed_empty_family_ids == ()
    assert not _family_page(wiz).removal_checkbox("family_2").isChecked()
    assert "family_2" not in wiz.plan.preview.removed_family_ids


def test_no_checkbox_when_neither_family_is_empty(qapp):
    wiz = _wizard(_service(second_family_has_child=True))
    _confirm_survivor(wiz)
    assert wiz.plan.empty_family_offers == ()
    assert all(page.removal_checkbox("family_2") is None for page in wiz.section_pages)
    texts = [
        _family_page(wiz).problems_list.item(i).text()
        for i in range(_family_page(wiz).problems_list.count())
    ]
    assert any("har samma partner" in t for t in texts)


def test_changing_the_survivor_resets_the_checkbox(qapp):
    wiz = _wizard(_service(second_family_has_child=False))
    _confirm_survivor(wiz)
    _family_page(wiz).removal_checkbox("family_2").setChecked(True)
    wiz.survivor_page.radios["person_2"].setChecked(True)
    box = _family_page(wiz).removal_checkbox("family_2")
    assert box is not None and not box.isChecked()
    assert wiz.build_decisions().remove_empty_family_ids == ()


def test_decision_reaches_the_executor(qapp, monkeypatch):
    service = _service(second_family_has_child=False)
    executor = _Executor()
    wiz = MergeReviewWizard(service, ["person_1", "person_2"], executor=executor, use_worker=False)
    _confirm_survivor(wiz)
    _family_page(wiz).removal_checkbox("family_2").setChecked(True)
    monkeypatch.setattr(wiz, "_confirm_merge", lambda text: True)
    wiz.check_saved_state = lambda: True
    wiz._on_execute()
    (plan,) = executor.plans
    assert plan.decisions.remove_empty_family_ids == ("family_2",)
    assert plan.removed_empty_family_ids == ("family_2",)
