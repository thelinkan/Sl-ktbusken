"""Slot_Search_Control: person search above one comparison slot.

Extends :class:`PersonSearchWidget`. The completer is fed by
:class:`PersonSearchIndex` (at least two characters, at most 50 results, name,
id and dates) and every result row shows name, life dates, birth place and id,
so same-named persons can be told apart (Requirement 9.7). When nothing
matches, a disabled row states that no person was found and the slot content
stays unchanged (9.8).
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtWidgets import QCompleter, QLineEdit, QWidget

from slaktbusken.services.person_search import (
    MIN_QUERY_LENGTH,
    PersonSearchIndex,
    PersonSearchResult,
)
from slaktbusken.ui.widgets.person_search_widget import PersonSearchWidget

NO_PERSON_FOUND = "Ingen person hittades."


def result_text(result: PersonSearchResult) -> str:
    """Row text: ``Anna Svensson   f. 1829-03-04 Ljusdal   d. 1890   [person_12]``.

    The birth place is part of ``life_dates`` (``f. <date> <place>``); when a
    person has a birth place but no birth date it is added explicitly.
    """
    text = result.display_text
    if result.birth_place and result.birth_place not in result.life_dates:
        text = f"{result.name or result.person_id}   {result.birth_place}   [{result.person_id}]"
    return text


class _ResultModel(QAbstractListModel):
    """List model of search results; a single disabled row when empty."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._texts: list[str] = []
        self._no_match = False

    def set_results(self, texts: list[str], no_match: bool) -> None:
        self.beginResetModel()
        self._texts = texts
        self._no_match = no_match
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return 1 if self._no_match else len(self._texts)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return NO_PERSON_FOUND if self._no_match else self._texts[index.row()]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if self._no_match:
            return Qt.ItemFlag.NoItemFlags
        return super().flags(index)


class SlotSearchControl(PersonSearchWidget):
    """Search field of one Person_Slot.

    Keeps the ``person_selected`` and ``person_cleared`` signals of
    :class:`PersonSearchWidget`.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._index: Optional[PersonSearchIndex] = None
        self._results: list[PersonSearchResult] = []
        self._no_match = False
        self._model = _ResultModel(self)
        self._completer.setModel(self._model)
        self._completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self._line_edit.textEdited.connect(self.update_results)
        self._line_edit.setAccessibleName("Sök person")
        self._clear_btn.setAccessibleName("Rensa sökning")

    # -- accessors -----------------------------------------------------------

    def line_edit(self) -> QLineEdit:
        return self._line_edit

    def focus_input(self) -> None:
        """Move keyboard focus to the search field."""
        self._line_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._line_edit.selectAll()

    def set_search_index(self, index: Optional[PersonSearchIndex]) -> None:
        self._index = index
        self.update_results(self._line_edit.text())

    def results(self) -> list[PersonSearchResult]:
        return list(self._results)

    def row_texts(self) -> list[str]:
        """Texts of the rows currently offered (including the no-match row)."""
        return [
            self._model.data(self._model.index(i, 0))
            for i in range(self._model.rowCount())
        ]

    def no_match_shown(self) -> bool:
        return self._no_match

    # -- behaviour -----------------------------------------------------------

    def update_results(self, text: str) -> None:
        """Refresh the offered rows for ``text`` (nothing under two characters)."""
        query = (text or "").strip()
        if self._index is None or len(query) < MIN_QUERY_LENGTH:
            self._results = []
            self._no_match = False
        else:
            self._results = self._index.search(query)
            self._no_match = not self._results
        self._name_to_id = {result_text(r): r.person_id for r in self._results}
        self._model.set_results([result_text(r) for r in self._results], self._no_match)

    def search(self, text: str) -> list[PersonSearchResult]:
        """Type ``text`` as the user would and return the results."""
        self._line_edit.setText(text)
        self.update_results(text)
        return self.results()

    def choose(self, person_id: str) -> bool:
        """Select a result row by person id as a click in the popup would."""
        for text, pid in self._name_to_id.items():
            if pid == person_id:
                self._on_completer_activated(text)
                return True
        return False

    def show_person(self, person_id: Optional[str], text: str = "") -> None:
        """Show the slot's current person without emitting signals."""
        self._selected_person_id = person_id
        self._line_edit.blockSignals(True)
        self._line_edit.setText(text if person_id else "")
        self._line_edit.blockSignals(False)
        self._results = []
        self._no_match = False
        self._model.set_results([], False)
