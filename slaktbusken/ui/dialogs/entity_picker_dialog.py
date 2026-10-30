"""Dialog for choosing one project entity (person, place, source and so on).

Used by the research case editor to add linked entities and examined sources.
It offers a searchable list of the existing entities of the chosen type.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.project import ProjectData
from slaktbusken.services.research_entities import entity_choices
from slaktbusken.ui.swedish_locale import get_research_entity_type_label


class EntityPickerDialog(QDialog):
    """Pick one existing entity.

    Args:
        project_data: The project to choose from.
        entity_types: The entity types on offer. With one type the type
            selector is hidden.
        title: Window title.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        entity_types: tuple[str, ...],
        title: str = "Välj objekt",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(420, 420)
        self._data = project_data

        layout = QVBoxLayout(self)

        self._type_combo = QComboBox()
        for entity_type in entity_types:
            self._type_combo.addItem(get_research_entity_type_label(entity_type), entity_type)
        if len(entity_types) > 1:
            row = QHBoxLayout()
            row.addWidget(QLabel("Typ:"))
            row.addWidget(self._type_combo, 1)
            layout.addLayout(row)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Sök...")
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        self._list = QListWidget()
        layout.addWidget(self._list, 1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Välj")
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Avbryt")
        layout.addWidget(self._buttons)

        self._type_combo.currentIndexChanged.connect(self._reload)
        self._search.textChanged.connect(self._reload)
        self._list.itemSelectionChanged.connect(self._update_ok)
        self._list.itemDoubleClicked.connect(lambda _item: self.accept())
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        self._reload()

    def _reload(self) -> None:
        self._list.clear()
        entity_type = self._type_combo.currentData()
        needle = self._search.text().strip().lower()
        for entity_id, label in entity_choices(self._data, entity_type):
            if needle and needle not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entity_id)
            self._list.addItem(item)
        self._update_ok()

    def _update_ok(self) -> None:
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            bool(self._list.selectedItems())
        )

    def selected(self) -> Optional[tuple[str, str]]:
        """Return the chosen ``(entity_type, entity_id)``, or None."""
        items = self._list.selectedItems()
        if not items:
            return None
        return (self._type_combo.currentData(), items[0].data(Qt.ItemDataRole.UserRole))

    @staticmethod
    def pick(
        project_data: ProjectData,
        entity_types: tuple[str, ...],
        title: str = "Välj objekt",
        parent: Optional[QWidget] = None,
    ) -> Optional[tuple[str, str]]:
        """Show the dialog modally; return the chosen pair or None if cancelled."""
        dialog = EntityPickerDialog(project_data, entity_types, title, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected()
        return None
