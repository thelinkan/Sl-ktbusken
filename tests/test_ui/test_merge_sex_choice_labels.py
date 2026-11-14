"""The sex choice in the merge wizard shows Swedish labels, not raw codes."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.services.merge_planner import UnresolvedChoice
from slaktbusken.ui.merge.merge_pages import SECTION_DEFS, SectionPage, build_choice_specs


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _specs(options):
    return build_choice_specs(
        [UnresolvedChoice("sex", "attributes", "Välj kön.", tuple(options))],
        lambda pid: pid, "p1", "p2", {}, [],
    )


def test_sex_options_keep_codes_and_use_swedish_labels():
    (spec,) = _specs(["F", "M"])
    assert [(o.value, o.text) for o in spec.options] == [("F", "Kvinna"), ("M", "Man")]


def test_sex_other_and_unknown_labels_and_fallback():
    (spec,) = _specs(["U", "X", "Z"])
    assert [o.text for o in spec.options] == ["Okänt", "Annat", "Z"]


def test_section_page_radio_texts_are_swedish(qapp):
    (spec,) = _specs(["F", "M"])
    page = SectionPage(*SECTION_DEFS[0])
    page.show_plan(None, [spec], {})
    assert page.choice_radio("sex", "F").text() == "Kvinna"
    assert page.choice_radio("sex", "M").text() == "Man"
