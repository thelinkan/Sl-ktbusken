"""Offscreen Qt tests of the Event_Editor citation table, prompts and selectors (task 9.4).

**Validates: Requirements 6.1, 7.1, 7.4, 7.5, 8.4, 8.5, 16.1, 16.3**
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QLabel, QMessageBox

from slaktbusken.model.event_citations import CitationContext as C
from slaktbusken.ui.editors.event_assembler import (
    CHOICE_LABELS_SV,
    CitationChoice,
    PromptNeed,
)
from slaktbusken.ui.editors.event_editor import (
    UNPARSED_DATE_TITLE_SV,
    EventEditor,
)

from tests.test_dataskydd.strategies_events import (
    event_with_all_contexts,
    make_project,
    unparsed_event,
)

pytestmark = pytest.mark.mandatory_integrity

_REMOVED = (CitationChoice.MOVE_TO_EVENT, CitationChoice.REMOVE_LINKS, CitationChoice.CANCEL)
_CHANGED = (CitationChoice.KEEP_FOR_NEW_PLACE,) + _REMOVED


def _default_text(box: QMessageBox) -> str:
    return box.defaultButton().text()


def test_place_citations_shown_in_table_with_context(qapp) -> None:
    event = event_with_all_contexts()
    editor = EventEditor(make_project(), event=event)
    table = editor._ui.sources_table
    assert table.rowCount() == 4
    contexts = [editor._row_context(row) for row in range(table.rowCount())]
    assert contexts == [C.EVENT, C.DATE, C.PLACE, C.FROM_PLACE]
    labels = [table.cellWidget(row, 3).currentText() for row in range(4)]
    assert labels == ["Händelse", "Datum", "Plats", "Från plats"]
    assert table.item(2, 2).text() == "plats"  # the place citation's note


def test_prompt_default_is_move(qapp) -> None:
    editor = EventEditor(make_project(), event=event_with_all_contexts())
    for context in (C.DATE, C.PLACE, C.FROM_PLACE):
        box, buttons = editor._build_citation_prompt(PromptNeed(context, "removed", 1, _REMOVED))
        assert _default_text(box) == CHOICE_LABELS_SV[CitationChoice.MOVE_TO_EVENT]
        assert _default_text(box) == "Flytta till händelsen"
        assert {buttons[b] for b in box.buttons()} == set(_REMOVED)
        assert buttons[box.escapeButton()] == CitationChoice.CANCEL
        assert box.escapeButton().text() == "Avbryt"


def test_change_place_prompt_default_is_move(qapp) -> None:
    editor = EventEditor(make_project(), event=event_with_all_contexts())
    for context in (C.PLACE, C.FROM_PLACE):
        box, buttons = editor._build_citation_prompt(PromptNeed(context, "changed", 1, _CHANGED))
        assert _default_text(box) == "Flytta till händelsen"
        assert {buttons[b] for b in box.buttons()} == set(_CHANGED)
        assert buttons[box.escapeButton()] == CitationChoice.CANCEL


def test_unparsed_date_shown_read_only_with_explanation(qapp) -> None:
    event = unparsed_event("ca vid midsommar 1850")
    editor = EventEditor(make_project(), event=event)
    notice = editor._unparsed_notice
    assert notice.isVisibleTo(editor)
    assert UNPARSED_DATE_TITLE_SV == "Tolkades inte vid import"
    assert UNPARSED_DATE_TITLE_SV in notice.text()
    assert "ca vid midsommar 1850" in notice.text()
    # The notice is a label (not editable); the date field is empty (a new date replaces it).
    assert isinstance(notice, QLabel)
    assert editor._ui.date_value_input.text() == ""
    editor._on_save()
    assert editor.saved_event is not None
    assert editor.saved_event.date == event.date


def test_from_place_selector_shown_only_for_flytt(qapp) -> None:
    editor = EventEditor(make_project(), subject_person_id="person_1")
    group = editor._from_place_group
    types = editor._ui.type_combo
    types.setCurrentIndex(types.findData("birth"))
    assert not group.isVisibleTo(editor)
    types.setCurrentIndex(types.findData("flytt"))
    assert group.isVisibleTo(editor)
    types.setCurrentIndex(types.findData("death"))
    assert not group.isVisibleTo(editor)


def test_from_place_selector_sets_from_place(qapp) -> None:
    editor = EventEditor(make_project(), subject_person_id="person_1")
    types = editor._ui.type_combo
    types.setCurrentIndex(types.findData("flytt"))
    combo = editor._from_place_combo
    combo.setCurrentIndex(combo.findData("place_2"))
    editor._ui.place_combo.setCurrentIndex(editor._ui.place_combo.findData("place_1"))
    editor._on_save()
    saved = editor.saved_event
    assert saved is not None
    assert saved.from_place is not None and saved.from_place.place_id == "place_2"
    assert saved.place is not None and saved.place.place_id == "place_1"
