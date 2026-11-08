"""Regression: comparison family-view expansion bands derive parents from
parent_child_links + sex, never from marriage/partner role.

The band renderer in :class:`ComparisonFamilyView` draws, for each expanded
person, a parent row above the focus person. This used to take *all* partners of
the parent family as parents; it now takes the expanded person's
``parent_child_links`` and orders the two parents by sex (male left, female
right) with a link-order fallback. These tests prove a parent family whose
partners carry role "make"/"maka" still draws BOTH parents in the band.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.merge.comparison_family_view import ComparisonFamilyView


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _person(pid: str, given: str, sex: str) -> Person:
    return Person(id=pid, sex=sex, names=[Name(type="birth", given=given, surname="T")])


def _data(*, father_role: str, mother_role: str,
          father_sex: str = "M", mother_sex: str = "F") -> ProjectData:
    """A focus person p1 with two parents (p2, p3) linked via parent_child_links."""
    focus = _person("p1", "Barn", "M")
    father = _person("p2", "Far", father_sex)
    mother = _person("p3", "Mor", mother_sex)
    family = Family(
        id="f1",
        partners=[
            FamilyPartner(person_id="p2", role=father_role),
            FamilyPartner(person_id="p3", role=mother_role),
        ],
        children=["p1"],
        parent_child_links=[
            ParentChildLink(child_id="p1", parent_id="p2", parentage_type="biological"),
            ParentChildLink(child_id="p1", parent_id="p3", parentage_type="biological"),
        ],
    )
    return ProjectData(
        project=ProjectMetadata(title="Cmp", main_person_id="p1"),
        persons=[focus, father, mother],
        families=[family],
    )


def _band_boxes(view: ComparisonFamilyView, ids: set[str]) -> dict[str, float]:
    """Map each drawn parent box id (from the band) to its x position."""
    return {
        b.person_id: b.x()
        for b in view.person_boxes()
        if b.person_id in ids
    }


def test_make_maka_band_draws_both_parents_sex_ordered(qapp):
    """Reported bug: 'make'/'maka' roles still draw both parents in the band."""
    view = ComparisonFamilyView(0)
    data = _data(father_role="make", mother_role="maka")
    # Expand the focus person so its parent band is rendered.
    view.render(data, "p1", PersonBoxConfig(name=True), expanded=("p1",))

    boxes = _band_boxes(view, {"p2", "p3"})
    assert set(boxes) == {"p2", "p3"}, "Both parents must appear in the band"
    # Male p2 to the left, female p3 to the right.
    assert boxes["p2"] < boxes["p3"]
    view.deleteLater()


def test_father_mother_band_not_regressed(qapp):
    """Existing father/mother roles keep both parents, father left/mother right."""
    view = ComparisonFamilyView(0)
    data = _data(father_role="father", mother_role="mother")
    view.render(data, "p1", PersonBoxConfig(name=True), expanded=("p1",))

    boxes = _band_boxes(view, {"p2", "p3"})
    assert set(boxes) == {"p2", "p3"}
    assert boxes["p2"] < boxes["p3"]
    view.deleteLater()


def test_equal_sex_band_falls_back_to_link_order(qapp):
    """Same-sex parents fall back to link order (first link -> left)."""
    view = ComparisonFamilyView(0)
    data = _data(father_role="make", mother_role="maka",
                 father_sex="M", mother_sex="M")
    view.render(data, "p1", PersonBoxConfig(name=True), expanded=("p1",))

    boxes = _band_boxes(view, {"p2", "p3"})
    assert set(boxes) == {"p2", "p3"}
    assert boxes["p2"] < boxes["p3"]
    view.deleteLater()
