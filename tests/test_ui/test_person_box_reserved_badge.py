"""Tests for the opt-in reserved badge height on PersonBoxItem (ITEM 4).

A Candidate_Assessment badge in the comparison family view used to be painted
over the box, covering the birth line. PersonBoxItem now offers an opt-in
``set_reserved_badge_rows`` used only by the comparison view: it grows
``box_height`` and the bounding rect so the badge sits in reserved space below
the text. The normal diagram never calls it, so its box height is unchanged.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QGraphicsScene

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.merge.comparison_family_view import ComparisonFamilyView
from slaktbusken.ui.merge.comparison_markers import BADGE_HEIGHT, CandidateAssessmentBadge
from slaktbusken.ui.widgets.person_box import PersonBoxItem

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.diagram_lookup import active_lookup, set_active_lookup


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _box(**config_kwargs) -> PersonBoxItem:
    config = PersonBoxConfig(name=True, birth_date=True, **config_kwargs)
    display = {"name": "Anna Svensson", "birth_date": "1888-11-14", "sex": "F"}
    return PersonBoxItem("person_1", display, config)


def test_reserving_one_badge_row_grows_box_by_badge_amount(qapp):
    box = _box()
    base_height = box.box_height
    base_rect = box.boundingRect().height()
    assert box.extra_bottom_height == 0.0

    box.set_reserved_badge_rows(1)
    grown = box.box_height
    reserved = box.extra_bottom_height
    assert reserved > 0.0
    assert grown == pytest.approx(base_height + reserved)
    assert grown > base_height + BADGE_HEIGHT - 1.0
    # The bounding rect grows by the same reserved amount.
    assert box.boundingRect().height() == pytest.approx(base_rect + reserved)


def test_reserved_rows_are_monotonic_and_idempotent(qapp):
    box = _box()
    box.set_reserved_badge_rows(1)
    one_row = box.box_height
    box.set_reserved_badge_rows(2)
    assert box.box_height > one_row
    # Reserving the same number again is a no-op on height.
    height = box.box_height
    box.set_reserved_badge_rows(2)
    assert box.box_height == height


def test_normal_diagram_box_height_is_unchanged(qapp):
    # A box that never gets a reserved-row call keeps exactly its content height.
    box = _box()
    assert box.extra_bottom_height == 0.0
    assert box.box_height == box._content_height


def _service_data() -> ProjectData:
    data = ProjectData()
    data.persons = [
        Person(id="person_1", sex="F", names=[Name(type="birth", given="Anna", surname="S")]),
    ]
    return data


def test_badge_sits_below_text_in_comparison_view(qapp):
    from slaktbusken.persistence.settings_io import PersonBoxConfig

    data = _service_data()
    view = ComparisonFamilyView(0)
    config = PersonBoxConfig(name=True, birth_date=True)
    lookup = active_lookup(data)
    try:
        view.render(data, "person_1", config, lookup=lookup)
    finally:
        set_active_lookup(None)

    box = view.box_for("person_1")
    assert box is not None
    content_bottom = box.box_height  # no badge yet, so this is the text bottom
    opened = {}
    badges = view.add_candidate_badge(
        "person_1", "Ej granskad", "tip", "cand_1", lambda cid: opened.setdefault("id", cid)
    )
    assert badges, "a badge must be added for the visible box"
    badge = badges[0]
    assert isinstance(badge, CandidateAssessmentBadge)
    # The box grew to reserve room for the badge.
    assert box.box_height > content_bottom
    # The badge top is at or below the text area (never over the birth line).
    text_bottom = box.box_height - box.extra_bottom_height
    assert badge.pos().y() >= text_bottom - 0.5
    view.deleteLater()
