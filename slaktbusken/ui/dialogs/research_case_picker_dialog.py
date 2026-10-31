"""Dialog for choosing an existing research case to link an entity to."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import ResearchCase
from slaktbusken.ui.swedish_locale import get_research_status_label


def linkable_cases(
    data: ProjectData, entity_type: str, entity_id: str, text: str = ""
) -> list[ResearchCase]:
    """Return the cases the entity is not yet linked to, filtered by title text."""
    from slaktbusken.services.research_editing import is_linked

    needle = text.strip().lower()
    return [
        case
        for case in data.research_cases
        if not is_linked(case, entity_type, entity_id)
        and (not needle or needle in case.title.lower())
    ]


class ResearchCasePickerDialog(QDialog):
    """Pick one research case among those an entity is not linked to yet."""

    def __init__(
        self,
        project_data: ProjectData,
        entity_type: str,
        entity_id: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Koppla befintligt forskningsärende")
        self.resize(420, 380)
        self._data = project_data
        self._entity = (entity_type, entity_id)

        layout = QVBoxLayout(self)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Sök rubrik...")
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)
        self._list = QListWidget()
        layout.addWidget(self._list, 1)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Koppla")
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        layout.addWidget(self._buttons)

        self._search.textChanged.connect(self._reload)
        self._list.itemSelectionChanged.connect(self._update_ok)
        self._list.itemDoubleClicked.connect(lambda _i: self.accept())
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._reload()

    def _reload(self) -> None:
        self._list.clear()
        for case in linkable_cases(self._data, *self._entity, self._search.text()):
            title = case.title.strip() or "(utan rubrik)"
            item = QListWidgetItem(f"{title}  [{get_research_status_label(case.status)}]")
            item.setData(Qt.ItemDataRole.UserRole, case.id)
            self._list.addItem(item)
        self._update_ok()

    def _update_ok(self) -> None:
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            bool(self._list.selectedItems())
        )

    def selected_case_id(self) -> Optional[str]:
        """Return the chosen case id, or None."""
        items = self._list.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    @staticmethod
    def pick(
        project_data: ProjectData,
        entity_type: str,
        entity_id: str,
        parent: Optional[QWidget] = None,
    ) -> Optional[str]:
        """Show the dialog modally; return the chosen case id or None."""
        dialog = ResearchCasePickerDialog(project_data, entity_type, entity_id, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected_case_id()
        return None
